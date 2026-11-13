"""Scenario tests for real datasets and financing assessment cases."""

from __future__ import annotations

import copy
import unittest
from pathlib import Path
from typing import Any

import pandas as pd

from modules.ai_insights import generate_financial_insights
from modules.data_validator import validate_dataset
from modules.document_extractor import (
    load_bank_transactions_pdf,
    load_company_profile,
    load_invoices,
)
from modules.financial_analyzer import analyze_financial_data
from modules.invoice_matcher import match_invoices_to_transactions


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_NAMES = (
    "sample_01_healthy",
    "sample_02_data_issues",
    "sample_03_cashflow",
    "sample_04_growth",
    "sample_05_complex",
)
_TOP_LEVEL_KEYS = {
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
}
_DECISION = {"status": "not_made", "decision_maker": "bank_employee"}
_FINDING_SECTIONS = (
    "financial_strengths",
    "potential_risks",
    "financing_request_assessment",
    "existing_obligations",
    "data_quality_issues",
    "missing_information",
    "recommended_actions",
    "limitations",
)


def _base_analysis() -> dict[str, Any]:
    """Create coherent, controlled input using the analyzer's output paths."""
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
            "monthly_net_cash_flow": [{"month": "2025-12", "amount": 30.0}],
        },
        "unclassified_transactions": {
            "unmatched_transaction_count": 0,
            "unmatched_positive_credit_total": 0.0,
            "unmatched_positive_debit_total": 0.0,
            "ambiguous_transaction_count": 0,
            "ambiguous_positive_credit_total": 0.0,
            "ambiguous_positive_debit_total": 0.0,
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
                    "missing_balance": 0,
                    "non_numeric_or_non_finite_balance": 0,
                    "negative_balance": 0,
                },
            },
        },
    }


def _base_matching() -> dict[str, Any]:
    return {
        "invoice_matches": [
            {
                "invoice_id": "INV-1",
                "invoice_total": 100.0,
                "total_collected": 100.0,
                "outstanding_amount": 0.0,
                "collection_status": "fully_collected",
                "matched_transaction_ids": ["TX-1"],
                "payment_status_discrepancy": False,
            }
        ],
        "unmatched_transactions": [],
        "ambiguous_transactions": [],
        "non_payment_transactions": [],
        "summary": {
            "ambiguous_transactions": 0,
            "unmatched_transactions": 0,
            "payment_status_discrepancies": 0,
        },
    }


def _base_validation() -> dict[str, Any]:
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


def _base_context(**overrides: Any) -> dict[str, Any]:
    context: dict[str, Any] = {
        "application_id": "SCENARIO-1",
        "requested_amount": 250_000.0,
        "requested_currency": "SAR",
        "financial_currency": "SAR",
        "requested_tenure_months": 24,
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
        _base_analysis() if analysis is None else analysis,
        _base_matching() if matching is None else matching,
        _base_validation() if validation is None else validation,
        _base_context() if context is None else context,
        language=language,
        policy=(
            {"purpose_document_requirements": {"equipment": []}}
            if policy is None else policy
        ),
    )


def _rules(result: dict[str, Any], section: str) -> set[str]:
    return {item["rule_id"] for item in result[section]}


def _items(result: dict[str, Any], section: str, rule_id: str) -> list[dict[str, Any]]:
    return [item for item in result[section] if item["rule_id"] == rule_id]


def _all_rule_ids(result: dict[str, Any]) -> set[str]:
    return {
        finding["rule_id"]
        for section in _FINDING_SECTIONS
        for finding in result[section]
    }


def _assert_output_contract(case: unittest.TestCase, result: dict[str, Any]) -> None:
    case.assertEqual(set(result), _TOP_LEVEL_KEYS)
    case.assertEqual(result["assessment_type"], "rule_based")
    case.assertEqual(result["decision"], _DECISION)
    case.assertTrue(result["rule_set_version"])
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
    for section in _FINDING_SECTIONS:
        for finding in result[section]:
            case.assertTrue(required_fields.issubset(finding))
            case.assertIsInstance(finding["evidence"], list)
            for item in finding["evidence"]:
                case.assertTrue({"source", "metric_path", "value"}.issubset(item))


