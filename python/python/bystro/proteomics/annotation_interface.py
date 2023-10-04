"""Query an annotation file and return a list of sample_ids and genes meeting the query criteria."""
import io
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Tuple

import pandas as pd
import ray
from bystro.proteomics.tests.example_query import DEFAULT_FIELDS, SPEC_FIELDS  # TK
from bystro.search.utils.annotation import AnnotationOutputs, get_delimiters
from bystro.search.utils.messages import SaveJobData
from bystro.search.utils.opensearch import gather_opensearch_args
from bystro.utils.config import get_opensearch_config
from opensearchpy import OpenSearch
from ruamel.yaml import YAML

ray.init(ignore_reinit_error=True, address="auto")
OPENSEARCH_CONFIG = get_opensearch_config()
RAY_ERROR = -1  # the error code we use if a ray remote job fails to return

ONE_DAY = "1d"  # default keep_alive time for opensearch point in time index


def _preprocess_query(input_query_body: dict[str, Any]) -> dict[str, Any]:
    clean_query_body = input_query_body.copy()
    clean_query_body["sort"] = ["_doc"]

    deletable_fields = ["aggs", "slice", "size"]
    for field in deletable_fields:
        clean_query_body.pop(field, None)

    return clean_query_body


def _get_header(field_names: list[str]) -> Tuple[list[str], list[str | list[str]]]:
    parents: list[str] = []
    children: list[str | list[str]] = []
    for field in field_names:
        if "." in field:
            path = field.split(".")
            parents.append(path[0])
            children.append(path[1:])
        else:
            parents.append(field)
            children.append(field)

    assert len(parents) == len(children)
    return parents, children


def _populate_data(
    field_path: list[str] | str, data_for_end_of_path: list[str] | dict[str, Any] | None
) -> dict[str, Any] | list[str] | None:
    if not isinstance(field_path, list) or data_for_end_of_path is None:
        return data_for_end_of_path
    assert isinstance(data_for_end_of_path, dict)  # noqa: S101
    for child_field in field_path:
        data_for_end_of_path = data_for_end_of_path.get(child_field)
        if data_for_end_of_path is None:
            return data_for_end_of_path

    return data_for_end_of_path


Sub = list[str | None] | str | None
PositionData = list[Sub]
Column = None | list[PositionData]
Row = list[Column]


def _make_output_string(rows: list[Row], delims: dict[str, str]) -> bytes:
    output_rows = [_do_row(row, delims) for row in rows]
    return bytes("\n".join(output_rows) + "\n", encoding="utf-8")


def _do_row(row: Row, delims: dict[str, str]) -> str:
    output_row = [_do_column(col, delims) for col in row]
    return delims["field"].join(output_row)


def _do_column(column: Column, delims: dict[str, str]) -> str:
    if column is None:
        return delims["empty_field"]
    if not isinstance(column, list):
        return str(column)
    output_column = [
        _do_position_data(pos_data, delims) for pos_data in column if isinstance(pos_data, list)
    ]
    return delims["overlap"].join(output_column)


def _do_position_data(position_data: list[Sub], delims: dict[str, str]) -> str:
    # if position_data is None:
    inner_values = [_do_sub(sub, delims) for sub in position_data]
    return delims["position"].join(inner_values)


def _do_sub(sub: Sub, delims: dict[str, str]) -> str:
    if sub is None:
        return delims["empty_field"]
    if isinstance(sub, list):
        sub_strings = [_to_string_or_empty_field_char(s, delims) for s in sub]
        return delims["value"].join(sub_strings)
    elif isinstance(sub, str):
        return sub
    else:
        raise TypeError(sub)
        return str(sub)


def _to_string_or_empty_field_char(x: str | None, delims: dict[str, str]) -> str:
    return str(x) if x is not None else delims["empty_field"]


from typing import cast


