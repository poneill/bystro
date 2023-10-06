"""Default fields to pass to OpenSearch query."""

DEFAULT_FIELDS = [
    "chrom",
    "pos",
    "trTv",
    "type",
    "heterozygotes",
    "heterozygosity",
    "homozygotes",
    "homozygosity",
    "missingGenos",
    "missingness",
    "ac",
    "an",
    "sampleMaf",
    "alt",
    "ref",
    "refSeq.siteType",
    "refSeq.exonicAlleleFunction",
    "refSeq.refCodon",
    "refSeq.altCodon",
    "refSeq.refAminoAcid",
    "refSeq.altAminoAcid",
    "refSeq.codonPosition",
    "refSeq.codonNumber",
    "refSeq.strand",
    "refSeq.kgID",
    "refSeq.mRNA",
    "refSeq.spID",
    "refSeq.spDisplayID",
    "refSeq.geneSymbol",
    "refSeq.tRnaName",
    "refSeq.ensemblID",
    "refSeq.name2",
    "refSeq.protAcc",
    "refSeq.description",
    "refSeq.rfamAcc",
    "refSeq.name",
    "refSeq.gene.name2",
    "refSeq.gene.pLi",
    "refSeq.gene.pRec",
    "refSeq.gene.pNull",
    "refSeq.gene.lofTool",
    "refSeq.gene.lofFdr",
    "refSeq.gene.pHi",
    "refSeq.gene.nonTCGA.pRec",
    "refSeq.gene.nonTCGA.pNull",
    "refSeq.gene.nonTCGA.pLi",
    "refSeq.gene.nonPsych.pRec",
    "refSeq.gene.nonPsych.pNull",
    "refSeq.gene.nonPsych.pLi",
    "refSeq.gene.gdi",
    "refSeq.gene.cnvScore",
    "refSeq.gene.cnvFlag",
    "refSeq.gene.uniprot.func",
    "refSeq.gene.pmid",
    "refSeq.gene.rvis",
    "refSeq.clinvar.alleleID",
    "refSeq.clinvar.phenotypeList",
    "refSeq.clinvar.origin",
    "refSeq.clinvar.numberSubmitters",
    "nearest.refSeq.name",
    "nearest.refSeq.name2",
    "nearest.refSeq.dist",
    "nearestTss.refSeq.name",
    "nearestTss.refSeq.name2",
    "nearestTss.refSeq.dist",
    "phastCons",
    "phyloP",
    "cadd",
    "dbSNP.name",
    "dbSNP.alleleNs",
    "dbSNP.alleleFreqs",
    "clinvar.alleleID",
    "clinvar.phenotypeList",
    "clinvar.phenotypeList.exact",
    "clinvar.clinicalSignificance",
    "clinvar.clinicalSignificance.exact",
    "clinvar.origin",
    "clinvar.numberSubmitters",
    "clinvar.reviewStatus",
    "clinvar.match.alt",
    "clinvar.match.variation_id",
    "clinvar.match.allele_id",
    "clinvar.match.strand",
    "clinvar.match.rcv",
    "clinvar.match.scv",
    "clinvar.match.hgvs_c",
    "clinvar.match.hgvs_p",
    "clinvar.match.traits",
    "clinvar.match.molecular_consequence",
    "clinvar.match.clinical_significance",
    "clinvar.match.pathogenic",
    "clinvar.match.likely_pathogenic",
    "clinvar.match.uncertain_significance",
    "clinvar.match.likely_benign",
    "clinvar.match.benign",
    "clinvar.match.review_status",
    "clinvar.match.last_evaluated",
    "clinvar.match.submitters",
    "clinvar.match.pmids",
    "clinvar.match.origin",
    "clinvar.match.xrefs",
    "gnomad.genomes.alt",
    "gnomad.genomes.id",
    "gnomad.genomes.trTv",
    "gnomad.genomes.af",
    "gnomad.genomes.ac",
    "gnomad.genomes.ac_afr",
    "gnomad.genomes.ac_amr",
    "gnomad.genomes.ac_asj",
    "gnomad.genomes.ac_eas",
    "gnomad.genomes.ac_fin",
    "gnomad.genomes.ac_nfe",
    "gnomad.genomes.ac_oth",
    "gnomad.genomes.ac_sas",
    "gnomad.genomes.ac_male",
    "gnomad.genomes.ac_female",
    "gnomad.genomes.an",
    "gnomad.genomes.an_afr",
    "gnomad.genomes.an_amr",
    "gnomad.genomes.an_asj",
    "gnomad.genomes.an_eas",
    "gnomad.genomes.an_fin",
    "gnomad.genomes.an_nfe",
    "gnomad.genomes.an_oth",
    "gnomad.genomes.an_male",
    "gnomad.genomes.an_female",
    "gnomad.genomes.af_afr",
    "gnomad.genomes.af_amr",
    "gnomad.genomes.af_asj",
    "gnomad.genomes.af_eas",
    "gnomad.genomes.af_fin",
    "gnomad.genomes.af_nfe",
    "gnomad.genomes.af_oth",
    "gnomad.genomes.af_male",
    "gnomad.genomes.af_female",
    "gnomad.exomes.alt",
    "gnomad.exomes.id",
    "gnomad.exomes.trTv",
    "gnomad.exomes.ac",
    "gnomad.exomes.af",
    "gnomad.exomes.an",
    "gnomad.exomes.ac_afr",
    "gnomad.exomes.ac_amr",
    "gnomad.exomes.ac_asj",
    "gnomad.exomes.ac_eas",
    "gnomad.exomes.ac_fin",
    "gnomad.exomes.ac_nfe",
    "gnomad.exomes.ac_oth",
    "gnomad.exomes.ac_male",
    "gnomad.exomes.ac_female",
    "gnomad.exomes.an_afr",
    "gnomad.exomes.an_amr",
    "gnomad.exomes.an_asj",
    "gnomad.exomes.an_eas",
    "gnomad.exomes.an_fin",
    "gnomad.exomes.an_nfe",
    "gnomad.exomes.an_oth",
    "gnomad.exomes.an_male",
    "gnomad.exomes.an_female",
    "gnomad.exomes.af_afr",
    "gnomad.exomes.af_amr",
    "gnomad.exomes.af_asj",
    "gnomad.exomes.af_eas",
    "gnomad.exomes.af_fin",
    "gnomad.exomes.af_nfe",
    "gnomad.exomes.af_oth",
    "gnomad.exomes.af_male",
    "gnomad.exomes.af_female",
    "cosmic.coding.id",
    "cosmic.coding.cnt",
    "cosmic.coding.cds",
    "cosmic.coding.gene",
    "cosmic.coding.strand",
    "cosmic.nonCoding.id",
    "cosmic.nonCoding.cnt",
    "cosmic.nonCoding.cds",
    "cosmic.nonCoding.gene",
    "cosmic.nonCoding.strand",
]
