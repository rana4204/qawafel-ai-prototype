"""Financial metrics derived from invoices and the invoice matcher report."""

import math
from collections import Counter
from typing import Any

import pandas as pd


INVOICE_DATE_COLUMN = "invoice_date"
INVOICE_TOTAL_COLUMN = "total_amount"
TRANSACTION_DATE_COLUMN = "transaction_date"
TRANSACTION_ID_COLUMN = "transaction_id"
CREDIT_COLUMN = "credit"
DEBIT_COLUMN = "debit"


def _missing_mask(values: pd.Series) -> pd.Series:
    """Identify null and blank-string values without changing the source."""
    return values.isna() | values.map(
        lambda value: isinstance(value, str) and not value.strip()
    )


def _numeric_values(values: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return finite numeric values, missing mask, and invalid-value mask."""
    missing = _missing_mask(values)
    numeric = pd.to_numeric(values.mask(missing), errors="coerce")
    finite = numeric.map(
        lambda value: math.isfinite(float(value)) if pd.notna(value) else False
    )
    invalid = ~missing & (~numeric.notna() | ~finite)
    return numeric.where(finite), missing, invalid


def _date_values(values: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return parsed dates and masks for missing and invalid input values."""
    missing = _missing_mask(values)
    dates = pd.to_datetime(values, errors="coerce")
    invalid = ~missing & dates.isna()
    return dates, missing, invalid


def _finite_number(value: Any) -> float | None:
    """Convert an individual value to a finite float, when possible."""
    if value is None or value is pd.NA:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _rounded(value: float | int | None) -> float | None:
    """Round a numeric result to two decimal places."""
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 2)


def _sum_or_zero(values: pd.Series) -> float:
    """Sum a numeric series, treating an empty series as zero."""
    return float(values.sum()) if not values.empty else 0.0


def _identifier_key(value: Any) -> tuple[str, str] | None:
    """Return a type-sensitive key for matching transaction identifiers."""
    if value is None or value is pd.NA:
        return None
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return type(value).__name__, str(value)


def _monthly_totals(
    dates: pd.Series,
    values: pd.Series,
) -> dict[str, float]:
    """Aggregate values by calendar month, omitting invalid or missing dates."""
    valid_dates = dates.notna()
    if not valid_dates.any():
        return {}
    frame = pd.DataFrame({
        "month": dates.loc[valid_dates].dt.to_period("M").astype(str),
        "value": values.loc[valid_dates].to_numpy(),
    })
    totals = frame.groupby("month", sort=True)["value"].sum()
    return {str(month): float(value) for month, value in totals.items()}


def _positive_values(values: pd.Series) -> pd.Series:
    """Keep strictly positive numeric values and replace others with zero."""
    return values.where(values > 0, 0).fillna(0)


def _transaction_row_positions(
    records: Any,
    transaction_count: int,
) -> list[int]:
    """Extract valid matcher-provided row positions without re-matching."""
    positions: list[int] = []
    if not isinstance(records, list):
        return positions
    for record in records:
        if not isinstance(record, dict):
            continue
        position = record.get("transaction_row")
        if isinstance(position, int) and 0 <= position < transaction_count:
            positions.append(position)
    return positions