def _periods_are_consecutive(months: list[str]) -> bool:
    if len(months) < 2:
        return False
    try:
        positions = []
        for month in months:
            year, month_number = (int(value) for value in month.split("-"))
            positions.append(year * 12 + month_number)
    except (AttributeError, TypeError, ValueError):
        return False
    return all(right - left == 1 for left, right in zip(positions, positions[1:]))


class RealSampleDatasetScenarios(unittest.TestCase):
    def test_all_five_real_sample_datasets(self) -> None:
        observed_names = {
            child.name
            for child in (_PROJECT_ROOT / "sample_data").iterdir()
            if child.is_dir()
        }
        self.assertEqual(observed_names, set(_SAMPLE_NAMES))

        for sample_name in _SAMPLE_NAMES:
            with self.subTest(dataset=sample_name):
                directory = _PROJECT_ROOT / "sample_data" / sample_name
                self.assertTrue((directory / "invoices.xlsx").is_file())
                self.assertTrue((directory / "bank_statement.pdf").is_file())
                self.assertFalse((directory / "bank_transactions.xlsx").exists())
                profile = load_company_profile(directory / "company_profile.json")
                invoices = load_invoices(directory / "invoices.xlsx")
                transactions = load_bank_transactions_pdf(
                    directory / "bank_statement.pdf"
                )
                invoices_before = invoices.copy(deep=True)
                transactions_before = transactions.copy(deep=True)
                profile_before = copy.deepcopy(profile)

                validation = validate_dataset({
                    "invoices": invoices,
                    "bank_transactions": transactions,
                })
                matching = match_invoices_to_transactions(invoices, transactions)
                analysis = analyze_financial_data(
                    invoices, transactions, matching
                )
                context = {
                    "application_id": sample_name,
                    "requested_currency": profile["currency"],
                    "financial_currency": profile["currency"],
                }
                result = generate_financial_insights(
                    analysis,
                    matching,
                    validation,
                    context,
                )

                _assert_output_contract(self, result)
                self.assertEqual(result["application_id"], sample_name)
                self.assertEqual(result["language"], "en")
                self.assertEqual(
                    validation["summary"]["is_valid"],
                    sample_name != "sample_02_data_issues",
                )
                self.assertEqual(
                    validation["summary"]["error_count"] > 0,
                    sample_name == "sample_02_data_issues",
                )
                invoice_report = validation["invoices"]
                bank_report = validation["bank_transactions"]
                data_quality_rules = _rules(result, "data_quality_issues")
                if invoice_report["duplicate_invoice_ids"] > 0:
                    self.assertIn("DQ-02", data_quality_rules)
                if invoice_report["total_mismatch_count"] > 0:
                    self.assertIn("DQ-04", data_quality_rules)
                invalid_invoice_values = any(
                    count > 0
                    for counter in (
                        invoice_report["non_numeric_amounts"],
                        invoice_report["negative_amounts"],
                    )
                    for count in counter.values()
                )
                invalid_bank_values = any(
                    count > 0
                    for counter in (
                        bank_report["non_numeric_values"],
                        bank_report["negative_values"],
                    )
                    for count in counter.values()
                )
                if invalid_invoice_values or invalid_bank_values:
                    self.assertIn("DQ-03", data_quality_rules)
                has_missing_validation_fields = any(
                    report["missing_columns"]
                    or any(value > 0 for value in report["missing_values"].values())
                    for report in (invoice_report, bank_report)
                )
                if has_missing_validation_fields:
                    self.assertIn("DQ-01", data_quality_rules)

                if sample_name == "sample_03_cashflow":
                    net_cash = analysis["cash_flow"]["net_cash_flow"]
                    if net_cash > 0:
                        self.assertIn("FS-02", _rules(result, "financial_strengths"))
                        self.assertNotIn("FR-02", _rules(result, "potential_risks"))
                    elif net_cash < 0:
                        self.assertIn("FR-02", _rules(result, "potential_risks"))
                        self.assertNotIn("FS-02", _rules(result, "financial_strengths"))
                    else:
                        self.assertNotIn("FS-02", _rules(result, "financial_strengths"))
                        self.assertNotIn("FR-02", _rules(result, "potential_risks"))
                    if analysis["receivables"]["outstanding_receivables"] > 0:
                        self.assertIn("FR-03", _rules(result, "potential_risks"))
                        self.assertIn(
                            "no aging",
                            _items(result, "potential_risks", "FR-03")[0][
                                "explanation"
                            ].casefold(),
                        )

                if sample_name == "sample_04_growth":
                    trend = analysis["sales"]["monthly_sales_trend"]
                    eligible = (
                        len(trend) >= 2
                        and _periods_are_consecutive(
                            [trend[-2]["month"], trend[-1]["month"]]
                        )
                        and trend[-1]["change_from_previous_month"] is not None
                    )
                    change = (
                        trend[-1]["change_from_previous_month"]
                        if eligible else None
                    )
                    expected_rule = (
                        "FS-01" if change is not None and change > 0
                        else "FR-01" if change is not None and change < 0
                        else None
                    )
                    observed_growth_rules = (
                        _rules(result, "financial_strengths") & {"FS-01"}
                    )
                    observed_decline_rules = (
                        _rules(result, "potential_risks") & {"FR-01"}
                    )
                    self.assertEqual(
                        bool(observed_growth_rules),
                        expected_rule == "FS-01",
                    )
                    self.assertEqual(
                        bool(observed_decline_rules),
                        expected_rule == "FR-01",
                    )

                if sample_name == "sample_05_complex":
                    matched_total = sum(
                        record["total_collected"]
                        for record in matching["invoice_matches"]
                    )
                    self.assertEqual(
                        analysis["collections"]["total_confirmed_collections"],
                        round(matched_total, 2),
                    )
                    if matching["unmatched_transactions"]:
                        self.assertIn("DQ-07", _rules(result, "data_quality_issues"))
                    if matching["ambiguous_transactions"]:
                        self.assertIn("DQ-06", _rules(result, "data_quality_issues"))
                    self.assertEqual(
                        result["decision"],
                        _DECISION,
                    )

                # All sample applications omit requested terms and capacity.
                self.assertTrue(_items(result, "missing_information", "FA-01"))
                self.assertTrue(_items(result, "missing_information", "FT-01"))
                self.assertTrue(_items(result, "missing_information", "FT-04"))
                self.assertNotIn(
                    "FA-01",
                    _rules(result, "financing_request_assessment"),
                )
                self.assertTrue(
                    any(
                        item["rule_id"] == "LIMIT-01"
                        and "not calculated" in item["explanation"].casefold()
                        for item in result["limitations"]
                    )
                )
                for receivables_finding in _items(
                    result, "potential_risks", "FR-03"
                ):
                    self.assertIn(
                        "no aging",
                        receivables_finding["explanation"].casefold(),
                    )
                self.assertEqual(result["decision"], _DECISION)
                self.assertEqual(profile, profile_before)
                pd.testing.assert_frame_equal(invoices, invoices_before)
                pd.testing.assert_frame_equal(transactions, transactions_before)

    def test_sample_05_confirmed_collections_exclude_unmatched_and_ambiguous(self) -> None:
        directory = _PROJECT_ROOT / "sample_data" / "sample_05_complex"
        profile = load_company_profile(directory / "company_profile.json")
        invoices = load_invoices(directory / "invoices.xlsx")
        transactions = load_bank_transactions_pdf(
            directory / "bank_statement.pdf"
        )
        validation = validate_dataset({
            "invoices": invoices,
            "bank_transactions": transactions,
        })
        matching = match_invoices_to_transactions(invoices, transactions)
        analysis = analyze_financial_data(invoices, transactions, matching)
        result = generate_financial_insights(
            analysis,
            matching,
            validation,
            {
                "application_id": "sample_05_complex",
                "requested_amount": 250_000,
                "requested_currency": profile["currency"],
                "financial_currency": profile["currency"],
            },
        )
        fa02 = _items(result, "financing_request_assessment", "FA-02")
        if fa02:
            evidence_values = [item["value"] for item in fa02[0]["evidence"]]
            self.assertNotIn(
                analysis["unclassified_transactions"][
                    "unmatched_positive_credit_total"
                ],
                evidence_values,
            )
            self.assertNotIn(
                analysis["unclassified_transactions"][
                    "ambiguous_positive_credit_total"
                ],
                evidence_values,
            )
        self.assertEqual(
            analysis["collections"]["total_confirmed_collections"],
            round(sum(row["total_collected"] for row in matching["invoice_matches"]), 2),
        )