def _process_rows(resp: dict, field_names: list[str]) -> list[Row]:
    parent_fields, child_fields = _get_header(field_names)
    try:
        discordant_idx = field_names.index("discordant")
    except ValueError as val_err:
        err_msg = f"response: {resp} with field_names: {field_names} lacked field: 'discordant'"
        raise ValueError(err_msg) from val_err
    rows: list[Row] = []
    docs = resp["hits"]["hits"]
    for doc in docs:
        row = []
        for parent_field, child_field in zip(parent_fields, child_fields):
            row.append(_populate_data(child_field, doc["_source"].get(parent_field)))
        row[discordant_idx][0][0] = cast(str, _fix_discordancy(row[discordant_idx][0][0]))  # type: ignore
        rows.append(row)  # type: ignore
    return rows


def _fix_discordancy(x: bool | str) -> str:
    return {False: "0", True: "1", "0": "0", "1": "1"}[x]


SampleID = str
GeneName = str
Dosage = int


def flatten(xs):
    if not isinstance(xs, list):
        return [xs]
    output = []
    for x in xs:
        output.extend(flatten(x))
    return output


def _process_hit(hit: dict[str, Any]) -> list[tuple[SampleID, GeneName, Dosage]]:
    source = hit["_source"]
    gene_names = flatten(source["refSeq"]["name2"])
    heterozygotes = flatten(source.get("heterozygotes", []))
    homozygotes = flatten(source.get("homozygotes", []))
    rows = []
    for gene_name in gene_names:
        for heterozygote in heterozygotes:
            rows.append(({"sample_id": heterozygote, "gene_name": gene_name, "dosage": 1}))
        for homozygote in homozygotes:
            rows.append(({"sample_id": homozygote, "gene_name": gene_name, "dosage": 2}))
    return pd.DataFrame(rows)


# @ray.remote
# def _process_query(
#     query_args: dict,
#     search_client_args: dict,
#     field_names: list,
#     chunk_output_name: str,
#     delimiters,
# ):
#     """Process OpenSearch query and save results.

#     - Run OpenSearch query against index specified in
#     - search_client_args Write output to disk under chunk_output_name.
#     - Warning: this method does not implement exception-based error
#       handling but returns an error code of RAY_ERROR if any exception is encountered.
#     - returns... what? TK
#     """

#     if resp["hits"]["total"]["value"] == 0:

#     # Each sliced scroll chunk should get all records for that chunk

#         with gzip.open(chunk_output_name, "wb") as fw:


@ray.remote
def _process_query_pure_ref(
    query_args: dict,
    search_client_args: dict,
    field_names: list,
    delimiters: dict[str, str],
) -> int | bytes:
    """Process OpenSearch query and return results."""
    client = OpenSearch(**search_client_args)
    resp = client.search(**query_args)
    return _process_response(resp, field_names, delimiters)


@ray.remote
def _process_query_pure(
    query_args: dict,
    search_client_args: dict,
    field_names: list,
    delimiters: dict[str, str],
) -> pd.DataFrame:
    """Process OpenSearch query and return results."""
    client = OpenSearch(**search_client_args)
    resp = client.search(**query_args)
    return _process_response2(resp)


def _process_response2(resp) -> pd.DataFrame:
    df = pd.concat([_process_hit(hit) for hit in resp["hits"]["hits"]])
    # we may have multiple variants per gene in the results, so we
    # need to drop duplicates here.
    return df.drop_duplicates()


def _process_response(resp, field_names, delimiters) -> int | bytes:
    if resp["hits"]["total"]["value"] == 0:
        return 0

    # Each sliced scroll chunk should get all records for that chunk
    if len(resp["hits"]["hits"]) != resp["hits"]["total"]["value"]:
        err_msg = (
            f"response hits: {len(resp['hits']['hits'])} didn't equal "
            f"total value: {resp['hits']['total']['value']}. "
            "This is a bug."
        )
        raise ValueError(err_msg)
    rows = _process_rows(resp, field_names)
    output_string = _make_output_string(rows, delimiters)
    return output_string


