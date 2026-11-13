"""Match invoice references in bank transactions and summarize collections."""

import math
import re
from typing import Any

import pandas as pd


INVOICE_ID_COLUMN = "invoice_id"
INVOICE_TOTAL_COLUMN = "total_amount"
PAYMENT_STATUS_COLUMN = "payment_status"
TRANSACTION_ID_COLUMN = "transaction_id"
DESCRIPTION_COLUMN = "description"
CREDIT_COLUMN = "credit"
DEBIT_COLUMN = "debit"
TRANSACTION_DATE_COLUMN = "transaction_date"


def _is_missing(value: Any) -> bool:
    """Return whether a scalar value is null or a blank string."""
    if value is None or value is pd.NA:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _as_finite_float(value: Any) -> float | None:
    """Convert a scalar to a finite float, or return None if it is invalid."""
    if _is_missing(value):
        return None

    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return None

    result = float(numeric)
    return result if math.isfinite(result) else None


def _invoice_id_pattern(invoice_id: str) -> re.Pattern[str]:
    """Build a case-insensitive whole-token pattern for an invoice ID."""
    return re.compile(
        rf"(?<![A-Za-z0-9]){re.escape(invoice_id)}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


def _status_discrepancy(
    collection_status: str | None,
    payment_status: Any,
) -> bool | None:
    """Compare calculated collection state with the reported payment status."""
    if collection_status is None or _is_missing(payment_status):
        return None

    normalized_status = str(payment_status).strip().casefold()
    expected_statuses = {
        "fully_collected": {"paid"},
        "partially_collected": {"partially paid"},
        "unmatched": {"pending", "overdue"},
        "overpaid": set(),
    }
    return normalized_status not in expected_statuses[collection_status]


def match_invoices_to_transactions(
    invoices: pd.DataFrame,
    transactions: pd.DataFrame,
    amount_tolerance: float = 0.01,
) -> dict[str, Any]:
    """Match uniquely referenced invoices to positive bank-credit payments.

    Transactions are matched only when their description contains exactly one
    known invoice ID as a whole token and that ID identifies one invoice row.
    Positive credits are aggregated per invoice; debits never count as
    collections. Ambiguous and unrecognized transactions are returned
    separately rather than silently assigned or discarded.
    """
    if not isinstance(invoices, pd.DataFrame):
        raise TypeError("invoices must be a pandas DataFrame")
    if not isinstance(transactions, pd.DataFrame):
        raise TypeError("transactions must be a pandas DataFrame")

    tolerance = float(amount_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("amount_tolerance must be a finite non-negative number")

    invoice_rows: list[dict[str, Any]] = []
    invoice_rows_by_key: dict[str, list[int]] = {}
    for row_number, (_, row) in enumerate(invoices.iterrows()):
        invoice_id = row.get(INVOICE_ID_COLUMN)
        total = _as_finite_float(row.get(INVOICE_TOTAL_COLUMN))
        invoice_rows.append({
            "invoice_id": invoice_id,
            "invoice_total": total,
            "total_collected": 0.0,
            "outstanding_amount": None,
            "collection_status": None,
            "matched_transaction_ids": [],
            "payment_status": row.get(PAYMENT_STATUS_COLUMN),
            "payment_status_discrepancy": None,
            "invoice_row": row_number,
        })

        if not _is_missing(invoice_id):
            invoice_key = str(invoice_id).casefold()
            invoice_rows_by_key.setdefault(invoice_key, []).append(row_number)

    patterns = {
        invoice_key: _invoice_id_pattern(invoice_key)
        for invoice_key in invoice_rows_by_key
    }

    unmatched_transactions: list[dict[str, Any]] = []
    ambiguous_transactions: list[dict[str, Any]] = []
    non_payment_transactions: list[dict[str, Any]] = []
    matched_transaction_count = 0

    for row_number, (_, row) in enumerate(transactions.iterrows()):
        description = row.get(DESCRIPTION_COLUMN)
        description_text = "" if _is_missing(description) else str(description)
        referenced_keys = [
            invoice_key
            for invoice_key, pattern in patterns.items()
            if pattern.search(description_text)
        ]
        reference_ids = [
            invoice_rows[invoice_rows_by_key[key][0]]["invoice_id"]
            for key in referenced_keys
        ]
        transaction_id = row.get(TRANSACTION_ID_COLUMN)

        if not referenced_keys:
            unmatched_transactions.append({
                "transaction_id": transaction_id,
                "transaction_row": row_number,
                "description": description,
                "reason": "no_recognized_invoice_reference",
            })
            continue

        duplicate_keys = [
            key for key in referenced_keys
            if len(invoice_rows_by_key[key]) != 1
        ]
        if len(referenced_keys) != 1 or duplicate_keys:
            reasons = []
            if len(referenced_keys) > 1:
                reasons.append("multiple_invoice_references")
            if duplicate_keys:
                reasons.append("duplicated_invoice_id")
            ambiguous_transactions.append({
                "transaction_id": transaction_id,
                "transaction_row": row_number,
                "description": description,
                "reference_invoice_ids": reference_ids,
                "reason": reasons,
            })
            continue

        invoice_key = referenced_keys[0]
        invoice_index = invoice_rows_by_key[invoice_key][0]
        credit = _as_finite_float(row.get(CREDIT_COLUMN))
        debit = _as_finite_float(row.get(DEBIT_COLUMN))
        if credit is None or credit <= 0:
            non_payment_transactions.append({
                "transaction_id": transaction_id,
                "transaction_row": row_number,
                "invoice_id": invoice_rows[invoice_index]["invoice_id"],
                "transaction_date": row.get(TRANSACTION_DATE_COLUMN),
                "debit": debit,
                "credit": credit,
                "reason": "credit_is_not_a_positive_amount",
            })
            continue

        invoice_record = invoice_rows[invoice_index]
        invoice_record["total_collected"] += credit
        invoice_record["matched_transaction_ids"].append(transaction_id)
        matched_transaction_count += 1

    fully_collected_count = 0
    partially_collected_count = 0
    unmatched_invoice_count = 0
    overpaid_count = 0
    discrepancy_count = 0

    for invoice_record in invoice_rows:
        total = invoice_record["invoice_total"]
        collected = invoice_record["total_collected"]

        if total is not None:
            invoice_record["outstanding_amount"] = max(total - collected, 0.0)

        if collected <= 0:
            collection_status = "unmatched"
            unmatched_invoice_count += 1
        elif total is None:
            collection_status = None
        elif collected > total + tolerance:
            collection_status = "overpaid"
            overpaid_count += 1
        elif abs(collected - total) <= tolerance:
            collection_status = "fully_collected"
            fully_collected_count += 1
        else:
            collection_status = "partially_collected"
            partially_collected_count += 1

        discrepancy = _status_discrepancy(
            collection_status,
            invoice_record["payment_status"],
        )
        invoice_record["collection_status"] = collection_status
        invoice_record["payment_status_discrepancy"] = discrepancy
        if discrepancy is True:
            discrepancy_count += 1

    return {
        "invoice_matches": invoice_rows,
        "unmatched_transactions": unmatched_transactions,
        "ambiguous_transactions": ambiguous_transactions,
        "non_payment_transactions": non_payment_transactions,
        "summary": {
            "total_invoices": len(invoice_rows),
            "fully_collected": fully_collected_count,
            "partially_collected": partially_collected_count,
            "unmatched": unmatched_invoice_count,
            "overpaid": overpaid_count,
            "ambiguous_transactions": len(ambiguous_transactions),
            "unmatched_transactions": len(unmatched_transactions),
            "non_payment_transactions": len(non_payment_transactions),
            "matched_payment_transactions": matched_transaction_count,
            "payment_status_discrepancies": discrepancy_count,
        },
    }