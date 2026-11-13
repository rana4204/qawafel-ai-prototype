
import json
import re
from pathlib import Path

import pandas as pd
import pdfplumber


# ==========================================
# 1. LOAD COMPANY PROFILE
# ==========================================

def load_company_profile(file_path):

    file_path = Path(file_path)

    with open(file_path, "r", encoding="utf-8") as file:
        profile = json.load(file)

    required_fields = [
        "company_name",
        "cr_number",
        "industry",
        "currency"
    ]

    for field in required_fields:
        if not profile.get(field):
            raise ValueError(
                f"Missing company information: {field}"
            )

    return profile


# ==========================================
# 2. LOAD INVOICES
# ==========================================

def load_invoices(file_path):

    file_path = Path(file_path)

    invoices = pd.read_excel(file_path)

    required_columns = [
        "invoice_id",
        "invoice_date",
        "customer_name",
        "net_amount",
        "vat_amount",
        "total_amount",
        "payment_status"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in invoices.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing invoice columns: {missing_columns}"
        )

    invoices["invoice_date"] = pd.to_datetime(
        invoices["invoice_date"],
        errors="coerce"
    )

    return invoices


# ==========================================
# 3. LOAD BANK TRANSACTIONS
# ==========================================

def load_bank_transactions(file_path):

    file_path = Path(file_path)

    transactions = pd.read_excel(file_path)

    required_columns = [
        "transaction_id",
        "transaction_date",
        "description",
        "debit",
        "credit",
        "balance"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in transactions.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing bank columns: {missing_columns}"
        )

    transactions["transaction_date"] = pd.to_datetime(
        transactions["transaction_date"],
        errors="coerce"
    )

    return transactions


# ==========================================
# 4. EXTRACT PDF TEXT
# ==========================================

def extract_pdf_text(file_path):

    file_path = Path(file_path)

    extracted_pages = []

    with pdfplumber.open(file_path) as pdf:

        for page_number, page in enumerate(pdf.pages, start=1):

            text = page.extract_text() or ""

            extracted_pages.append({
                "page_number": page_number,
                "text": text
            })

    full_text = "\n".join(
        page["text"]
        for page in extracted_pages
    )

    if not full_text.strip():
        raise ValueError(
            "No readable text found in PDF. "
            "The document may require OCR."
        )

    return {
        "file_name": file_path.name,
        "total_pages": len(extracted_pages),
        "pages": extracted_pages,
        "full_text": full_text
    }