class FinancingApplicationScenarios(unittest.TestCase):
    def test_a_complete_financing_request(self) -> None:
        context = _base_context(
            requested_amount=250_000,
            requested_currency="SAR",
            financial_currency="SAR",
            requested_tenure_months=24,
            financing_purpose_code="equipment",
            repayment_schedule={"frequency": "monthly"},
            repayment_capacity={
                "amount": 12_000,
                "currency": "SAR",
                "measurement_period": "monthly",
                "verification_status": "borrower_declared",
                "source": "Applicant declaration",
            },
            existing_financing={
                "declared": True,
                "exists": True,
                "outstanding_balance": 80_000,
                "monthly_repayment": 4_000,
                "provider": "Declared lender",
                "remaining_tenure_months": 18,
                "verification_status": "borrower_declared",
            },
        )
        result = _assess(context=context)
        request_rules = _rules(result, "financing_request_assessment")
        self.assertTrue({"FA-01", "FA-02", "FA-03", "FA-04", "FT-01", "FT-02", "FT-04"} <= request_rules)
        self.assertTrue(_items(result, "missing_information", "FT-03"))
        self.assertEqual(
            _items(result, "existing_obligations", "FO-02")[0]["status"],
            "Borrower-declared",
        )
        self.assertEqual(
            _items(result, "existing_obligations", "FO-03")[0]["status"],
            "Borrower-declared",
        )
        capacity_finding = _items(
            result, "financing_request_assessment", "FT-04"
        )[0]
        self.assertIn("does not establish affordability",
                      capacity_finding["explanation"].casefold())
        self.assertIn(
            "no installment or dscr is calculated",
            next(
                item["explanation"].casefold()
                for item in result["limitations"]
                if item["rule_id"] == "LIMIT-03"
            ),
        )

    def test_b_missing_requested_amount(self) -> None:
        result = _assess(context=_base_context(requested_amount=None))
        self.assertTrue(_items(result, "missing_information", "FA-01"))
        self.assertNotIn("FA-01", _rules(result, "financing_request_assessment"))

    def test_c_missing_requested_currency(self) -> None:
        result = _assess(context=_base_context(requested_currency=None))
        self.assertTrue(_items(result, "missing_information", "FA-01"))
        self.assertNotIn("FA-01", _rules(result, "financing_request_assessment"))

    def test_d_requested_currency_differs_from_financial_currency(self) -> None:
        result = _assess(
            context=_base_context(requested_currency="USD", financial_currency="SAR")
        )
        for rule_id in ("FA-01", "FA-02", "FA-03", "FA-04"):
            self.assertTrue(_items(result, "missing_information", rule_id))
            self.assertNotIn(rule_id, _rules(result, "financing_request_assessment"))

    def test_e_missing_requested_tenure(self) -> None:
        result = _assess(context=_base_context(requested_tenure_months=None))
        self.assertTrue(_items(result, "missing_information", "FT-01"))
        self.assertNotIn("FT-01", _rules(result, "financing_request_assessment"))

    def test_f_missing_repayment_schedule(self) -> None:
        result = _assess(context=_base_context(repayment_schedule=None))
        self.assertTrue(_items(result, "missing_information", "FT-02"))

    def test_g_missing_financing_cost(self) -> None:
        result = _assess(context=_base_context(financing_cost=None))
        self.assertTrue(_items(result, "missing_information", "FT-03"))

    def test_h_missing_repayment_capacity(self) -> None:
        result = _assess(context=_base_context(repayment_capacity=None))
        self.assertTrue(_items(result, "missing_information", "FT-04"))
        self.assertIn(
            "historical cash flow alone is insufficient",
            _items(result, "missing_information", "FT-04")[0][
                "recommended_action"
            ],
        )

    def test_i_existing_financing_declared_as_none(self) -> None:
        result = _assess(context=_base_context(existing_financing={
            "declared": True,
            "exists": False,
            "verification_status": "borrower_declared",
        }))
        self.assertTrue(_items(result, "existing_obligations", "FO-01"))
        self.assertEqual(
            _items(result, "existing_obligations", "FO-02")[0]["status"],
            "Not applicable based on declaration",
        )
        self.assertNotIn("FO-02", _rules(result, "missing_information"))

    def test_j_existing_financing_missing_outstanding_balance(self) -> None:
        result = _assess(context=_base_context(existing_financing={
            "declared": True,
            "exists": True,
            "monthly_repayment": 4_000,
            "provider": "Declared lender",
            "remaining_tenure_months": 18,
            "verification_status": "borrower_declared",
        }))
        fo04 = _items(result, "missing_information", "FO-04")[0]
        self.assertIn(
            "existing_financing.outstanding_balance",
            {item["metric_path"] for item in fo04["evidence"]},
        )

    def test_k_existing_financing_missing_monthly_repayment(self) -> None:
        result = _assess(context=_base_context(existing_financing={
            "declared": True,
            "exists": True,
            "outstanding_balance": 80_000,
            "provider": "Declared lender",
            "remaining_tenure_months": 18,
            "verification_status": "borrower_declared",
        }))
        fo04 = _items(result, "missing_information", "FO-04")[0]
        self.assertIn(
            "existing_financing.monthly_repayment",
            {item["metric_path"] for item in fo04["evidence"]},
        )

    def test_l_borrower_declared_information_is_not_verified(self) -> None:
        result = _assess(context=_base_context(existing_financing={
            "declared": True,
            "exists": True,
            "outstanding_balance": 80_000,
            "monthly_repayment": 4_000,
            "provider": "Declared lender",
            "remaining_tenure_months": 18,
            "verification_status": "borrower_declared",
        }))
        for rule_id in ("FO-02", "FO-03", "FO-05"):
            self.assertEqual(
                _items(result, "existing_obligations", rule_id)[0]["status"],
                "Borrower-declared",
            )

    def test_m_missing_existing_financing_declaration_is_not_zero(self) -> None:
        result = _assess(context=_base_context())
        finding = _items(result, "missing_information", "FO-01")[0]
        self.assertIn("does not mean obligations are zero", finding["explanation"])


