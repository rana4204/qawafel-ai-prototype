"""Focused tests for the in-process mock bank API."""

from unittest import TestCase

from modules.mock_bank_api import (
    DuplicateSubmissionError,
    InvalidRequestError,
    MockBankAPI,
    SimulatedBankError,
)


class MockBankAPITests(TestCase):
    def setUp(self):
        self.bank = MockBankAPI()
        self.application = {
            "application_id": "APP-123ABC",
            "company_name": "Example Trading LLC",
            "financing_type": "Working capital",
            "requested_amount": 125000.0,
            "requested_currency": "SAR",
        }
        self.package = {
            "financing_purpose_description": "Purchase inventory",
            "requested_tenure_months": 12,
            "repayment_schedule": {"frequency": "monthly"},
            "financial_summary": {"monthly_revenue": 42000.0},
        }

    def test_successful_submission_returns_ack_and_stores_payload(self):
        acknowledgment = self.bank.submit_application(self.application, self.package)

        self.assertTrue(acknowledgment["acknowledged"])
        self.assertEqual(acknowledgment["application_reference"], "APP-123ABC")
        self.assertTrue(acknowledgment["bank_reference"].startswith("MB-"))
        self.assertEqual(acknowledgment["status"], "received")
        self.assertTrue(acknowledgment["received_at"])
        self.assertFalse(acknowledgment["duplicate"])
        stored = self.bank.get_application("APP-123ABC")
        self.assertEqual(stored["application"], self.application)
        self.assertEqual(stored["financing_package"], self.package)

    def test_identical_duplicate_is_idempotent_and_changed_duplicate_is_rejected(self):
        first = self.bank.submit_application(self.application, self.package)
        duplicate = self.bank.submit_application(self.application, self.package)

        self.assertEqual(duplicate["bank_reference"], first["bank_reference"])
        self.assertEqual(duplicate["received_at"], first["received_at"])
        self.assertTrue(duplicate["duplicate"])
        with self.assertRaises(DuplicateSubmissionError):
            self.bank.submit_application(
                {**self.application, "requested_amount": 130000.0}, self.package
            )

    def test_invalid_application_package_and_reference_are_rejected(self):
        with self.assertRaises(InvalidRequestError):
            self.bank.submit_application({}, self.package)
        with self.assertRaises(InvalidRequestError):
            self.bank.submit_application(
                {**self.application, "application_id": " "}, self.package
            )
        with self.assertRaises(InvalidRequestError):
            self.bank.submit_application(
                {**self.application, "requested_amount": float("nan")}, self.package
            )
        with self.assertRaises(InvalidRequestError):
            self.bank.submit_application(self.application, {})
        with self.assertRaises(InvalidRequestError):
            self.bank.get_application_status("MISSING")

    def test_simulated_bank_error_is_clear_and_does_not_store_request(self):
        with self.assertRaisesRegex(SimulatedBankError, "simulated error"):
            self.bank.submit_application(
                self.application, self.package, simulate_error=True
            )
        with self.assertRaises(InvalidRequestError):
            self.bank.get_application_status("APP-123ABC")

    def test_status_retrieval_reflects_current_status(self):
        acknowledgment = self.bank.submit_application(self.application, self.package)

        status = self.bank.get_application_status("APP-123ABC")

        self.assertEqual(status["status"], "received")
        self.assertEqual(status["bank_reference"], acknowledgment["bank_reference"])
        self.assertEqual(status["updated_at"], acknowledgment["received_at"])

    def test_status_update_returns_consumable_event_and_updates_history(self):
        acknowledgment = self.bank.submit_application(self.application, self.package)

        event = self.bank.generate_status_update(
            "APP-123ABC", "under_review", note="Initial assessment started"
        )

        self.assertEqual(event["previous_status"], "received")
        self.assertEqual(event["status"], "under_review")
        self.assertEqual(event["bank_reference"], acknowledgment["bank_reference"])
        self.assertTrue(event["event_id"].startswith("EVT-"))
        self.assertEqual(self.bank.get_application_status("APP-123ABC")["status"], "under_review")
        self.assertEqual(len(self.bank.get_status_events("APP-123ABC")), 2)
        with self.assertRaises(InvalidRequestError):
            self.bank.generate_status_update("APP-123ABC", "not-a-status")
