# Qawafel SME Financing Prototype

Qawafel is a Python and Streamlit prototype that demonstrates an SME financing application workflow. It processes business invoices and bank statements, extracts and validates financial data, reconciles invoice payments against bank transactions, and prepares a structured financing assessment.

An in-process Mock Bank API simulates the submission and receipt of financing applications, including bank reference generation and status updates. This prototype does not connect to a real bank.

## Features and Workflow

1. **Create a Financing Application:** The customer enters financing details, including the requested amount, purpose, and repayment information.
2. **Upload Documents:** The customer uploads a sales invoice Excel workbook and a bank statement PDF. An additional supporting PDF is optional.
3. **Extract and Validate Data:** The system extracts invoice records and bank transactions, then checks the data for missing, duplicate, or invalid information.
4. **Reconcile Transactions:** The system matches invoice payments against bank transactions and identifies confirmed, unmatched, or ambiguous matches.
5. **Financial Analysis:** The system calculates financial summaries and generates rule-based insights based on the submitted data.
6. **Submit the Application:** Once processing is complete and required validation checks pass, the application and its structured financing package are submitted to the Mock Bank API.
7. **Track Application Status:** The Client Portal displays the simulated bank acknowledgment, bank reference, current status, and timestamped status history.

The prototype does not include a Bank Portal or a bank employee interface.

## Technology Stack

- Python 3.10+
- Streamlit
- pandas and openpyxl
- pdfplumber
- ReportLab
- Plotly

The financial insights are generated using deterministic, rule-based Python logic. They do not represent an automated credit decision.

## Project Structure

```text
qawafel-ai-prototype/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .gitattributes
├── assets/
│   └── qawafel_logo_dark.png
├── modules/
│   ├── ai_insights.py
│   ├── client_submission.py
│   ├── data_validator.py
│   ├── document_extractor.py
│   ├── financial_analyzer.py
│   ├── invoice_matcher.py
│   ├── mock_bank_api.py
│   ├── generate_sample_data.py
│   ├── validate_sample_data.py
│   └── test_*.py
└── sample_data/
    ├── sample_01_healthy/
    ├── sample_02_data_issues/
    ├── sample_03_cashflow/
    ├── sample_04_growth/
    └── sample_05_complex/
```

## How to Run the Project

### Prerequisites

- Python 3.10 or newer
- Git (if cloning the repository)

### 1. Clone the repository

```bash
git clone https://github.com/rana4204/qawafel-ai-prototype.git
cd qawafel-ai-prototype
```

Alternatively, download the repository as a ZIP file and extract it.

### 2. Create a virtual environment

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Run the application

From the project root directory:

```bash
streamlit run app.py
```

Streamlit will provide a local URL, usually:

```text
http://localhost:8501
```

Open this URL in your browser to access the Client Portal.

No `.env` file, API key, or bank credentials are required to run the current prototype.

## Where to Find Sample Data

The synthetic sample datasets are available in the `sample_data/` directory.

Each scenario folder contains:

- `company_profile.json` — fictional company information.
- `invoices.xlsx` — synthetic sales invoice records.
- `bank_statement.pdf` — synthetic bank statement transactions.

The five scenarios demonstrate different processing and validation cases:

| Scenario | Description |
|---|---|
| `sample_01_healthy` | Complete and consistent invoice and transaction records. |
| `sample_02_data_issues` | Intentional data-quality issues, including duplicate and missing invoice information. |
| `sample_03_cashflow` | Overdue invoices demonstrating collection and cash-flow pressure. |
| `sample_04_growth` | Increasing monthly invoice revenue over the sample period. |
| `sample_05_complex` | Partial payments and more complex invoice-to-transaction matching cases. |

All sample records are synthetic and intended for demonstration and testing only. They do not represent real companies, customers, or bank accounts.

### Generate Sample Data

To regenerate all five sample scenarios:

```bash
python -m modules.generate_sample_data
```

### Validate Sample Data

To check that the generated scenarios contain their intended data characteristics:

```bash
python -m modules.validate_sample_data
```

## Processing and Financial Assessment

### Document Extraction

`modules/document_extractor.py` extracts invoice data from Excel workbooks and transaction data from selectable-text PDF bank statements. It can also extract text from an optional supporting PDF.

### Data Validation

`modules/data_validator.py` checks required fields, missing or malformed values, duplicate invoices, and transaction data quality. Blocking validation errors prevent application submission until they are resolved.

### Invoice Reconciliation

`modules/invoice_matcher.py` compares invoice records against bank transaction descriptions and amounts to identify confirmed, unmatched, or ambiguous payment matches.

### Financial Analysis

`modules/financial_analyzer.py` calculates financial summaries and metrics based on the uploaded records.

`modules/ai_insights.py` generates rule-based findings from the available financial data. These insights are intended to support review and highlight relevant patterns, not to approve or reject financing applications.

## Mock Bank API Simulation

The prototype includes an in-process Mock Bank API implemented in `modules/mock_bank_api.py`.

When a financing application passes the required validation checks, the application and its structured financing package are submitted through the mock API.

The simulated API:

- Validates the submitted application and required package fields.
- Generates a unique bank reference number.
- Returns a simulated acknowledgment.
- Assigns an initial `received` status.
- Records timestamped status events.
- Supports simulated status updates, including `under_review`, `more_information_required`, `approved`, and `rejected`.
- Handles identical submissions idempotently within the same API instance.

The Client Portal displays the latest known status and the application's status history.

**Important:** This is a local Python simulation, not a real external banking API. Status updates are generated by directly calling the mock API module. There is no external bank endpoint, webhook, or automatic bank-to-Qawafel communication.

## Assumptions and Limitations

### Assumptions

- The prototype uses synthetic company profiles, invoices, and bank statements.
- The uploaded invoice workbook follows the expected structure used by the application.
- Bank statements contain selectable PDF text that can be extracted using `pdfplumber`.
- Invoice and transaction records contain sufficient information to attempt payment matching.
- Financial calculations and insights are based only on the information provided in the uploaded documents.
- Required validation checks must pass before an application can be submitted.
- The Mock Bank API represents the bank integration boundary for demonstration purposes.
- The bank is responsible for the final financing decision. Qawafel prepares and submits the financing package but does not make the bank's lending decision.

### Limitations

- **No real bank integration:** The Mock Bank API does not communicate with an actual bank.
- **In-memory storage:** Application and bank status records are not stored in a persistent database and may be lost when the Streamlit session ends.
- **No authentication or authorization:** The prototype does not implement production user identity verification, company membership, or role-based permissions.
- **No bank employee interface:** Bank-side review is outside the scope of the current prototype.
- **No OCR:** Scanned or image-based PDFs may not be extractable because OCR is not implemented.
- **Rule-based insights:** Financial findings use predefined rules and are not generated by a trained credit-scoring model or generative AI service.
- **No lending decision engine:** The prototype does not determine financing eligibility or guarantee repayment capacity.
- **Prototype security:** Production-grade access controls, encryption policies, audit infrastructure, and data-retention controls are not implemented.

## Tests and Verification

Run the full test suite from the project root:

```bash
python -m unittest discover -s modules -p "test_*.py"
```

Run the Mock Bank API and client submission tests:

```bash
python -m unittest modules.test_mock_bank_api modules.test_client_submission
```

Compile the application and modules:

```bash
python -m compileall -q app.py modules
```

## AI Tools Used During Development

OpenAI Codex was used as an AI-assisted development tool for code review, implementation support, debugging, and documentation.

The running prototype does not depend on a generative AI service. Financial insights are generated using deterministic, rule-based Python logic.