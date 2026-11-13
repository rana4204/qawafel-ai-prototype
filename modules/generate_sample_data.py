
import json
import random
from pathlib import Path
from datetime import date, timedelta

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from xml.sax.saxutils import escape


# ==========================================
# 1. PROJECT CONFIGURATION
# ==========================================

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_DIR / "sample_data"

random.seed(42)

VAT_RATE = 0.15
START_DATE = date(2025, 1, 1)

CUSTOMERS = [
    "Demo Customer A",
    "Demo Customer B",
    "Demo Customer C",
    "Demo Customer D",
    "Demo Customer E",
    "Demo Customer F",
]

SCENARIOS = {
    "sample_01_healthy": {
        "company_name": "Synthetic Test Company Alpha",
        "test_record_id": "001",
        "industry": "Wholesale Trading",
        "description": "Synthetic test scenario: healthy, consistent financial records.",
        "monthly_revenue": 90000,
        "issue": "none"
    },
    "sample_02_data_issues": {
        "company_name": "Synthetic Test Company Beta",
        "test_record_id": "002",
        "industry": "Retail Supplies",
        "description": "Synthetic test scenario: incomplete and inconsistent records.",
        "monthly_revenue": 75000,
        "issue": "data_issues"
    },
    "sample_03_cashflow": {
        "company_name": "Synthetic Test Company Gamma",
        "test_record_id": "003",
        "industry": "Retail",
        "description": "Synthetic test scenario: collection and cash-flow challenges.",
        "monthly_revenue": 100000,
        "issue": "cashflow"
    },
    "sample_04_growth": {
        "company_name": "Synthetic Test Company Delta",
        "test_record_id": "004",
        "industry": "Retail and Distribution",
        "description": "Synthetic test scenario: increasing monthly revenue.",
        "monthly_revenue": 70000,
        "issue": "growth"
    },
    "sample_05_complex": {
        "company_name": "Synthetic Test Company Epsilon",
        "test_record_id": "005",
        "industry": "Distribution",
        "description": "Synthetic test scenario: partial payments and complex transactions.",
        "monthly_revenue": 110000,
        "issue": "complex"
    }
}


# ==========================================
# 2. COMPANY PROFILE GENERATOR
# ==========================================

def generate_company_profile(config):

    return {
        "company_name": config["company_name"],
        "cr_number": f"TEST-CR-{config['test_record_id']}",
        "data_classification": "Synthetic test data only; no real company or bank records.",
        "industry": config["industry"],
        "city": "Riyadh",
        "country": "Saudi Arabia",
        "establishment_date": "2019-03-15",
        "currency": "SAR",
        "vat_rate": VAT_RATE,
        "description": config["description"]
    }


# ==========================================
# 3. INVOICE GENERATOR
# ==========================================

def generate_invoices(config):

    invoices = []
    issue = config["issue"]
    invoice_number = 1001

    for month in range(12):

        month_start = (
            START_DATE + pd.DateOffset(months=month)
        ).date()

        # Growth scenario: revenue increases over time
        if issue == "growth":
            revenue_factor = 1 + (month * 0.08)
        else:
            revenue_factor = 1

        monthly_target = (
            config["monthly_revenue"] * revenue_factor
        )

        for index in range(4):

            invoice_date = (
                month_start + timedelta(days=index * 5 + 2)
            )

            net_amount = round(
                monthly_target / 4 * random.uniform(0.85, 1.15),
                2
            )

            vat_amount = round(net_amount * VAT_RATE, 2)
            total_amount = round(net_amount + vat_amount, 2)

            status = "Paid"

            if issue == "cashflow" and index >= 2:
                status = "Overdue"

            elif issue == "complex" and index == 3:
                status = "Partially Paid"

            elif issue == "data_issues" and index == 2:
                status = "Pending"

            invoice = {
                "invoice_id": f"INV-{invoice_number}",
                "invoice_date": invoice_date.isoformat(),
                "customer_name": random.choice(CUSTOMERS),
                "net_amount": net_amount,
                "vat_amount": vat_amount,
                "total_amount": total_amount,
                "payment_status": status
            }

            # Intentional missing customer name
            if issue == "data_issues" and invoice_number == 1003:
                invoice["customer_name"] = None

            invoices.append(invoice)
            invoice_number += 1

    # Intentional duplicate invoice
    if issue == "data_issues":
        duplicate = invoices[5].copy()
        invoices.append(duplicate)

    return pd.DataFrame(invoices)


