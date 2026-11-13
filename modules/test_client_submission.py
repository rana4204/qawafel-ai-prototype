"""Tests for the client to Mock Bank API submission flow."""

from unittest import TestCase
from unittest.mock import Mock

from modules.client_submission import (
    SubmissionBlockedError,
    apply_bank_status_events,
    submit_client_application,
)
from modules.mock_bank_api import MockBankAPI, MockBankError


class ClientSubmissionTests(TestCase):
    def setUp(self):
        self.bank = MockBankAPI()
        self.pending = {
            "draft_id": "DRAFT-001",
            "lifecycle_state": "analysis_ready",
            "analysis_stale": False,
            "company_name": "Example Trading LLC",
            "company_profile_snapshot": {"company_name": "Example Trading LLC", "currency": "SAR"},
            "financing_type": "Working capital",
            "requested_amount": 125000.0,
            "requested_currency": "SAR",
            "application_context": {"requested_tenure_months": 12},
            "documents": [{"document_type": "invoices"}],
            "validation_report": {"summary": {"is_valid": True}},
            "invoice_matching_result": {},
            "financial_analysis_result": {},
            "financial_insights_result": {},
        }
        self.applications = []

    def test_successful_submission_stores_ack_and_package(self):
        record, duplicate = submit_client_application(
            self.bank, self.pending, self.applications
        )

        self.assertFalse(duplicate)
        self.assertEqual(record["lifecycle_state"], "submitted")
        self.assertEqual(record["status"], "received")
        self.assertTrue(record["bank_reference"].startswith("MB-"))
        self.assertEqual(record["submitted_at"], record["bank_acknowledgment"]["received_at"])
        self.assertIn("financial_analysis", record["financing_package"])
        self.assertEqual(len(self.applications), 1)

    def test_api_failure_preserves_pending_application_and_stable_retry_reference(self):
        failing_bank = Mock()
        failing_bank.submit_application.side_effect = MockBankError("simulated outage")
        with self.assertRaisesRegex(MockBankError, "simulated outage"):
            submit_client_application(failing_bank, self.pending, self.applications)
        retry_reference = self.pending["application_id"]
        self.assertEqual(self.pending["lifecycle_state"], "analysis_ready")
        self.assertEqual(self.applications, [])

        record, _ = submit_client_application(self.bank, self.pending, self.applications)
        self.assertEqual(record["application_id"], retry_reference)

    def test_validation_or_stale_analysis_blocks_submission(self):
        self.pending["validation_report"]["summary"]["is_valid"] = False
        with self.assertRaises(SubmissionBlockedError):
            submit_client_application(self.bank, self.pending, self.applications)
        self.pending["validation_report"]["summary"]["is_valid"] = True
        self.pending["analysis_stale"] = True
        with self.assertRaises(SubmissionBlockedError):
            submit_client_application(self.bank, self.pending, self.applications)
        self.assertEqual(self.applications, [])

    def test_duplicate_draft_does_not_call_api_twice(self):
        first, duplicate = submit_client_application(
            self.bank, self.pending, self.applications
        )
        second, was_duplicate = submit_client_application(
            self.bank, self.pending, self.applications
        )
        self.assertFalse(duplicate)
        self.assertTrue(was_duplicate)
        self.assertIs(first, second)
        self.assertEqual(len(self.applications), 1)

    def test_api_status_history_is_ready_for_client_details(self):
        record, _ = submit_client_application(self.bank, self.pending, self.applications)
        reference = record["application_id"]
        update = self.bank.generate_status_update(reference, "under_review", note="Review started")
        apply_bank_status_events(
            record,
            self.bank.get_application_status(reference),
            self.bank.get_status_events(reference),
        )
        self.assertEqual(record["status"], "under_review")
        self.assertEqual(record["status_history"][-1]["new_status"], "under_review")
        self.assertEqual(record["status_history"][-1]["event_id"], update["event_id"])
        self.assertEqual(record["status_history"][-1]["source"], "Mock Bank API")
