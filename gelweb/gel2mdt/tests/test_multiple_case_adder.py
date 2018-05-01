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
import unittest
from django.test import TestCase

from ..database_utils.multiple_case_adder import MultipleCaseAdder
from ..database_utils.case_handler import Case, CaseModel, ManyCaseModel
from ..models import *

import re
import os
import json
import hashlib
import pprint
from datetime import datetime
from django.utils import timezone


class TestCaseOperations(object):
    """
    Common operations on our test zoo.
    """
    def __init__(self):
        self.file_path_list = [
            # get the list of absolute file paths for the cases in test_files
            os.path.join(
                os.getcwd(),
                "gel2mdt/tests/test_files/{filename}".format(
                    filename=filename)
            ) for filename in os.listdir(
                os.path.join(
                    os.getcwd(),
                    "gel2mdt/tests/test_files"
                )
            )
        ]

        self.json_list = [
            json.load(open(file_path)) for file_path in self.file_path_list
        ]

        self.request_id_list = [
            str(x["interpretation_request_id"]) + "-" + str(x["version"])
            for x in self.json_list]

        self.json_hashes = {
            str(x["interpretation_request_id"]) + "-" + str(x["version"]):
                hashlib.sha512(
                    json.dumps(x, sort_keys=True).encode('utf-8')
                ).hexdigest() for x in self.json_list
                }

    def get_case_mapping(self, multiple_case_adder):
        """
        Return a tuple mapping of case, test_case for all of the newly
        created cases.
        """
        test_cases = self.json_list
        cases = multiple_case_adder.list_of_cases
        case_mapping = []
        for case in cases:
            for test_case in test_cases:
                if case.request_id \
                    == str(test_case["interpretation_request_id"]) + "-" \
                        + str(test_case["version"]):
                    case_mapping.append(case, test_case)

    def add_cases_to_database(self, change_hash=False):
        """
        For all the cases we have stored, add them all to the database.
        :param change_hash: Default=False. If True, hashes will be changes for
        GELInterpretationReport entries so that test cases in MCA get flagged
        for update.
        """
        # make dummy related tables
        clinician = Clinician.objects.create(
            name="test_clinician",
            email="test@email.com",
            hospital="test_hospital"
        )
        family = Family.objects.create(
            clinician=clinician,
            gel_family_id=100
        )

        # convert our test data into IR and IRfamily model instances
        ir_family_instances = [InterpretationReportFamily(
            participant_family=family,
            cip=json["cip"],
            ir_family_id=str(json["interpretation_request_id"]) +
            "-" + str(json["version"]),
            priority=json["case_priority"]
        ) for json in self.json_list]
        InterpretationReportFamily.objects.bulk_create(ir_family_instances)

        ir_instances = [GELInterpretationReport(
            ir_family=InterpretationReportFamily.objects.get(
                ir_family_id=str(json["interpretation_request_id"]) +
                "-" + str(json["version"])),
            polled_at_datetime=timezone.make_aware(datetime.now()),
            sha_hash=self.get_hash(json, change_hash),
            status=json["status"][0]["status"],
            updated=json["status"][0]["created_at"],
            user=json["status"][0]["user"]
        ) for json in self.json_list]
        for ir in ir_instances:
            ir.save()

    def get_hash(self, json, change_hash):
        """
        Take a json and whether or not to change a hash, then return
        the hash of that json. Changing hash may be required if testing
        whether a case has mismatching hash values from the latest stored.
        """
        hash_digest = self.json_hashes[
            str(json["interpretation_request_id"]) +
            "-" + str(json["version"])]
        if change_hash:
            hash_digest = hash_digest[::-1]

        return hash_digest


class TestUpdateCases(TestCase):
    """
    Test that all jsons can be added, then if one changes it is updated
    with a new version number on the JSON but still associated with the same
    IR family.
    """
    def setUp(self):
        """
        Instaniate a MCA for the zoo of test cases, unedited.
        """
        self.case_update_handler = MultipleCaseAdder(test_data=True)


