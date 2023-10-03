"""
The majority of functions in dx_requests.py relate to interacting with
DNAnexus via dxpy API calls to either manage data (in DXManage) or for
launching jobs (in DXExecute).

Functions not covered by unit tests:
    - Everything in DXExecute - all functions relate to launching jobs,
        going to test these manually by running the app (probably, we shall
        see if I get the motivation to try patch things well to test them)
"""
from copy import deepcopy
import os
import sys
import unittest
from unittest import mock
from unittest.mock import patch

import dxpy
import pandas as pd
import pytest


sys.path.append(os.path.abspath(
    os.path.join(os.path.realpath(__file__), '../../')
))

from utils.dx_requests import DXExecute, DXManage


TEST_DATA_DIR = (
    os.path.join(os.path.dirname(__file__), 'test_data')
)

class TestDXManageReadAssayConfigFile():
    """
    Tests for DXManage.read_assaay_config_file()

    Function is used where a specific assay config file is provided, and
    reads this into a dict object
    """

    @patch('utils.dx_requests.dxpy.DXFile')
    @patch('utils.dx_requests.DXManage.read_dxfile')
    def test_config_correctly_read(self, mock_read, mock_file):
        """
        Test config file is correctly read in, function uses already tested
        DXManage.read_dxfile() to read the contents into a list, so this will
        just test that the contents is returned as a dict and the filename
        is added under the key 'name'
        """
        # minimal describe call return from config file
        mock_file.return_value.describe.return_value = {
            'id': 'file-xxx',
            'name': 'testAssayConfig.json'
        }

        # minimal example of what would be returned from DXManage.read_dxfile
        mock_read.return_value = [
            '{"assay": "test", "version": "1.0.0"}'
        ]

        contents = DXManage().read_assay_config_file(file='file-xxx')

        correct_contents = {
            "assay": "test",
            "version": "1.0.0",
            "dxid": "file-xxx",
            "name": "testAssayConfig.json"
        }

        assert contents == correct_contents, (
            "Contents parsed from config file incorrect"
        )