def load_bank_transactions_pdf(file_path):
    """Extract clearly tabular bank transactions from a text-based PDF."""
    file_path = Path(file_path)
    column_aliases = {
        "transaction_id": {
            "transactionid", "transactionno", "transactionnumber", "txnid",
            "referenceno", "referencenumber", "refno",
        },
        "transaction_date": {
            "date", "transactiondate", "txndate", "valuedate", "postingdate",
        },
        "description": {
            "description", "details", "transactiondetails", "narration",
            "particulars", "remarks",
        },
        "debit": {
            "debit", "debitamount", "withdrawal", "withdrawals",
            "withdrawalamount",
        },
        "credit": {
            "credit", "creditamount", "deposit", "deposits", "depositamount",
        },
        "amount": {"amount", "transactionamount"},
        "direction": {"type", "transactiontype", "drcr", "debitcredit"},
        "balance": {"balance", "runningbalance", "closingbalance"},
    }

    def normalized_header(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())

    def map_header(row):
        normalized = [normalized_header(cell) for cell in row]
        indices = {}
        for field, aliases in column_aliases.items():
            for index, value in enumerate(normalized):
                if any(value.startswith(alias) for alias in aliases):
                    indices[field] = index
                    break
        has_split_amounts = "debit" in indices and "credit" in indices
        has_directed_amount = "amount" in indices and "direction" in indices
        if (
            "transaction_date" not in indices
            or "description" not in indices
            or "balance" not in indices
            or not (has_split_amounts or has_directed_amount)
        ):
            return None
        return indices

    def cell(row, index):
        return row[index] if index < len(row) else None

    def parse_amount(value, *, allow_blank=False, row_number):
        text = "" if value is None else str(value).strip()
        if not text or text in {"-", "—", "–"}:
            if allow_blank:
                return 0.0
            raise ValueError(
                f"Bank statement row {row_number} has no balance amount."
            )
        compact = re.sub(r"\s+", "", text).replace(",", "")
        compact = re.sub(
            r"(?i)(SAR|USD|EUR|GBP|AED|KWD|BHD|QAR|OMR|CR|DR)",
            "",
            compact,
        )
        if not re.fullmatch(r"[+]?\d+(?:\.\d+)?", compact):
            raise ValueError(
                f"Bank statement row {row_number} has an unreadable amount: "
                f"{text!r}."
            )
        return float(compact)

    transactions = []
    with pdfplumber.open(file_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                if not table:
                    continue
                header_position = next(
                    (
                        position
                        for position, row in enumerate(table)
                        if row and map_header(row) is not None
                    ),
                    None,
                )
                if header_position is None:
                    continue
                header = map_header(table[header_position])
                for row_position, row in enumerate(
                    table[header_position + 1:],
                    start=1,
                ):
                    if not row or not any(str(value or "").strip() for value in row):
                        continue
                    source_row = f"page {page_number}, row {row_position}"
                    date_text = str(
                        cell(row, header["transaction_date"]) or ""
                    ).strip()
                    transaction_date = pd.to_datetime(
                        date_text,
                        errors="coerce",
                        dayfirst=True,
                    )
                    if pd.isna(transaction_date):
                        raise ValueError(
                            f"Bank statement {source_row} has an unreadable "
                            f"transaction date: {date_text!r}."
                        )
                    description = str(
                        cell(row, header["description"]) or ""
                    ).strip()
                    if not description:
                        raise ValueError(
                            f"Bank statement {source_row} is missing a "
                            "transaction description."
                        )
                    balance = parse_amount(
                        cell(row, header["balance"]),
                        row_number=source_row,
                    )
                    if "debit" in header and "credit" in header:
                        debit = parse_amount(
                            cell(row, header["debit"]),
                            allow_blank=True,
                            row_number=source_row,
                        )
                        credit = parse_amount(
                            cell(row, header["credit"]),
                            allow_blank=True,
                            row_number=source_row,
                        )
                    else:
                        amount = parse_amount(
                            cell(row, header["amount"]),
                            row_number=source_row,
                        )
                        direction = str(
                            cell(row, header["direction"]) or ""
                        ).strip().casefold()
                        if direction in {"debit", "dr", "withdrawal", "withdraw"}:
                            debit, credit = amount, 0.0
                        elif direction in {"credit", "cr", "deposit"}:
                            debit, credit = 0.0, amount
                        else:
                            raise ValueError(
                                f"Bank statement {source_row} has an "
                                f"unrecognized transaction direction: {direction!r}."
                            )

                    transaction_id = (
                        str(cell(row, header["transaction_id"]) or "").strip()
                        if "transaction_id" in header
                        else ""
                    )
                    transactions.append({
                        "transaction_id": transaction_id or (
                            f"{file_path.stem}-p{page_number}-r{row_position}"
                        ),
                        "transaction_date": transaction_date,
                        "description": description,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance,
                    })

    if not transactions:
        raise ValueError(
            "No supported transaction table was found in the bank statement. "
            "Upload a text-based PDF with columns for date, description, "
            "debit and credit (or amount and direction), and balance. "
            "Scanned statements may require OCR."
        )
    return pd.DataFrame(
        transactions,
        columns=[
            "transaction_id",
            "transaction_date",
            "description",
            "debit",
            "credit",
            "balance",
        ],
    )


# ==========================================
# 5. LOAD COMPLETE COMPANY DATASET
# ==========================================

def load_company_dataset(sample_folder):

    sample_folder = Path(sample_folder)

    company = load_company_profile(
        sample_folder / "company_profile.json"
    )

    invoices = load_invoices(
        sample_folder / "invoices.xlsx"
    )

    bank_transactions = load_bank_transactions_pdf(
        sample_folder / "bank_statement.pdf"
    )

    return {
        "company": company,
        "invoices": invoices,
        "bank_transactions": bank_transactions
    }