class TestAddCases(TestCase):
    @unittest.skip("skip whilst testing hashcheck")
    def setUp(self):
        """
        Instantiate a MultipleCaseAdder for the zoo of test cases.
        """
        self.case_update_handler = MultipleCaseAdder(test_data=True)

    @unittest.skip("skip whilst testing hashcheck")
    def test_request_id_format(self):
        """
        For each test case, assert that we correctly parse the IR ID.
        """
        for case in self.case_update_handler.list_of_cases:
            assert re.match("\d+-\d+", case.request_id)

    @unittest.skip("skip whilst testing hashcheck")
    def test_hash_cases(self):
        """
        For each test case, assert that we reliably hash the json.
        """
        test_cases = TestCaseOperations()
        for case in self.case_update_handler.list_of_cases:
            assert case.json_hash == test_cases.json_hashes[case.request_id]

    @unittest.skip("skip whilst testing hashcheck")
    def test_extract_proband(self):
        """
        Test that we can get the proband out of the json as a dict-type.
        """
        test_cases = TestCaseOperations()
        case_mapping = test_cases.get_case_mapping(case_update_handler)

        for case, test_case in case_mapping:
            ir_data = test_case["interpretation_request_data"]["json_request"]
            participants = ir_data["pedigree"]["participants"]
            proband = None
            for participant in participants:
                if participant["isProband"]:
                    proband = participant
            assert case.proband["gelId"] == proband["gelId"]

    @unittest.skip("skip whilst testing hashcheck")
    def test_extract_latest_status(self):
        """
        Test that the status extracted has the latest date and most progressed
        status of all the statuses.
        """
        test_cases = TestCaseOperations()
        case_mapping = test_cases.get_case_mapping(case_update_handler)

        for case, test_case in case_mapping:
            status_list = test_case["status"]
            max_date = None
            max_progress = None
            for status in status_list:
                if max_date is None:
                    max_date = timezone.make_aware(status["created_at"])
                elif max_date < timezone.make_aware(status["created_at"]):
                    max_date = timezone.make_aware(status["created_at"])
                if max_progress is None:
                    max_progress = status["status"]
                elif status["status"] == "report_sent":
                    max_progress = "report_sent"
                elif status["status"] == "report_generated":
                    max_progress = "report_generated"
                elif status["status"] == "sent_to_gmcs":
                    max_progress = "sent_to_gmcs"
            assert case.status["status"] == max_progress
            assert timezone.make_aware(case.status["created_at"]) \
                == max_date

class TestIdentifyCases(TestCase):
    """
    Tests to ensure that MultipleCaseAdder can correctly determine
    which cases should be added, updated, and skipped.
    """
    @unittest.skip("long time to poll panelapp")
    def test_identify_cases_to_add(self):
        """
        MultipleCaseAdder recognises which cases need to be added.
        """
        case_update_handler = MultipleCaseAdder(test_data=True)
        test_cases = TestCaseOperations()

        for case in case_update_handler.cases_to_add:
            # all the test cases should be flagged as 'to add' since none added
            assert case.request_id in test_cases.request_id_list

        assert not case_update_handler.cases_to_update

    @unittest.skip("long time to poll panelapp")
    def test_identify_cases_to_update(self):
        """
        MultipleCaseAdder recognises hash differences to determine updates.
        """
        # add all of our test cases first. change hashes to trick MCA into
        # thinking the test files need to be updated in the database
        test_cases = TestCaseOperations()
        test_cases.add_cases_to_database(change_hash=True)

        # now cases are added, MCA should recognise this when checking
        case_update_handler = MultipleCaseAdder(test_data=True)

        to_update = case_update_handler.cases_to_update
        assert len(to_update) > 0
        for case in to_update:
            assert case.request_id in test_cases.request_id_list

    @unittest.skip("long time to poll panelapp")
    def test_identify_cases_to_skip(self):
        """
        MultipleCaseAdder recognises when latest version hashes match current.
        """
        test_cases = TestCaseOperations()
        # add all the test cases to db but retain hash so attempting to re-add
        # should cause a skip
        test_cases.add_cases_to_database()

        case_update_handler = MultipleCaseAdder(test_data=True)

        to_skip = case_update_handler.cases_to_skip
        assert len(to_skip) > 0
        for case in to_skip:
            assert case.request_id in test_cases.request_id_list