class TestDXManageGetAssayConfig(unittest.TestCase):
    """
    Tests for DXManage.get_assay_config()

    Function either takes a path and assay string to search in DNAnexus
    and return the highest config file version for
    """
    def setUp(self):
        """
        Setup our mocks
        """
        # set up patches for each sub function call in DXExecute.cnv_calling
        self.loads_patch = mock.patch('utils.dx_requests.json.loads')
        self.find_patch = mock.patch('utils.dx_requests.dxpy.find_data_objects')
        self.file_patch = mock.patch('utils.dx_requests.dxpy.bindings.dxfile.DXFile')

        # create our mocks to reference
        self.mock_loads = self.loads_patch.start()
        self.mock_find = self.find_patch.start()
        self.mock_file = self.file_patch.start()


    def tearDown(self):
        self.loads_patch.stop()
        self.mock_find.stop()
        self.mock_file.stop()


    @pytest.fixture(autouse=True)
    def capsys(self, capsys):
        """Capture stdout to provide it to tests"""
        self.capsys = capsys


    def test_error_raised_when_path_invalid(self):
        """
        AssertionError should be raised if path param is not valid
        """
        expected_error = 'path to assay configs appears invalid: invalid_path'

        with pytest.raises(AssertionError, match=expected_error):
            DXManage().get_assay_config(path='invalid_path', assay='')


    def test_error_raised_when_no_config_files_found(self):
        """
        AssertionError should be raised if no JSON files found, patch
        the return of the dxpy.find_data_objects() call to be empty and
        check we raise an error correctly
        """
        self.find_patch.return_value = []

        expected_error = (
            'No config files found in given path: project-xxx:/test_path'
        )
        with pytest.raises(AssertionError, match=expected_error):
            DXManage().get_assay_config(path='project-xxx:/test_path', assay='')


    def test_error_raised_when_no_config_file_found_for_assay(self):
        """
        AssertionError should be raised if we find some JSON files but
        after parsing through none of them match our given assay string
        against the 'assay' key in the config
        """
        # set output of find to be minimal describe call output with
        # required keys for iterating over
        self.mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'name': 'config1.json',
                    'archivalState': 'live'
                }
            }
        ]

        # patch the DXFile object that read() gets called on
        self.mock_file.return_value = dxpy.bindings.dxfile.DXFile

        # patch the output from DXFile.read() to just be all the same dict
        self.mock_loads.return_value = {'assay': 'CEN', 'version': '1.0.0'}

        expected_error = (
            "No config file was found for test from project-xxx:/test_path"
        )

        with pytest.raises(AssertionError, match=expected_error):
            DXManage().get_assay_config(
                path='project-xxx:/test_path',
                assay='test'
            )


    def test_highest_version_correctly_selected(self):
        """
        Test that when multiple configs are found for an assay, the
        highest version is correctly returned. We're using
        packaging.version.Version to compare versions parsed from
        the config files so this _should_ work as we expect
        """
        # set output of find to be minimal describe call output with
        # required keys for iterating over, here we need a dict per
        # `mock_read` return values that we want to test with
        self.mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'name': 'config.json',
                    'archivalState': 'live'
                }
            }
        ] * 5

        # patch the DXFile object that read() gets called on
        self.mock_file.return_value = dxpy.bindings.dxfile.DXFile

        # patch the output from DXFile.read() to simulate looping over
        # the return of reading multiple configs
        self.mock_loads.side_effect = [
            {'assay': 'test', 'version': '1.0.0'},
            {'assay': 'test', 'version': '1.1.0'},
            {'assay': 'test', 'version': '1.0.10'},
            {'assay': 'test', 'version': '1.1.11'},
            {'assay': 'test', 'version': '1.2.1'}
        ]

        config = DXManage().get_assay_config(
            path='project-xxx:/test_path',
            assay='test'
        )

        assert config['version'] == '1.2.1', (
            "Incorrect config file version returned"            
        )


    def test_non_live_files_skipped(self):
        """
        Test when one or more configs are not in a live state that these
        are skipped
        """
        # minimal dxpy.find_data_objects return of a live and archived config
        self.mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe': {
                    'name': 'config1.json',
                    'archivalState': 'live'
                }
            },
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe': {
                    'name': 'config2.json',
                    'archivalState': 'archived'
                }
            }
        ]

        # patch the DXFile object that read() gets called on
        self.mock_file.return_value = dxpy.bindings.dxfile.DXFile

        # patch the output from DXFile.read() for our live config
        self.mock_loads.side_effect = [
            {'assay': 'test', 'version': '1.0.0'}
        ]

        DXManage().get_assay_config(
            path='project-xxx:/test_path',
            assay='test'
        )

        stdout = self.capsys.readouterr().out

        expected_warning = (
            "Config file not in live state - will not be used: "
            "config2.json (file-xxx)"
        )

        assert expected_warning in stdout, (
            "Warning not printed for archived file"
        )


class TestDXManageGetFileProjectContext():
    """
    Tests for DXManage.get_file_project_context()

    Function takes a DXFile ID and returns a project ID in which
    the file has been found in a live state
    """

    @patch('utils.dx_requests.dxpy.DXFile.describe')
    @patch('utils.dx_requests.dxpy.DXFile')
    @patch('utils.dx_requests.dxpy.find_data_objects')
    def test_no_live_files(
            self,
            mock_find,
            mock_file,
            mock_describe
        ):
        """
        Test that when no files in a live state are found that an
        AssertionError is raised
        """
        # patch the DXFile object to nothing as we won't use it,
        # and the output of dx find to be a minimal set of describe calls
        mock_describe.return_value = {}
        mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'archivalState': 'archived'
                }
            },
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'archivalState': 'archival'
                }
            }
        ]

        correct_error = 'No live files could be found for the ID: file-xxx'

        with pytest.raises(AssertionError, match=correct_error):
            DXManage().get_file_project_context(file='file-xxx')


    @patch('utils.dx_requests.dxpy.DXFile.describe')
    @patch('utils.dx_requests.dxpy.DXFile')
    @patch('utils.dx_requests.dxpy.find_data_objects')
    def test_live_files(
        self,
        mock_find,
        mock_file,
        mock_describe,
        capsys
    ):
        # patch the DXFile object to nothing as we won't use it,
        # and the output of dx find to be a minimal set of describe calls
        mock_describe.return_value = {}
        mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe': {
                    'archivalState': 'live'
                }
            },
            {
                'project': 'project-yyy',
                'id': 'file-xxx',
                'describe': {
                    'archivalState': 'live'
                }
            }
        ]

        returned = DXManage().get_file_project_context(file='file-xxx')

        errors = []

        # check we print what we expect
        stdout = capsys.readouterr().out
        expected_print = (
            'Found file-xxx in 2 projects, using project-xxx as project context'
        )

        if expected_print not in stdout:
            errors.append('Did not print expected file project context')

        if not returned == mock_find.return_value[0]:
            errors.append('Incorrect file context returned')

        assert not errors, errors


