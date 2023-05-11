"""A module to handle the saving of search results into a new annotation"""
# TODO 2023-05-08: Track number of skipped entries
# TODO 2023-05-08: Write to Arrow IPC or Parquet, alongside tsv.
# TODO 2023-05-08: Implement distributed pipeline/filters/transforms
# TODO 2023-05-08: Support sort queries
# TODO 2023-05-08: get max_slices from opensearch index settings
# TODO 2023-05-08: concatenate chunks in a different ray worker

import math
import os
import pathlib
import subprocess
import traceback
from typing import TypedDict

import mgzip # type: ignore
import numpy as np
from opensearchpy import  OpenSearch
import ray

from search.utils.beanstalkd import Publisher, get_progress_reporter
from search.utils.opensearch import gather_opensearch_args
from search.utils.annotation import get_delimiters

ray.init(ignore_reinit_error='true', address='auto')

STATISTICS_TYPE = TypedDict("STATISTICS_TYPE", {"json": str, "tab": str, "qc": str})

OUTPUT_NAMES_TYPE = TypedDict('OUTPUT_NAMES_TYPE', {"log": str, "annotation": str,
                                                    "sampleList": str, "archived": str,
                                                    "statistics": STATISTICS_TYPE}, total=False)

def make_output_names(output_base_path: str, statistics: bool,
                      compress: bool, archive: bool):
    """Make a dictionary of output file names based on the output base path and the output options"""
    out: OUTPUT_NAMES_TYPE = {}

    basename = os.path.basename(output_base_path)
    out['log'] = f"{basename}.log"
    out['annotation'] = f"{basename}.annotation.tsv"
    if compress:
        out['annotation'] += '.gz'
    out['sampleList'] = f"{basename}.sample_list"

    if statistics:
        out['statistics'] = {
            'json': f"{basename}.statistics.json",
            'tab': f"{basename}.statistics.tab",
            'qc': f"{basename}.statistics.qc.tab"
        }

    if archive:
        out['archived'] = f"{basename}.tar"

    return out


def _clamp(n, min_num, max_num):
    if n < min_num:
        return min_num

    if n > max_num:
        return max_num

    return n

def _clean_query(input_query_body: dict):
    input_query_body["sort"] = ["_doc"]

    if "aggs" in input_query_body:
        del input_query_body["aggs"]

    if "slice" in input_query_body:
        del input_query_body["slice"]

    if "size" in input_query_body:
        del input_query_body["size"]

    return input_query_body


def _get_header(field_names):
    children = [None] * len(field_names)
    parents = [None] * len(field_names)

    for i, field in enumerate(field_names):
        if "." in field:
            path = field.split(".")
            parents[i] = path[0]
            children[i] = path[1:]
        else:
            parents[i] = field
            children[i] = field

    return parents, children


def _populate_data(field_path, data_for_end_of_path):
    if not isinstance(field_path, list):
        return data_for_end_of_path

    for child_field in field_path:
        data_for_end_of_path = data_for_end_of_path[child_field]

    return data_for_end_of_path


def _make_output_string(rows, delims):
    empty_field_char = delims['empty_field']
    for row_idx, row in enumerate(rows): # pylint:disable=too-many-nested-blocks
        # Some fields may just be missing; we won't store even the alt/pos [[]] structure for those
        for i, column in enumerate(row):
            if column is None:
                row[i] = empty_field_char
                continue

            # For now, we don't store multiallelics; top level array is placeholder only
            # With breadth 1
            if not isinstance(column, list):
                row[i] = str(column)
                continue

            for j, position_data in enumerate(column):
                if position_data is None:
                    column[j] = empty_field_char
                    continue

                if isinstance(position_data, list):
                    inner_values = []
                    for sub in position_data:
                        if sub is None:
                            inner_values.append(empty_field_char)
                            continue

                        if isinstance(sub, list):
                            inner_values.append(delims['value'].join(
                                map(lambda x: str(x) if x is not None else empty_field_char, sub)))
                        else:
                            inner_values.append(str(sub))

                    column[j] = delims['position'].join(inner_values)

            row[i] = delims['overlap'].join(column)

        rows[row_idx] = delims['field'].join(row)

    return "\n".join(rows) + "\n"