class TestCaseModel(TestCase):
    """
    Test functions carried out by the CaseModel class, ie. checking if an
    entry for a particular case needs to be added or is already present in
    the database.
    """
    @unittest.skip("skip whilst testing hashcheck")
    def test_new_clinician(self):
        """
        Return created=False when a Clinician is not known to the db.
        """
        clinician_objects = Clinician.objects.all()
        clinician = CaseModel(Clinician, {
            "name": "test",
            "email": "test",
            "hospital": "test"
        }, clinician_objects)
        print(clinician.entry)
        assert clinician.entry is False  # checking for a literal False

    def test_existing_clinician(self):
        """
        Returns a clinician object when Clinician is known to the db.
        """
        clinician_attributes = {
            "name": "test",
            "email": "test",
            "hospital": "test"
        }
        archived_clinician = Clinician.objects.create(
            **clinician_attributes
        )
        clinician_objects = Clinician.objects.all()

        test_clinician = CaseModel(Clinician, clinician_attributes, clinician_objects)
        assert test_clinician.entry.id == archived_clinician.id


class TestAddCases(TestCase):
    """
    Test that a case has been faithfully added to the database along with
    all of the required related tables when needed.
    """
    def test_updated(self):
        """
        Generic test to make sure models have become populated by MCM.
        """
        check_cases = True
        case_list_handler = MultipleCaseAdder(test_data=True)
        for model in (
            Clinician,
            Family,
            Proband,
            Relative,
            Phenotype,
            Panel,
            PanelVersion,
            Transcript,
            InterpretationReportFamily,
            GELInterpretationReport,
            ToolOrAssemblyVersion,
            Variant,
            TranscriptVariant,
            ProbandVariant,
            ProbandTranscriptVariant,
            ReportEvent,
        ):
            all_models = model.objects.all().values()
            if not all_models:
                print("Fail on:",model)
                check_cases = False


        assert check_cases


    @unittest.skip("long time to poll panelapp")
    def test_add_clinician(self):
        """
        Clinician has been fetched or added that matches the json
        """
        case_list_handler = MultipleCaseAdder(test_data=True)
        try:
            Clinician.objects.get(**{
                "name": "unknown",
                "email": "unknown",
                "hospital": "unknown"
            })
            created = True
        except Clinician.DoesNotExist as e:
            created = False
        assert created
        # now check that we are refreshing clinician in the case models:
        for case in case_list_handler.cases_to_add:
            clinician_cam = case.attribute_managers[Clinician]
            assert clinician_cam.case_model.entry is not False

        assert False

    @unittest.skip("long time to poll panelapp")
    def test_add_family(self):
        case_list_handler = MultipleCaseAdder(test_data=True)
        test_cases = TestCaseOperations()
        try:
            for test_case in test_cases.json_list:
                Family.objects.get(
                    **{
                        "gel_family_id": int(test_case["family_id"])
                    }
                )
            created = True
        except Family.DoesNotExist as e:
            created = False
        assert created

    @unittest.skip("long time to poll panelapp")
    def test_add_phenotypes(self):
        """
        All phenotypes in json added with HPO & description.
        """
        case_list_handler = MultipleCaseAdder(test_data=True)
        test_cases = TestCaseOperations()

        for case in case_list_handler.cases_to_add:
            phenotype_cam = case.attribute_managers[Phenotype]
            for phenotype in phenotype_cam.case_model.case_models:
                assert phenotype.entry is not False

    def test_associated_family_and_phenotypes(self):
        """
        Once phenotypes have been added, ensure M2M creation with Family.
        """
        pass

    def test_add_ir_family(self):
        """
        Family matching json data has been added/fetched
        """
        pass

    def test_add_or_get_panel_version(self):
        """
        Panel and panelversion from json added/fetched faithfully.
        """
        pass

    def test_add_or_get_panel_version_genes(self):
        """
        If panel version is new, check that genes corroborate with panelApp.
        """
        pass

    def test_add_ir_family(self):
        """
        Test that a new IRfamily has been made with a request ID matching the
        json.
        """
        pass

    def test_add_ir(self):
        """
        Test that a new IR has been made and links to the correct IRfamily.
        """
        pass