class TestDXManageFindFiles():
    """
    Tests for DXManage.find_files()

    Function takes a path in DNAnexus and returns a set of files,
    will optionally filter these to a sub directory and also regex
    pattern for the file name to match
    """

    @patch('utils.dx_requests.dxpy.find_data_objects')
    def test_files_just_path_returned(self, mock_find):
        """
        Test when a set of files is returned from dxpy.find_data_objects()
        and no sub dir or pattern is specified that all the files are returned
        """
        mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'name': 'file1',
                    'archivalState': 'live'
                }
            },
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'name': 'file2',
                    'archivalState': 'live'
                }
            }
        ]

        files = DXManage().find_files(path='project-xxx:/some_path/')

        assert files == mock_find.return_value, 'Incorrect files returned'


    @patch('utils.dx_requests.dxpy.find_data_objects')
    def test_sub_dir_filters_correctly(self, mock_find):
        """
        Test when a sub dir is provided, the files are correctly filtered
        """
        mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'name': 'file1',
                    'archivalState': 'live',
                    'folder': '/path_to_files/subdir1/app1'
                }
            },
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe' : {
                    'name': 'file2',
                    'archivalState': 'live',
                    'folder': 'path_to_files/subdir2/app1'
                }
            }
        ]

        files = DXManage().find_files(
            path='project-xxx:/path_to_files/',
            subdir='/subdir1'
        )

        assert files == [mock_find.return_value[0]], (
            'Incorrect file returned when filtering to subdir'
        )


    @patch('utils.dx_requests.dxpy.find_data_objects')
    def test_archived_files_flagged_in_logs(self, mock_find, capsys):
        """
        If any files are found to be not live, a warning should be added
        to the logs, and then this will raises an error when
        DXManage.check_archival_state is called before running any jobs
        """
        mock_find.return_value = [
            {
                'project': 'project-xxx',
                'id': 'file-xxx',
                'describe': {
                    'name': 'file1',
                    'archivalState': 'archived',
                    'folder': '/path_to_files/subdir1/app1'
                }
            }
        ]

        DXManage().find_files(
            path='project-xxx:/path_to_files/'
        )

        stdout = capsys.readouterr().out
        expected_warning = (
            'WARNING: some files found are in an archived state, if these are '
            'for samples to be analysed this will raise an error...'
            '\n[\n    "file1 (file-xxx)"\n]'
        )

        assert expected_warning in stdout, (
            'Expected warning for archived files not printed'
        )






