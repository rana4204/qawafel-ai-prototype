"""Validation helpers for the company dataset loaded by document_extractor."""

from typing import Any

import pandas as pd


INVOICE_REQUIRED_COLUMNS = [
    "invoice_id",
    "invoice_date",
    "customer_name",
    "net_amount",
    "vat_amount",
    "total_amount",
    "payment_status",
]

BANK_REQUIRED_COLUMNS = [
    "transaction_id",
    "transaction_date",
    "description",
    "debit",
    "credit",
    "balance",
]

ALLOWED_PAYMENT_STATUSES = {
    "Paid",
    "Pending",
    "Overdue",
    "Partially Paid",
}

AMOUNT_TOLERANCE = 0.01


def _is_missing(series: pd.Series) -> pd.Series:
    """Return a mask treating nulls and whitespace-only strings as missing."""
    return series.isna() | series.map(
        lambda value: isinstance(value, str) and not value.strip()
    )


def _new_report() -> dict[str, Any]:
    """Create the common validation report structure."""
    return {
        "is_valid": True,
        "error_count": 0,
        "warning_count": 0,
        "errors": [],
        "warnings": [],
    }


def _add_issue(
    report: dict[str, Any],
    severity: str,
    check: str,
    count: int,
    message: str,
) -> None:
    """Add a counted validation issue to a report."""
    if count <= 0:
        return

    issue = {"check": check, "count": count, "message": message}
    if severity == "error":
        report["errors"].append(issue)
        report["error_count"] += count
        report["is_valid"] = False
    else:
        report["warnings"].append(issue)
        report["warning_count"] += count


def _missing_values(df: pd.DataFrame) -> dict[str, int]:
    """Count missing cells in every present column."""
    return {column: int(_is_missing(df[column]).sum()) for column in df.columns}