# ==========================================
# 4. BANK TRANSACTION GENERATOR
# ==========================================

def generate_bank_transactions(invoices, issue):

    transactions = []
    transaction_number = 1

    for _, invoice in invoices.iterrows():

        status = invoice["payment_status"]

        if status == "Overdue":
            continue

        invoice_date = date.fromisoformat(
            invoice["invoice_date"]
        )

        payment_date = invoice_date + timedelta(
            days=random.randint(2, 15)
        )

        amount = invoice["total_amount"]

        # Partial payment
        if status == "Partially Paid":
            amount = round(amount * 0.5, 2)

        # Another partial payment for the complex case
        if (
            issue == "complex"
            and invoice["invoice_id"] == "INV-1002"
        ):
            amount = round(amount * 0.75, 2)

        transactions.append({
            "transaction_id": f"TXN-{transaction_number:04d}",
            "transaction_date": payment_date.isoformat(),
            "description": f"Payment for {invoice['invoice_id']}",
            "debit": 0,
            "credit": amount
        })

        transaction_number += 1

    # Unmatched transaction
    if issue in ["data_issues", "complex"]:
        transactions.append({
            "transaction_id": f"TXN-{transaction_number:04d}",
            "transaction_date": "2025-08-20",
            "description": "Unknown incoming transfer",
            "debit": 0,
            "credit": 12500
        })

        transaction_number += 1

    # Monthly operating expenses
    for month in range(12):

        expense_date = (
            START_DATE + pd.DateOffset(months=month)
        ).date() + timedelta(days=25)

        if issue == "cashflow":
            expense = random.randint(18000, 25000)
        else:
            expense = random.randint(5000, 10000)

        transactions.append({
            "transaction_id": f"TXN-{transaction_number:04d}",
            "transaction_date": expense_date.isoformat(),
            "description": "Monthly operating expenses",
            "debit": expense,
            "credit": 0
        })

        transaction_number += 1

    # Multiple payments for complex scenario
    if issue == "complex":
        transactions.append({
            "transaction_id": f"TXN-{transaction_number:04d}",
            "transaction_date": "2025-09-15",
            "description": "Additional customer payment",
            "debit": 0,
            "credit": 8500
        })

    # Sort and calculate running balance
    transactions.sort(
        key=lambda transaction: transaction["transaction_date"]
    )

    balance = 150000

    for transaction in transactions:

        balance += transaction["credit"]
        balance -= transaction["debit"]

        transaction["balance"] = round(balance, 2)

    return pd.DataFrame(transactions)


def _draw_synthetic_footer(canvas, document):
    """Mark every generated page as synthetic test data."""
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#9B1C1C"))
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawCentredString(
        landscape(A4)[0] / 2,
        6 * mm,
        "SYNTHETIC TEST DATA - NOT A REAL BANK RECORD",
    )
    canvas.restoreState()