class TestDXManageReadDXfile():
    """
    Tests for DXManage.read_dxfile()

    Generic method for reading the contents of a DNAnexus file into a
    list of strings, accepts file ID input as some form of string or
    $dnanexus_link mapping
    """
    def test_none_object_passed(self, capsys):
        """
        If an empty object gets passed we should just print and return
        """
        DXManage().read_dxfile(file=None)
        stdout = capsys.readouterr().out

        assert 'Empty file passed to read_dxfile() :sadpepe:' in stdout, (
            "Function didn't return as expected for empty input"
        )

    @patch('utils.dx_requests.dxpy.DXFile.read')
    @patch('utils.dx_requests.dxpy.DXFile')
    def test_file_as_dict(self, mock_file, mock_read):
        """
        Test when file input is a dict (i.e. $dnanexus_link mapping) that
        we correctly parse the link to query with
        
        set variables for reading the file
        """
        file = {
            "$dnanexus_link": "project-xxx:file-xxx"
        }

        # project and file should get split and pass the assert, we have
        # patched DXFile.read() so nothing will get returned as we expect
        DXManage().read_dxfile(file=file)


    @patch('utils.dx_requests.DXManage.get_file_project_context')
    @patch('utils.dx_requests.dxpy.DXFile.read')
    @patch('utils.dx_requests.dxpy.DXFile')
    def test_file_as_just_file_id(self, mock_file, mock_read, mock_context):
        """
        Test when we provide file ID as just 'file-xxx' that it we call
        DXManage.get_file_project_context to return the project string,
        and then this passes through the function with no errors raised
        """
        # patch a minimal DXObject response
        mock_context.return_value = {
            'project': 'project-xxx',
            'id': 'file-xxx'
        }

        # project and file should get split from the get_file_project_context
        # response and pass the assert, we have patched DXFile.read() so
        # nothing will get returned as we expect
        DXManage().read_dxfile(file='file-xxx')


    @patch('utils.dx_requests.DXManage.get_file_project_context')
    @patch('utils.dx_requests.dxpy.DXFile.read')
    @patch('utils.dx_requests.dxpy.DXFile')
    def test_assertion_error_raised(self, mock_file, mock_read, mock_context):
        """
        Test when we provide file ID as just 'file-xxx' that it we call
        DXManage.get_file_project_context to return the project string,
        and that if there is something wrong in the format of the response
        (i.e. its empty but somehow didn't raise an error), we catch this
        with an AssertionError
        """
        # patch a DXObject response as being empty
        mock_context.return_value = {}

        with pytest.raises(
            AssertionError,
            match=r'Missing project and \/ or file ID - project: None, file: None'
        ):
            DXManage().read_dxfile(file='file-xxx')


    @patch('utils.dx_requests.dxpy.DXFile.read')
    @patch('utils.dx_requests.dxpy.DXFile')
    def test_file_as_project_and_file(self, mock_file, mock_read):
        """
        Test when file input is string with both project and file IDs
        that this get correctly split and used
        
        set variables for reading the file
        """
        # project and file should get split and pass the assert, we have
        # patched DXFile.read() so nothing will get returned as we expect
        DXManage().read_dxfile(file='project-xxx:file-xxx')


    def test_invalid_string_raises_error(self):
        """
        Test if an invalid string is passed that an error is raised
        """
        with pytest.raises(
            RuntimeError,
            match=r'DXFile not in an expected format: invalid_str'
        ):
            DXManage().read_dxfile(file='invalid_str')


class TestDXManageCheckArchivalState():
    """
    Tests for DXManage.check_archival_state()

    Function takes in a list of files (and optionally a list of sample names
    to filter by), and checks the archival state of the files to ensure all
    are live before launching jobs
    """
    # minimal dxpy.find_data_objects() return that we expect to pass in
    files = [
        {
            'id': 'file-xxx',
            'describe': {
                'name': 'sample1-file1',
                'archivalState': 'live'
            }
        },
        {
            'id': 'file-xxx',
            'describe': {
                'name': 'sample2-file1',
                'archivalState': 'live'
            }
        },
        {
            'id': 'file-xxx',
            'describe': {
                'name': 'sample3-file1',
                'archivalState': 'live'
            }
        },
        {
            'id': 'file-xxx',
            'describe': {
                'name': 'sample4-file1',
                'archivalState': 'live'
            }
        },
    ]

    # same as above but with an archived file added in
    files_w_archive = files + [
        {
            'id': 'file-xxx',
            'describe': {
                'name': 'sample5-file1',
                'archivalState': 'archived'
            }
        }
    ]

    def test_all_live(self, capsys):
        """
        Test no error is raised when all provided files are live
        """
        DXManage().check_archival_state(
            files=self.files,
            unarchive=False
        )

        # since we don't explicitly return anything when there are no
        # archived files, check stdout for expected string printed
        # to ensure the function passed through all checks to the end
        stdout = capsys.readouterr().out

        assert 'No required files in archived state' in stdout, (
            'Expected print for all live files not in captured stdout'
        )


    def test_error_raised_for_archived_files(self):
        """
        Test when files contains an archived file that a RuntimeError
        is correctly raised
        """
        with pytest.raises(
            RuntimeError,
            match='Files required for analysis archived'
        ):
            DXManage().check_archival_state(
            files=self.files_w_archive,
            unarchive=False
        )


    def test_archived_files_filtered_out_when_not_in_sample_list(self, capsys):
        """
        Test when a list of sample names is provided that any files for other
        samples are filtered out, we will test this by adding an archived file
        for a non-matching sample and checking it is removed
        """
        # provide list of sample names to filter by
        DXManage().check_archival_state(
            files=self.files_w_archive,
            unarchive=False,
            samples=['sample1', 'sample2', 'sample3', 'sample4']
        )

        # since we don't explicitly return anything for all being live check
        # stdout for expected string printed to ensure we got where we expect
        stdout = capsys.readouterr().out

        assert 'No required files in archived state' in stdout, (
            'Expected print for all live files not in captured stdout'
        )


    def test_archived_files_kept_when_in_sample_list(self):
        """
        Test when we have some archived files and a provided list of samples,
        and the archived files are for those selected samples
        """
        with pytest.raises(
            RuntimeError,
            match='Files required for analysis archived'
        ):
            # provide list of sample names to filter by, sample5 has
            # archived file and unarchive=False => should raise error
            DXManage().check_archival_state(
                files=self.files_w_archive,
                unarchive=False,
                samples=['sample5']
            )



    @patch('utils.dx_requests.DXManage.unarchive_files')
    def test_unarchive_files_called_when_specified(self, mock_unarchive):
        """
        Test when we have archived files and unarchive=True specified that
        we call the function to start unarchiving
        """
        DXManage().check_archival_state(
            files=self.files_w_archive,
            unarchive=True
        )

        assert mock_unarchive.called, (
            'DXManage.unarchive_files not called for unarchive=True'
        )