def validate_invoices(invoices: pd.DataFrame) -> dict:
    """Validate invoice structure and values, returning a structured report."""
    report = _new_report()
    if not isinstance(invoices, pd.DataFrame):
        _add_issue(
            report, "error", "invalid_input", 1,
            "Invoices input must be a pandas DataFrame.",
        )
        report["missing_columns"] = INVOICE_REQUIRED_COLUMNS.copy()
        report["missing_values"] = {}
        return report

    missing_columns = [
        column for column in INVOICE_REQUIRED_COLUMNS
        if column not in invoices.columns
    ]
    report["missing_columns"] = missing_columns
    for column in missing_columns:
        _add_issue(
            report, "error", "missing_column", 1,
            f"Required invoice column is missing: {column}.",
        )

    report["missing_values"] = _missing_values(invoices)
    for column in INVOICE_REQUIRED_COLUMNS:
        if column in invoices.columns:
            missing_count = report["missing_values"][column]
            _add_issue(
                report, "error", "missing_values", missing_count,
                f"Missing values found in required invoice column: {column}.",
            )
    for column, count in report["missing_values"].items():
        if column not in INVOICE_REQUIRED_COLUMNS:
            _add_issue(
                report, "warning", "optional_missing_values", count,
                f"Missing values found in optional invoice column: {column}.",
            )

    if "invoice_id" in invoices.columns:
        ids = invoices["invoice_id"]
        ids = ids[~_is_missing(ids)]
        report["duplicate_invoice_ids"] = int(ids.duplicated().sum())
        _add_issue(
            report, "error", "duplicate_invoice_ids",
            report["duplicate_invoice_ids"],
            "Duplicate invoice IDs found beyond the first occurrence.",
        )
    else:
        report["duplicate_invoice_ids"] = 0

    if "invoice_date" in invoices.columns:
        dates = pd.to_datetime(invoices["invoice_date"], errors="coerce")
        report["invalid_invoice_dates"] = int(
            (~_is_missing(invoices["invoice_date"]) & dates.isna()).sum()
        )
        _add_issue(
            report, "error", "invalid_invoice_dates",
            report["invalid_invoice_dates"],
            "Non-empty invoice dates could not be parsed.",
        )
    else:
        report["invalid_invoice_dates"] = 0

    amount_columns = ["net_amount", "vat_amount", "total_amount"]
    report["non_numeric_amounts"] = {}
    report["negative_amounts"] = {}
    numeric_amounts: dict[str, pd.Series] = {}
    for column in amount_columns:
        if column not in invoices.columns:
            report["non_numeric_amounts"][column] = 0
            report["negative_amounts"][column] = 0
            continue

        source = invoices[column]
        missing = _is_missing(source)
        numeric = pd.to_numeric(source.mask(missing), errors="coerce")
        numeric_amounts[column] = numeric
        non_numeric_count = int((~missing & numeric.isna()).sum())
        negative_count = int((numeric < 0).sum())
        report["non_numeric_amounts"][column] = non_numeric_count
        report["negative_amounts"][column] = negative_count
        _add_issue(
            report, "error", "non_numeric_amounts", non_numeric_count,
            f"Non-numeric values found in invoice amount column: {column}.",
        )
        _add_issue(
            report, "error", "negative_amounts", negative_count,
            f"Negative values found in invoice amount column: {column}.",
        )

    report["total_mismatch_count"] = 0
    if all(column in numeric_amounts for column in amount_columns):
        net = numeric_amounts["net_amount"]
        vat = numeric_amounts["vat_amount"]
        total = numeric_amounts["total_amount"]
        comparable = net.notna() & vat.notna() & total.notna()
        mismatch = comparable & ((total - (net + vat)).abs() > AMOUNT_TOLERANCE)
        report["total_mismatch_count"] = int(mismatch.sum())
    _add_issue(
        report, "error", "total_mismatch",
        report["total_mismatch_count"],
        "Invoice totals differ from net plus VAT by more than 0.01.",
    )

    report["payment_status_counts"] = {}
    report["unexpected_payment_statuses"] = {}
    if "payment_status" in invoices.columns:
        statuses = invoices["payment_status"]
        report["payment_status_counts"] = {
            str(status): int(count)
            for status, count in statuses.value_counts(dropna=False).items()
        }
        missing_status = _is_missing(statuses)
        unexpected = ~missing_status & ~statuses.isin(ALLOWED_PAYMENT_STATUSES)
        report["unexpected_payment_statuses"] = {
            str(status): int(count)
            for status, count in statuses[unexpected].value_counts().items()
        }
        _add_issue(
            report, "error", "unexpected_payment_statuses",
            int(unexpected.sum()),
            "Unexpected invoice payment statuses found.",
        )

    return report