class PurposeDocumentPolicyScenarios(unittest.TestCase):
    def test_required_purpose_document_is_uploaded(self) -> None:
        result = _assess(
            context=_base_context(
                uploaded_documents=[{"document_type": "purchase_order"}]
            ),
            policy={
                "purpose_document_requirements": {
                    "equipment": ["purchase_order"],
                }
            },
        )
        self.assertNotIn("DQ-08", _rules(result, "data_quality_issues"))
        self.assertNotIn("FP-01", _rules(result, "missing_information"))
        self.assertIn("FP-01", _rules(result, "financing_request_assessment"))

    def test_required_purpose_document_is_missing(self) -> None:
        result = _assess(
            context=_base_context(uploaded_documents=[]),
            policy={
                "purpose_document_requirements": {
                    "equipment": ["purchase_order"],
                }
            },
        )
        self.assertIn("DQ-08", _rules(result, "data_quality_issues"))
        self.assertIn("FP-01", _rules(result, "missing_information"))

    def test_policy_configuration_is_missing(self) -> None:
        result = _assess(policy={})
        self.assertEqual(
            _items(result, "data_quality_issues", "DQ-08")[0]["status"],
            "Configuration missing",
        )
        self.assertIn("FP-01", _rules(result, "missing_information"))

    def test_purpose_code_is_missing(self) -> None:
        result = _assess(
            context=_base_context(financing_purpose_code=None),
            policy={
                "purpose_document_requirements": {
                    "equipment": ["purchase_order"],
                }
            },
        )
        self.assertEqual(
            _items(result, "data_quality_issues", "DQ-08")[0]["status"],
            "Configuration missing",
        )

    def test_uploaded_document_types_must_match_policy(self) -> None:
        result = _assess(
            context=_base_context(uploaded_documents=["supplier_invoice"]),
            policy={
                "purpose_document_requirements": {
                    "equipment": ["purchase_order"],
                }
            },
        )
        self.assertIn("DQ-08", _rules(result, "data_quality_issues"))
        self.assertIn(
            "purchase_order",
            str(_items(result, "data_quality_issues", "DQ-08")[0]["evidence"]),
        )


