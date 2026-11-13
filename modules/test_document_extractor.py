
from pathlib import Path
from modules.document_extractor import load_company_dataset

PROJECT_DIR = Path(__file__).resolve().parent.parent
sample_folder = PROJECT_DIR / "sample_data" / "sample_01_healthy"

data = load_company_dataset(sample_folder)

print("\n--- Synthetic Sample Context ---")
print(data["company"])

print("\n--- Invoices ---")
print(data["invoices"].head())

print("\nTotal invoices:", len(data["invoices"]))

print("\n--- Bank Transactions ---")
print(data["bank_transactions"].head())

print("\nTotal transactions:", len(data["bank_transactions"]))