def save_bank_statement_pdf(profile, transactions, output_path):
    """Write generated transactions as a selectable-text bank statement."""
    statement_dates = pd.to_datetime(transactions["transaction_date"])
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="StatementTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#5A4228"),
        fontSize=17,
        leading=21,
        spaceAfter=5 * mm,
    ))
    styles.add(ParagraphStyle(
        name="StatementMetadata",
        parent=styles["Normal"],
        fontSize=9,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        name="SyntheticNotice",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#9B1C1C"),
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        spaceAfter=4 * mm,
    ))
    styles.add(ParagraphStyle(
        name="TransactionDescription",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
    ))
    styles.add(ParagraphStyle(
        name="TransactionHeader",
        parent=styles["Normal"],
        fontSize=7.5,
        leading=9,
        textColor=colors.white,
        alignment=TA_CENTER,
    ))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title=f"SYNTHETIC TEST BANK STATEMENT - {profile['company_name']}",
        author="Qawafel Synthetic Sample Data Generator",
    )
    story = [
        Paragraph("Synthetic Test Bank Statement", styles["StatementTitle"]),
        Paragraph(
            "SYNTHETIC TEST DATA - NOT A REAL BANK STATEMENT OR FINANCIAL RECORD",
            styles["SyntheticNotice"],
        ),
        Paragraph(
            f"<b>Account holder:</b> {escape(profile['company_name'])}<br/>"
            f"<b>Commercial Registration:</b> {escape(profile['cr_number'])}<br/>"
            "<b>Account type:</b> Business current account<br/>"
            f"<b>Currency:</b> {profile['currency']}<br/>"
            "<b>Statement period:</b> "
            f"{statement_dates.min():%d %b %Y} – "
            f"{statement_dates.max():%d %b %Y}",
            styles["StatementMetadata"],
        ),
        Spacer(1, 6 * mm),
    ]

    headers = [
        "Transaction ID",
        "Transaction Date",
        "Description",
        f"Debit ({profile['currency']})",
        f"Credit ({profile['currency']})",
        f"Running Balance ({profile['currency']})",
    ]
    rows = [[Paragraph(value, styles["TransactionHeader"]) for value in headers]]
    for transaction in transactions.to_dict("records"):
        rows.append([
            str(transaction["transaction_id"]),
            pd.to_datetime(transaction["transaction_date"]).strftime("%d/%m/%Y"),
            Paragraph(
                str(transaction["description"]),
                styles["TransactionDescription"],
            ),
            f"{transaction['debit']:,.2f}" if transaction["debit"] else "-",
            f"{transaction['credit']:,.2f}" if transaction["credit"] else "-",
            f"{transaction['balance']:,.2f}",
        ])

    table = Table(
        rows,
        colWidths=[25 * mm, 27 * mm, 78 * mm, 27 * mm, 27 * mm, 33 * mm],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#72552F")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7D0C5")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white,
            colors.HexColor("#F7F4EE"),
        ]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    doc.build(
        story,
        onFirstPage=_draw_synthetic_footer,
        onLaterPages=_draw_synthetic_footer,
    )


# ==========================================
# 5. GENERATE ONE COMPLETE SAMPLE
# ==========================================

def generate_sample(folder_name, config):

    sample_path = SAMPLE_DIR / folder_name
    sample_path.mkdir(parents=True, exist_ok=True)

    profile = generate_company_profile(config)
    invoices = generate_invoices(config)

    transactions = generate_bank_transactions(
        invoices,
        config["issue"]
    )

    # Save company profile
    with open(
        sample_path / "company_profile.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            profile,
            file,
            indent=4,
            ensure_ascii=False
        )

    # Keep the invoice table as the first sheet for the existing data loader.
    # A separate visible notice sheet labels the workbook as synthetic.
    with pd.ExcelWriter(sample_path / "invoices.xlsx", engine="openpyxl") as writer:
        invoices.to_excel(writer, sheet_name="Invoices", index=False)
        notice = pd.DataFrame({
            "Synthetic Test Data Notice": [
                "Fictional sample records for software testing only.",
                "Not real companies, customers, invoices, or bank transactions.",
            ]
        })
        notice.to_excel(writer, sheet_name="About This Data", index=False)
        writer.book.properties.title = "Synthetic Test Invoice Data"
        writer.book.properties.subject = "Fictional software test records"

    # Save the bank statement as selectable text so the PDF parser can read it.
    save_bank_statement_pdf(
        profile,
        transactions,
        sample_path / "bank_statement.pdf",
    )
    (sample_path / "bank_transactions.xlsx").unlink(missing_ok=True)

    print(f"\nGenerated: {profile['company_name']}")
    print(f"Invoices: {len(invoices)}")
    print(f"Bank transactions: {len(transactions)}")
    print("Synthetic bank statement: bank_statement.pdf")


# ==========================================
# 6. GENERATE ALL FIVE SAMPLES
# ==========================================

def generate_all_samples():

    print("=" * 50)
    print("QAWAFEL AI - SAMPLE DATA GENERATOR")
    print("=" * 50)

    for folder_name, config in SCENARIOS.items():

        generate_sample(folder_name, config)

    print("\nAll five sample datasets generated!")
    print(f"Location: {SAMPLE_DIR}")


if __name__ == "__main__":
    generate_all_samples()