class FinancialEdgeCaseScenarios(unittest.TestCase):
    def test_positive_net_cash_flow(self) -> None:
        result = _assess()
        self.assertIn("FS-02", _rules(result, "financial_strengths"))
        self.assertNotIn("FR-02", _rules(result, "potential_risks"))

    def test_negative_net_cash_flow(self) -> None:
        analysis = _base_analysis()
        analysis["cash_flow"]["net_cash_flow"] = -1.0
        result = _assess(analysis=analysis)
        self.assertIn("FR-02", _rules(result, "potential_risks"))
        self.assertNotIn("FS-02", _rules(result, "financial_strengths"))

    def test_zero_net_cash_flow_is_neither_positive_nor_negative(self) -> None:
        analysis = _base_analysis()
        analysis["cash_flow"]["net_cash_flow"] = 0.0
        result = _assess(analysis=analysis)
        self.assertNotIn("FS-02", _rules(result, "financial_strengths"))
        self.assertNotIn("FR-02", _rules(result, "potential_risks"))

    def test_unmatched_positive_credits_remain_unconfirmed(self) -> None:
        analysis = _base_analysis()
        analysis["unclassified_transactions"]["unmatched_positive_credit_total"] = 900.0
        matching = _base_matching()
        matching["unmatched_transactions"] = [{"transaction_row": 0}]
        matching["summary"]["unmatched_transactions"] = 1
        result = _assess(analysis=analysis, matching=matching)
        self.assertIn("FR-04", _rules(result, "potential_risks"))
        fa02 = _items(result, "financing_request_assessment", "FA-02")[0]
        values = [item["value"] for item in fa02["evidence"]]
        self.assertIn(100.0, values)
        self.assertNotIn(900.0, values)

    def test_ambiguous_transactions_are_not_confirmed(self) -> None:
        analysis = _base_analysis()
        analysis["unclassified_transactions"]["ambiguous_positive_credit_total"] = 600.0
        matching = _base_matching()
        matching["ambiguous_transactions"] = [{"transaction_row": 1}]
        matching["summary"]["ambiguous_transactions"] = 1
        result = _assess(analysis=analysis, matching=matching)
        self.assertIn("FR-05", _rules(result, "potential_risks"))
        self.assertIn("DQ-06", _rules(result, "data_quality_issues"))
        fa02 = _items(result, "financing_request_assessment", "FA-02")[0]
        self.assertNotIn(
            600.0,
            [item["value"] for item in fa02["evidence"]],
        )

    def test_payment_status_discrepancy(self) -> None:
        analysis = _base_analysis()
        analysis["data_quality"]["payment_status_discrepancies"] = 1
        matching = _base_matching()
        matching["summary"]["payment_status_discrepancies"] = 1
        result = _assess(analysis=analysis, matching=matching)
        self.assertIn("FR-06", _rules(result, "potential_risks"))
        self.assertIn("DQ-05", _rules(result, "data_quality_issues"))

    def test_outstanding_receivables_are_not_overdue_without_due_dates(self) -> None:
        result = _assess()
        finding = _items(result, "potential_risks", "FR-03")[0]
        text = " ".join(
            (
                finding["title"],
                finding["explanation"],
                finding["recommended_action"],
            )
        ).casefold()
        self.assertIn("outstanding", text)
        self.assertNotIn("overdue", finding["title"].casefold())
        self.assertNotIn("days past due", text)
        self.assertTrue(
            any(item["rule_id"] == "LIMIT-01" for item in result["limitations"])
        )

    def test_invalid_financial_values(self) -> None:
        analysis = _base_analysis()
        analysis["data_quality"]["missing_or_invalid_financial_values"][
            "invoices"
        ]["amount_columns"]["total_amount"]["non_numeric_or_non_finite"] = 1
        validation = _base_validation()
        validation["invoices"]["non_numeric_amounts"]["total_amount"] = 1
        result = _assess(analysis=analysis, validation=validation)
        self.assertIn("DQ-03", _rules(result, "data_quality_issues"))
        self.assertNotIn("FS-03", _rules(result, "financial_strengths"))

    def test_missing_financial_values_are_reported_as_missing_required_fields(self) -> None:
        analysis = _base_analysis()
        analysis["data_quality"]["missing_or_invalid_financial_values"][
            "invoices"
        ]["amount_columns"]["total_amount"]["missing"] = 1
        validation = _base_validation()
        validation["invoices"]["missing_values"]["total_amount"] = 1
        result = _assess(analysis=analysis, validation=validation)
        self.assertIn("DQ-01", _rules(result, "data_quality_issues"))
        self.assertNotIn("FS-03", _rules(result, "financial_strengths"))

    def test_invoice_total_mismatch(self) -> None:
        validation = _base_validation()
        validation["invoices"]["total_mismatch_count"] = 1
        result = _assess(validation=validation)
        self.assertIn("DQ-04", _rules(result, "data_quality_issues"))

    def test_currency_mismatch_prevents_financial_request_comparisons(self) -> None:
        result = _assess(
            context=_base_context(
                requested_currency="USD",
                financial_currency="SAR",
            )
        )
        for rule_id in ("FA-01", "FA-02", "FA-03", "FA-04"):
            self.assertNotIn(
                rule_id,
                _rules(result, "financing_request_assessment"),
            )
            self.assertIn(rule_id, _rules(result, "missing_information"))

    def test_no_dscr_overdue_aging_or_unsupported_affordability_conclusion(self) -> None:
        result = _assess()
        self.assertEqual(result["decision"], _DECISION)
        limit_ids = {item["rule_id"] for item in result["limitations"]}
        self.assertIn("LIMIT-01", limit_ids)
        self.assertIn("LIMIT-02", limit_ids)
        self.assertIn("LIMIT-03", limit_ids)
        fa03 = _items(result, "financing_request_assessment", "FA-03")[0]
        self.assertIn(
            "does not establish future repayment affordability",
            fa03["explanation"].casefold(),
        )


