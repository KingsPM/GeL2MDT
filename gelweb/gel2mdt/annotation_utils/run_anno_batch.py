"""Copyright (c) 2018 Great Ormond Street Hospital for Children NHS Foundation
Trust & Birmingham Women's and Children's NHS Foundation Trust

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import os
import tempfile
import subprocess
import csv
from ..config import load_config
from . import parse_vep
import paramiko
from pycellbase.cbclient import CellBaseClient


class CaseVariant:
    def __init__(self, chromosome, position, case_id, variant_count, ref, alt, genome_build):
        self.chromosome = chromosome
        self.position = position
        self.case_id = case_id
        self.variant_count = variant_count
        self.ref = ref
        self.alt = alt
        self.genome_build = genome_build


class CaseTranscript:
    def __init__(self, case_id, variant_count, gene_ensembl_id, gene_hgnc_name, gene_hgnc_id, transcript_name, transcript_canonical,
                 transcript_strand, proband_transcript_variant_effect, transcript_variant_af_max, variant_polyphen,
                 variant_sift, transcript_variant_hgvs_c, transcript_variant_hgvs_p, transcript_variant_hgvs_g):
        self.case_id = case_id
        self.variant_count = variant_count
        self.gene_ensembl_id = gene_ensembl_id
        self.gene_hgnc_name = gene_hgnc_name
        self.gene_hgnc_id = gene_hgnc_id
        self.transcript_name = transcript_name
        self.transcript_canonical = transcript_canonical
        self.transcript_strand = transcript_strand
        self.proband_transcript_variant_effect = proband_transcript_variant_effect
        self.transcript_variant_af_max = transcript_variant_af_max
        self.variant_polyphen = variant_polyphen
        self.variant_sift = variant_sift
        self.transcript_variant_hgvs_c = transcript_variant_hgvs_c
        self.transcript_variant_hgvs_p = transcript_variant_hgvs_p
        self.transcript_variant_hgvs_g = transcript_variant_hgvs_g
        self.gene_model = None
        self.transcript_entry = None
        self.proband_variant_entry = None
        self.selected = False


def get_variant_list(variants):
    '''
    Function which creates a list from variant objects specified from MCA.

    :param variants: List of CaseVariant objects
    :return: A dict of lists. Keys are GRCh37 and GRCh38 which releate to the different
    genome builds
    '''
    grch37_variant_list = []
    grch38_variant_list = []
    for variant in variants:
        if 'GRCh37' in variant.genome_build:
            grch37_variant_list.append(f"{variant.chromosome}:{variant.position}:{variant.ref}:{variant.alt}")
        elif 'GRCh38' in variant.genome_build:
            grch38_variant_list.append(f"{variant.chromosome}:{variant.position}:{variant.ref}:{variant.alt}")
    variant_dict = {'GRCh37': grch37_variant_list, 'GRCh38': grch38_variant_list}
    return variant_dict


def run_cellbase(variant_dict):
    cbc = CellBaseClient()
    vc = cbc.get_variant_client()
    annotated_dict = {}
    for key in variant_dict:
        variants_info = vc.get_annotation(variant_dict[key], assembly=key)
        annotated_dict[key] = variants_info
    return annotated_dict


def parse_cellbase(variants_list, annotated_variants_dict):
    transcript_list = []
    count = 0
    for variant in variants_list:
        for annotated_variant in annotated_variants_dict[variant.genome_build]:
            if annotated_variant['id'] == f"{variant.chromosome}:{variant.position}:{variant.ref}:{variant.alt}":
                for result in annotated_variant['result']: # Not sure why there would be 2 results
                    for consequence in result['consequenceTypes']: # Again no idea why a list
                        gene_id = consequence['ensemblGeneId']
                        gene_name = consequence['geneName']
                        canonical = False
                        transcript_name = consequence['ensemblTranscriptId']
                        transcript_strand = consequence['strand']
                        for consequence_types in consequence['sequenceOntologyTerms']:
                            proband_transcript_variant_effect = consequence_types['name']
                            continue
                        for scores in consequence['proteinVariantAnnotation']['substitutionScores']:
                            if scores['source'] == 'sift':
                                variant_sift = f"{scores['description']} {scores['score']}"



                    # gene_id = result[]
                    # gene_name = variant['transcript_data'][transcript]['SYMBOL']
                    # hgnc_id = variant['transcript_data'][transcript]['HGNC_ID']
                    # if hgnc_id.startswith('HGNC:'):
                    #     hgnc_id = str(hgnc_id.split(':')[1])
                    # if variant['transcript_data'][transcript]['CANONICAL'] == '':
                    #     canonical = False
                    # else:
                    #     canonical = variant['transcript_data'][transcript]['CANONICAL']
                    # transcript_name = variant['transcript_data'][transcript]['Feature']
                    # transcript_strand = variant['transcript_data'][transcript]['STRAND']
                    # proband_transcript_variant_effect = variant['transcript_data'][transcript]['Consequence']
                    # transcript_variant_af_max = variant['transcript_data'][transcript]['MAX_AF']
                    # variant_polyphen = variant['transcript_data'][transcript]['PolyPhen']
                    # variant_sift = variant['transcript_data'][transcript]['SIFT']
                    # transcript_variant_hgvs_c = variant['transcript_data'][transcript]['HGVSc']
                    # transcript_variant_hgvs_p = variant['transcript_data'][transcript]['HGVSp']
                    # transcript_variant_hgvs_g = variant['transcript_data'][transcript]['HGVSg']

                continue

        # case_transcript = CaseTranscript(variant.case_id,
        #                                  count,
        #                                  gene_id, gene_name, hgnc_id, transcript_name,
        #                                  canonical,
        #                                  transcript_strand, proband_transcript_variant_effect,
        #                                  transcript_variant_af_max, variant_polyphen, variant_sift,
        #                                  transcript_variant_hgvs_c, transcript_variant_hgvs_p,
        #                                  transcript_variant_hgvs_g)
        # transcripts_list.append(case_transcript)
        # count += 1
    return None


def generate_vcf(variants):
    '''
    Function which creates a VCF formatted file from variant objects specified from MCA.
    :param variants: List of CaseVariant objects
    :return: A dict of 2 vcfs. Keys are hg19_vcf and hg38_vcf which releate to the different
    genome builds
    '''
    tmphg19 = tempfile.NamedTemporaryFile(mode='w+t', delete=False)
    tmphg38 = tempfile.NamedTemporaryFile(mode='w+t', delete=False)
    for variant in variants:
        if 'GRCh37' in variant.genome_build:
            row_to_write = str(variant.chromosome) + '\t' + str(variant.position) + '\t' + str(variant.case_id) + ":" + \
                           str(variant.variant_count) + '\t' + variant.ref + '\t' + variant.alt + '\n'
            tmphg19.writelines(row_to_write)
        elif 'GRCh38' in variant.genome_build:
            row_to_write = str(variant.chromosome) + '\t' + str(variant.position) + '\t' + str(variant.case_id) + ":" + \
                           str(variant.variant_count) + '\t' + variant.ref + '\t' + variant.alt + '\n'
            tmphg38.writelines(row_to_write)
    tmphg19.close()
    tmphg38.close()
    print(tmphg19.name, tmphg38.name)
    variant_dict = {'hg19_vcf': tmphg19.name, 'hg38_vcf': tmphg38.name}
    return variant_dict

def parse_vep_annotations(infile=None):
    '''
    Takes the results from VEP and converts them into CaseTranscript objects which will then be passed to CAM for
    inserting into the database

    :param infile: Dict from run_vep function which contains VEP vcf file locations
    :return: List of CaseTranscript objects
    '''
    transcripts_list = []
    if infile is not None:
        hg19_variants = []
        hg38_variants = []
        if 'hg19_vep' in infile:
            if os.stat(infile['hg19_vep']).st_size != 0:
                hg19_variants = parse_vep.ParseVep().read_file(infile['hg19_vep'])
        if 'hg38_vep' in infile:
            if os.stat(infile['hg38_vep']).st_size != 0:
                hg38_variants = parse_vep.ParseVep().read_file(infile['hg38_vep'])
        # concatenate the two lists of variant dictionaries
        variants = hg19_variants + hg38_variants

        for variant in variants:
            case_id = variant['id'].split(":")[0]
            variant_count = variant['id'].split(":")[1]
            for transcript in variant['transcript_data']:
                gene_id = variant['transcript_data'][transcript]['Gene']
                gene_name = variant['transcript_data'][transcript]['SYMBOL']
                hgnc_id = variant['transcript_data'][transcript]['HGNC_ID']
                if hgnc_id.startswith('HGNC:'):
                    hgnc_id = str(hgnc_id.split(':')[1])
                if variant['transcript_data'][transcript]['CANONICAL'] == '':
                    canonical = False
                else:
                    canonical = variant['transcript_data'][transcript]['CANONICAL']
                transcript_name = variant['transcript_data'][transcript]['Feature']
                transcript_strand = variant['transcript_data'][transcript]['STRAND']
                proband_transcript_variant_effect = variant['transcript_data'][transcript]['Consequence']
                transcript_variant_af_max = variant['transcript_data'][transcript]['MAX_AF']
                variant_polyphen = variant['transcript_data'][transcript]['PolyPhen']
                variant_sift = variant['transcript_data'][transcript]['SIFT']
                transcript_variant_hgvs_c = variant['transcript_data'][transcript]['HGVSc']
                transcript_variant_hgvs_p = variant['transcript_data'][transcript]['HGVSp']
                transcript_variant_hgvs_g = variant['transcript_data'][transcript]['HGVSg']
                case_transcript = CaseTranscript(case_id, variant_count, gene_id, gene_name, hgnc_id, transcript_name, canonical,
                                                 transcript_strand, proband_transcript_variant_effect,
                                                 transcript_variant_af_max, variant_polyphen, variant_sift,
                                                 transcript_variant_hgvs_c, transcript_variant_hgvs_p,
                                                 transcript_variant_hgvs_g)
                transcripts_list.append(case_transcript)
    return transcripts_list


def generate_transcripts(variant_list):
    '''
    Wrapper function for running VEP for MCA. This take as input a variant_list which contains all the variants
    for the cases which MCA will update/add. If bypass_VEP function is used from the config, this will read in
    the temp.vep.vcf file for transcripts

    :param variant_list: A list of Casevariant objects
    :return: A list of CaseTranscript objects for all the CaseVariants
    '''
    variant_vcf_dict = get_variant_list(variant_list)
    annotated_dict = run_cellbase(variant_vcf_dict)
    transcripts_list = parse_cellbase(variant_list, annotated_dict)
    return transcripts_list
