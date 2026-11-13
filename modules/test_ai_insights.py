"""Unit tests for the rule-based financial assessment engine."""

from __future__ import annotations

import copy
import unittest
from typing import Any

import pandas as pd

from modules.ai_insights import generate_financial_insights
from modules.data_validator import validate_dataset
from modules.financial_analyzer import analyze_financial_data
from modules.invoice_matcher import match_invoices_to_transactions


def _analysis() -> dict[str, Any]:
    """Return a small, valid analyzer-shaped report for controlled rule tests."""
    monthly_sales = [
        {"month": f"2025-{month:02d}", "amount": 100.0}
        for month in range(1, 13)
    ]
    return {
        "sales": {
            "total_invoiced_sales": 1200.0,
            "monthly_invoiced_sales": monthly_sales,
            "monthly_sales_trend": [
                {
                    "month": "2025-11",
                    "sales": 100.0,
                    "change_from_previous_month": 0.0,
                    "change_percent": 0.0,
                },
                {
                    "month": "2025-12",
                    "sales": 125.0,
                    "change_from_previous_month": 25.0,
                    "change_percent": 25.0,
                },
            ],
        },
        "collections": {
            "total_confirmed_collections": 100.0,
            "collection_to_sales_ratio_percent": 8.33,
        },
        "receivables": {
            "outstanding_receivables": 50.0,
            "fully_collected_invoice_count": 1,
            "partially_collected_invoice_count": 1,
            "unmatched_invoice_count": 1,
            "overpaid_invoice_count": 0,
            "total_excess_collections": 0.0,
            "invoice_collection_coverage_percent": 50.0,
        },
        "cash_flow": {
            "total_incoming_cash": 140.0,
            "total_outgoing_cash": 110.0,
            "net_cash_flow": 30.0,
            "monthly_net_cash_flow": [
                {"month": "2025-12", "amount": 30.0},
            ],
        },
        "unclassified_transactions": {
            "unmatched_transaction_count": 0,
            "unmatched_positive_credit_total": 0.0,
            "ambiguous_transaction_count": 0,
            "ambiguous_positive_credit_total": 0.0,
        },
        "data_quality": {
            "payment_status_discrepancies": 0,
            "missing_or_invalid_financial_values": {
                "invoices": {
                    "missing_invoice_date": 0,
                    "invalid_invoice_date": 0,
                    "amount_columns": {
                        column: {
                            "missing": 0,
                            "non_numeric_or_non_finite": 0,
                            "negative": 0,
                        }
                        for column in ("net_amount", "vat_amount", "total_amount")
                    },
                },
                "bank_transactions": {
                    "missing_transaction_date": 0,
                    "invalid_transaction_date": 0,
                    "missing_credit": 0,
                    "non_numeric_or_non_finite_credit": 0,
                    "negative_credit": 0,
                    "missing_debit": 0,
                    "non_numeric_or_non_finite_debit": 0,
                    "negative_debit": 0,
                },
            },
        },
    }


def _matching_result() -> dict[str, Any]:
    return {
        "invoice_matches": [
            {
                "invoice_id": "INV-1",
                "total_collected": 100.0,
                "collection_status": "fully_collected",
                "payment_status_discrepancy": False,
            },
        ],
        "unmatched_transactions": [],
        "ambiguous_transactions": [],
        "summary": {
            "ambiguous_transactions": 0,
            "unmatched_transactions": 0,
            "payment_status_discrepancies": 0,
        },
    }


def _validation_report() -> dict[str, Any]:
    return {
        "invoices": {
            "missing_columns": [],
            "missing_values": {"total_amount": 0},
            "duplicate_invoice_ids": 0,
            "non_numeric_amounts": {"total_amount": 0},
            "negative_amounts": {"total_amount": 0},
            "total_mismatch_count": 0,
        },
        "bank_transactions": {
            "missing_columns": [],
            "missing_values": {"credit": 0, "debit": 0},
            "non_numeric_values": {"credit": 0, "debit": 0},
            "negative_values": {"credit": 0, "debit": 0},
        },
        "summary": {
            "is_valid": True,
            "error_count": 0,
            "warning_count": 0,
            "errors": [],
        },
    }