def _get_num_slices(
    client: OpenSearch,
    index_name: str,
    max_query_size: int,
    max_slices: int,
    query: dict[str, Any],
) -> int:
    """Count number of hits for the index."""
    query_no_sort = query.copy()
    query_no_sort.pop("sort", None)  # delete these keys if present
    query_no_sort.pop("track_total_hits", None)

    response = client.count(body=query_no_sort, index=index_name)

    n_docs = response["count"]
    if n_docs < 1:
        err_msg = (
            f"Expected at least one document in response['count'], got response: {response} instead."
        )
        raise RuntimeError(err_msg)

    num_slices_necessary = math.ceil(n_docs / max_query_size)
    num_slices_planned = min(num_slices_necessary, max_slices)
    return max(num_slices_planned, 1)


# def run_query_and_write_output_pure_ref(
#     job_data: SaveJobData,
#     search_conf: dict,
#     max_query_size: int = 10_000,
#     max_slices=1024,
#     keep_alive=ONE_DAY,
# ) -> pd.DataFrame:
#     assert isinstance(max_query_size, int), type(max_query_size)
#     header = bytes("\t".join(job_data.fieldNames) + "\n", encoding="utf-8")

#     search_client_args = gather_opensearch_args(search_conf)
#     client = OpenSearch(**search_client_args)
#     delimiters = get_delimiters()

#     query = _preprocess_query(job_data.queryBody)
#     num_slices = _get_num_slices(client, job_data.indexName, max_query_size, max_slices, query)
#     point_in_time = client.create_point_in_time(  # type: ignore[attr-defined]
#         index=job_data.indexName, params={"keep_alive": keep_alive}
#     )
#     pit_id = point_in_time["pit_id"]
#     query["pit"] = {"id": pit_id}
#     query["size"] = max_query_size
#     remote_queries = []
#     for slice_id in range(num_slices):
#         slice_query = query.copy()
#         if num_slices > 1:
#             # Slice queries require max > 1
#             slice_query["slice"] = {"id": slice_id, "max": num_slices}
#         remote_query = _process_query_pure.remote(  # type: ignore[call-arg]
#             query_args={"body": slice_query},
#             search_client_args=search_client_args,
#             field_names=job_data.fieldNames,
#             delimiters=delimiters,
#         )
#         remote_queries.append(remote_query)
#     results_processed: list[bytes] = ray.get(remote_queries)
#     client.delete_point_in_time(body={"pit_id": pit_id})  # type: ignore
#     if RAY_ERROR in results_processed:
#         failing_idx = results_processed.index(RAY_ERROR)
#         err_msg = (
#             f"Encountered Ray error while processing query {failing_idx} of {len(results_processed)}"
#         )
#         raise OSError(err_msg)

#     payload = [header, *results_processed]
#     return _process_payload(payload, delimiters)


def run_query_and_write_output_pure(
    job_data: SaveJobData,
    search_conf: dict,
    max_query_size: int = 10_000,
    max_slices=1024,
    keep_alive=ONE_DAY,
) -> pd.DataFrame:
    assert isinstance(max_query_size, int), type(max_query_size)
    header = bytes("\t".join(job_data.fieldNames) + "\n", encoding="utf-8")

    search_client_args = gather_opensearch_args(search_conf)
    client = OpenSearch(**search_client_args)
    delimiters = get_delimiters()

    query = _preprocess_query(job_data.queryBody)
    num_slices = _get_num_slices(client, job_data.indexName, max_query_size, max_slices, query)
    point_in_time = client.create_point_in_time(  # type: ignore[attr-defined]
        index=job_data.indexName, params={"keep_alive": keep_alive}
    )
    pit_id = point_in_time["pit_id"]
    query["pit"] = {"id": pit_id}
    query["size"] = max_query_size
    remote_queries = []
    for slice_id in range(num_slices):
        slice_query = query.copy()
        if num_slices > 1:
            # Slice queries require max > 1
            slice_query["slice"] = {"id": slice_id, "max": num_slices}
        remote_query = _process_query_pure.remote(  # type: ignore[call-arg]
            query_args={"body": slice_query},
            search_client_args=search_client_args,
            field_names=job_data.fieldNames,
            delimiters=delimiters,
        )
        remote_queries.append(remote_query)
    results_processed = ray.get(remote_queries)
    client.delete_point_in_time(body={"pit_id": pit_id})  # type: ignore
    # if RAY_ERROR in results_processed:
    #     failing_idx = results_processed.index(RAY_ERROR)
    #     err_msg = (
    #         f"Encountered Ray error while processing query {failing_idx} of {len(results_processed)}"
    #     )
    #     raise OSError(err_msg)

    return pd.concat(results_processed)