class TestDXManageUnarchiveFiles():
    """
    Tests for DXManage.unarchive_files()

    Function called by DXManage.check_archival_state where one or more
    archived files found and unarchive=True set, will go through the
    given file IDs and start the unarchiving process
    """
    # minimal dxpy.find_data_objects() return that we expect to unarchive
    files = [
        {
            'project': 'project-xxx',
            'id': 'file-xxx',
            'describe': {
                'name': 'sample1-file1',
                'archivalState': 'archived'
            }
        },
        {
            'project': 'project-xxx',
            'id': 'file-xxx',
            'describe': {
                'name': 'sample2-file1',
                'archivalState': 'archived'
            }
        }
    ]

    @patch('utils.dx_requests.dxpy.DXJob.add_tags')
    @patch('utils.dx_requests.dxpy.DXJob')
    @patch('utils.dx_requests.dxpy.DXFile.unarchive')
    @patch('utils.dx_requests.dxpy.DXFile')
    @patch('utils.dx_requests.sys.exit')
    def test_unarchiving_called(
            self,
            exit,
            mock_file,
            mock_unarchive,
            mock_job,
            mock_tags,
            capsys
        ):
        """
        Test that DXFile.unarchive() gets called on the provided list
        of DXFile objects
        """
        # mock_unarchive.return_value = True
        DXManage().unarchive_files(
            self.files
        )

        # lots of prints go to stdout once we have started unarchiving
        stdout = capsys.readouterr().out

        expected_stdout = [
            "Unarchiving requested for 2 files, this will take some time...",
            "The state of all files may be checked with the following command:",
            (
                "echo file-xxx file-xxx | xargs -n1 -d' ' -P32 -I{} bash -c "
                "'dx describe --json {} ' | grep archival | uniq -c"
            ),
            "This job can be relaunched once unarchiving is complete by running:",
            "dx run app-eggd_dias_batch --clone None -iunarchive=false"
        ]

        assert all(x in stdout for x in expected_stdout), (
            "stdout does not contain the expected output"
        )


    @patch('utils.dx_requests.dxpy.DXFile', side_effect=Exception('Error'))
    @patch('utils.dx_requests.sleep')
    def test_error_raised_if_unable_to_unarchive(
            self,
            mock_sleep,
            mock_dxfile
        ):
        """
        Function will try and catch up to 5 times to unarchive a file,
        if it can't unarchive a file an error should be raised. Here
        we make it raise an Exception to test it in the loop and ensure
        that it stops after failing.
        """
        with pytest.raises(
            RuntimeError,
            match=r'\[Attempt 5/5\] Error in unarchiving file: file-xxx'
        ):
           DXManage().unarchive_files(self.files)