def _context(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "application_id": "APP-1",
        "requested_amount": 50.0,
        "requested_currency": "SAR",
        "financial_currency": "SAR",
        "requested_tenure_months": 12,
        "financing_purpose_code": "equipment",
    }
    context.update(overrides)
    return context


def _assess(
    *,
    analysis: dict[str, Any] | None = None,
    matching: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    language: str = "en",
) -> dict[str, Any]:
    return generate_financial_insights(
        _analysis() if analysis is None else analysis,
        _matching_result() if matching is None else matching,
        _validation_report() if validation is None else validation,
        _context() if context is None else context,
        language=language,
        policy=(
            {"purpose_document_requirements": {"equipment": []}}
            if policy is None else policy
        ),
    )


def _finding_sections(result: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        name: result[name]
        for name in (
            "financial_strengths",
            "potential_risks",
            "financing_request_assessment",
            "existing_obligations",
            "data_quality_issues",
            "missing_information",
        )
    }


def _rule_items(result: dict[str, Any], section: str, rule_id: str) -> list[dict[str, Any]]:
    return [
        finding
        for finding in result[section]
        if finding.get("rule_id") == rule_id
    ]


def _all_findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        finding
        for section in _finding_sections(result).values()
        for finding in section
    ] + result["recommended_actions"] + result["limitations"]


def _synthetic_pipeline() -> tuple[
    pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any], dict[str, Any]
]:
    invoices = pd.DataFrame([
        {
            "invoice_id": "INV-1",
            "invoice_date": "2025-01-05",
            "customer_name": "Customer A",
            "net_amount": 100.0,
            "vat_amount": 15.0,
            "total_amount": 115.0,
            "payment_status": "Paid",
        },
        {
            "invoice_id": "INV-2",
            "invoice_date": "2025-01-10",
            "customer_name": "Customer B",
            "net_amount": 200.0,
            "vat_amount": 30.0,
            "total_amount": 230.0,
            "payment_status": "Pending",
        },
    ])
    transactions = pd.DataFrame([
        {
            "transaction_id": "TX-1",
            "transaction_date": "2025-01-15",
            "description": "Payment INV-1",
            "debit": 0.0,
            "credit": 115.0,
            "balance": 115.0,
        },
        {
            "transaction_id": "TX-2",
            "transaction_date": "2025-01-16",
            "description": "Unreferenced deposit",
            "debit": 0.0,
            "credit": 300.0,
            "balance": 415.0,
        },
        {
            "transaction_id": "TX-3",
            "transaction_date": "2025-01-17",
            "description": "Combined INV-1 and INV-2",
            "debit": 0.0,
            "credit": 400.0,
            "balance": 815.0,
        },
    ])
    validation = validate_dataset({
        "invoices": invoices,
        "bank_transactions": transactions,
    })
    matching = match_invoices_to_transactions(invoices, transactions)
    analysis = analyze_financial_data(invoices, transactions, matching)
    return invoices, transactions, validation, matching, analysis


def _assert_nested_unchanged(
    case: unittest.TestCase,
    actual: Any,
    expected: Any,
) -> None:
    if isinstance(expected, pd.DataFrame):
        case.assertIsInstance(actual, pd.DataFrame)
        pd.testing.assert_frame_equal(actual, expected)
    elif isinstance(expected, dict):
        case.assertIsInstance(actual, dict)
        case.assertEqual(actual.keys(), expected.keys())
        for key in expected:
            _assert_nested_unchanged(case, actual[key], expected[key])
    elif isinstance(expected, list):
        case.assertIsInstance(actual, list)
        case.assertEqual(len(actual), len(expected))
        for actual_item, expected_item in zip(actual, expected):
            _assert_nested_unchanged(case, actual_item, expected_item)
    else:
        case.assertEqual(actual, expected)