def validate_bank_transactions(tx: pd.DataFrame) -> dict:
    """Validate bank transaction structure and values, returning a report."""
    report = _new_report()
    if not isinstance(tx, pd.DataFrame):
        _add_issue(
            report, "error", "invalid_input", 1,
            "Bank transactions input must be a pandas DataFrame.",
        )
        report["missing_columns"] = BANK_REQUIRED_COLUMNS.copy()
        report["missing_values"] = {}
        return report

    missing_columns = [
        column for column in BANK_REQUIRED_COLUMNS
        if column not in tx.columns
    ]
    report["missing_columns"] = missing_columns
    for column in missing_columns:
        _add_issue(
            report, "error", "missing_column", 1,
            f"Required bank transaction column is missing: {column}.",
        )

    report["missing_values"] = _missing_values(tx)
    allowed_blank_columns = {"debit", "credit"}
    for column in BANK_REQUIRED_COLUMNS:
        if column not in tx.columns:
            continue
        missing_count = report["missing_values"][column]
        if column in allowed_blank_columns:
            _add_issue(
                report, "warning", "optional_missing_values", missing_count,
                f"Blank values are allowed in bank transaction column: {column}.",
            )
        else:
            _add_issue(
                report, "error", "missing_values", missing_count,
                f"Missing values found in required bank transaction column: {column}.",
            )
    for column, count in report["missing_values"].items():
        if column not in BANK_REQUIRED_COLUMNS:
            _add_issue(
                report, "warning", "optional_missing_values", count,
                f"Missing values found in optional bank transaction column: {column}.",
            )

    if "transaction_id" in tx.columns:
        ids = tx["transaction_id"]
        ids = ids[~_is_missing(ids)]
        report["duplicate_transaction_ids"] = int(ids.duplicated().sum())
        _add_issue(
            report, "error", "duplicate_transaction_ids",
            report["duplicate_transaction_ids"],
            "Duplicate transaction IDs found beyond the first occurrence.",
        )
    else:
        report["duplicate_transaction_ids"] = 0

    if "transaction_date" in tx.columns:
        dates = pd.to_datetime(tx["transaction_date"], errors="coerce")
        report["invalid_transaction_dates"] = int(
            (~_is_missing(tx["transaction_date"]) & dates.isna()).sum()
        )
        _add_issue(
            report, "error", "invalid_transaction_dates",
            report["invalid_transaction_dates"],
            "Non-empty transaction dates could not be parsed.",
        )
    else:
        report["invalid_transaction_dates"] = 0

    report["non_numeric_values"] = {}
    report["negative_values"] = {}
    for column in ["debit", "credit", "balance"]:
        if column not in tx.columns:
            report["non_numeric_values"][column] = 0
            report["negative_values"][column] = 0
            continue

        source = tx[column]
        missing = _is_missing(source)
        numeric = pd.to_numeric(source.mask(missing), errors="coerce")
        non_numeric_count = int((~missing & numeric.isna()).sum())
        negative_count = int((numeric < 0).sum())
        report["non_numeric_values"][column] = non_numeric_count
        report["negative_values"][column] = negative_count
        _add_issue(
            report, "error", "non_numeric_values", non_numeric_count,
            f"Non-numeric values found in bank transaction column: {column}.",
        )
        _add_issue(
            report, "error", "negative_values", negative_count,
            f"Negative values found in bank transaction column: {column}.",
        )

    if "debit" in tx.columns and "credit" in tx.columns:
        debit_numeric = pd.to_numeric(
            tx["debit"].mask(_is_missing(tx["debit"])),
            errors="coerce",
        )
        credit_numeric = pd.to_numeric(
            tx["credit"].mask(_is_missing(tx["credit"])),
            errors="coerce",
        )
        report["both_debit_and_credit_count"] = int(
            ((debit_numeric > 0) & (credit_numeric > 0)).sum()
        )
    else:
        report["both_debit_and_credit_count"] = 0
    _add_issue(
        report, "warning", "both_debit_and_credit",
        report["both_debit_and_credit_count"],
        "Rows have both debit and credit amounts greater than zero; review these transactions.",
    )

    return report


def validate_dataset(dataset: dict) -> dict:
    """Validate invoices and bank transactions in a loaded company dataset."""
    if not isinstance(dataset, dict):
        dataset = {}
        dataset_input_error = True
    else:
        dataset_input_error = False

    invoices_input = dataset.get("invoices", pd.DataFrame())
    bank_input = dataset.get("bank_transactions", pd.DataFrame())
    invoice_report = validate_invoices(invoices_input)
    bank_report = validate_bank_transactions(bank_input)

    dataset_errors = []
    if dataset_input_error:
        dataset_errors.append({
            "check": "invalid_input",
            "count": 1,
            "message": "Dataset input must be a dictionary.",
        })
    for key in ["invoices", "bank_transactions"]:
        if key not in dataset:
            dataset_errors.append({
                "check": "missing_dataset_component",
                "count": 1,
                "message": f"Dataset is missing required component: {key}.",
            })

    summary_errors = (
        dataset_errors
        + invoice_report["errors"]
        + bank_report["errors"]
    )
    error_count = (
        invoice_report["error_count"]
        + bank_report["error_count"]
        + sum(error["count"] for error in dataset_errors)
    )
    warning_count = (
        invoice_report["warning_count"] + bank_report["warning_count"]
    )
    return {
        "invoices": invoice_report,
        "bank_transactions": bank_report,
        "summary": {
            "is_valid": error_count == 0,
            "error_count": error_count,
            "warning_count": warning_count,
            "errors": summary_errors,
        },
    }