class TestDXManageFormatOutputFolders(unittest.TestCase):
    """
    Tests for DXManage.format_output_folders()

    Function takes all the stages of a workflow, single output directory
    and a time stamp string to build a mapping of stages -> output folders
    """

    @patch('utils.dx_requests.dxpy.describe')
    def test_correct_folder_applet(self, mock_describe):
        """
        Test when an applet is inlcuded as a stage that the path is
        correctly set, applets are treat differently to apps as the
        'executable' key in the workflow details is just the applet ID
        instead of the human name and version for apps
        """
        mock_describe.return_value = {'name': 'applet1-v1.2.3'}

        workflow_details = {
            'name': 'workflow1',
            'stages': [
                {
                    'id': 'stage1',
                    'executable': 'applet-xxx'
                }
            ]
        }

        returned_stage_folder = DXManage().format_output_folders(
            workflow=workflow_details,
            single_output='some_output_path',
            time_stamp='010123_1303'
        )

        correct_stage_folder = {
            "stage1": "/some_output_path/workflow1/010123_1303/applet1-v1.2.3/"
        }

        assert correct_stage_folder == returned_stage_folder, (
            "Incorrect stage folders returned for applet"
        )

    def test_correct_folder_app(self):
        """
        Test when an app is included as a stage that the path is correctly
        set from its 'executable' value as this will contain the name
        and the version for the app
        """
        workflow_details = {
            'name': 'workflow1',
            'stages': [
                {
                    'id': 'stage1',
                    'executable': 'app-xxx/1.2.3'
                }
            ]
        }

        correct_stage_folder = {
            "stage1": "/some_output_path/workflow1/010123_1303/xxx-1.2.3/"
        }

        returned_stage_folder = DXManage().format_output_folders(
            workflow=workflow_details,
            single_output='some_output_path',
            time_stamp='010123_1303'
        )

        assert correct_stage_folder == returned_stage_folder, (
            "Invalid stage folders returned for app"
        )