def analyze_financial_data(
    invoices: pd.DataFrame,
    transactions: pd.DataFrame,
    matching_result: dict,
) -> dict[str, Any]:
    """Calculate sales, collections, receivables, and cash-flow metrics.

    Confirmed invoice collections and transaction classifications are taken
    exclusively from the supplied invoice matcher result. Bank-wide cash flow
    includes positive credits and debits regardless of invoice references.
    """
    if not isinstance(invoices, pd.DataFrame):
        raise TypeError("invoices must be a pandas DataFrame")
    if not isinstance(transactions, pd.DataFrame):
        raise TypeError("transactions must be a pandas DataFrame")
    if not isinstance(matching_result, dict):
        raise TypeError("matching_result must be a dictionary")

    invoice_dates_source = (
        invoices[INVOICE_DATE_COLUMN]
        if INVOICE_DATE_COLUMN in invoices.columns
        else pd.Series(index=invoices.index, dtype="object")
    )
    invoice_totals_source = (
        invoices[INVOICE_TOTAL_COLUMN]
        if INVOICE_TOTAL_COLUMN in invoices.columns
        else pd.Series(index=invoices.index, dtype="object")
    )
    transaction_dates_source = (
        transactions[TRANSACTION_DATE_COLUMN]
        if TRANSACTION_DATE_COLUMN in transactions.columns
        else pd.Series(index=transactions.index, dtype="object")
    )
    credits_source = (
        transactions[CREDIT_COLUMN]
        if CREDIT_COLUMN in transactions.columns
        else pd.Series(index=transactions.index, dtype="object")
    )
    debits_source = (
        transactions[DEBIT_COLUMN]
        if DEBIT_COLUMN in transactions.columns
        else pd.Series(index=transactions.index, dtype="object")
    )
    balances_source = (
        transactions["balance"]
        if "balance" in transactions.columns
        else pd.Series(index=transactions.index, dtype="object")
    )

    invoice_dates, missing_invoice_dates, invalid_invoice_dates = _date_values(
        invoice_dates_source
    )
    transaction_dates, missing_transaction_dates, invalid_transaction_dates = _date_values(
        transaction_dates_source
    )
    invoice_amount_quality: dict[str, dict[str, Any]] = {}
    invoice_amount_values: dict[str, pd.Series] = {}
    for column in ["net_amount", "vat_amount", INVOICE_TOTAL_COLUMN]:
        source = (
            invoices[column]
            if column in invoices.columns
            else pd.Series(index=invoices.index, dtype="object")
        )
        values, missing, invalid = _numeric_values(source)
        invoice_amount_values[column] = values
        invoice_amount_quality[column] = {
            "missing": int(missing.sum()),
            "non_numeric_or_non_finite": int(invalid.sum()),
            "negative": int((values < 0).sum()),
        }
    invoice_totals = invoice_amount_values[INVOICE_TOTAL_COLUMN]
    credits, missing_credits, invalid_credits = _numeric_values(credits_source)
    debits, missing_debits, invalid_debits = _numeric_values(debits_source)
    balances, missing_balances, invalid_balances = _numeric_values(balances_source)

    positive_credits = _positive_values(credits)
    positive_debits = _positive_values(debits)
    total_sales = _sum_or_zero(invoice_totals)
    total_incoming = _sum_or_zero(positive_credits)
    total_outgoing = _sum_or_zero(positive_debits)

    invoice_matches = matching_result.get("invoice_matches", [])
    if not isinstance(invoice_matches, list):
        invoice_matches = []
    invoice_matches = [
        record for record in invoice_matches if isinstance(record, dict)
    ]

    total_collected = 0.0
    outstanding_receivables = 0.0
    total_excess_collections = 0.0
    fully_collected = 0
    partially_collected = 0
    unmatched_invoices = 0
    overpaid_invoices = 0
    payment_status_discrepancies = 0
    coverage_numerator = 0.0
    invalid_match_amounts = 0
    matched_identifier_counts: Counter[tuple[str, str]] = Counter()

    for record in invoice_matches:
        collected = _finite_number(record.get("total_collected"))
        total = _finite_number(record.get("invoice_total"))
        if collected is None:
            invalid_match_amounts += 1
            collected = 0.0
        total_collected += collected

        if total is not None:
            outstanding_receivables += max(total - collected, 0.0)
            coverage_numerator += max(min(collected, total), 0.0)
            excess = max(collected - total, 0.0)
            total_excess_collections += excess
        else:
            invalid_match_amounts += 1

        status = record.get("collection_status")
        if status == "fully_collected":
            fully_collected += 1
        elif status == "partially_collected":
            partially_collected += 1
        elif status == "unmatched":
            unmatched_invoices += 1
        elif status == "overpaid":
            overpaid_invoices += 1

        if record.get("payment_status_discrepancy") is True:
            payment_status_discrepancies += 1

        identifiers = record.get("matched_transaction_ids", [])
        if isinstance(identifiers, list):
            for identifier in identifiers:
                key = _identifier_key(identifier)
                if key is not None:
                    matched_identifier_counts[key] += 1

    matched_transaction_positions: list[int] = []
    duplicate_identifier_monthly_count = 0
    if TRANSACTION_ID_COLUMN in transactions.columns:
        transaction_keys = transactions[TRANSACTION_ID_COLUMN].map(_identifier_key)
        input_identifier_counts = Counter(
            key for key in transaction_keys if key is not None
        )
        remaining_counts = matched_identifier_counts.copy()
        for position, key in enumerate(transaction_keys):
            if key is None or remaining_counts.get(key, 0) <= 0:
                continue
            if input_identifier_counts[key] > 1:
                duplicate_identifier_monthly_count += 1
                remaining_counts[key] -= 1
                continue
            matched_transaction_positions.append(position)
            remaining_counts[key] -= 1
    else:
        duplicate_identifier_monthly_count = sum(matched_identifier_counts.values())

    confirmed_monthly_values = pd.Series(0.0, index=transactions.index)
    if matched_transaction_positions:
        confirmed_monthly_values.iloc[matched_transaction_positions] = (
            positive_credits.iloc[matched_transaction_positions].to_numpy()
        )

    monthly_sales = _monthly_totals(invoice_dates, invoice_totals.fillna(0))
    monthly_confirmed_collections = _monthly_totals(
        transaction_dates, confirmed_monthly_values
    )
    monthly_incoming = _monthly_totals(transaction_dates, positive_credits)
    monthly_outgoing = _monthly_totals(transaction_dates, positive_debits)
    monthly_net = {
        month: monthly_incoming.get(month, 0.0) - monthly_outgoing.get(month, 0.0)
        for month in set(monthly_incoming) | set(monthly_outgoing)
    }

    monthly_sales_trend: list[dict[str, Any]] = []
    previous_sales: float | None = None
    for month, sales in sorted(monthly_sales.items()):
        change = None if previous_sales is None else sales - previous_sales
        change_percent = (
            None
            if previous_sales is None or previous_sales == 0
            else (change / previous_sales) * 100
        )
        monthly_sales_trend.append({
            "month": month,
            "sales": _rounded(sales),
            "change_from_previous_month": _rounded(change),
            "change_percent": _rounded(change_percent),
        })
        previous_sales = sales

    months = sorted(
        set(monthly_sales)
        | set(monthly_confirmed_collections)
        | set(monthly_incoming)
        | set(monthly_outgoing)
        | set(monthly_net)
    )
    monthly_trends = [
        {
            "month": month,
            "invoiced_sales": _rounded(monthly_sales.get(month, 0.0)),
            "confirmed_invoice_collections": _rounded(
                monthly_confirmed_collections.get(month, 0.0)
            ),
            "incoming_cash": _rounded(monthly_incoming.get(month, 0.0)),
            "outgoing_cash": _rounded(monthly_outgoing.get(month, 0.0)),
            "net_cash_flow": _rounded(monthly_net.get(month, 0.0)),
        }
        for month in months
    ]

    unmatched_records = matching_result.get("unmatched_transactions", [])
    ambiguous_records = matching_result.get("ambiguous_transactions", [])
    non_payment_records = matching_result.get("non_payment_transactions", [])
    unmatched_positions = _transaction_row_positions(
        unmatched_records, len(transactions)
    )
    ambiguous_positions = _transaction_row_positions(
        ambiguous_records, len(transactions)
    )

    def unclassified_totals(positions: list[int]) -> dict[str, float]:
        """Sum positive credits and debits for matcher-classified bank rows."""
        credits_total = (
            _sum_or_zero(positive_credits.iloc[positions])
            if positions else 0.0
        )
        debits_total = (
            _sum_or_zero(positive_debits.iloc[positions])
            if positions else 0.0
        )
        return {
            "positive_credit_total": credits_total,
            "positive_debit_total": debits_total,
        }

    unmatched_totals = unclassified_totals(unmatched_positions)
    ambiguous_totals = unclassified_totals(ambiguous_positions)
    ambiguous_count = (
        len(ambiguous_records) if isinstance(ambiguous_records, list) else 0
    )

    invoice_missing_or_invalid = {
        "missing_invoice_date": int(missing_invoice_dates.sum()),
        "invalid_invoice_date": int(invalid_invoice_dates.sum()),
        "amount_columns": invoice_amount_quality,
    }
    bank_missing_or_invalid = {
        "missing_transaction_date": int(missing_transaction_dates.sum()),
        "invalid_transaction_date": int(invalid_transaction_dates.sum()),
        "missing_credit": int(missing_credits.sum()),
        "non_numeric_or_non_finite_credit": int(invalid_credits.sum()),
        "negative_credit": int((credits < 0).sum()),
        "missing_debit": int(missing_debits.sum()),
        "non_numeric_or_non_finite_debit": int(invalid_debits.sum()),
        "negative_debit": int((debits < 0).sum()),
        "missing_balance": int(missing_balances.sum()),
        "non_numeric_or_non_finite_balance": int(invalid_balances.sum()),
        "negative_balance": int((balances < 0).sum()),
    }
    missing_columns = {
        "invoices": [
            column for column in [INVOICE_DATE_COLUMN, INVOICE_TOTAL_COLUMN]
            if column not in invoices.columns
        ],
        "transactions": [
            column for column in [
                TRANSACTION_DATE_COLUMN, CREDIT_COLUMN, DEBIT_COLUMN, "balance"
            ]
            if column not in transactions.columns
        ],
    }

    collection_to_sales_ratio = (
        total_collected / total_sales * 100 if total_sales > 0 else None
    )
    invoice_collection_coverage = (
        coverage_numerator / total_sales * 100 if total_sales > 0 else None
    )

    return {
        "sales": {
            "total_invoiced_sales": _rounded(total_sales),
            "monthly_invoiced_sales": [
                {"month": month, "amount": _rounded(amount)}
                for month, amount in sorted(monthly_sales.items())
            ],
            "monthly_sales_trend": monthly_sales_trend,
        },
        "collections": {
            "total_confirmed_collections": _rounded(total_collected),
            "collection_to_sales_ratio_percent": _rounded(
                collection_to_sales_ratio
            ),
        },
        "receivables": {
            "outstanding_receivables": _rounded(outstanding_receivables),
            "fully_collected_invoice_count": fully_collected,
            "partially_collected_invoice_count": partially_collected,
            "unmatched_invoice_count": unmatched_invoices,
            "overpaid_invoice_count": overpaid_invoices,
            "total_excess_collections": _rounded(total_excess_collections),
            "invoice_collection_coverage_percent": _rounded(
                invoice_collection_coverage
            ),
        },
        "cash_flow": {
            "total_incoming_cash": _rounded(total_incoming),
            "total_outgoing_cash": _rounded(total_outgoing),
            "net_cash_flow": _rounded(total_incoming - total_outgoing),
            "monthly_incoming_cash": [
                {"month": month, "amount": _rounded(amount)}
                for month, amount in sorted(monthly_incoming.items())
            ],
            "monthly_outgoing_cash": [
                {"month": month, "amount": _rounded(amount)}
                for month, amount in sorted(monthly_outgoing.items())
            ],
            "monthly_net_cash_flow": [
                {"month": month, "amount": _rounded(amount)}
                for month, amount in sorted(monthly_net.items())
            ],
        },
        "monthly_trends": monthly_trends,
        "unclassified_transactions": {
            "unmatched_transaction_count": (
                len(unmatched_records)
                if isinstance(unmatched_records, list) else 0
            ),
            "unmatched_positive_credit_total": _rounded(
                unmatched_totals["positive_credit_total"]
            ),
            "unmatched_positive_debit_total": _rounded(
                unmatched_totals["positive_debit_total"]
            ),
            "ambiguous_transaction_count": ambiguous_count,
            "ambiguous_positive_credit_total": _rounded(
                ambiguous_totals["positive_credit_total"]
            ),
            "ambiguous_positive_debit_total": _rounded(
                ambiguous_totals["positive_debit_total"]
            ),
            "non_payment_transaction_count": (
                len(non_payment_records)
                if isinstance(non_payment_records, list) else 0
            ),
        },
        "data_quality": {
            "payment_status_discrepancies": payment_status_discrepancies,
            "ambiguous_invoice_references": ambiguous_count,
            "missing_or_invalid_financial_values": {
                "invoices": invoice_missing_or_invalid,
                "bank_transactions": bank_missing_or_invalid,
                "matcher_invoice_amounts_missing_or_invalid": invalid_match_amounts,
            },
            "missing_required_columns": missing_columns,
            "matched_transactions_with_duplicate_ids": (
                duplicate_identifier_monthly_count
            ),
        },
        "summary": {
            "total_invoices": len(invoices),
            "total_transactions": len(transactions),
            "total_invoiced_sales": _rounded(total_sales),
            "total_confirmed_collections": _rounded(total_collected),
            "outstanding_receivables": _rounded(outstanding_receivables),
            "net_cash_flow": _rounded(total_incoming - total_outgoing),
        },
    }