"""Tests for converting tabular bank statement PDFs to transaction rows."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from modules.data_validator import validate_dataset
from modules.document_extractor import load_bank_transactions_pdf, load_invoices
from modules.financial_analyzer import analyze_financial_data
from modules.invoice_matcher import match_invoices_to_transactions


class BankStatementExtractorTests(TestCase):
    def test_generated_sample_statements_preserve_transaction_rows(self):
        project_root = Path(__file__).resolve().parents[1]
        sample_names = (
            "sample_01_healthy",
            "sample_02_data_issues",
            "sample_03_cashflow",
            "sample_04_growth",
            "sample_05_complex",
        )

        for sample_name in sample_names:
            with self.subTest(sample=sample_name):
                sample_dir = project_root / "sample_data" / sample_name
                transactions = load_bank_transactions_pdf(
                    sample_dir / "bank_statement.pdf"
                )

                self.assertGreater(len(transactions), 0)
                self.assertTrue(
                    transactions["transaction_id"].str.startswith("TXN-").all()
                )
                self.assertEqual(
                    transactions["transaction_id"].nunique(),
                    len(transactions),
                )

    @patch("modules.document_extractor.pdfplumber.open")
    def test_extracts_transactions_from_split_debit_credit_columns(self, open_pdf):
        page = type("Page", (), {
            "extract_tables": lambda self: [[
                ["Transaction Date", "Description", "Debit (SAR)", "Credit (SAR)", "Balance (SAR)"],
                ["2025-01-03", "Invoice INV-1001", "1,200.50", "", "8,799.50"],
                ["2025-01-04", "Customer payment", "", "500.00", "9,299.50"],
            ],
        ]})()
        document = type("Pdf", (), {
            "pages": [page],
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        })()
        open_pdf.return_value = document

        result = load_bank_transactions_pdf(Path("statement.pdf"))

        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]["debit"], 1200.50)
        self.assertEqual(result.iloc[0]["credit"], 0.0)
        self.assertEqual(result.iloc[1]["credit"], 500.0)
        self.assertEqual(result.iloc[0]["transaction_id"], "statement-p1-r1")

    @patch("modules.document_extractor.pdfplumber.open")
    def test_requires_an_explicit_direction_for_single_amount_column(self, open_pdf):
        page = type("Page", (), {
            "extract_tables": lambda self: [[
                ["Date", "Description", "Amount", "Balance"],
                ["2025-01-03", "Invoice INV-1001", "1,200.50", "8,799.50"],
            ],
        ]})()
        document = type("Pdf", (), {
            "pages": [page],
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        })()
        open_pdf.return_value = document

        with self.assertRaisesRegex(ValueError, "No supported transaction table"):
            load_bank_transactions_pdf(Path("statement.pdf"))

    @patch("modules.document_extractor.pdfplumber.open")
    def test_splits_amount_using_explicit_direction_column(self, open_pdf):
        page = type("Page", (), {
            "extract_tables": lambda self: [[
                ["Date", "Description", "Transaction Amount (SAR)",
                 "Transaction Type", "Balance"],
                ["2025-01-03", "Invoice INV-1001", "1,200.50", "DR", "8,799.50"],
                ["2025-01-04", "Customer payment", "500.00", "CR", "9,299.50"],
            ]],
        })()
        document = type("Pdf", (), {
            "pages": [page],
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        })()
        open_pdf.return_value = document

        result = load_bank_transactions_pdf(Path("statement.pdf"))

        self.assertEqual(result.iloc[0]["debit"], 1200.50)
        self.assertEqual(result.iloc[0]["credit"], 0.0)
        self.assertEqual(result.iloc[1]["debit"], 0.0)
        self.assertEqual(result.iloc[1]["credit"], 500.0)

    @patch("modules.document_extractor.pdfplumber.open")
    def test_rejects_unreadable_transaction_amounts(self, open_pdf):
        page = type("Page", (), {
            "extract_tables": lambda self: [[
                ["Date", "Description", "Debit", "Credit", "Balance"],
                ["2025-01-03", "Invoice INV-1001", "unknown", "", "8,799.50"],
            ],
        ]})()
        document = type("Pdf", (), {
            "pages": [page],
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        })()
        open_pdf.return_value = document

        with self.assertRaisesRegex(ValueError, "unreadable amount"):
            load_bank_transactions_pdf(Path("statement.pdf"))

    @patch("modules.document_extractor.pdfplumber.open")
    def test_pdf_transactions_feed_existing_validation_and_analysis(self, open_pdf):
        page = type("Page", (), {
            "extract_tables": lambda self: [[
                ["Transaction ID", "Date", "Description", "Debit", "Credit", "Balance"],
                ["T-1", "2025-01-07", "Payment INV-1001", "", "22187.89", "172187.89"],
            ]],
        })()
        document = type("Pdf", (), {
            "pages": [page],
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        })()
        open_pdf.return_value = document
        invoices = load_invoices(
            Path(__file__).resolve().parents[1]
            / "sample_data"
            / "sample_01_healthy"
            / "invoices.xlsx"
        )

        transactions = load_bank_transactions_pdf(Path("statement.pdf"))
        validation = validate_dataset({
            "invoices": invoices,
            "bank_transactions": transactions,
        })
        matching = match_invoices_to_transactions(invoices, transactions)
        analysis = analyze_financial_data(invoices, transactions, matching)

        self.assertTrue(validation["summary"]["is_valid"])
        self.assertEqual(len(transactions), 1)
        self.assertEqual(analysis["cash_flow"]["total_incoming_cash"], 22187.89)