class TestDXExecuteCNVCalling(unittest.TestCase):
    """
    Tests for DXExecute.cnv_calling

    This is the main function that calls all others to set up inputs for
    CNV calling and runs the app. The majority of what is called here is
    already covered by other unit tests, and therefore a lot will be
    mocked where called functions make dx requests etc themselves.

    We will mostly be testing that where the different inputs are given,
    that expected prints go to stdout since that is the most we can test
    """
    config = {
        'modes': {
            'cnv_call': {
                'inputs': {
                    'bambais': {
                        'folder': '/sentieon-dnaseq',
                        'name': '.bam$|.bam.bai$'
                    }
                }
            }
        }
    }

    def setUp(self):
        """
        Set up test class wide patches
        """
        # set up patches for each sub function call in DXExecute.cnv_calling
        self.path_patch = mock.patch('utils.dx_requests.make_path')
        self.find_patch = mock.patch('utils.dx_requests.DXManage.find_files')
        self.check_archival_state_patch = mock.patch(
            'utils.dx_requests.DXManage.check_archival_state'
        )
        self.describe_patch = mock.patch('utils.dx_requests.dxpy.describe')
        self.dxapp_patch = mock.patch('utils.dx_requests.dxpy.DXApp')
        self.run_patch = mock.patch('utils.dx_requests.dxpy.run')
        self.job_patch = mock.patch('utils.dx_requests.dxpy.DXJob')
        self.wait_patch = mock.patch('utils.dx_requests.dxpy.bindings.DXJob.wait_on_done')

        # create our mocks to reference
        self.mock_path = self.path_patch.start()
        self.mock_find = self.find_patch.start()
        self.mock_archive = self.check_archival_state_patch.start()
        self.mock_describe = self.describe_patch.start()
        self.mock_dxapp = self.dxapp_patch.start()
        self.mock_run = self.run_patch.start()
        self.mock_job = self.job_patch.start()
        self.mock_wait = self.wait_patch.start()

        # our test returns to use for the mocks

        # utils.make_path called twice, once to get path for searching for
        # BAM files then again for setting app output
        self.mock_path.side_effect = [
            'project-GZ025k04VjykZx3bJ7YP837:/output/CEN-230719_1604/sentieon',
            (
                'project-GZ025k04VjykZx3bJ7YP837:/output/CEN-230719_1604/'
                'GATK_gCNV_call-1.2.3/0925-17'
            )
        ]

        # mocked return of calling DXManage.find_files to search for input BAMs
        self.mock_find.return_value = [
            {
                'id': 'file-xxx',
                'describe': {
                    'name': 'sample1.bam'
                }
            },
            {
                'id': 'file-xxx',
                'describe': {
                    'name': 'sample1.bam.bai'
                }
            },
            {
                'id': 'file-xxx',
                'describe': {
                    'name': 'sample2.bam'
                }
            },
            {
                'id': 'file-xxx',
                'describe': {
                    'name': 'sample2.bam.bai'
                }
            },
            {
                'id': 'file-xxx',
                'describe': {
                    'name': 'sample3.bam'
                }
            },
            {
                'id': 'file-xxx',
                'describe': {
                    'name': 'sample3.bam.bai'
                }
            }
        ]

        # first dxpy.describe call is on app ID, second is on job ID
        # patch in minimal responses with required keys
        self.mock_describe.side_effect = [
            {
                'name': 'GATK_gCNV_call',
                'version': '1.2.3'
            },
            {
                'id': 'job-GXvQjz04YXKx5ZPjk36B17j2'
            }
        ]


    def tearDown(self):
        """
        Remove test class wide patches
        """
        self.mock_path.stop()
        self.mock_find.stop()
        self.mock_archive.stop()
        self.mock_describe.stop()
        self.mock_dxapp.stop()
        self.mock_run.stop()
        self.mock_job.stop()
        self.mock_wait.stop()


    @pytest.fixture(autouse=True)
    def capsys(self, capsys):
        """Capture stdout to provide it to tests"""
        self.capsys = capsys


    def test_cnv_call(self):
        """
        Test with everything patched that no errors are raised
        """
        DXExecute().cnv_calling(
            config=deepcopy(self.config),
            single_output_dir='',
            exclude=[],
            start='',
            wait=False,
            unarchive=False
        )


    def test_wait_on_done(self):
        """
        Test if wait=True is specified that the app will be held until
        calling completes
        """
        DXExecute().cnv_calling(
            config=deepcopy(self.config),
            single_output_dir='',
            exclude=[],
            start='',
            wait=True,
            unarchive=False
        )

        stdout = self.capsys.readouterr().out

        assert 'Holding app until CNV calling completes...' in stdout, (
            'App not waiting with wait=True specified'
        )


    def test_exclude(self):
        """
        Test when exclude samples is specified that these are used
        """
        DXExecute().cnv_calling(
            config=deepcopy(self.config),
            single_output_dir='',
            exclude=['sample2', 'sample3'],
            start='',
            wait=False,
            unarchive=False
        )

        stdout = self.capsys.readouterr().out

        correct_exclude = (
            '2 .bam/.bai files after excluding:\n\tsample1.bam\n\tsample1.bam.bai'
        )

        assert correct_exclude in stdout, (
            'exclude samples incorrect'
        )


    def test_exclude_invalid_sample(self):
        """
        Test when exclude samples is specified with a sample not in BAM
        files that a warning is printed
        """
        DXExecute().cnv_calling(
            config=deepcopy(self.config),
            single_output_dir='',
            exclude=['sample1000'],
            start='',
            wait=False,
            unarchive=False
        )

        stdout = self.capsys.readouterr().out

        correct_warning = (
            "WARNING: sample ID(s) provided to exclude not present in bam "
            "files found for CNV calling:\n\t['sample1000']\nIgnoring "
            "these and continuing..."
        )

        assert correct_warning in stdout, (
            'Invalid exclude sample specified not correctly removed'
        )


    def test_correct_error_raised_on_calling_failing(self):
        """
        If error raised during CNV calling whilst waiting to complete,
        test this is caught and exits the app
        """
        # patch return of DXJob to be an empty DXJob object, and set the
        # error to be raised from DXJob.wait_on_done()
        self.mock_job.return_value = dxpy.bindings.DXJob(dxid='localjob-')
        self.mock_wait.side_effect = dxpy.exceptions.DXJobFailureError(
            'oh no :sadpanda:')

        with pytest.raises(
            dxpy.exceptions.DXJobFailureError, match='oh no :sadpanda:'
        ):
            DXExecute().cnv_calling(
                config=deepcopy(self.config),
                single_output_dir='',
                exclude=[],
                start='',
                wait=True,
                unarchive=False
            )