@ray.remote
def _process_query(query_args: dict, search_client_args: dict, field_names: list,
                         chunk_output_name: str, reporter, delimiters):
    client = OpenSearch(**search_client_args)
    resp = client.search(**query_args)

    if resp["hits"]["total"]["value"] == 0:
        return 0

    rows = []

    parent_fields, child_fields = _get_header(field_names)

    discordant_idx = field_names.index("discordant")
    assert discordant_idx > -1

    # Each sliced scroll chunk should get all records for that chunk
    assert len(resp["hits"]["hits"]) == resp["hits"]["total"]["value"]

    for doc in resp["hits"]["hits"]:
        row = np.empty(len(field_names), dtype=object)
        for y in range(len(field_names)):
            row[y] = _populate_data(
                child_fields[y], doc["_source"][parent_fields[y]])

        if row[discordant_idx][0][0] is False:
            row[discordant_idx][0][0] = 0
        elif row[discordant_idx][0][0] is True:
            row[discordant_idx][0][0] = 1

        rows.append(row)

    try:
        with mgzip.open(chunk_output_name, "wt", thread=8, blocksize=2*10**8) as fw:
            fw.write(_make_output_string(rows, delimiters))
        reporter.increment.remote(resp["hits"]["total"]["value"])
    except Exception:
        traceback.print_exc()
        return -1

    return resp["hits"]["total"]["value"]

def _get_num_slices(client, input_body, max_query_size, max_slices, query):
    """Count number of hits for the index"""
    query_no_sort = query.copy()
    if "sort" in query_no_sort:
        del query_no_sort["sort"]
    if "track_total_hits" in query_no_sort:
        del query_no_sort["track_total_hits"]

    response = client.count( body=query_no_sort, index=input_body["indexName"])

    n_docs = response["count"]
    assert n_docs > 0

    return _clamp(math.ceil(n_docs / max_query_size), 1, max_slices)

async def go( # pylint:disable=invalid-name
    input_body: dict,
    search_conf: dict,
    publisher: Publisher,
    max_query_size: int = 10_000,
    max_slices=1024,
    keep_alive="1d",
):
    """Main function for running the query and writing the output"""
    if not input_body['compress']:
        print("\nWarning: still compressing outputs\n")

    output_names = make_output_names(
        input_body['outputBasePath'], input_body['run_statistics'], True, input_body['archive'])

    output_dir = os.path.dirname(input_body['outputBasePath'])
    pathlib.Path(output_dir).mkdir(parents=True, exist_ok=True)

    written_chunks = [os.path.join(output_dir, f"{input_body['indexName']}_header")]

    header = "\t".join(input_body['fieldNames']) + "\n"
    with mgzip.open(written_chunks[-1], "wt", thread=8, blocksize=2*10**8) as fw:
        fw.write(header)

    search_client_args = gather_opensearch_args(search_conf)
    client = OpenSearch(**search_client_args)

    query = _clean_query(input_body["queryBody"])
    num_slices = _get_num_slices(client, input_body, max_query_size, max_slices, query)
    pit_id = client.create_point_in_time(index=input_body["indexName"], params={"keep_alive": keep_alive})['pit_id'] # type: ignore
    try:
        reporter = get_progress_reporter(publisher)
        query['pit'] = {'id': pit_id}
        query["size"] = max_query_size

        reqs = []
        for slice_id in range(num_slices):
            written_chunks.append(os.path.join(output_dir, f"{input_body['indexName']}_{slice_id}"))
            body = query.copy()
            if num_slices > 1:
                # Slice queries require max > 1
                body['slice'] = {"id": slice_id, "max": num_slices}
            res = _process_query.remote({'body': body}, search_client_args,
                                        input_body["fieldNames"], written_chunks[-1],
                                        reporter, get_delimiters())
            reqs.append(res)
        results_processed = ray.get(reqs)

        if -1 in results_processed:
            raise IOError("Failed to process chunk")

        all_chunks = " ".join(written_chunks)

        annotation_path = os.path.join(output_dir, output_names['annotation'])
        ret = subprocess.call(f'cat {all_chunks} > {annotation_path}; rm {all_chunks}', shell=True)
        if ret != 0:
            raise IOError(f"Failed to write {annotation_path}")

        if input_body['archive']:
            tarball_path = os.path.join(output_dir, output_names['archived'])
            tarball_name = output_names['archived']

            ret = subprocess.call(f'cd {output_dir}; tar --exclude ".*" --exclude={tarball_name} -cf {tarball_name} * --remove-files', shell=True)
            if ret != 0:
                raise IOError(f"Failed to write {tarball_path}")
    except Exception as err:
        client.delete_point_in_time(body={"pit_id": pit_id}) # type: ignore
        raise IOError(err) from err

    client.delete_point_in_time(body={"pit_id": pit_id}) # type: ignore

    return output_names