def _process_payload(payload: list[bytes], delimiters: dict[str, str]) -> pd.DataFrame:
    payload_str = "".join([byte_str.decode("utf-8") for byte_str in payload])
    samples_and_genes_df = pd.read_csv(io.StringIO(payload_str), sep="\t")
    assert all(
        samples_and_genes_df.columns == ["discordant", "homozygotes", "heterozygotes", "refSeq.name2"]
    )
    samples_and_genes_df = samples_and_genes_df.drop("discordant", axis=1)
    samples_and_genes_df = samples_and_genes_df.rename({"refSeq.name2": "gene_name"}, axis=1)
    output = []
    for _i, row in samples_and_genes_df.iterrows():
        gene_names = deduplicate(split_gene_names(row.gene_name, delimiters))
        homozygotes = row.homozygotes.split("|") if row.homozygotes != "!" else []
        heterozygotes = row.heterozygotes.split("|") if row.heterozygotes != "!" else []
        for gene_name in gene_names:
            for heterozygote in heterozygotes:
                output.append((heterozygote, gene_name, 1))
            for homozygote in homozygotes:
                output.append((homozygote, gene_name, 2))
    return pd.DataFrame(output, columns=["sample_id", "gene_name", "dosage"])


def split_gene_names(gene_names: str, delimiters: dict[str, str]) -> list[str]:
    names = []
    for group in gene_names.split(delimiters["position"]):
        for name in group.split(delimiters["overlap"]):
            names.append(name)
    return names


def deduplicate(xs: list) -> list:
    return list(set(xs))


def _write_tarball(written_chunks: list[str], output_dir: str, outputs: AnnotationOutputs) -> None:
    all_chunks = " ".join(written_chunks)
    annotation_path = os.path.join(output_dir, outputs.annotation)
    cat_command = f"cat {all_chunks} > {annotation_path}; rm {all_chunks}"
    ret_code = subprocess.call(cat_command, shell=True)
    if ret_code != 0:
        msg = f"Failed to write {annotation_path}"
        raise OSError(msg)

    tarball_name = os.path.basename(outputs.archived)
    tar_command = (
        f"cd {output_dir} && "
        f'{GNU_TAR_EXECUTABLE_NAME} --exclude ".*" --exclude={tarball_name} '
        f"-cf {tarball_name} * --remove-files"
    )
    ret_code = subprocess.call(tar_command, shell=True)
    if ret_code != 0:
        msg = f"Command: '{tar_command}', failed with retcode {ret_code}, could not generate: {outputs.archived}"
        raise OSError(msg)


def _package_opensearch_query_from_query_string(query_string: str) -> dict[str, Any]:
    return {
        "query": {
            "bool": {
                "filter": {
                    "query_string": {
                        "default_operator": "AND",
                        "query": query_string,
                        # "fields": SPEC_FIELDS,
                        "fields": DEFAULT_FIELDS,
                        "lenient": True,
                        "phrase_slop": 5,
                        "tie_breaker": 0.3,
                    }
                }
            }
        }
    }


def get_samples_and_genes(user_query_string: str, index_name: str) -> Tuple[set[str], set[str]]:
    """Given a query and index, return a list of samples and genes for subsetting a proteomics matrix."""
    query = _package_opensearch_query_from_query_string(user_query_string)
    field_names = ["discordant", "homozygotes", "heterozygotes", "refSeq.name2"]
    job_data = SaveJobData(
        submissionID="1337",
        assembly="hg38",
        queryBody=query,
        indexName=index_name,
        outputBasePath=".",
        fieldNames=field_names,
    )
    samples_and_genes_df = run_query_and_write_output_pure(job_data, OPENSEARCH_CONFIG)
    return samples_and_genes_df