class BilingualScenarioConsistency(unittest.TestCase):
    def test_english_and_arabic_preserve_rule_ids_and_numeric_evidence(self) -> None:
        context = _base_context(
            existing_financing={
                "declared": True,
                "exists": True,
                "outstanding_balance": 80_000,
                "monthly_repayment": 4_000,
                "provider": "Applicant lender",
                "remaining_tenure_months": 18,
                "verification_status": "borrower_declared",
            },
            financing_cost=None,
        )
        policy = {
            "purpose_document_requirements": {
                "equipment": ["purchase_order"],
            }
        }
        english = _assess(
            context=context,
            policy=policy,
            language="en",
        )
        arabic = _assess(
            context=context,
            policy=policy,
            language="ar",
        )
        _assert_output_contract(self, english)
        _assert_output_contract(self, arabic)
        self.assertEqual(english["language"], "en")
        self.assertEqual(arabic["language"], "ar")
        self.assertEqual(english["decision"], _DECISION)
        self.assertEqual(arabic["decision"], _DECISION)
        self.assertEqual(_all_rule_ids(english), _all_rule_ids(arabic))
        for section in _FINDING_SECTIONS:
            english_items = english[section]
            arabic_items = arabic[section]
            self.assertEqual(
                [item["rule_id"] for item in english_items],
                [item["rule_id"] for item in arabic_items],
            )
            for english_item, arabic_item in zip(english_items, arabic_items):
                english_numbers = [
                    (item["metric_path"], item["value"])
                    for item in english_item["evidence"]
                    if isinstance(item.get("value"), (int, float))
                    and not isinstance(item.get("value"), bool)
                ]
                arabic_numbers = [
                    (item["metric_path"], item["value"])
                    for item in arabic_item["evidence"]
                    if isinstance(item.get("value"), (int, float))
                    and not isinstance(item.get("value"), bool)
                ]
                self.assertEqual(english_numbers, arabic_numbers)
        english_fs01 = _items(english, "financial_strengths", "FS-01")[0]
        arabic_fs01 = _items(arabic, "financial_strengths", "FS-01")[0]
        self.assertNotEqual(english_fs01["title"], arabic_fs01["title"])
        self.assertNotEqual(english_fs01["explanation"], arabic_fs01["explanation"])
        self.assertNotEqual(
            english_fs01["recommended_action"],
            arabic_fs01["recommended_action"],
        )


if __name__ == "__main__":
    unittest.main()
