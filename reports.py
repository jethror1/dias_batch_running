#!/usr/bin/python

from collections import OrderedDict
import json
import subprocess

from general_functions import (
    dx_get_project_id,
    dx_get_object_name,
    get_workflow_stage_info,
    get_stage_inputs,
    make_workflow_out_dir,
    make_app_out_dirs,
    find_files,
    parse_genepanels,
    parse_Epic_manifest,
    parse_Gemini_manifest,
    prepare_batch_writing,
    create_batch_file,
    assess_batch_file,
    format_relative_paths,
    create_job_reports
)


# reports
def run_reports(
    ss_workflow_out_dir, dry_run, assay_config, assay_id,
    sample_ID_Rcode=None, sample_X_CI=None
):
    """Reads in the manifest file given on the command line and runs the
    SNV reports workflow.

    Collects input files for the reports workflow and sets off jobs

    Args:
        ss_workflow_out_dir: DNAnexus path to single output directory
            e.g /output/dias_single or /output/CEN-YYMMDD-HHMM
        dry_run: optional flag to set up but not run jobs
        assay_config: contains all the dynamic input file DNAnexus IDs
        assay_id: arg from cmd line what assay this is for
        sample_ID_Rcode: filename of Epic manifest containing sample identifiers
            and specifying R_codes (or _HGNC IDs) to analyse samples with
            used with reports command
        sample_X_CI: filename of Gemini manifest containing X numbers
            and specifying clinical indications to analyse samples with
            used with reanalysis command
    """

    ### Set up environment: make output folders
    # Find project to create jobs and outdirs in
    project_id = dx_get_project_id()
    project_name = dx_get_object_name(project_id)
    print("Jobs will be set off in project {}".format(project_name))

    # Check that provided input directory is an absolute path
    assert ss_workflow_out_dir.startswith("/output/"), (
        "Input directory must be full path (starting with /output/)")

    # Create workflow output folder named after workflow and config used
    rpt_workflow_out_dir = make_workflow_out_dir(
        assay_config.rpt_workflow_id, assay_id, ss_workflow_out_dir
    )
    # Identify executables for each stage within the workflow
    # stages[stage['id']] = {"app_id": app_id, "app_name": app_name}
    rpt_workflow_stage_info = get_workflow_stage_info(
        assay_config.rpt_workflow_id
    )
    # Create output folders for each executable within the workflow
    rpt_output_dirs = make_app_out_dirs(
        rpt_workflow_stage_info, rpt_workflow_out_dir
    )

    ### Identify samples to run reports workflow for
    # Gather sample names that have a Sentieon VCF generated
    ## current pattern picks up both "normal" and "genomic" VCFs
    single_sample_vcfs = find_files(
        project_name, ss_workflow_out_dir, pattern="-E '(.*).vcf.gz$'"
    )
    single_sample_names = [str(x).split('_')[0] for x in single_sample_vcfs]

    ### Identify panels and clinical indications for each sample
    # Placeholder for list of sample names that are available in:
    # has Sentieon VCF and present in manifest (see below)
    sample_name_list = []
    # Placeholder dict for gene_CIs and clinical indications
    # based on R code from manifest (see below)
    sample2CIpanel_dict = {}

    # Load genepanels information
    CI2panels_dict = parse_genepanels(assay_config.genepanels_file)

    ## Based on the command arg input, identify samples and panels from the
    ## Epic or Gemini-style manifest file
    if sample_ID_Rcode is not None:
        print("running dias_reports with sample identifiers and test codes "
                "from Epic")
        # Gather samples from the Epic manifest file (command line input file-ID)
        ## manifest_data is a {sample: {CIs: []}} dict
        manifest_data = parse_Epic_manifest(sample_ID_Rcode)
        manifest_samples = manifest_data.keys()

        # manifest file only has partial sample names/identifiers
        for sample in single_sample_names:
            Instrument_ID = sample.split('-')[0]
            Specimen_ID = sample.split('-')[1]
            partial_identifier = "-".join([Instrument_ID, Specimen_ID])
            if partial_identifier in manifest_samples:
                    sample_name_list.append(sample)
                    manifest_data[partial_identifier]["sample"] = sample

        # With the relevant samples identified,
        # parse the clinical indications (R code or HGNC) they were booked for
        sample2Rcodes_dict = dict(
            (sample_CI["sample"], sample_CI["CIs"]) for sample_CI 
                in manifest_data.values() if "sample" in sample_CI.keys()
        )

        # Get gene panels based on R code from manifest
        for sample, R_codes in sample2Rcodes_dict.items():
            CIs = []
            panels = []
            for R_code in R_codes:
                if R_code.startswith("_"):
                    CIs.append(R_code)
                    panels.append(R_code)
                else:
                    clinical_indication = next(
                        (key for key in CI2panels_dict.keys() if key.split("_")[0] == R_code),
                        None)
                    CIs.append(clinical_indication)
                    panels.extend(list(CI2panels_dict[clinical_indication]))
            sample2CIpanel_dict[sample] = {
                "clinical_indications": CIs,
                "panels": panels
            }

    elif sample_X_CI is not None:
        print("running dias_reports with X numbers and clinical indications "
                "from Gemini")
        # Gather samples from the Gemini manifest file (command line input filename)
        ## manifest_data is a {sample: {CIs: []}} dict
        # parse reanalysis file into 
        manifest_data = parse_Gemini_manifest(sample_X_CI)
        manifest_samples = manifest_data.keys() # list of tuples

        # manifest file only has partial sample names/identifiers
        for sample in single_sample_names:
            partial_identifier = sample.split('-')[0] # X number
            if partial_identifier in manifest_samples:
                    sample_name_list.append(sample)
                    manifest_data[partial_identifier]["sample"] = sample

        # With the relevant samples identified, parse the R codes they were booked
        sample2Rcodes_dict = dict(
            (sample_CI["sample"], sample_CI["CIs"]) for sample_CI 
                in manifest_data.values() if "sample" in sample_CI.keys()
        )

        # Get gene panels based on R code from manifest
        for sample, R_codes in sample2Rcodes_dict.items():
            CIs = []
            panels = []
            for R_code in R_codes:
                if R_code.startswith("_"):
                    CIs.append(R_code)
                    panels.append(R_code)
                else:
                    clinical_indication = next(
                        (key for key in CI2panels_dict if key.startswith(R_code)),
                        None)
                    CIs.append(clinical_indication)
                    panels.extend(list(CI2panels_dict[clinical_indication]))
            sample2CIpanel_dict[sample] = {
                "clinical_indications": CIs,
                "panels": panels
            }

    else:
        assert sample_ID_Rcode or sample_X_CI, "No file was provided with sample & panel information"

    # Gather sample-specific input file IDs based on the given app-pattern
    sample2stage_input2files_dict = get_stage_inputs(
        ss_workflow_out_dir, sample_name_list, assay_config.rpt_stage_input_dict
    )

    # list to represent the header row in the batch.tsv file
    headers = []
    # list to represent the rows/lines for each sample in the batch.tsv file
    values = []

    job_dict = {"starting": [], "missing_from_manifest": [], "symbols": []}

    # get the headers and values from the staging inputs
    rpt_headers, rpt_values = prepare_batch_writing(
        sample2stage_input2files_dict, "reports",
        assay_config_athena_stage_id=assay_config.athena_stage_id,
        assay_config_generate_workbook_stage_id=assay_config.generate_workbook_stage_id,
        workflow_specificity=assay_config.rpt_dynamic_files
    )

    # manually add the headers for panel/clinical_indication inputs
    for header in rpt_headers:
        new_headers = [field for field in header]
        new_headers.extend([
            "{}.clinical_indication".format(assay_config.generate_workbook_stage_id),
            "{}.panel".format(assay_config.generate_bed_vep_stage_id),
            "{}.panel".format(assay_config.generate_bed_athena_stage_id),
            "{}.panel".format(assay_config.generate_workbook_stage_id)
        ])
        headers.append(tuple(new_headers))

    for line in rpt_values:
        # sample id is the first element of every list according to
        # the prepare_batch_writing function
        sample_id = line[0]

        if sample_id in sample2CIpanel_dict:
            CIs = sample2CIpanel_dict[sample_id]["clinical_indications"]
            panels = sample2CIpanel_dict[sample_id]["panels"]

            # get single genes with the sample
            single_genes = [
                panel for panel in panels if panel.startswith("_")
            ]

            # if there are single genes
            if single_genes:
                # check if they are HGNC ids
                symbols = [gene.startswith("_HGNC") for gene in single_genes]

                # if they are not, assume it is gene symbols or at least
                # something is going on and needs checking
                if not all(symbols):
                    job_dict["symbols"].append(
                        (sample_id, ";".join(CIs))
                    )
                    continue

            job_dict["starting"].append(sample_id)
            # join up potential lists of CIs and panels to align the batch
            # file properly
            cis = ";".join(CIs)
            panels = ";".join(panels)
            line.extend([cis, cis, cis, panels])
            values.append(line)
        else:
            job_dict["missing_from_manifest"].append(sample_id)

    report_file = create_job_reports(
        rpt_workflow_out_dir, sample_name_list, job_dict
    )

    print("Created and uploaded job report file: {}".format(report_file))

    rpt_batch_file = create_batch_file(headers, values)
    # Check batch file is correct every time
    check_batch_file = assess_batch_file(rpt_batch_file)

    if check_batch_file is True:
        print(
            "Format of the file is correct: {}".format(rpt_batch_file)
        )
    else:
        print((
            "Number of columns in header doesn't match "
            "number of columns in values at line {}".format(check_batch_file)
        ))

    command = "dx run -y --rerun-stage '*' {} --batch-tsv={}".format(
        assay_config.rpt_workflow_id, rpt_batch_file
    )
    command += " -i{}.flank={} ".format(
        assay_config.generate_bed_vep_stage_id, assay_config.vep_bed_flank
    )

    if assay_config.assay_name == "TWE":
        command += " -i{}.buffer_size=1000".format(assay_config.vep_stage_id)

    # assign stage out folders
    app_relative_paths = format_relative_paths(rpt_workflow_stage_info)
    command += " --destination={} {} ".format(
        rpt_workflow_out_dir, app_relative_paths
    )

    if dry_run:
        print("Created workflow out dir: {}".format(rpt_workflow_out_dir))
        print("Created stage out dirs: ")
        print(json.dumps(
            OrderedDict(sorted(rpt_output_dirs.iteritems())), indent=4)
        )
        print("Inputs gathered:")
        print(json.dumps(sample2stage_input2files_dict, indent=4))
        print("Final cmd: {}".format(command))
        print("Deleting '{}' as part of the dry-run".format(rpt_workflow_out_dir))
        delete_folders_cmd = "dx rm -r {}".format(rpt_workflow_out_dir)
        subprocess.call(delete_folders_cmd, shell=True)
    else:
        subprocess.call(command, shell=True)

    return rpt_workflow_out_dir