class GenerateFinancialInsightsTests(unittest.TestCase):
    def test_output_contract_metadata_and_all_finding_shapes(self) -> None:
        result = _assess()
        self.assertEqual(
            set(result),
            {
                "application_id",
                "assessment_type",
                "rule_set_version",
                "language",
                "financial_strengths",
                "potential_risks",
                "financing_request_assessment",
                "existing_obligations",
                "data_quality_issues",
                "missing_information",
                "recommended_actions",
                "limitations",
                "decision",
            },
        )
        self.assertEqual(result["application_id"], "APP-1")
        self.assertEqual(result["assessment_type"], "rule_based")
        self.assertTrue(result["rule_set_version"])
        self.assertEqual(result["language"], "en")
        self.assertEqual(
            result["decision"],
            {"status": "not_made", "decision_maker": "bank_employee"},
        )
        required_fields = {
            "rule_id",
            "category",
            "status",
            "title",
            "explanation",
            "evidence",
            "recommended_action",
            "review_status",
        }
        for finding in _all_findings(result):
            with self.subTest(rule_id=finding["rule_id"], category=finding["category"]):
                self.assertTrue(required_fields.issubset(finding))
                self.assertIsInstance(finding["evidence"], list)
                for evidence in finding["evidence"]:
                    self.assertTrue(
                        {"source", "metric_path", "value"}.issubset(evidence)
                    )

    def test_sales_growth_requires_two_consecutive_valid_periods(self) -> None:
        result = _assess()
        self.assertEqual(
            len(_rule_items(result, "financial_strengths", "FS-01")), 1
        )
        analysis = _analysis()
        analysis["sales"]["monthly_sales_trend"][-1]["month"] = "2026-01"
        result = _assess(analysis=analysis)
        self.assertEqual(_rule_items(result, "financial_strengths", "FS-01"), [])
        self.assertEqual(_rule_items(result, "potential_risks", "FR-01"), [])

    def test_positive_and_negative_net_cash_flow(self) -> None:
        result = _assess()
        self.assertEqual(
            len(_rule_items(result, "financial_strengths", "FS-02")), 1
        )
        analysis = _analysis()
        analysis["cash_flow"]["net_cash_flow"] = -30.0
        result = _assess(analysis=analysis)
        self.assertEqual(_rule_items(result, "financial_strengths", "FS-02"), [])
        self.assertEqual(len(_rule_items(result, "potential_risks", "FR-02")), 1)

    def test_collection_coverage_and_fully_collected_invoices(self) -> None:
        result = _assess()
        self.assertEqual(
            len(_rule_items(result, "financial_strengths", "FS-03")), 1
        )
        self.assertEqual(
            len(_rule_items(result, "financial_strengths", "FS-04")), 1
        )
        analysis = _analysis()
        analysis["receivables"]["invoice_collection_coverage_percent"] = 0.0
        analysis["receivables"]["fully_collected_invoice_count"] = 0
        result = _assess(analysis=analysis)
        self.assertEqual(_rule_items(result, "financial_strengths", "FS-03"), [])
        self.assertEqual(_rule_items(result, "financial_strengths", "FS-04"), [])

    def test_outstanding_receivables_are_not_called_overdue(self) -> None:
        finding = _rule_items(
            _assess(), "potential_risks", "FR-03"
        )[0]
        combined_text = " ".join(
            (finding["title"], finding["explanation"], finding["recommended_action"])
        ).casefold()
        self.assertIn("outstanding", combined_text)
        self.assertNotIn("overdue", finding["title"].casefold())
        self.assertNotIn("days past due", combined_text)
        self.assertIn("no aging", finding["explanation"].casefold())

    def test_unmatched_and_ambiguous_credits_are_excluded_from_collections(self) -> None:
        invoices, transactions, validation, matching, analysis = _synthetic_pipeline()
        self.assertEqual(analysis["collections"]["total_confirmed_collections"], 115.0)
        self.assertEqual(
            analysis["unclassified_transactions"]["unmatched_positive_credit_total"],
            300.0,
        )
        self.assertEqual(
            analysis["unclassified_transactions"]["ambiguous_positive_credit_total"],
            400.0,
        )
        result = _assess(
            analysis=analysis,
            matching=matching,
            validation=validation,
            context=_context(financial_currency="SAR"),
        )
        self.assertEqual(
            _rule_items(result, "potential_risks", "FR-04")[0]["evidence"][0]["value"],
            300.0,
        )
        self.assertIn("FR-05", {
            finding["rule_id"] for finding in result["potential_risks"]
        })
        fa02 = _rule_items(result, "financing_request_assessment", "FA-02")[0]
        evidence = {
            item["metric_path"]: item["value"] for item in fa02["evidence"]
        }
        self.assertEqual(
            evidence["collections.total_confirmed_collections"], 115.0
        )
        self.assertNotIn(300.0, evidence.values())
        self.assertNotIn(400.0, evidence.values())
        self.assertEqual(len(invoices), 2)
        self.assertEqual(len(transactions), 3)

    def test_payment_status_discrepancies_are_reported(self) -> None:
        analysis = _analysis()
        analysis["data_quality"]["payment_status_discrepancies"] = 1
        result = _assess(analysis=analysis)
        self.assertEqual(
            len(_rule_items(result, "potential_risks", "FR-06")), 1
        )
        self.assertEqual(
            len(_rule_items(result, "data_quality_issues", "DQ-05")), 1
        )

    def test_request_amount_comparisons_use_actual_period_metrics(self) -> None:
        result = _assess()
        findings = {
            finding["rule_id"]: finding
            for finding in result["financing_request_assessment"]
        }
        for rule_id in ("FA-01", "FA-02", "FA-03", "FA-04"):
            self.assertIn(rule_id, findings)
        fa01 = findings["FA-01"]
        self.assertIn(
            "2025-01 to 2025-12",
            " ".join(item.get("measurement_period", "") for item in fa01["evidence"]),
        )
        fa03_period = next(
            item["measurement_period"]
            for item in findings["FA-03"]["evidence"]
            if item["metric_path"] == "cash_flow.net_cash_flow"
        )
        self.assertEqual(fa03_period, "2025-12")
        self.assertIn("does not establish future repayment affordability",
                      findings["FA-03"]["explanation"])

    def test_currency_mismatch_prevents_amount_comparisons(self) -> None:
        result = _assess(context=_context(requested_currency="USD"))
        for rule_id in ("FA-01", "FA-02", "FA-03", "FA-04"):
            self.assertEqual(
                _rule_items(result, "financing_request_assessment", rule_id), []
            )
        self.assertTrue(
            all(
                _rule_items(result, "missing_information", rule_id)
                for rule_id in ("FA-01", "FA-02", "FA-03", "FA-04")
            )
        )

    def test_missing_amount_currency_and_tenure_are_reported(self) -> None:
        context = _context(
            requested_amount=None,
            requested_currency=None,
            financial_currency=None,
            requested_tenure_months=None,
        )
        result = _assess(context=context)
        self.assertTrue(
            _rule_items(result, "missing_information", "FA-01")
        )
        self.assertTrue(
            _rule_items(result, "missing_information", "FT-01")
        )
        self.assertEqual(
            _rule_items(result, "financing_request_assessment", "FA-01"), []
        )

    def test_missing_repayment_terms_and_capacity_are_not_invented(self) -> None:
        result = _assess()
        for rule_id in ("FT-02", "FT-03", "FT-04"):
            self.assertTrue(
                _rule_items(result, "missing_information", rule_id)
            )
        all_text = " ".join(
            finding["title"] + " " + finding["explanation"]
            for finding in _all_findings(result)
        ).casefold()
        self.assertNotIn("affordable", all_text)
        self.assertNotIn("repayment capacity is", all_text)

    def test_missing_obligation_declaration_is_not_zero(self) -> None:
        result = _assess(context=_context())
        declaration = _rule_items(result, "missing_information", "FO-01")[0]
        self.assertIn("does not mean obligations are zero", declaration["explanation"])

    def test_declared_financing_reports_borrower_declared_values_and_gaps(self) -> None:
        result = _assess(context=_context(existing_financing={
            "declared": True,
            "exists": True,
            "outstanding_balance": 500.0,
            "monthly_repayment": 50.0,
            "provider": "Example lender",
            "remaining_tenure_months": 10,
            "verification_status": "borrower_declared",
            "supporting_evidence": None,
        }))
        for rule_id in ("FO-01", "FO-02", "FO-03", "FO-05"):
            self.assertTrue(_rule_items(result, "existing_obligations", rule_id))
        for rule_id in ("FO-02", "FO-03"):
            self.assertEqual(
                _rule_items(result, "existing_obligations", rule_id)[0]["status"],
                "Borrower-declared",
            )

    def test_missing_obligation_balance_and_repayment_are_flagged(self) -> None:
        result = _assess(context=_context(existing_financing={
            "declared": True,
            "exists": True,
            "provider": "Example lender",
            "remaining_tenure_months": 10,
            "verification_status": "borrower_declared",
        }))
        fo04 = _rule_items(result, "missing_information", "FO-04")[0]
        paths = {item["metric_path"] for item in fo04["evidence"]}
        self.assertIn("existing_financing.outstanding_balance", paths)
        self.assertIn("existing_financing.monthly_repayment", paths)

    def test_verified_status_remains_a_supplied_claim_not_engine_verification(self) -> None:
        result = _assess(context=_context(existing_financing={
            "declared": True,
            "exists": True,
            "outstanding_balance": 500.0,
            "monthly_repayment": 50.0,
            "provider": "Example lender",
            "remaining_tenure_months": 10,
            "verification_status": "verified",
            "supporting_evidence": ["declaration.pdf"],
        }))
        verified = _rule_items(result, "existing_obligations", "FO-05")[0]
        self.assertEqual(verified["status"], "Marked as verified")
        self.assertIn("does not authenticate", verified["explanation"])

    def test_invalid_financial_values_are_reported_from_dependency_shapes(self) -> None:
        analysis = _analysis()
        analysis["data_quality"]["missing_or_invalid_financial_values"][
            "invoices"
        ]["amount_columns"]["total_amount"]["non_numeric_or_non_finite"] = 1
        validation = _validation_report()
        validation["invoices"]["non_numeric_amounts"]["total_amount"] = 1
        result = _assess(analysis=analysis, validation=validation)
        finding = _rule_items(result, "data_quality_issues", "DQ-03")[0]
        paths = {item["metric_path"] for item in finding["evidence"]}
        self.assertIn("invoices.non_numeric_amounts.total_amount", paths)
        self.assertFalse(_rule_items(result, "financial_strengths", "FS-03"))

    def test_invoice_total_mismatch_is_reported(self) -> None:
        validation = _validation_report()
        validation["invoices"]["total_mismatch_count"] = 1
        result = _assess(validation=validation)
        finding = _rule_items(result, "data_quality_issues", "DQ-04")[0]
        self.assertEqual(finding["evidence"][0]["value"], 1)
        self.assertEqual(
            finding["evidence"][0]["metric_path"],
            "invoices.total_mismatch_count",
        )

    def test_duplicate_invoice_ids_are_reported(self) -> None:
        validation = _validation_report()
        validation["invoices"]["duplicate_invoice_ids"] = 1
        result = _assess(validation=validation)
        finding = _rule_items(result, "data_quality_issues", "DQ-02")[0]
        self.assertEqual(finding["evidence"][0]["value"], 1)

    def test_ambiguous_and_unmatched_transactions_have_separate_data_quality_rules(self) -> None:
        matching = _matching_result()
        matching["ambiguous_transactions"] = [{"transaction_id": "TX-A"}]
        matching["unmatched_transactions"] = [{"transaction_id": "TX-U"}]
        matching["summary"]["ambiguous_transactions"] = 1
        matching["summary"]["unmatched_transactions"] = 1
        result = _assess(matching=matching)
        self.assertEqual(
            _rule_items(result, "data_quality_issues", "DQ-06")[0]["evidence"][0][
                "value"
            ],
            1,
        )
        self.assertEqual(
            _rule_items(result, "data_quality_issues", "DQ-07")[0]["evidence"][0][
                "value"
            ],
            1,
        )

    def test_missing_purpose_policy_is_configuration_issue(self) -> None:
        result = _assess(policy={})
        finding = _rule_items(result, "data_quality_issues", "DQ-08")[0]
        self.assertEqual(finding["status"], "Configuration missing")

    def test_policy_required_documents_are_compared_with_uploaded_types(self) -> None:
        policy = {
            "purpose_document_requirements": {
                "equipment": ["purchase_quote", "supplier_invoice"],
            }
        }
        result = _assess(
            context=_context(uploaded_documents=["purchase_quote"]),
            policy=policy,
        )
        finding = _rule_items(result, "data_quality_issues", "DQ-08")[0]
        missing_info = _rule_items(result, "missing_information", "FP-01")[0]
        self.assertIn("supplier_invoice", str(finding["evidence"]))
        self.assertIn("supplier_invoice", missing_info["explanation"])

    def test_empty_and_incomplete_inputs_return_safe_structured_results(self) -> None:
        result = generate_financial_insights({}, {}, {}, {})
        self.assertEqual(
            result["decision"],
            {"status": "not_made", "decision_maker": "bank_employee"},
        )
        self.assertIsNone(result["application_id"])
        self.assertTrue(result["missing_information"])
        self.assertTrue(result["limitations"])
        with self.assertRaises(TypeError):
            generate_financial_insights([], {}, {}, {})

    def test_english_and_arabic_keep_same_rule_ids(self) -> None:
        english = _assess(language="en")
        arabic = _assess(language="ar")
        self.assertEqual(english["language"], "en")
        self.assertEqual(arabic["language"], "ar")
        for section in _finding_sections(english):
            english_ids = [item["rule_id"] for item in english[section]]
            arabic_ids = [item["rule_id"] for item in arabic[section]]
            self.assertEqual(english_ids, arabic_ids)
        self.assertNotEqual(
            english["financial_strengths"][0]["title"],
            arabic["financial_strengths"][0]["title"],
        )
        self.assertEqual(english["decision"], arabic["decision"])

    def test_unsupported_language_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "language must be 'en' or 'ar'"):
            _assess(language="fr")

    def test_input_dictionaries_nested_structures_and_dataframes_are_immutable(self) -> None:
        invoices, transactions, validation, matching, analysis = _synthetic_pipeline()
        context = _context(
            applicant_metadata={"tags": ["borrower-provided"], "profile": {"x": 1}},
            supporting_frames={
                "invoices": invoices,
                "transactions": transactions,
            },
        )
        policy = {"purpose_document_requirements": {"equipment": ["quote"]}}
        inputs = {
            "financial_analysis": analysis,
            "matching_result": matching,
            "validation_report": validation,
            "application_context": context,
            "policy": policy,
        }
        snapshots = copy.deepcopy(inputs)
        generate_financial_insights(
            analysis,
            matching,
            validation,
            context,
            policy=policy,
        )
        _assert_nested_unchanged(self, inputs, snapshots)


if __name__ == "__main__":
    unittest.main()
