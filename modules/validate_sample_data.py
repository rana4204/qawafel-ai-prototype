
from pathlib import Path

import pandas as pd

from modules.document_extractor import load_company_dataset

PROJECT_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_DIR / "sample_data"


def validate_sample(folder_name):

    path = SAMPLE_DIR / folder_name

    dataset = load_company_dataset(path)
    invoices = dataset["invoices"]
    bank = dataset["bank_transactions"]

    duplicate_count = invoices["invoice_id"].duplicated().sum()
    missing_customers = invoices["customer_name"].isna().sum()

    overdue_count = (
        invoices["payment_status"] == "Overdue"
    ).sum()

    partial_count = (
        invoices["payment_status"] == "Partially Paid"
    ).sum()

    unknown_transactions = bank[
        bank["description"].isin([
            "Unknown incoming transfer",
            "Additional customer payment"
        ])
    ]

    monthly_revenue = invoices.copy()
    monthly_revenue["invoice_date"] = pd.to_datetime(
        monthly_revenue["invoice_date"]
    )

    monthly_revenue = (
        monthly_revenue.groupby(
            monthly_revenue["invoice_date"].dt.month
        )["total_amount"].sum()
    )

    print("\n" + "=" * 45)
    print(f"Synthetic scenario: {folder_name}")
    print("=" * 45)

    print(f"Total invoices: {len(invoices)}")
    print(f"Total transactions: {len(bank)}")
    print(f"Duplicate invoices: {duplicate_count}")
    print(f"Missing customer names: {missing_customers}")
    print(f"Overdue invoices: {overdue_count}")
    print(f"Partially paid invoices: {partial_count}")
    print(f"Unmatched transaction candidates: {len(unknown_transactions)}")

    if folder_name == "sample_04_growth":
        print(
            "Revenue growth:",
            f"First 3 months = {monthly_revenue.head(3).mean():,.2f}",
            f"| Last 3 months = {monthly_revenue.tail(3).mean():,.2f}"
        )


def validate_all():

    for folder in sorted(SAMPLE_DIR.iterdir()):

        if folder.is_dir():
            validate_sample(folder.name)


if __name__ == "__main__":
    validate_all()
