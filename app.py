"""Initial Streamlit dashboard for the Qawafel SME financing prototype."""

from copy import deepcopy
from datetime import datetime
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pandas as pd
import streamlit as st

from modules.ai_insights import generate_financial_insights
from modules.data_validator import validate_dataset
from modules.document_extractor import (
    extract_pdf_text,
    load_bank_transactions,
    load_bank_transactions_pdf,
    load_company_profile,
    load_invoices,
)
from modules.financial_analyzer import analyze_financial_data
from modules.invoice_matcher import match_invoices_to_transactions
from modules.mock_bank_api import MockBankAPI, MockBankError
from modules.client_submission import (
    SubmissionBlockedError,
    apply_bank_status_events,
    submit_client_application,
)


PROJECT_ROOT = Path(__file__).resolve().parent
LOGO_PATH = PROJECT_ROOT / "assets" / "qawafel_logo_dark.png"

CLIENT_APPLICATION_STATUSES = [
    "Draft",
    "Submitted",
    "Received",
    "Under Review",
    "More Information Required",
    "Approved",
    "Rejected",
    "Cancelled",
]
CLIENT_DEMO_COMPANY_PROFILE = {
    "company_name": "Synthetic Demo Company",
    "cr_number": "TEST-CR-DEMO-001",
    "data_classification": "Synthetic demo profile; not a real company.",
    "industry": "Wholesale Trading",
    "city": "Riyadh",
    "country": "Saudi Arabia",
    "establishment_date": "2019-03-15",
    "currency": "SAR",
    "vat_rate": 0.15,
    "description": "Registered demo company profile for the Client Portal.",
}
APPLICATION_STATUS_LABELS = {
    "received": {
        "client": "Received",
    },
    "submitted": {
        "client": "Submitted",
    },
    "under_review": {
        "client": "Under Review",
    },
    "more_information_required": {
        "client": "More Information Required",
    },
    "approved": {
        "client": "Approved",
    },
    "rejected": {
        "client": "Rejected",
    },
}

st.set_page_config(
    page_title="Qawafel | SME Financing",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)

# Keep the simulated bank store alive across Streamlit reruns for this client.
MOCK_BANK_API = st.session_state.setdefault("_mock_bank_api", MockBankAPI())

st.markdown(
    """
    <style>
    :root {
        --qawafel-ink: #171717;
        --qawafel-muted: #777777;
        --qawafel-paper: #F5F5F3;
        --qawafel-border: #E5E5E3;
        --qawafel-accent: #EEEEEC;
    }

    .stApp {
        background: var(--qawafel-paper);
        color: var(--qawafel-ink);
    }

    [data-testid="stSidebar"] {
        background: #FFFFFF;
        border-right: 1px solid var(--qawafel-border);
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: var(--qawafel-muted);
    }

    .sidebar-caption {
        margin-top: 0.3rem;
        margin-bottom: 1.6rem;
        font-size: 0.83rem;
    }

    .st-key-portal-navigation {
        margin: 0.2rem 0 1.5rem;
        padding-bottom: 0.55rem;
        border-bottom: 1px solid var(--qawafel-border);
    }

    .st-key-portal-navigation [role="radiogroup"] {
        gap: 0.45rem;
        flex-wrap: wrap;
    }

    .st-key-portal-navigation [data-testid="stRadioOption"] {
        display: flex;
        align-items: center;
        min-height: 2.65rem;
        padding: 0.55rem 1rem;
        border: 1px solid transparent;
        border-radius: 0.6rem;
        color: var(--qawafel-muted) !important;
        font-weight: 620;
    }

    .st-key-portal-navigation [data-testid="stRadioOption"] * {
        color: inherit !important;
    }

    .st-key-portal-navigation [data-testid="stRadioOption"][data-selected="true"] {
        border-color: #D4D4D1;
        background: #FFFFFF;
        color: var(--qawafel-ink) !important;
        box-shadow: 0 1px 2px rgba(23, 23, 23, 0.06);
    }

    .eyebrow {
        color: var(--qawafel-muted);
        font-size: 0.76rem;
        font-weight: 750;
        letter-spacing: 0.13em;
        text-transform: uppercase;
        margin-bottom: 0.8rem;
    }

    .hero {
        padding: clamp(2rem, 5vw, 4.5rem);
        border: 1px solid var(--qawafel-border);
        border-radius: 1.2rem;
        background: #FFFFFF;
        box-shadow: 0 1rem 2.5rem rgba(23, 23, 23, 0.035);
        margin: 0.7rem 0 2.4rem;
    }

    .hero h1 {
        color: var(--qawafel-ink);
        font-size: clamp(2.4rem, 5.2vw, 4.25rem);
        font-weight: 720;
        letter-spacing: -0.045em;
        line-height: 1.08;
        max-width: 760px;
        margin: 0 0 1rem;
    }

    .hero-copy {
        color: var(--qawafel-muted);
        font-size: 1.12rem;
        line-height: 1.75;
        max-width: 690px;
        margin-bottom: 0;
    }

    .section-heading {
        color: var(--qawafel-ink);
        font-size: 1.45rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.35rem;
    }

    .section-copy {
        color: var(--qawafel-muted);
        margin-bottom: 1.2rem;
    }

    .feature-card {
        min-height: 12.5rem;
        padding: 1.35rem;
        border: 1px solid var(--qawafel-border);
        border-radius: 0.9rem;
        background: #FFFFFF;
    }

    .feature-icon {
        display: inline-flex;
        width: 2.5rem;
        height: 2.5rem;
        align-items: center;
        justify-content: center;
        border-radius: 0.8rem;
        background: var(--qawafel-accent);
        font-size: 1.15rem;
        margin-bottom: 0.8rem;
    }

    .feature-title {
        color: var(--qawafel-ink);
        font-size: 1.03rem;
        font-weight: 700;
        margin-bottom: 0.35rem;
    }

    .feature-copy {
        color: var(--qawafel-muted);
        font-size: 0.92rem;
        line-height: 1.55;
    }

    .assessment-note {
        padding: 1rem 1.1rem;
        border-left: 3px solid #B8B8B5;
        border-radius: 0 0.6rem 0.6rem 0;
        background: #ECECEA;
        color: var(--qawafel-muted);
        font-size: 0.92rem;
    }

    .st-key-company-dashboard {
        padding: clamp(1rem, 2.5vw, 2rem);
        border-radius: 1.1rem;
        background: #FAF8F4;
        color: #29251F;
    }

    .st-key-company-dashboard .company-dashboard-welcome {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1.5rem;
        padding: clamp(1.4rem, 3vw, 2.2rem);
        margin-bottom: 1.4rem;
        border: 1px solid #E8DFD0;
        border-radius: 1rem;
        background: #F3EDE1;
    }

    .st-key-company-dashboard .company-dashboard-eyebrow,
    .st-key-company-dashboard .company-dashboard-label {
        color: #827568;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .st-key-company-dashboard .company-dashboard-welcome h1 {
        margin: 0.35rem 0 0.45rem;
        color: #29251F;
        font-size: clamp(1.8rem, 3.4vw, 2.65rem);
        font-weight: 720;
        letter-spacing: -0.04em;
        line-height: 1.12;
    }

    .st-key-company-dashboard .company-dashboard-welcome p {
        margin: 0;
        color: #827568;
        font-size: 1rem;
    }

    .st-key-company-dashboard .company-dashboard-company-name {
        margin-top: 1rem;
        color: #A77938;
        font-size: 1rem;
        font-weight: 650;
    }

    .st-key-company-dashboard .company-dashboard-section-title {
        margin: 1.65rem 0 0.8rem;
        color: #29251F;
        font-size: 1.2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .st-key-company-dashboard .company-dashboard-info-card,
    .st-key-company-dashboard .company-dashboard-kpi,
    .st-key-company-dashboard .company-dashboard-application-card,
    .st-key-company-dashboard .company-dashboard-action-card,
    .st-key-company-dashboard .company-dashboard-empty {
        height: 100%;
        padding: 1.1rem 1.2rem;
        border: 1px solid #EAE4DA;
        border-radius: 0.85rem;
        background: #FFFFFF;
        box-shadow: 0 0.35rem 1.1rem rgba(63, 48, 29, 0.045);
    }

    .st-key-company-dashboard .company-dashboard-info-card {
        display: flex;
        flex-wrap: wrap;
        gap: 1.5rem 3rem;
        align-items: center;
    }

    .st-key-company-dashboard .company-dashboard-info-value {
        margin-top: 0.28rem;
        color: #29251F;
        font-size: 1rem;
        font-weight: 650;
        overflow-wrap: anywhere;
    }

    .st-key-company-dashboard .company-dashboard-kpi {
        min-height: 7.1rem;
        padding: 1rem 1.1rem;
    }

    .st-key-company-dashboard .company-dashboard-kpi-value {
        margin-top: 0.55rem;
        color: #29251F;
        font-size: 1.8rem;
        font-weight: 720;
        letter-spacing: -0.04em;
    }

    .st-key-company-dashboard .company-dashboard-application-card {
        min-height: 11.5rem;
        padding: 1.1rem;
    }

    .st-key-company-dashboard .company-dashboard-application-id {
        color: #29251F;
        font-weight: 700;
        overflow-wrap: anywhere;
    }

    .st-key-company-dashboard .company-dashboard-application-type {
        min-height: 2.7rem;
        margin: 0.6rem 0;
        color: #827568;
        font-size: 0.9rem;
    }

    .st-key-company-dashboard .company-dashboard-application-meta {
        color: #51483E;
        font-size: 0.87rem;
        line-height: 1.7;
    }

    .st-key-company-dashboard .company-dashboard-status {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        padding: 0.22rem 0.58rem;
        border: 1px solid transparent;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 680;
        line-height: 1.25;
        white-space: nowrap;
    }

    .st-key-company-dashboard .company-dashboard-status--approved {
        border-color: #D7E4D6;
        background: #EDF4EC;
        color: #527A5A;
    }

    .st-key-company-dashboard .company-dashboard-status--review {
        border-color: #E8DCC8;
        background: #F6F0E5;
        color: #8A683A;
    }

    .st-key-company-dashboard .company-dashboard-status--submitted {
        border-color: #EAE4DA;
        background: #F4F1EB;
        color: #766B5E;
    }

    .st-key-company-dashboard .company-dashboard-status--rejected,
    .st-key-company-dashboard .company-dashboard-status--error {
        border-color: #EBD4CF;
        background: #F8EEEB;
        color: #B45C4D;
    }

    .st-key-company-dashboard .company-dashboard-action-card {
        margin-bottom: 0.7rem;
        border-left: 3px solid #A77938;
        box-shadow: none;
    }

    .st-key-company-dashboard .company-dashboard-empty {
        color: #827568;
        text-align: center;
        box-shadow: none;
    }

    .st-key-company-dashboard div.stButton > button[kind="primary"] {
        border: 1px solid #A77938;
        background: #A77938;
        color: #FFFFFF;
        font-weight: 680;
    }

    .st-key-company-dashboard div.stButton > button[kind="primary"]:hover {
        border-color: #8F642F;
        background: #8F642F;
        color: #FFFFFF;
    }

    .st-key-client-financing-flow {
        padding: 0.25rem 0.35rem 1rem;
        color: #29251F;
    }

    .st-key-client-financing-flow .financing-flow-header {
        padding: 1.25rem 1.4rem;
        border: 1px solid #E8DFD0;
        border-radius: 0.9rem;
        background: #F3EDE1;
    }

    .st-key-client-financing-flow .financing-flow-eyebrow {
        color: #827568;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .st-key-client-financing-flow .financing-flow-header h2 {
        margin: 0.35rem 0;
        color: #29251F;
        font-size: 1.65rem;
        letter-spacing: -0.035em;
    }

    .st-key-client-financing-flow .financing-flow-header p {
        margin: 0;
        color: #827568;
    }

    .st-key-client-financing-flow .financing-flow-stepper {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.6rem;
        margin: 1rem 0 0.5rem;
    }

    .st-key-client-financing-flow .financing-flow-step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #827568;
        font-size: 0.84rem;
        font-weight: 650;
    }

    .st-key-client-financing-flow .financing-flow-step-number {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 1.7rem;
        height: 1.7rem;
        border: 1px solid #DDD3C3;
        border-radius: 50%;
        background: #FFFFFF;
        color: #827568;
    }

    .st-key-client-financing-flow .financing-flow-step--current {
        color: #A77938;
    }

    .st-key-client-financing-flow .financing-flow-step--current
    .financing-flow-step-number,
    .st-key-client-financing-flow .financing-flow-step--complete
    .financing-flow-step-number {
        border-color: #A77938;
        background: #A77938;
        color: #FFFFFF;
    }

    .st-key-client-financing-flow [class*="st-key-client-financing-step-"],
    .st-key-client-financing-flow [class*="st-key-client-financing-invoice-upload"],
    .st-key-client-financing-flow [class*="st-key-client-financing-statement-upload"],
    .st-key-client-financing-flow [class*="st-key-client-financing-supporting-upload"] {
        padding: 1.1rem;
        border: 1px solid #EAE4DA;
        border-radius: 0.9rem;
        background: #FFFFFF;
        box-shadow: 0 0.35rem 1.1rem rgba(63, 48, 29, 0.045);
    }

    .st-key-client-financing-flow
    [data-testid="stFileUploader"] [data-testid="stIconMaterial"] {
        font-size: 0 !important;
    }

    .st-key-client-financing-flow
    [data-testid="stFileUploader"] [data-testid="stIconMaterial"]::before {
        content: "↑";
        display: inline-block;
        font-family: Arial, sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        line-height: 1;
    }

    .st-key-client-financing-flow div.stButton > button[kind="primary"],
    .st-key-client-financing-flow button[kind="primaryFormSubmit"] {
        border: 1px solid #A77938;
        background: #A77938;
        color: #FFFFFF;
        font-weight: 680;
    }

    .st-key-client-financing-flow div.stButton > button[kind="primary"]:hover,
    .st-key-client-financing-flow button[kind="primaryFormSubmit"]:hover {
        border-color: #8F642F;
        background: #8F642F;
        color: #FFFFFF;
    }

    .st-key-client-applications-page {
        padding: clamp(1rem, 2.5vw, 2rem);
        border-radius: 1.1rem;
        background: #FAF8F4;
        color: #29251F;
    }

    .st-key-client-applications-page .st-key-client-applications-hero,
    .st-key-client-applications-page .st-key-client-applications-summary {
        padding-bottom: 1.75rem;
    }

    .st-key-client-applications-page .st-key-client-applications-summary
    div[data-testid="stHorizontalBlock"] {
        column-gap: 1.6rem !important;
    }

    .st-key-client-applications-page [class*="st-key-client-application-row-"]
    div[data-testid="stHorizontalBlock"] {
        column-gap: 1.6rem !important;
    }

    .st-key-client-applications-page [class*="st-key-client-application-row-"] {
        padding-bottom: 1.5rem;
    }

    .st-key-client-applications-page .applications-page-header {
        padding: clamp(1.35rem, 3vw, 2rem);
        border: 1px solid #E8DFD0;
        border-radius: 1rem;
        background: #F3EDE1;
    }

    .st-key-client-applications-page .applications-page-eyebrow,
    .st-key-client-applications-page .applications-page-label {
        color: #827568;
        font-size: 0.76rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }

    .st-key-client-applications-page .applications-page-header h1 {
        margin: 0.35rem 0 0.45rem;
        color: #29251F;
        font-size: clamp(1.8rem, 3.4vw, 2.55rem);
        font-weight: 720;
        letter-spacing: -0.04em;
        line-height: 1.12;
    }

    .st-key-client-applications-page .applications-page-header p {
        margin: 0;
        color: #827568;
        font-size: 1rem;
    }

    .st-key-client-applications-page .applications-page-section-title {
        margin: 0 0 0.8rem;
        color: #29251F;
        font-size: 1.2rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }

    .st-key-client-applications-page .applications-summary-card,
    .st-key-client-applications-page .applications-record-card,
    .st-key-client-applications-page .applications-empty-state,
    .st-key-client-applications-page .applications-draft-notice {
        height: 100%;
        padding: 1.5rem 1.6rem;
        border: 1px solid #EAE4DA;
        border-radius: 0.85rem;
        background: #FFFFFF;
        box-shadow: 0 0.35rem 1.1rem rgba(63, 48, 29, 0.045);
    }

    .st-key-client-applications-page .applications-summary-card {
        min-height: 6.6rem;
    }

    .st-key-client-applications-page .applications-summary-value {
        margin-top: 0.45rem;
        color: #29251F;
        font-size: 1.8rem;
        font-weight: 720;
        letter-spacing: -0.04em;
    }

    .st-key-client-applications-page .applications-list-tools {
        margin: 0.3rem 0 0.75rem;
    }

    .st-key-client-applications-page .applications-record-card {
        min-height: 13.5rem;
        padding: 1.5rem 1.6rem;
    }

    .st-key-client-applications-page .applications-record-top {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.6rem;
        flex-wrap: wrap;
    }

    .st-key-client-applications-page .applications-record-reference {
        color: #29251F;
        font-size: 0.95rem;
        font-weight: 700;
        overflow-wrap: anywhere;
    }

    .st-key-client-applications-page .applications-record-type {
        min-height: 2.5rem;
        margin: 0.6rem 0;
        color: #51483E;
        font-size: 0.94rem;
        font-weight: 620;
    }

    .st-key-client-applications-page .applications-record-meta {
        display: flex;
        justify-content: space-between;
        gap: 0.75rem;
        color: #827568;
        font-size: 0.83rem;
        line-height: 1.6;
        flex-wrap: wrap;
    }

    .st-key-client-applications-page .applications-status-badge {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        padding: 0.22rem 0.58rem;
        border: 1px solid transparent;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 680;
        line-height: 1.25;
        white-space: nowrap;
    }

    .st-key-client-applications-page .applications-status-badge--approved,
    .st-key-client-applications-page .client-status-badge--approved {
        border-color: #D7E4D6;
        background: #EDF4EC;
        color: #527A5A;
    }

    .st-key-client-applications-page .applications-status-badge--review,
    .st-key-client-applications-page .client-status-badge--under-review,
    .st-key-client-applications-page .client-status-badge--more-information {
        border-color: #E8DCC8;
        background: #F6F0E5;
        color: #8A683A;
    }

    .st-key-client-applications-page .applications-status-badge--submitted,
    .st-key-client-applications-page .client-status-badge--submitted,
    .st-key-client-applications-page .client-status-badge--draft {
        border-color: #EAE4DA;
        background: #F4F1EB;
        color: #766B5E;
    }

    .st-key-client-applications-page .applications-status-badge--rejected,
    .st-key-client-applications-page .client-status-badge--rejected {
        border-color: #EBD4CF;
        background: #F8EEEB;
        color: #B45C4D;
    }

    .st-key-client-applications-page .applications-empty-state {
        color: #827568;
        text-align: center;
        box-shadow: none;
    }

    .st-key-client-applications-page .applications-draft-notice {
        margin: 0.5rem 0 0.75rem;
        box-shadow: none;
    }

    .st-key-client-applications-page div.stButton > button[kind="primary"] {
        border: 1px solid #A77938;
        background: #A77938;
        color: #FFFFFF;
        font-weight: 680;
    }

    .st-key-client-applications-page div.stButton > button[kind="primary"]:hover {
        border-color: #8F642F;
        background: #8F642F;
        color: #FFFFFF;
    }

    .client-status-badge,
    .client-status-badge--draft {
        display: inline-flex;
        align-items: center;
        width: fit-content;
        padding: 0.22rem 0.58rem;
        border: 1px solid transparent;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 650;
        line-height: 1.2;
        white-space: nowrap;
        color: #52525B;
        background: #F4F4F5;
        border-color: #E4E4E7;
    }

    .client-status-badge--submitted {
        color: #1D4ED8;
        background: #EFF6FF;
        border-color: #DBEAFE;
    }

    .client-status-badge--under-review {
        color: #B45309;
        background: #FFF7ED;
        border-color: #FED7AA;
    }

    .client-status-badge--more-information {
        color: #7E22CE;
        background: #FAF5FF;
        border-color: #E9D5FF;
    }

    .client-status-badge--approved {
        color: #15803D;
        background: #F0FDF4;
        border-color: #BBF7D0;
    }

    .client-status-badge--rejected {
        color: #B91C1C;
        background: #FEF2F2;
        border-color: #FECACA;
    }

    div.stButton > button[kind="primary"] {
        min-height: 3rem;
        padding: 0.55rem 1.2rem;
        border: 0;
        border-radius: 0.55rem;
        background: #171717;
        color: #FFFFFF;
        font-weight: 650;
    }

    div.stButton > button[kind="primary"]:hover {
        background: #333333;
        color: #FFFFFF;
        border: 0;
    }

    footer {
        visibility: hidden;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def _clear_application_results() -> None:
    """Remove prior application data and every derived result."""
    for key in (
        "application_id",
        "application_context",
        "company_profile",
        "invoices",
        "bank_transactions",
        "pdf_extraction_results",
        "validation_report",
        "financial_analysis_result",
        "invoice_matching_result",
        "financial_insights_result",
        "financial_analysis_application_id",
        "_financial_analysis_inputs",
        "_financial_analysis_application_id",
    ):
        st.session_state.pop(key, None)


def _remember_client_navigation() -> None:
    """Keep the last client page when its navigation widget is hidden."""
    st.session_state["last_client_navigation"] = st.session_state[
        "client_navigation"
    ]


def _render_issues(title: str, issues: list[dict], issue_type: str) -> None:
    """Display validator issues with their check name, count, and guidance."""
    if not issues:
        return

    total = sum(issue.get("count", 0) for issue in issues)
    with st.expander(f"{title} ({total})", expanded=issue_type == "error"):
        for issue in issues:
            st.markdown(
                f"- **{issue.get('check', 'Validation check')}** "
                f"({issue.get('count', 0)}): {issue.get('message', '')}"
            )


def _render_financing_application() -> None:
    """Collect a financing request and process its uploaded company data."""
    st.markdown(
        '<div class="eyebrow">Financing application</div>',
        unsafe_allow_html=True,
    )
    st.title("طلب تمويل")
    st.markdown(
        "Complete the financing request and provide company records for local "
        "financial analysis. This prototype does not submit applications to a bank."
    )

    with st.container(border=True):
        st.subheader("A. Financing Request Information")
        request_columns = st.columns(2)
        with request_columns[0]:
            requested_amount = st.number_input(
                "Requested financing amount",
                min_value=0.0,
                value=0.0,
                step=1000.0,
                format="%.2f",
                key="requested_amount_input",
            )
            requested_currency = st.text_input(
                "Currency",
                value="SAR",
                key="requested_currency_input",
            )
            financing_type = st.text_input(
                "Financing type",
                placeholder="Enter the financing type you are requesting",
                help="Applicant-provided type; this prototype does not define bank products.",
                key="financing_type_input",
            )
        with request_columns[1]:
            financing_purpose = st.text_input(
                "Financing purpose",
                placeholder="Describe how the funds will be used",
                help="Separate from financing type. No official document policy is configured.",
                key="financing_purpose_input",
            )
            requested_tenure_months = st.number_input(
                "Requested tenure (months)",
                min_value=0,
                value=0,
                step=1,
                key="requested_tenure_input",
            )
            repayment_frequency = st.selectbox(
                "Repayment frequency / schedule",
                ["Select frequency", "Monthly", "Quarterly", "Semi-annual", "Annual", "Other"],
                key="repayment_frequency_input",
            )

    with st.container(border=True):
        st.subheader("B. Repayment and Financing Information")
        repayment_columns = st.columns(2)
        with repayment_columns[0]:
            financing_cost_amount = st.number_input(
                "Financing cost / fees (optional)",
                min_value=0.0,
                value=None,
                step=100.0,
                format="%.2f",
                help="Leave blank if bank pricing or fees are not known.",
                key="financing_cost_input",
            )
            declare_capacity = st.checkbox(
                "Provide a borrower-declared repayment capacity",
                value=False,
                key="declare_repayment_capacity_input",
            )
        with repayment_columns[1]:
            capacity_amount = st.number_input(
                "Declared repayment capacity amount",
                min_value=0.0,
                value=None,
                step=100.0,
                format="%.2f",
                disabled=not declare_capacity,
                key="repayment_capacity_amount_input",
            )
            capacity_currency = st.text_input(
                "Repayment capacity currency",
                value="SAR",
                disabled=not declare_capacity,
                key="repayment_capacity_currency_input",
            )
            capacity_period = st.selectbox(
                "Repayment capacity measurement period",
                ["Monthly", "Quarterly", "Annual"],
                disabled=not declare_capacity,
                key="repayment_capacity_period_input",
            )
        st.caption(
            "Declared capacity is borrower-provided, not bank-verified, and "
            "does not establish affordability."
        )

    with st.container(border=True):
        st.subheader("C. Existing Financial Obligations")
        existing_financing_answer = st.radio(
            "Does the company currently have existing financing or financial obligations?",
            ["Select an answer", "Yes", "No"],
            horizontal=True,
            key="existing_financing_answer_input",
        )
        obligation_values: dict[str, object] = {}
        if existing_financing_answer == "Yes":
            obligation_columns = st.columns(2)
            with obligation_columns[0]:
                obligation_provider = st.text_input(
                    "Financing provider",
                    key="obligation_provider_input",
                )
                obligation_balance = st.number_input(
                    "Outstanding balance",
                    min_value=0.0,
                    value=None,
                    step=1000.0,
                    format="%.2f",
                    key="obligation_balance_input",
                )
            with obligation_columns[1]:
                obligation_monthly_repayment = st.number_input(
                    "Monthly repayment",
                    min_value=0.0,
                    value=None,
                    step=100.0,
                    format="%.2f",
                    key="obligation_monthly_repayment_input",
                )
                obligation_remaining_tenure = st.number_input(
                    "Remaining tenure (months)",
                    min_value=0,
                    value=0,
                    step=1,
                    key="obligation_remaining_tenure_input",
                )
            obligation_values = {
                "provider": obligation_provider.strip() or None,
                "outstanding_balance": obligation_balance,
                "monthly_repayment": obligation_monthly_repayment,
                "remaining_tenure_months": (
                    obligation_remaining_tenure
                    if obligation_remaining_tenure > 0 else None
                ),
                "verification_status": "borrower_declared",
            }
            st.caption(
                "These details remain borrower-declared. Supporting documents "
                "are not independently verified by this prototype."
            )

    with st.container(border=True):
        st.subheader("D. Required Company Documents")
        st.caption(
            "Accepted formats: Company Profile JSON, Invoices XLSX, "
            "Bank Transactions XLSX. All three are required."
        )
        company_file = st.file_uploader(
            "Company Profile — JSON (required)",
            type=["json"],
            help="Must include company_name, cr_number, industry, and currency.",
            key="company_profile_upload",
        )
        invoice_file = st.file_uploader(
            "Invoices — XLSX (required)",
            type=["xlsx"],
            help="Upload a workbook with the required invoice columns.",
            key="invoices_upload",
        )
        transaction_file = st.file_uploader(
            "Bank Transactions — XLSX (required)",
            type=["xlsx"],
            help="Upload a workbook with the required bank transaction columns.",
            key="bank_transactions_upload",
        )
        pdf_file = st.file_uploader(
            "Supporting Documents — PDF (optional)",
            type=["pdf"],
            help="Optional text-readable PDF. Scanned PDFs may require OCR.",
            key="supporting_pdf_upload",
        )

    if st.button(
        "Process Financing Application",
        type="primary",
        use_container_width=True,
        key="process_financing_application",
    ):
        _clear_application_results()
        st.session_state["processing_status"] = "processing"
        form_errors = []
        if requested_amount <= 0:
            form_errors.append("Enter a requested financing amount greater than zero.")
        if not requested_currency.strip():
            form_errors.append("Enter the requested financing currency.")
        if not financing_type.strip():
            form_errors.append("Enter the financing type.")
        if not financing_purpose.strip():
            form_errors.append("Enter the financing purpose.")
        if requested_tenure_months <= 0:
            form_errors.append("Enter a requested tenure greater than zero.")
        if repayment_frequency == "Select frequency":
            form_errors.append("Select a repayment frequency or schedule.")
        if existing_financing_answer == "Select an answer":
            form_errors.append("Answer the existing-financing declaration.")
        if declare_capacity:
            if capacity_amount is None:
                form_errors.append(
                    "Enter the declared repayment capacity amount or uncheck its declaration."
                )
            if not capacity_currency.strip():
                form_errors.append("Enter the repayment capacity currency.")

        required_uploads = {
            "Company Profile (JSON)": company_file,
            "Invoices (XLSX)": invoice_file,
            "Bank Transactions (XLSX)": transaction_file,
        }
        missing_uploads = [
            label for label, uploaded_file in required_uploads.items()
            if uploaded_file is None
        ]
        if form_errors or missing_uploads:
            st.session_state["processing_status"] = "error"
            for error in form_errors:
                st.error(error)
            if missing_uploads:
                st.error(
                    "Upload all required documents before processing: "
                    + ", ".join(missing_uploads)
                    + "."
                )
        else:
            extraction_errors = []
            company_profile = None
            invoices = None
            bank_transactions = None
            pdf_results = None
            try:
                with st.spinner("Processing documents and preparing the assessment..."):
                    with TemporaryDirectory(prefix="qawafel_upload_") as temporary_dir:
                        temporary_path = Path(temporary_dir)
                        for label, uploaded_file, filename, loader in (
                            ("Company Profile", company_file, "company_profile.json", load_company_profile),
                            ("Invoices", invoice_file, "invoices.xlsx", load_invoices),
                            ("Bank Transactions", transaction_file, "bank_transactions.xlsx", load_bank_transactions),
                        ):
                            try:
                                file_path = temporary_path / filename
                                file_path.write_bytes(uploaded_file.getvalue())
                                loaded = loader(file_path)
                                if label == "Company Profile":
                                    company_profile = loaded
                                elif label == "Invoices":
                                    invoices = loaded
                                else:
                                    bank_transactions = loaded
                            except Exception as exc:
                                extraction_errors.append(
                                    f"{label}: unable to extract the uploaded file "
                                    f"({type(exc).__name__}: {exc})."
                                )

                        if pdf_file is not None:
                            try:
                                pdf_path = temporary_path / "supporting_document.pdf"
                                pdf_path.write_bytes(pdf_file.getvalue())
                                pdf_results = extract_pdf_text(pdf_path)
                            except Exception as exc:
                                extraction_errors.append(
                                    "Supporting PDF: unable to extract readable text "
                                    f"({type(exc).__name__}: {exc})."
                                )

                    if extraction_errors:
                        st.session_state["processing_status"] = "error"
                        for error in extraction_errors:
                            st.error(error)
                    else:
                        validation_report = validate_dataset({
                            "company": company_profile,
                            "invoices": invoices,
                            "bank_transactions": bank_transactions,
                        })
                        matching_result = match_invoices_to_transactions(
                            invoices,
                            bank_transactions,
                        )
                        financial_analysis = analyze_financial_data(
                            invoices,
                            bank_transactions,
                            matching_result,
                        )
                        application_id = str(uuid4())
                        purpose_code = " ".join(
                            financing_purpose.strip().split()
                        ).casefold()
                        repayment_capacity = (
                            {
                                "amount": capacity_amount,
                                "currency": capacity_currency.strip(),
                                "measurement_period": capacity_period.casefold(),
                                "verification_status": "borrower_declared",
                                "source": "Applicant declaration",
                            }
                            if declare_capacity else None
                        )
                        financing_cost = (
                            {"amount": financing_cost_amount}
                            if financing_cost_amount is not None else None
                        )
                        existing_financing = (
                            {
                                "declared": True,
                                "exists": True,
                                **obligation_values,
                            }
                            if existing_financing_answer == "Yes"
                            else {
                                "declared": True,
                                "exists": False,
                                "verification_status": "borrower_declared",
                            }
                        )
                        uploaded_documents = [
                            {"document_type": "company_profile", "file_name": company_file.name},
                            {"document_type": "invoices", "file_name": invoice_file.name},
                            {"document_type": "bank_transactions", "file_name": transaction_file.name},
                        ]
                        if pdf_file is not None:
                            uploaded_documents.append({
                                "document_type": "supporting_pdf",
                                "file_name": pdf_file.name,
                            })
                        application_context = {
                            "application_id": application_id,
                            "requested_amount": requested_amount,
                            "requested_currency": requested_currency.strip(),
                            "financial_currency": company_profile.get("currency"),
                            "requested_tenure_months": requested_tenure_months,
                            "financing_type": financing_type.strip(),
                            "financing_purpose_code": purpose_code,
                            "financing_purpose_description": financing_purpose.strip(),
                            "repayment_schedule": {
                                "frequency": repayment_frequency.casefold(),
                            },
                            "financing_cost": financing_cost,
                            "repayment_capacity": repayment_capacity,
                            "existing_financing": existing_financing,
                            "uploaded_documents": uploaded_documents,
                        }
                        insights_result = generate_financial_insights(
                            financial_analysis,
                            matching_result,
                            validation_report,
                            application_context,
                        )
                        st.session_state["application_id"] = application_id
                        st.session_state["application_context"] = application_context
                        st.session_state["company_profile"] = company_profile
                        st.session_state["invoices"] = invoices
                        st.session_state["bank_transactions"] = bank_transactions
                        st.session_state["pdf_extraction_results"] = pdf_results
                        st.session_state["validation_report"] = validation_report
                        st.session_state["invoice_matching_result"] = matching_result
                        st.session_state["financial_analysis_result"] = financial_analysis
                        st.session_state["financial_insights_result"] = insights_result
                        st.session_state["financial_analysis_application_id"] = application_id
                        st.session_state["_financial_analysis_inputs"] = (
                            invoices,
                            bank_transactions,
                        )
                        st.session_state["_financial_analysis_application_id"] = application_id
                        st.session_state["financial_analysis_application_id"] = application_id
                        st.session_state["processing_status"] = "completed"
            except Exception as exc:
                st.session_state["processing_status"] = "error"
                st.error(
                    "The application could not be analyzed "
                    f"({type(exc).__name__}: {exc}). Correct the inputs and try again."
                )

    processing_status = st.session_state.get("processing_status")
    if processing_status == "processing":
        st.info("Your documents are being analyzed locally.")
    elif processing_status == "error":
        st.warning(
            "No results are available for this processing attempt. Previous "
            "application results were cleared."
        )

    if processing_status == "completed":
        company_profile = st.session_state["company_profile"]
        invoices = st.session_state["invoices"]
        bank_transactions = st.session_state["bank_transactions"]
        validation_report = st.session_state["validation_report"]
        validation_summary = validation_report["summary"]

        st.markdown("---")
        st.subheader("Processing Summary")
        summary_columns = st.columns(5)
        summary_values = [
            ("Application ID", st.session_state["application_id"]),
            ("Company", company_profile.get("company_name", "Not provided")),
            ("Invoices", f"{len(invoices):,}"),
            ("Bank transactions", f"{len(bank_transactions):,}"),
            (
                "Validation / errors",
                f"{'Valid' if validation_summary['is_valid'] else 'Needs attention'}"
                f" / {validation_summary['error_count']}",
            ),
        ]
        for column, (label, value) in zip(summary_columns, summary_values):
            with column:
                st.metric(label, value)
        pdf_results = st.session_state.get("pdf_extraction_results")
        if pdf_results is not None:
            st.caption(
                f"Supporting PDF text extracted from {pdf_results['total_pages']} page(s)."
            )
        if validation_summary["is_valid"]:
            st.success("The documents were processed and passed validation.")
        else:
            st.error(
                "Documents were extracted, but validation found errors. "
                "Review and correct them before relying on the analysis."
            )
        st.caption(
            f"Validation warnings: {validation_summary['warning_count']}. "
            "Document processing and financial analysis are completed locally."
        )
        st.subheader("Validation Details")
        invoice_report = validation_report["invoices"]
        bank_report = validation_report["bank_transactions"]
        _render_issues("Invoice errors", invoice_report.get("errors", []), "error")
        _render_issues("Invoice warnings", invoice_report.get("warnings", []), "warning")
        _render_issues("Bank transaction errors", bank_report.get("errors", []), "error")
        _render_issues(
            "Bank transaction warnings",
            bank_report.get("warnings", []),
            "warning",
        )
        for issue in validation_summary.get("errors", []):
            st.error(
                f"{issue.get('message', 'Dataset validation error')} "
                f"(count: {issue.get('count', 0)})"
            )


def _save_client_application_draft(
    pending: dict | None,
    form_data: dict,
    uploaded_file_contents: dict,
    uploaded_file_names: dict,
    step: int,
) -> dict:
    """Persist an unsubmitted request without retaining stale analysis results."""
    company_profile = st.session_state.setdefault(
        "client_company_profile",
        deepcopy(CLIENT_DEMO_COMPANY_PROFILE),
    )
    draft = dict(pending or {})
    company_snapshot = deepcopy(
        draft.get("company_profile_snapshot") or company_profile
    )
    document_specs = (
        ("invoices", "invoices", True),
        ("bank_statement_pdf", "bank_statement_pdf", True),
        ("supporting_pdf", "supporting_pdf", False),
    )
    documents = [
        {
            "document_type": document_type,
            "file_name": uploaded_file_names[upload_key],
            "required": required,
        }
        for document_type, upload_key, required in document_specs
        if uploaded_file_names.get(upload_key)
    ]
    draft.update({
        "draft_id": draft.get("draft_id") or f"DRAFT-{uuid4().hex[:12].upper()}",
        "company_name": company_snapshot.get("company_name", "Company"),
        "company_profile_snapshot": company_snapshot,
        "form_data": form_data,
        **form_data,
        "created_at": draft.get("created_at") or datetime.now().isoformat(timespec="seconds"),
        "lifecycle_state": "draft",
        "analysis_stale": True,
        "creation_step": step,
        "uploaded_file_contents": uploaded_file_contents,
        "uploaded_file_names": uploaded_file_names,
        "documents": documents,
    })
    draft.pop("processing_error", None)
    for key in (
        "application_context",
        "pdf_extraction_results",
        "supporting_pdf_extraction_results",
        "invoices",
        "bank_transactions",
        "validation_report",
        "invoice_matching_result",
        "financial_analysis_result",
        "financial_insights_result",
    ):
        draft.pop(key, None)
    st.session_state["client_pending_application"] = draft
    return draft


def _analyze_client_application_draft(draft: dict) -> dict:
    """Process the saved invoice workbook and bank-statement PDF."""
    form_data = draft["form_data"]
    uploads = draft.get("uploaded_file_contents", {})
    upload_names = draft.get("uploaded_file_names", {})
    invoice_content = uploads.get("invoices")
    statement_content = uploads.get("bank_statement_pdf")
    if not invoice_content or not statement_content:
        raise ValueError(
            "Upload a Sales Invoices Excel file and a Bank Statements PDF "
            "before processing."
        )

    with TemporaryDirectory(prefix="qawafel_client_application_") as folder:
        temporary_path = Path(folder)
        invoices_path = temporary_path / "invoices.xlsx"
        statement_path = temporary_path / "bank_statement.pdf"
        invoices_path.write_bytes(invoice_content)
        statement_path.write_bytes(statement_content)
        invoices = load_invoices(invoices_path)
        transactions = load_bank_transactions_pdf(statement_path)
        statement_extraction = extract_pdf_text(statement_path)
        supporting_pdf_extraction = None
        supporting_pdf_content = uploads.get("supporting_pdf")
        if supporting_pdf_content:
            supporting_path = temporary_path / "supporting_document.pdf"
            supporting_path.write_bytes(supporting_pdf_content)
            supporting_pdf_extraction = extract_pdf_text(supporting_path)

    company_snapshot = deepcopy(draft["company_profile_snapshot"])
    validation_report = validate_dataset({
        "company": company_snapshot,
        "invoices": invoices,
        "bank_transactions": transactions,
    })
    matching_result = match_invoices_to_transactions(invoices, transactions)
    financial_analysis = analyze_financial_data(
        invoices,
        transactions,
        matching_result,
    )
    capacity_amount = form_data.get("capacity_amount")
    financing_cost_amount = form_data.get("financing_cost_amount")
    existing_answer = form_data.get("existing_financing_answer")
    obligation_provider = form_data.get("obligation_provider")
    obligation_balance = form_data.get("obligation_balance")
    obligation_monthly_repayment = form_data.get("obligation_monthly_repayment")
    obligation_remaining_tenure = form_data.get("obligation_remaining_tenure")
    repayment_capacity = (
        {
            "amount": capacity_amount,
            "currency": str(form_data.get("capacity_currency") or "").strip(),
            "measurement_period": str(
                form_data.get("capacity_period", "Monthly")
            ).casefold(),
            "verification_status": "borrower_declared",
            "source": "Applicant declaration",
        }
        if capacity_amount is not None else None
    )
    financing_cost = (
        {"amount": financing_cost_amount}
        if financing_cost_amount is not None else None
    )
    existing_financing = (
        {
            "declared": True,
            "exists": True,
            "provider": str(obligation_provider or "").strip() or None,
            "outstanding_balance": obligation_balance,
            "monthly_repayment": obligation_monthly_repayment,
            "remaining_tenure_months": (
                obligation_remaining_tenure
                if obligation_remaining_tenure and obligation_remaining_tenure > 0
                else None
            ),
            "verification_status": "borrower_declared",
            "supporting_evidence": (
                [upload_names["supporting_pdf"]]
                if upload_names.get("supporting_pdf") else None
            ),
        }
        if existing_answer == "Yes"
        else {
            "declared": True,
            "exists": False,
            "verification_status": "borrower_declared",
        }
    )
    application_context = {
        "application_id": draft["draft_id"],
        "requested_amount": form_data["requested_amount"],
        "requested_currency": form_data["requested_currency"],
        "financial_currency": company_snapshot.get("currency"),
        "requested_tenure_months": form_data["requested_tenure_months"],
        "financing_type": form_data["financing_type"],
        "financing_purpose_code": " ".join(
            form_data["financing_purpose"].split()
        ).casefold(),
        "financing_purpose_description": form_data["financing_purpose"],
        "repayment_schedule": {
            "frequency": form_data["repayment_frequency"].casefold(),
        },
        "financing_cost": financing_cost,
        "repayment_capacity": repayment_capacity,
        "existing_financing": existing_financing,
        "uploaded_documents": [
            {"document_type": document["document_type"]}
            for document in draft.get("documents", [])
        ],
    }
    insights = generate_financial_insights(
        financial_analysis,
        matching_result,
        validation_report,
        application_context,
    )
    return {
        **draft,
        "lifecycle_state": "analysis_ready",
        "analysis_stale": False,
        "application_context": application_context,
        "pdf_extraction_results": statement_extraction,
        "supporting_pdf_extraction_results": supporting_pdf_extraction,
        "invoices": invoices,
        "bank_transactions": transactions,
        "validation_report": validation_report,
        "invoice_matching_result": matching_result,
        "financial_analysis_result": financial_analysis,
        "financial_insights_result": insights,
    }


@st.dialog("Request Financing", width="large")
def _request_financing_dialog() -> None:
    """Render the three-step financing request and document-processing flow."""
    pending = st.session_state.get("client_pending_application")
    company_profile = st.session_state.setdefault(
        "client_company_profile",
        deepcopy(CLIENT_DEMO_COMPANY_PROFILE),
    )
    form_data = dict((pending or {}).get("form_data", {}))
    if pending and not form_data:
        form_data = {
            field: pending.get(field)
            for field in (
                "requested_amount", "requested_currency", "financing_type",
                "financing_purpose", "requested_tenure_months",
                "repayment_frequency", "financing_cost_amount",
                "capacity_amount", "capacity_currency", "capacity_period",
                "existing_financing_answer", "obligation_provider",
                "obligation_balance", "obligation_monthly_repayment",
                "obligation_remaining_tenure",
            )
            if field in pending
        }
    saved_uploads = dict((pending or {}).get("uploaded_file_contents", {}))
    saved_names = dict((pending or {}).get("uploaded_file_names", {}))
    for document in (pending or {}).get("documents", []):
        if isinstance(document, dict) and document.get("file_name"):
            saved_names.setdefault(
                document.get("document_type"), document["file_name"]
            )
    generation = st.session_state.setdefault("client_form_generation", 0)

    def field_key(name: str) -> str:
        return f"client_{name}_{generation}"

    def keep_request_dialog_open() -> None:
        st.session_state["client_open_request_dialog"] = True

    defaults = {
        "requested_amount": 0.0,
        "requested_currency": company_profile.get("currency", "SAR"),
        "financing_type": "",
        "financing_purpose": "",
        "requested_tenure_months": 0,
        "repayment_frequency": "Select frequency",
        "financing_cost_amount": None,
        "capacity_amount": None,
        "capacity_currency": company_profile.get("currency", "SAR"),
        "capacity_period": "Monthly",
        "existing_financing_answer": "Select an answer",
        "obligation_provider": "",
        "obligation_balance": None,
        "obligation_monthly_repayment": None,
        "obligation_remaining_tenure": 0,
    }
    widget_names = {
        "requested_amount": "requested_amount",
        "requested_currency": "requested_currency",
        "financing_type": "financing_type",
        "financing_purpose": "financing_purpose",
        "requested_tenure_months": "requested_tenure",
        "repayment_frequency": "repayment_frequency",
        "financing_cost_amount": "financing_cost",
        "capacity_amount": "capacity_amount",
        "capacity_currency": "capacity_currency",
        "capacity_period": "capacity_period",
        "existing_financing_answer": "existing_financing_answer",
        "obligation_provider": "obligation_provider",
        "obligation_balance": "obligation_balance",
        "obligation_monthly_repayment": "obligation_monthly_repayment",
        "obligation_remaining_tenure": "obligation_remaining_tenure",
    }
    def current_form_data() -> dict:
        return {
            data_name: st.session_state.get(field_key(key_name), defaults[data_name])
            for data_name, key_name in widget_names.items()
        }

    def persist_uploads() -> tuple[dict, dict]:
        contents = dict(saved_uploads)
        names = dict(saved_names)
        for document_type, key_name in (
            ("invoices", "invoices_upload"),
            ("bank_statement_pdf", "bank_statement_upload"),
            ("supporting_pdf", "supporting_pdf_upload"),
        ):
            uploaded = st.session_state.get(field_key(key_name))
            if uploaded is not None:
                contents[document_type] = uploaded.getvalue()
                names[document_type] = uploaded.name
        if not st.session_state.get(field_key("keep_saved_supporting"), True):
            if st.session_state.get(field_key("supporting_pdf_upload")) is None:
                contents.pop("supporting_pdf", None)
                names.pop("supporting_pdf", None)
        return contents, names

    def save_step(target_step: int, errors: list[str] | None = None) -> None:
        contents, names = persist_uploads()
        draft = _save_client_application_draft(
            pending,
            dict((pending or {}).get("form_data") or form_data),
            contents,
            names,
            target_step,
        )
        draft["step_errors"] = errors or []
        st.session_state["client_pending_application"] = draft
        st.session_state["client_open_request_dialog"] = True

    def advance_details() -> None:
        values = current_form_data()
        errors = []
        if values["requested_amount"] <= 0:
            errors.append("Enter a requested amount greater than zero.")
        if not str(values["requested_currency"]).strip():
            errors.append("Enter a currency.")
        if not str(values["financing_type"]).strip():
            errors.append("Enter a financing type.")
        if not str(values["financing_purpose"]).strip():
            errors.append("Enter a financing purpose.")
        if values["requested_tenure_months"] <= 0:
            errors.append("Enter a financing tenure greater than zero.")
        if values["repayment_frequency"] == "Select frequency":
            errors.append("Select a repayment frequency.")
        if values["existing_financing_answer"] == "Select an answer":
            errors.append("Declare whether existing financing is present.")
        draft = _save_client_application_draft(
            pending, values, saved_uploads, saved_names, 1 if errors else 2
        )
        draft["step_errors"] = errors
        st.session_state["client_pending_application"] = draft
        st.session_state["client_open_request_dialog"] = True

    def advance_documents() -> None:
        contents, names = persist_uploads()
        errors = []
        if not contents.get("invoices"):
            errors.append("Upload the required Sales Invoices Excel file.")
        if not contents.get("bank_statement_pdf"):
            errors.append("Upload the required Bank Statements PDF file.")
        draft = _save_client_application_draft(
            pending,
            dict((pending or {}).get("form_data") or form_data),
            contents,
            names,
            2 if errors else 3,
        )
        draft["step_errors"] = errors
        st.session_state["client_pending_application"] = draft
        st.session_state["client_open_request_dialog"] = True

    def back_to_details() -> None:
        save_step(1)

    def back_to_documents() -> None:
        save_step(2)

    step = int((pending or {}).get("creation_step", 1))
    if step not in (1, 2, 3):
        step = 1
    step_titles = ("Financing Details", "Document Upload", "Review & Process")
    indicator = "".join(
        '<div class="financing-flow-step financing-flow-step--{}">'
        '<span class="financing-flow-step-number">{}</span><span>{}</span></div>'.format(
            "current" if step == index else "complete" if step > index else "upcoming",
            index,
            title,
        )
        for index, title in enumerate(step_titles, start=1)
    )
    with st.container(key="client-financing-flow"):
        st.markdown(
            '<div class="financing-flow-header"><div class="financing-flow-eyebrow">'
            'Financing application</div><h2>New Financing Application</h2>'
            '<p>Complete each step, then process your documents when you are ready.</p>'
            '</div>'
            f'<div class="financing-flow-stepper">{indicator}</div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Registered company: {company_profile.get('company_name', 'Company')} · "
            f"{company_profile.get('industry', 'Industry not provided')} · "
            f"{company_profile.get('currency', 'SAR')}"
        )
        for error in (pending or {}).get("step_errors", []):
            st.error(error)

        if (
            pending
            and pending.get("lifecycle_state") == "analysis_ready"
            and not pending.get("analysis_stale")
        ):
            _render_client_analysis_preview()
            return

        if step == 1:
            with st.container(key="client-financing-step-details"):
                with st.form("client_financing_request_form", clear_on_submit=False):
                    st.subheader("Step 1 — Financing Details")
                    amount_column, currency_column = st.columns(2)
                    with amount_column:
                        st.number_input(
                            "Requested Amount", min_value=0.0,
                            value=float(form_data.get("requested_amount", 0.0) or 0.0),
                            step=1000.0, key=field_key("requested_amount"),
                        )
                        st.text_input(
                            "Financing Type", value=form_data.get("financing_type", ""),
                            key=field_key("financing_type"),
                        )
                        st.number_input(
                            "Financing Tenure (months)", min_value=0,
                            value=int(form_data.get("requested_tenure_months", 0) or 0),
                            step=1, key=field_key("requested_tenure"),
                        )
                    with currency_column:
                        st.text_input(
                            "Currency", value=form_data.get(
                                "requested_currency", company_profile.get("currency", "SAR")
                            ), key=field_key("requested_currency"),
                        )
                        st.text_input(
                            "Financing Purpose", value=form_data.get("financing_purpose", ""),
                            key=field_key("financing_purpose"),
                        )
                        repayment_options = [
                            "Select frequency", "Monthly", "Quarterly",
                            "Semi-annual", "Annual", "Other",
                        ]
                        saved_frequency = form_data.get(
                            "repayment_frequency", "Select frequency"
                        )
                        st.selectbox(
                            "Repayment Frequency", repayment_options,
                            index=repayment_options.index(saved_frequency)
                            if saved_frequency in repayment_options else 0,
                            key=field_key("repayment_frequency"),
                        )
                    st.markdown("#### Repayment Information")
                    st.number_input(
                        "Financing Cost (optional)", min_value=0.0,
                        value=form_data.get("financing_cost_amount"), step=100.0,
                        key=field_key("financing_cost"),
                    )
                    capacity_column, capacity_details_column = st.columns(2)
                    with capacity_column:
                        st.number_input(
                            "Borrower-declared Repayment Capacity (optional)",
                            min_value=0.0, value=form_data.get("capacity_amount"),
                            step=100.0, key=field_key("capacity_amount"),
                        )
                    with capacity_details_column:
                        st.text_input(
                            "Capacity Currency", value=form_data.get(
                                "capacity_currency", company_profile.get("currency", "SAR")
                            ), key=field_key("capacity_currency"),
                        )
                        capacity_periods = ["Monthly", "Quarterly", "Annual"]
                        saved_period = form_data.get("capacity_period", "Monthly")
                        st.selectbox(
                            "Capacity Measurement Period", capacity_periods,
                            index=capacity_periods.index(saved_period)
                            if saved_period in capacity_periods else 0,
                            key=field_key("capacity_period"),
                        )
                    st.caption(
                        "Repayment capacity is borrower-declared and is not independently verified."
                    )
                    st.markdown("#### Existing Financing")
                    existing_options = ["Select an answer", "Yes", "No"]
                    saved_answer = form_data.get(
                        "existing_financing_answer", "Select an answer"
                    )
                    st.radio(
                        "Does the company have existing financing or financial obligations?",
                        existing_options,
                        index=existing_options.index(saved_answer)
                        if saved_answer in existing_options else 0,
                        horizontal=True, key=field_key("existing_financing_answer"),
                    )
                    if st.session_state.get(field_key("existing_financing_answer")) == "Yes":
                        obligation_column, obligation_details_column = st.columns(2)
                        with obligation_column:
                            st.text_input(
                                "Provider (if applicable)",
                                value=form_data.get("obligation_provider", ""),
                                key=field_key("obligation_provider"),
                            )
                            st.number_input(
                                "Outstanding Balance (if applicable)", min_value=0.0,
                                value=form_data.get("obligation_balance"), step=1000.0,
                                key=field_key("obligation_balance"),
                            )
                        with obligation_details_column:
                            st.number_input(
                                "Monthly Repayment (if applicable)", min_value=0.0,
                                value=form_data.get("obligation_monthly_repayment"), step=100.0,
                                key=field_key("obligation_monthly_repayment"),
                            )
                            st.number_input(
                                "Remaining Tenure (months, if applicable)", min_value=0,
                                value=int(form_data.get("obligation_remaining_tenure", 0) or 0),
                                step=1, key=field_key("obligation_remaining_tenure"),
                            )
                    st.caption(
                        "Existing obligation details remain borrower-declared. Missing details are unspecified."
                    )
                    st.form_submit_button(
                        "Continue to Document Upload", type="primary",
                        use_container_width=True, on_click=advance_details,
                    )

        elif step == 2:
            invoice_column, statement_column = st.columns(2)
            with invoice_column:
                with st.container(key="client-financing-invoice-upload"):
                    st.markdown("#### Sales Invoices")
                    st.caption(
                        "Upload the required 12 months of sales invoice data as an Excel workbook (.xlsx)."
                    )
                    st.file_uploader(
                        "Sales Invoices (Excel only)", type=["xlsx"],
                        key=field_key("invoices_upload"),
                        on_change=keep_request_dialog_open,
                    )
                    file_name = saved_names.get("invoices")
                    uploaded = st.session_state.get(field_key("invoices_upload"))
                    if uploaded is not None:
                        st.success(f"Selected: {uploaded.name} · XLSX · Ready to upload")
                    elif file_name:
                        st.success(f"Uploaded: {file_name} · XLSX · Saved; select a file to replace it")
                    else:
                        st.caption("No invoice file uploaded yet.")
            with statement_column:
                with st.container(key="client-financing-statement-upload"):
                    st.markdown("#### Bank Statements")
                    st.caption(
                        "Upload the required 12 months of bank statements as a text-based PDF."
                    )
                    st.file_uploader(
                        "Bank Statements (PDF only)", type=["pdf"],
                        key=field_key("bank_statement_upload"),
                        on_change=keep_request_dialog_open,
                    )
                    file_name = saved_names.get("bank_statement_pdf")
                    uploaded = st.session_state.get(field_key("bank_statement_upload"))
                    if uploaded is not None:
                        st.success(f"Selected: {uploaded.name} · PDF · Ready to upload")
                    elif file_name:
                        st.success(f"Uploaded: {file_name} · PDF · Saved; select a file to replace it")
                    else:
                        st.caption("No bank statement uploaded yet.")
            with st.container(key="client-financing-supporting-upload"):
                st.markdown("#### Additional Supporting Document (optional)")
                st.caption("You may include one additional text-readable PDF for supporting context.")
                st.file_uploader(
                    "Supporting Document (PDF only, optional)", type=["pdf"],
                    key=field_key("supporting_pdf_upload"),
                    on_change=keep_request_dialog_open,
                )
                supporting_name = saved_names.get("supporting_pdf")
                if supporting_name:
                    st.checkbox(
                        f"Keep saved supporting document: {supporting_name}",
                        value=True, key=field_key("keep_saved_supporting"),
                        on_change=keep_request_dialog_open,
                    )
                    st.caption("Select a new PDF above to replace this document.")
                else:
                    st.caption("No optional supporting document uploaded.")
            back_column, continue_column = st.columns(2)
            back_column.button(
                "Back to Financing Details", key="client_request_back_to_details",
                on_click=back_to_details, use_container_width=True,
            )
            continue_column.button(
                "Continue to Review", key="client_request_continue_to_review",
                type="primary", on_click=advance_documents, use_container_width=True,
            )

        else:
            with st.container(key="client-financing-step-review"):
                st.subheader("Step 3 — Review & Process")
                st.caption(
                    "Review the request and uploaded files. Processing starts only when you select Process Documents."
                )
                detail_column, document_column = st.columns(2)
                with detail_column:
                    st.markdown("#### Financing Details")
                    st.write(f"**Financing Type:** {form_data.get('financing_type', 'Not provided')}")
                    st.write(
                        f"**Requested Amount:** {form_data.get('requested_currency', '')} "
                        f"{form_data.get('requested_amount', 0):,.2f}"
                    )
                    st.write(f"**Purpose:** {form_data.get('financing_purpose', 'Not provided')}")
                    st.write(f"**Tenure:** {form_data.get('requested_tenure_months', 0)} months")
                    st.write(f"**Repayment Frequency:** {form_data.get('repayment_frequency', 'Not provided')}")
                with document_column:
                    st.markdown("#### Uploaded Documents")
                    for doc_type, label, file_type in (
                        ("invoices", "Sales Invoices", "Excel workbook (.xlsx)"),
                        ("bank_statement_pdf", "Bank Statements", "PDF statement"),
                        ("supporting_pdf", "Additional Supporting Document", "PDF document"),
                    ):
                        file_name = saved_names.get(doc_type)
                        if file_name:
                            st.write(f"**{label}:** {file_name} · {file_type} · Ready")
                        elif doc_type != "supporting_pdf":
                            st.error(f"{label}: required file is missing.")
                        else:
                            st.caption(f"{label}: not provided (optional).")
                if pending and pending.get("processing_error"):
                    st.error(
                        "Processing could not be completed: "
                        f"{pending['processing_error']}"
                    )
                back_column, process_column = st.columns(2)
                back_column.button(
                    "Back to Document Upload", key="client_request_back_to_documents",
                    on_click=back_to_documents, use_container_width=True,
                )
                process_clicked = process_column.button(
                    "Process Documents", key="client_process_financing_documents",
                    type="primary", use_container_width=True,
                    on_click=lambda: st.session_state.__setitem__(
                        "client_open_request_dialog", True
                    ),
                )
                if process_clicked:
                    current_draft = st.session_state.get("client_pending_application")
                    if not current_draft or current_draft.get("creation_step") != 3:
                        st.error(
                            "Complete the required financing details and document uploads first."
                        )
                    else:
                        current_draft.pop("processing_error", None)
                        st.session_state["client_pending_application"] = current_draft
                        try:
                            with st.spinner("Extracting and analyzing your documents..."):
                                application = _analyze_client_application_draft(current_draft)
                            application.pop("step_errors", None)
                            application.pop("processing_error", None)
                            st.session_state["client_pending_application"] = application
                            _render_client_analysis_preview()
                            return
                        except Exception as exc:
                            current_draft["processing_error"] = (
                                f"{type(exc).__name__}: {exc}"
                            )
                            st.session_state["client_pending_application"] = current_draft
                            st.error(
                                "The documents could not be processed. Check that the invoice workbook "
                                "has the required columns and that the bank-statement PDF contains a "
                                "supported transaction table, then replace the file and try again. "
                                f"Details: {type(exc).__name__}: {exc}"
                            )
def _submit_pending_client_application() -> None:
    """Submit the current valid analysis-ready request through the mock API."""
    pending = st.session_state.get("client_pending_application")
    if not pending:
        st.error("There is no current financing request to submit.")
        return

    applications = st.session_state.setdefault("client_applications", [])
    try:
        application, duplicate = submit_client_application(
            MOCK_BANK_API,
            pending,
            applications,
        )
    except SubmissionBlockedError as exc:
        st.error(str(exc))
        return
    except MockBankError as exc:
        # Keep the analysis-ready pending request in session state so it can be
        # retried. Its stable application ID makes an ambiguous timeout safe.
        st.error(
            f"The simulated bank did not confirm this submission: {exc} "
            "Your request is still saved. Retry Submit to try again."
        )
        return

    if not duplicate:
        application_context = dict(application.get("application_context", {}))
        application_context["application_id"] = application["application_id"]
        application["application_context"] = application_context
    st.session_state.pop("client_pending_application", None)
    st.session_state.pop("client_selected_application_id", None)
    st.session_state["client_applications_view"] = "applications"
    st.session_state["client_open_request_dialog"] = False
    st.session_state["client_success_message"] = (
        f"Application {application['application_id']} was received by the "
        f"simulated partner bank. Bank reference: {application['bank_reference']}."
    )
    st.session_state["client_form_generation"] = (
        st.session_state.get("client_form_generation", 0) + 1
    )


def _finish_pending_client_application(
    status: str,
    success_message: str,
) -> None:
    """Save or cancel the current analyzed request and return to the list."""
    pending = st.session_state.get("client_pending_application")
    if not pending or pending.get("lifecycle_state") != "analysis_ready":
        st.error("There is no processed financing request to update.")
        return

    application = dict(pending)
    application_id = str(
        application.get("application_id")
        or application.get("draft_id")
        or f"DRAFT-{uuid4().hex[:12].upper()}"
    )
    now = datetime.now().isoformat(timespec="seconds")
    existing_application = next(
        (
            saved for saved in _client_applications()
            if saved.get("draft_id") == application.get("draft_id")
            or saved.get("application_id") == application_id
        ),
        None,
    )
    previous_status = (
        _client_application_status_label(existing_application)
        if existing_application
        else "Request Started"
    )
    application.update({
        "application_id": application_id,
        "status": status,
        "lifecycle_state": status.casefold(),
        "analysis_stale": False,
        "updated_at": now,
    })
    if status == "Cancelled":
        application["cancelled_at"] = now
    history = (
        _client_application_status_history(existing_application)
        if existing_application
        else []
    )
    if previous_status != status:
        history.append({
            "previous_status": previous_status,
            "new_status": status,
            "recorded_at": now,
            "source": "Qawafel",
        })
    application["status_history"] = history

    applications = _client_applications()
    existing_index = next(
        (
            index
            for index, saved in enumerate(applications)
            if saved.get("draft_id") == application.get("draft_id")
            or saved.get("application_id") == application_id
        ),
        None,
    )
    if existing_index is None:
        applications.append(application)
    else:
        applications[existing_index] = application

    st.session_state.pop("client_pending_application", None)
    st.session_state.pop("client_selected_application_id", None)
    st.session_state["client_applications_view"] = "applications"
    st.session_state["client_open_request_dialog"] = False
    st.session_state["client_success_message"] = success_message
    st.session_state["client_form_generation"] = (
        st.session_state.get("client_form_generation", 0) + 1
    )


def _edit_saved_client_draft(application_id: str) -> None:
    """Load a saved draft into the request popup for editing."""
    application = next(
        (
            item for item in _client_applications()
            if item.get("application_id") == application_id
            and item.get("lifecycle_state") == "draft"
        ),
        None,
    )
    if application is None:
        st.error("This saved draft is no longer available.")
        return

    st.session_state["client_pending_application"] = dict(application)
    _resume_pending_edit()
    st.session_state.pop("client_selected_application_id", None)
    st.session_state["client_applications_view"] = "applications"
    st.session_state["client_open_request_dialog"] = True


def _render_legacy_company_documents() -> None:
    """Render upload controls, process documents, and display validation."""
    st.markdown('<div class="eyebrow">Document center</div>', unsafe_allow_html=True)
    st.title("Company Documents")
    st.markdown(
        "Upload your core company and financial records to check their structure "
        "and data quality. Your files are processed temporarily and are not saved "
        "to the project."
    )

    with st.container(border=True):
        st.subheader("Required documents")
        company_file = st.file_uploader(
            "Company Profile",
            type=["json"],
            help="Upload the company profile as a JSON file.",
            key="company_profile_upload",
        )
        invoice_file = st.file_uploader(
            "Invoices",
            type=["xlsx"],
            help="Upload an XLSX workbook containing invoice records.",
            key="invoices_upload",
        )
        transaction_file = st.file_uploader(
            "Bank Transactions",
            type=["xlsx"],
            help="Upload an XLSX workbook containing bank transaction records.",
            key="bank_transactions_upload",
        )

    with st.container(border=True):
        st.subheader("Supporting document")
        pdf_file = st.file_uploader(
            "Supporting Documents (optional)",
            type=["pdf"],
            help="Upload a text-readable PDF. Scanned PDFs may require OCR.",
            key="supporting_pdf_upload",
        )

    if st.button(
        "Process Documents",
        type="primary",
        use_container_width=True,
        key="process_documents",
    ):
        _clear_application_results()
        st.session_state["processing_status"] = "processing"
        required_uploads = {
            "Company Profile (JSON)": company_file,
            "Invoices (XLSX)": invoice_file,
            "Bank Transactions (XLSX)": transaction_file,
        }
        missing_uploads = [
            label for label, uploaded_file in required_uploads.items()
            if uploaded_file is None
        ]
        if missing_uploads:
            st.session_state["processing_status"] = "error"
            st.error(
                "Upload all required documents before processing: "
                + ", ".join(missing_uploads)
                + "."
            )
        else:
            extraction_errors = []
            with TemporaryDirectory(prefix="qawafel_upload_") as temporary_dir:
                temporary_path = Path(temporary_dir)
                try:
                    company_path = temporary_path / "company_profile.json"
                    company_path.write_bytes(company_file.getvalue())
                    company_profile = load_company_profile(company_path)
                except Exception as exc:
                    extraction_errors.append(
                        f"Company Profile: unable to extract the JSON file "
                        f"({type(exc).__name__}: {exc})."
                    )

                try:
                    invoices_path = temporary_path / "invoices.xlsx"
                    invoices_path.write_bytes(invoice_file.getvalue())
                    invoices = load_invoices(invoices_path)
                except Exception as exc:
                    extraction_errors.append(
                        f"Invoices: unable to read the XLSX workbook "
                        f"({type(exc).__name__}: {exc})."
                    )

                try:
                    transactions_path = temporary_path / "bank_transactions.xlsx"
                    transactions_path.write_bytes(transaction_file.getvalue())
                    bank_transactions = load_bank_transactions(transactions_path)
                except Exception as exc:
                    extraction_errors.append(
                        f"Bank Transactions: unable to read the XLSX workbook "
                        f"({type(exc).__name__}: {exc})."
                    )

                pdf_results = None
                if pdf_file is not None:
                    try:
                        pdf_path = temporary_path / "supporting_document.pdf"
                        pdf_path.write_bytes(pdf_file.getvalue())
                        pdf_results = extract_pdf_text(pdf_path)
                    except Exception as exc:
                        extraction_errors.append(
                            f"Supporting PDF: unable to extract readable text "
                            f"({type(exc).__name__}: {exc})."
                        )

            if extraction_errors:
                st.session_state["processing_status"] = "error"
                for error in extraction_errors:
                    st.error(error)
            else:
                extracted_dataset = {
                    "company": company_profile,
                    "invoices": invoices,
                    "bank_transactions": bank_transactions,
                }
                validation_report = validate_dataset(extracted_dataset)
                st.session_state["company_profile"] = company_profile
                st.session_state["invoices"] = invoices
                st.session_state["bank_transactions"] = bank_transactions
                st.session_state["pdf_extraction_results"] = pdf_results
                st.session_state["validation_report"] = validation_report
                st.session_state["processing_status"] = "completed"

    if st.session_state.get("processing_status") == "completed":
        company_profile = st.session_state["company_profile"]
        invoices = st.session_state["invoices"]
        bank_transactions = st.session_state["bank_transactions"]
        validation_report = st.session_state["validation_report"]
        validation_summary = validation_report["summary"]

        st.markdown("---")
        st.subheader("Processing Summary")
        status_label = (
            "Valid"
            if validation_summary["is_valid"]
            else "Needs attention"
        )
        summary_columns = st.columns(5)
        summary_values = [
            ("Company", company_profile.get("company_name", "Not provided")),
            ("Invoices", f"{len(invoices):,}"),
            ("Bank transactions", f"{len(bank_transactions):,}"),
            ("Validation", status_label),
            (
                "Errors / warnings",
                f"{validation_summary['error_count']} / "
                f"{validation_summary['warning_count']}",
            ),
        ]
        for column, (label, value) in zip(summary_columns, summary_values):
            with column:
                st.metric(label, value)

        pdf_results = st.session_state.get("pdf_extraction_results")
        if pdf_results is not None:
            st.caption(
                "Supporting PDF text extracted from "
                f"{pdf_results['total_pages']} page(s)."
            )

        if validation_summary["is_valid"]:
            st.success("Required documents were processed and passed validation.")
        else:
            st.error(
                "Documents were extracted, but validation found errors. "
                "Review and correct the issues below before relying on the data."
            )

        st.subheader("Validation Details")
        invoice_report = validation_report["invoices"]
        bank_report = validation_report["bank_transactions"]
        _render_issues("Invoice errors", invoice_report.get("errors", []), "error")
        _render_issues(
            "Invoice warnings", invoice_report.get("warnings", []), "warning"
        )
        _render_issues("Bank transaction errors", bank_report.get("errors", []), "error")
        _render_issues(
            "Bank transaction warnings",
            bank_report.get("warnings", []),
            "warning",
        )
        for issue in validation_summary.get("errors", []):
            st.error(
                f"{issue.get('message', 'Dataset validation error')} "
                f"(count: {issue.get('count', 0)})"
            )
        if (
            not invoice_report.get("errors")
            and not invoice_report.get("warnings")
            and not bank_report.get("errors")
            and not bank_report.get("warnings")
            and not validation_summary.get("errors")
        ):
            st.info("No validation errors or warnings were reported.")


def _render_financial_analysis() -> None:
    """Render financial metrics based on processed documents and matcher results."""
    st.markdown(
        '<div class="eyebrow">Financial overview</div>',
        unsafe_allow_html=True,
    )
    st.title("Financial Analysis")
    st.markdown(
        "Review invoiced sales, confirmed invoice collections, and bank cash "
        "flow as separate measures. Confirmed collections include only eligible "
        "positive credits matched to a unique invoice reference."
    )

    processing_status = st.session_state.get("processing_status", "not_processed")
    if processing_status != "completed":
        st.info(
            "Complete and process a financing application first."
        )
        return

    invoices = st.session_state.get("invoices")
    transactions = st.session_state.get("bank_transactions")
    if not isinstance(invoices, pd.DataFrame) or not isinstance(
        transactions, pd.DataFrame
    ):
        st.error(
            "Document processing is marked complete, but invoice or bank "
            "transaction data is unavailable. Reprocess the financing application."
        )
        return

    validation_report = st.session_state.get("validation_report")
    validation_summary = (
        validation_report.get("summary", {})
        if isinstance(validation_report, dict)
        else {}
    )
    if validation_summary.get("is_valid") is False:
        st.warning(
            "The processed dataset has validation errors. The figures below "
            "are shown for diagnostic purposes and should not be treated as "
            "clean financial results."
        )
    elif not validation_summary:
        st.warning(
            "No validation report is available for this dataset. Review data "
            "quality before relying on the results."
        )

    cached_inputs = st.session_state.get("_financial_analysis_inputs")
    application_id = st.session_state.get("application_id")
    if (
        isinstance(cached_inputs, tuple)
        and len(cached_inputs) == 2
        and cached_inputs[0] is invoices
        and cached_inputs[1] is transactions
        and st.session_state.get("_financial_analysis_application_id")
        == application_id
        and st.session_state.get("financial_analysis_application_id")
        == application_id
        and "financial_analysis_result" in st.session_state
        and "invoice_matching_result" in st.session_state
    ):
        matching_result = st.session_state["invoice_matching_result"]
        analysis = st.session_state["financial_analysis_result"]
    else:
        try:
            matching_result = match_invoices_to_transactions(
                invoices,
                transactions,
            )
            analysis = analyze_financial_data(
                invoices,
                transactions,
                matching_result,
            )
        except Exception as exc:
            st.error(
                "Financial analysis could not be completed "
                f"({type(exc).__name__}: {exc}). Check the uploaded data and "
                "reprocess the financing application."
            )
            return

        st.session_state["invoice_matching_result"] = matching_result
        st.session_state["financial_analysis_result"] = analysis
        st.session_state["_financial_analysis_inputs"] = (
            invoices,
            transactions,
        )
        st.session_state["_financial_analysis_application_id"] = application_id

    st.subheader("Key financial indicators")
    collection_ratio = analysis["collections"].get(
        "collection_to_sales_ratio_percent"
    )
    kpis = [
        (
            "Total Invoiced Sales",
            analysis["sales"]["total_invoiced_sales"],
        ),
        (
            "Confirmed Invoice Collections",
            analysis["collections"]["total_confirmed_collections"],
        ),
        (
            "Outstanding Receivables",
            analysis["receivables"]["outstanding_receivables"],
        ),
        (
            "Collection-to-Sales Ratio",
            None if collection_ratio is None else f"{collection_ratio:.2f}%",
        ),
        ("Net Cash Flow", analysis["cash_flow"]["net_cash_flow"]),
    ]
    for column, (label, value) in zip(st.columns(5), kpis):
        with column:
            display_value = (
                "—"
                if value is None
                else value
                if isinstance(value, str)
                else f"{value:,.2f}"
            )
            st.metric(label, display_value)
    st.caption(
        "Collection-to-Sales Ratio compares confirmed collections with sales; "
        "it is not a true invoice collection rate. Invoice sales are not cash "
        "collected, and bank incoming cash includes credits unrelated to invoices."
    )

    trends = analysis.get("monthly_trends", [])
    if trends:
        trend_data = pd.DataFrame(trends).set_index("month")
        st.subheader("Monthly financial trends")
        left, right = st.columns(2)
        with left:
            st.markdown("**Monthly Sales**")
            st.line_chart(trend_data[["invoiced_sales"]])
        with right:
            st.markdown("**Confirmed Collections**")
            st.line_chart(trend_data[["confirmed_invoice_collections"]])

        left, right = st.columns(2)
        with left:
            st.markdown("**Bank Incoming and Outgoing**")
            st.line_chart(trend_data[["incoming_cash", "outgoing_cash"]])
        with right:
            st.markdown("**Net Cash Flow**")
            st.line_chart(trend_data[["net_cash_flow"]])
    else:
        st.info(
            "Monthly trends are unavailable because no valid invoice or "
            "transaction dates were found."
        )

    st.subheader("Transaction classification")
    classification = analysis["unclassified_transactions"]
    match_summary = matching_result.get("summary", {})
    classification_items = [
        (
            "Confirmed invoice collections",
            match_summary.get("matched_payment_transactions", 0),
            f"{analysis['collections']['total_confirmed_collections']:,.2f} "
            "confirmed",
        ),
        (
            "Unmatched transactions",
            classification.get("unmatched_transaction_count", 0),
            "Positive credits: "
            f"{classification.get('unmatched_positive_credit_total', 0):,.2f}; "
            "positive debits: "
            f"{classification.get('unmatched_positive_debit_total', 0):,.2f}",
        ),
        (
            "Ambiguous transactions",
            classification.get("ambiguous_transaction_count", 0),
            "Positive credits: "
            f"{classification.get('ambiguous_positive_credit_total', 0):,.2f}; "
            "positive debits: "
            f"{classification.get('ambiguous_positive_debit_total', 0):,.2f}",
        ),
        (
            "Non-payment transactions",
            classification.get("non_payment_transaction_count", 0),
            "Referenced transactions without a positive incoming credit",
        ),
    ]
    for column, (label, count, detail) in zip(st.columns(4), classification_items):
        with column:
            st.metric(label, f"{count:,}")
            st.caption(detail)
    st.caption(
        f"Total bank incoming cash is "
        f"{analysis['cash_flow']['total_incoming_cash']:,.2f}; this includes "
        "unmatched and ambiguous credits. Those credits are excluded from "
        "confirmed invoice collections."
    )

    st.subheader("Data quality")
    discrepancies = analysis["data_quality"].get(
        "payment_status_discrepancies", 0
    )
    ambiguous_references = analysis["data_quality"].get(
        "ambiguous_invoice_references", 0
    )
    quality_columns = st.columns(4)
    quality_columns[0].metric(
        "Payment-status discrepancies",
        f"{discrepancies:,}",
    )
    quality_columns[1].metric(
        "Ambiguous invoice references",
        f"{ambiguous_references:,}",
    )
    if validation_summary:
        quality_columns[2].metric(
            "Validation errors",
            f"{validation_summary.get('error_count', 0):,}",
        )
        quality_columns[3].metric(
            "Validation warnings",
            f"{validation_summary.get('warning_count', 0):,}",
        )

    if validation_report:
        invoice_report = validation_report.get("invoices", {})
        bank_report = validation_report.get("bank_transactions", {})
        _render_issues(
            "Invoice validation errors",
            invoice_report.get("errors", []),
            "error",
        )
        _render_issues(
            "Invoice validation warnings",
            invoice_report.get("warnings", []),
            "warning",
        )
        _render_issues(
            "Bank validation errors",
            bank_report.get("errors", []),
            "error",
        )
        _render_issues(
            "Bank validation warnings",
            bank_report.get("warnings", []),
            "warning",
        )

    financial_quality = analysis["data_quality"].get(
        "missing_or_invalid_financial_values", {}
    )
    quality_findings = []

    def collect_quality_findings(value: object, label: str) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                collect_quality_findings(nested_value, f"{label}.{key}")
        elif isinstance(value, list):
            if value:
                quality_findings.append(f"{label}: {', '.join(map(str, value))}")
        elif isinstance(value, (int, float)) and value > 0:
            quality_findings.append(f"{label}: {value}")

    collect_quality_findings(
        financial_quality,
        "Missing or invalid financial values",
    )
    collect_quality_findings(
        analysis["data_quality"].get("missing_required_columns", {}),
        "Missing required columns",
    )
    duplicate_ids = analysis["data_quality"].get(
        "matched_transactions_with_duplicate_ids", 0
    )
    if duplicate_ids:
        quality_findings.append(
            f"Matched transactions with duplicate IDs: {duplicate_ids}"
        )
    if quality_findings:
        with st.expander("Financial data-quality details"):
            for finding in quality_findings:
                st.markdown(f"- {finding}")

    if discrepancies:
        st.warning(
            f"{discrepancies} invoice payment-status value(s) conflict with "
            "the calculated bank collection status. The recorded status alone "
            "is not treated as proof of collection."
        )
    st.caption(
        "Invoice aging and days past due are not calculated because the "
        "provided invoice data has no due-date field."
    )


def _render_financing_insights() -> None:
    """Render rule-based observations, missing information, and limitations."""
    st.markdown(
        '<div class="eyebrow">Rule-based financing assessment</div>',
        unsafe_allow_html=True,
    )
    st.title("Financing Insights")
    result = st.session_state.get("financial_insights_result")
    application_id = st.session_state.get("application_id")
    if (
        st.session_state.get("processing_status") != "completed"
        or not isinstance(result, dict)
        or result.get("application_id") != application_id
    ):
        st.info("Process a financing application to view its assessment.")
        return

    st.warning(
        "No financing decision has been made by the system. All findings are "
        "descriptive and require review by a bank employee."
    )
    st.caption(
        f"Application: {application_id} · Rule set {result.get('rule_set_version')} "
        f"· Assessment type: {result.get('assessment_type')}"
    )
    sections = (
        ("Financial Strengths", "financial_strengths", "observation"),
        ("Potential Risks", "potential_risks", "observation"),
        (
            "Financing Request Assessment",
            "financing_request_assessment",
            "observation",
        ),
        ("Existing Obligations", "existing_obligations", "observation"),
        ("Data Quality Issues", "data_quality_issues", "review"),
        ("Missing Information", "missing_information", "missing"),
        ("Recommended Actions", "recommended_actions", "action"),
        ("Limitations", "limitations", "limitation"),
    )
    for title, key, group in sections:
        findings = result.get(key, [])
        if not findings:
            continue
        st.subheader(title)
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            with st.container(border=True):
                st.markdown(
                    f"**{finding.get('title', 'Finding')}** "
                    f"`{finding.get('rule_id', 'unknown')}` · "
                    f"{finding.get('status', '')}"
                )
                st.write(finding.get("explanation", ""))
                if finding.get("evidence"):
                    with st.expander("Evidence"):
                        st.json(finding["evidence"])
                if finding.get("recommended_action"):
                    st.caption(
                        f"Recommended action: {finding['recommended_action']}"
                    )
                if group == "review":
                    st.caption("Requires data-quality review.")
                elif group == "missing":
                    st.caption("Missing information; not interpreted as zero.")
                elif group == "limitation":
                    st.caption("Assessment limitation.")

    decision = result.get("decision", {})
    st.subheader("Decision Status")
    if (
        decision.get("status") == "not_made"
        and decision.get("decision_maker") == "bank_employee"
    ):
        st.info("Decision: not made by the system — review by a bank employee.")
    else:
        st.error(
            "Unexpected decision metadata; do not treat this assessment as a decision."
        )


def _canonical_application_status(status: object) -> str | None:
    """Translate legacy presentation labels to the shared internal status."""
    normalized = str(status).strip().casefold().replace(" ", "_")
    aliases = {
        "received": "received",
        "new": "submitted",
        "submitted": "submitted",
        "under_review": "under_review",
        "more_information_required": "more_information_required",
        "approved": "approved",
        "rejected": "rejected",
    }
    return aliases.get(normalized)


def _client_application_status_label(application: dict) -> str:
    """Return the client-facing label for a shared application record."""
    canonical = _canonical_application_status(application.get("status"))
    if canonical:
        return APPLICATION_STATUS_LABELS[canonical]["client"]
    return str(application.get("status", "Not Available"))


def _client_application_status_history(application: dict) -> list[dict]:
    """Return stored status events, or derive a timeline for older records."""
    history = application.get("status_history")
    if isinstance(history, list) and history:
        return sorted(
            [
                event for event in history
                if isinstance(event, dict)
            ],
            key=lambda event: str(event.get("recorded_at", "")),
        )

    events = []
    submitted_at = application.get("submitted_at")
    if submitted_at:
        events.append({
            "previous_status": "Draft",
            "new_status": "Submitted",
            "recorded_at": submitted_at,
            "source": "Qawafel",
        })
    elif application.get("created_at"):
        events.append({
            "previous_status": "Request Started",
            "new_status": _client_application_status_label(application),
            "recorded_at": application["created_at"],
            "source": "Qawafel",
        })

    for event in application.get("review_history", []):
        if not isinstance(event, dict):
            continue
        events.append({
            "previous_status": event.get("previous_status", "Not Available"),
            "new_status": event.get("new_status", "Not Available"),
            "recorded_at": event.get("recorded_at", "Not Available"),
            "source": "Bank",
            "note": event.get("note", ""),
        })

    cancelled_at = application.get("cancelled_at")
    if cancelled_at and not any(
        str(event.get("new_status", "")).casefold() == "cancelled"
        for event in events
    ):
        events.append({
            "previous_status": "Submitted",
            "new_status": "Cancelled",
            "recorded_at": cancelled_at,
            "source": "Qawafel",
        })
    return sorted(
        events,
        key=lambda event: str(event.get("recorded_at", "")),
    )


def _client_applications() -> list[dict]:
    """Return this client session's financing application collection."""
    st.session_state.setdefault("client_company_profile", deepcopy(CLIENT_DEMO_COMPANY_PROFILE))
    return st.session_state.setdefault("client_applications", [])


def _client_status_badge(status: str) -> str:
    """Render a compact status badge for client-owned application records."""
    status_class = {
        "Draft": "draft",
        "Cancelled": "draft",
        "Submitted": "submitted",
        "Received": "submitted",
        "Under Review": "under-review",
        "More Information Required": "more-information",
        "Approved": "approved",
        "Rejected": "rejected",
    }.get(status)
    if status_class is None:
        return (
            '<span class="client-status-badge">'
            f"{escape(str(status))}</span>"
        )
    return (
        f'<span class="client-status-badge client-status-badge--{status_class}">'
        f"{escape(status)}</span>"
    )


def _render_client_page_header(title: str, description: str) -> None:
    """Render a consistent title row with the shared financing request action."""
    st.markdown(
        '<div class="eyebrow">Client Portal</div>',
        unsafe_allow_html=True,
    )
    title_column, action_column = st.columns([5, 1.5], vertical_alignment="center")
    with title_column:
        st.title(title)
    with action_column:
        if st.button(
            "Request Financing",
            type="primary",
            key=f"client_request_financing_{title.lower().replace(' ', '_')}",
            use_container_width=True,
        ):
            _request_financing_dialog()
    st.markdown(description)


def _show_pending_preview() -> None:
    """Reopen the financing popup for a processed but unfinished draft."""
    st.session_state["client_applications_view"] = "applications"
    st.session_state["client_open_request_dialog"] = True


def _open_financing_request_from_dashboard() -> None:
    """Navigate to applications and open the existing request dialog."""
    st.session_state["client_navigation"] = "Financing Applications"
    st.session_state["last_client_navigation"] = "Financing Applications"
    st.session_state["client_applications_view"] = "applications"
    st.session_state["client_open_request_dialog"] = True


def _resume_pending_edit() -> None:
    """Mark a draft's previous analysis stale before reopening its form."""
    pending = st.session_state.get("client_pending_application")
    if pending:
        pending["lifecycle_state"] = "draft"
        pending["analysis_stale"] = True
        pending["creation_step"] = 1
        st.session_state["client_pending_application"] = pending
        st.session_state["client_applications_view"] = "edit"


def _render_client_dashboard() -> None:
    """Render company application activity from its own session-state records."""
    st.session_state.setdefault(
        "client_company_profile",
        deepcopy(CLIENT_DEMO_COMPANY_PROFILE),
    )
    company = st.session_state["client_company_profile"]
    applications = _client_applications()
    company_name = str(company.get("company_name") or "Company")
    registration_number = str(company.get("cr_number") or "Not Available")
    current_hour = datetime.now().hour
    greeting = (
        "Good morning!"
        if current_hour < 12
        else "Good afternoon!"
        if current_hour < 17
        else "Good evening!"
    )
    statuses = [
        _client_application_status_label(application)
        for application in applications
    ]
    counts = {
        status: statuses.count(status)
        for status in (
            "Under Review",
            "Approved",
            "More Information Required",
        )
    }
    kpis = (
        ("Total Financing Applications", len(applications)),
        ("Under Review", counts["Under Review"]),
        ("Approved", counts["Approved"]),
        ("Action Required", counts["More Information Required"]),
    )

    def status_badge(status: str) -> str:
        status_class = {
            "Approved": "approved",
            "Under Review": "review",
            "More Information Required": "review",
            "Submitted": "submitted",
            "Received": "submitted",
            "Rejected": "rejected",
            "Draft": "submitted",
            "Cancelled": "submitted",
        }.get(status, "error")
        return (
            f'<span class="company-dashboard-status '
            f'company-dashboard-status--{status_class}">'
            f"{escape(status)}</span>"
        )

    with st.container(key="company-dashboard"):
        welcome_column, action_column = st.columns(
            [4, 1.6],
            vertical_alignment="center",
        )
        with welcome_column:
            st.markdown(
                '<div class="company-dashboard-welcome">'
                "<div>"
                '<div class="company-dashboard-eyebrow">Company dashboard</div>'
                f"<h1>{greeting}</h1>"
                "<p>Here is your company's financing overview.</p>"
                f'<div class="company-dashboard-company-name">{escape(company_name)}</div>'
                "</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        with action_column:
            st.button(
                "New Financing Application",
                key="client_dashboard_new_financing",
                type="primary",
                use_container_width=True,
                on_click=_open_financing_request_from_dashboard,
            )

        st.markdown(
            '<div class="company-dashboard-section-title">Company Information</div>'
            '<div class="company-dashboard-info-card">'
            '<div><div class="company-dashboard-label">Company Name</div>'
            f'<div class="company-dashboard-info-value">{escape(company_name)}</div></div>'
            '<div><div class="company-dashboard-label">Commercial Registration Number</div>'
            f'<div class="company-dashboard-info-value">{escape(registration_number)}</div></div>'
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="company-dashboard-section-title">Financing Overview</div>',
            unsafe_allow_html=True,
        )
        for column, (label, value) in zip(st.columns(4), kpis):
            with column:
                st.markdown(
                    '<div class="company-dashboard-kpi">'
                    f'<div class="company-dashboard-label">{escape(label)}</div>'
                    f'<div class="company-dashboard-kpi-value">{value:,}</div>'
                    "</div>",
                    unsafe_allow_html=True,
                )

        st.markdown(
            '<div class="company-dashboard-section-title">Recent Financing Applications</div>',
            unsafe_allow_html=True,
        )
        recent_applications = sorted(
            applications,
            key=lambda application: str(
                application.get("submitted_at")
                or application.get("updated_at")
                or application.get("created_at")
                or ""
            ),
            reverse=True,
        )[:3]
        if recent_applications:
            for column, application in zip(
                st.columns(len(recent_applications)),
                recent_applications,
            ):
                status = _client_application_status_label(application)
                amount = application.get("requested_amount")
                amount_text = (
                    f"{escape(str(application.get('requested_currency') or ''))} "
                    f"{amount:,.2f}"
                    if isinstance(amount, (int, float))
                    else "Not Available"
                )
                submitted_at = str(
                    application.get("submitted_at")
                    or application.get("created_at")
                    or application.get("cancelled_at")
                    or "Not Available"
                )
                submitted_date = submitted_at.split("T", 1)[0]
                date_label = "Created" if status == "Draft" else (
                    "Cancelled" if status == "Cancelled" else "Submitted"
                )
                with column:
                    st.markdown(
                        '<div class="company-dashboard-application-card">'
                        '<div style="display:flex;justify-content:space-between;'
                        'align-items:flex-start;gap:0.6rem;flex-wrap:wrap">'
                        f'<div class="company-dashboard-application-id">'
                        f"{escape(str(application.get('application_id') or 'Not Available'))}"
                        "</div>"
                        f"{status_badge(status)}"
                        "</div>"
                        f'<div class="company-dashboard-application-type">'
                        f"{escape(str(application.get('financing_type') or 'Not Available'))}"
                        "</div>"
                        f'<div class="company-dashboard-application-meta">'
                        f"<strong>{amount_text}</strong><br>"
                        f"{date_label} {escape(submitted_date)}"
                        "</div></div>",
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown(
                '<div class="company-dashboard-empty">'
                "<strong>No financing applications yet</strong><br>"
                "Your submitted applications will appear here."
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            '<div class="company-dashboard-section-title">Action Required</div>',
            unsafe_allow_html=True,
        )
        action_required = [
            application for application in applications
            if _client_application_status_label(application)
            == "More Information Required"
        ]
        if action_required:
            for application in action_required:
                history = application.get("review_history", [])
                latest_note = next(
                    (
                        str(event.get("note", "")).strip()
                        for event in reversed(history)
                        if isinstance(event, dict)
                        and event.get("action") == "request_more_information"
                        and str(event.get("note", "")).strip()
                    ),
                    "",
                )
                requirement = (
                    escape(latest_note)
                    if latest_note
                    else "Review the application details for the requested information."
                )
                st.markdown(
                    '<div class="company-dashboard-action-card">'
                    f'<strong>{escape(str(application.get("application_id") or "Application"))}</strong>'
                    f'<div class="company-dashboard-application-meta">'
                    f"{escape(str(application.get('financing_type') or 'Financing application'))}"
                    f" · {requirement}</div></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div class="company-dashboard-empty">'
                '<span style="color:#527A5A;font-weight:650">'
                "You're all caught up</span><br>"
                "No applications currently need your attention."
                "</div>",
                unsafe_allow_html=True,
            )

        pending = st.session_state.get("client_pending_application")
        if pending:
            st.markdown(
                '<div class="company-dashboard-section-title">Draft in Progress</div>',
                unsafe_allow_html=True,
            )
            if pending.get("lifecycle_state") == "analysis_ready":
                st.caption(
                    "Processing is complete. Choose an action in the request popup."
                )
                st.button(
                    "Continue Request",
                    key="client_dashboard_continue_preview",
                    on_click=_open_financing_request_from_dashboard,
                )
            else:
                st.caption(
                    "An unsubmitted draft needs analysis before it can be submitted."
                )
                st.button(
                    "Continue Editing Draft",
                    key="client_dashboard_edit_draft",
                    on_click=_open_financing_request_from_dashboard,
                )

        st.caption(
            "Submissions and bank status updates are simulated through the "
            "Mock Bank API."
        )


def _render_client_financial_analysis(
    application: dict,
    *,
    title: str = "Financial Analysis",
    include_insights: bool = True,
) -> None:
    """Render one application's financial report in the client card style."""
    with st.container(border=True):
        _render_client_financial_analysis_content(
            application,
            title=title,
            include_insights=include_insights,
        )


def _render_client_financial_analysis_content(
    application: dict,
    *,
    title: str = "Financial Analysis",
    include_insights: bool = True,
) -> None:
    """Render analysis exclusively from the selected client application."""
    analysis = application["financial_analysis_result"]
    validation = application["validation_report"]
    insights = application.get("financial_insights_result", {})
    summary = validation.get("summary", {})
    st.subheader(title)
    application_reference = application.get(
        "application_id",
        application.get("draft_id", "this application"),
    )
    st.caption(
        "This analysis uses only the documents and information provided for "
        f"{application_reference}. It is not a financing approval or rejection."
    )
    if summary.get("is_valid") is False:
        st.warning(
            "The submitted dataset contains validation errors. Review the "
            "data-quality details before relying on these figures."
        )

    st.subheader("Financial Overview")
    overview = [
        ("Total Sales", analysis["sales"]["total_invoiced_sales"]),
        (
            "Confirmed Collections",
            analysis["collections"]["total_confirmed_collections"],
        ),
        (
            "Outstanding Receivables",
            analysis["receivables"]["outstanding_receivables"],
        ),
    ]
    for column, (label, value) in zip(st.columns(3), overview):
        with column:
            st.metric(label, "Not Available" if value is None else f"{value:,.2f}")

    st.subheader("Cash Flow")
    cash_flow = analysis["cash_flow"]
    flow_columns = st.columns(3)
    flow_columns[0].metric(
        "Bank Inflows",
        f"{cash_flow['total_incoming_cash']:,.2f}",
    )
    flow_columns[1].metric(
        "Bank Outflows",
        f"{cash_flow['total_outgoing_cash']:,.2f}",
    )
    flow_columns[2].metric(
        "Net Cash Flow",
        f"{cash_flow['net_cash_flow']:,.2f}",
    )
    st.caption(
        "Bank inflows may include unmatched or ambiguous credits; confirmed "
        "collections include only uniquely matched invoice payments."
    )

    st.subheader("Monthly Financial Trends")
    trends = analysis.get("monthly_trends", [])
    if trends:
        trend_data = pd.DataFrame(trends).set_index("month")
        for heading, columns in (
            ("Invoiced Sales and Confirmed Collections", [
                "invoiced_sales",
                "confirmed_invoice_collections",
            ]),
            ("Bank Inflows and Outflows", ["incoming_cash", "outgoing_cash"]),
            ("Net Cash Flow", ["net_cash_flow"]),
        ):
            st.markdown(f"**{heading}**")
            st.line_chart(trend_data[columns])
    else:
        st.info("Monthly trends are unavailable because no valid dates were found.")

    st.subheader("Data Validation Results")
    st.write(
        f"Validation errors: {summary.get('error_count', 0)} · "
        f"Warnings: {summary.get('warning_count', 0)}"
    )
    for key, title in (
        ("invoices", "Invoice data"),
        ("bank_transactions", "Bank transaction data"),
    ):
        report = validation.get(key, {})
        _render_issues(f"{title} errors", report.get("errors", []), "error")
        _render_issues(f"{title} warnings", report.get("warnings", []), "warning")

    if include_insights:
        _render_client_financial_insights(insights)


def _render_client_financial_insights(insights: dict) -> None:
    """Render the rule-based insight categories for a client application."""
    st.subheader("Financial Insights")
    st.caption(
        f"Rule set {insights.get('rule_set_version', 'Not Available')} · "
        "Descriptive findings only; not a financing decision."
    )
    for title, key in (
        ("Financial Strengths", "financial_strengths"),
        ("Potential Risks", "potential_risks"),
        ("Financing Request Assessment", "financing_request_assessment"),
        ("Existing Obligations", "existing_obligations"),
        ("Data Quality Issues", "data_quality_issues"),
        ("Missing Information", "missing_information"),
        ("Recommended Actions", "recommended_actions"),
        ("Limitations", "limitations"),
    ):
        findings = [
            item for item in insights.get(key, [])
            if isinstance(item, dict)
        ]
        with st.expander(f"{title} ({len(findings)})"):
            if findings:
                for finding in findings:
                    st.markdown(
                        f"- **{finding.get('title', title)}:** "
                        f"{finding.get('explanation', '')}"
                    )
            else:
                st.caption("No findings in this category.")


def _render_client_application_detail(application: dict) -> None:
    """Show one client's application, its stored timeline, and saved results."""
    bank_reference = application.get("bank_reference")
    if bank_reference:
        try:
            current_status = MOCK_BANK_API.get_application_status(
                application.get("application_id", "")
            )
            events = MOCK_BANK_API.get_status_events(
                application.get("application_id", "")
            )
            apply_bank_status_events(application, current_status, events)
        except MockBankError:
            # Show the last acknowledged client state if the status service is
            # temporarily unavailable; a later detail refresh can retry.
            pass
    st.button(
        "Back to Financing Applications",
        key="client_back_to_applications",
        on_click=lambda: st.session_state.pop(
            "client_selected_application_id",
            None,
        ),
    )
    status = _client_application_status_label(application)
    application_id = str(
        application.get("application_id")
        or application.get("draft_id")
        or "Not Available"
    )
    submitted_at = (
        application.get("submitted_at")
        or application.get("created_at")
        or "Not Available"
    )
    if status == "Draft":
        date_label = "Created"
    elif status == "Cancelled":
        date_label = "Cancelled"
        submitted_at = application.get("cancelled_at") or submitted_at
    else:
        date_label = "Submitted"

    st.markdown(
        '<div class="eyebrow">Financing application</div>',
        unsafe_allow_html=True,
    )
    st.title("Financing Application Details")
    if status == "Cancelled":
        st.info("This request was cancelled and is available for viewing only.")
    elif status == "Draft":
        st.caption("This draft is not submitted to a bank.")
    else:
        st.caption("Submitted to the simulated partner bank for status updates.")

    with st.container(border=True):
        st.subheader("Application Overview")
        overview_columns = st.columns(5)
        overview_columns[0].write(f"**Reference**  \n{application_id}")
        overview_columns[1].write(
            f"**Financing Type**  \n{application.get('financing_type') or 'Not Available'}"
        )
        amount = application.get("requested_amount")
        amount_text = (
            f"{application.get('requested_currency') or ''} {amount:,.2f}"
            if isinstance(amount, (int, float))
            else "Not Available"
        )
        overview_columns[2].write(f"**Requested Amount**  \n{amount_text}")
        overview_columns[3].write(
            f"**{date_label} Date**  \n{str(submitted_at)[:19]}"
        )
        overview_columns[4].markdown(
            _client_status_badge(status),
            unsafe_allow_html=True,
        )
        if application.get("bank_reference"):
            st.caption(
                f"Bank reference: {application['bank_reference']} | "
                f"Last status update: {application.get('bank_status_updated_at') or 'Not available'}"
            )

    if status == "Draft":
        st.button(
            "Continue Editing Draft",
            key=f"client_detail_edit_draft_{application_id}",
            type="primary",
            on_click=_edit_saved_client_draft,
            args=(application_id,),
        )

    with st.container(border=True):
        st.subheader("Status History")
        status_history = _client_application_status_history(application)
        if not status_history:
            st.caption("No status changes have been recorded.")
        else:
            for event in status_history:
                previous_status = str(
                    event.get("previous_status") or "Not Available"
                )
                new_status = str(event.get("new_status") or "Not Available")
                previous_canonical = _canonical_application_status(previous_status)
                new_canonical = _canonical_application_status(new_status)
                if previous_canonical:
                    previous_status = APPLICATION_STATUS_LABELS[previous_canonical]["client"]
                if new_canonical:
                    new_status = APPLICATION_STATUS_LABELS[new_canonical]["client"]
                st.markdown(
                    f"**{previous_status}** → **{new_status}**"
                )
                st.caption(
                    f"{event.get('recorded_at', 'Timestamp unavailable')} · "
                    f"Source: {event.get('source') or 'Bank'}"
                )
                if event.get("note"):
                    st.write(event["note"])

    details = application.get("form_data")
    if not isinstance(details, dict):
        details = application
    with st.container(border=True):
        st.subheader("Financing Details")
        detail_columns = st.columns(2)
        with detail_columns[0]:
            st.write(
                f"**Financing Purpose:** "
                f"{details.get('financing_purpose') or 'Not Available'}"
            )
            st.write(
                f"**Requested Tenure:** "
                f"{details.get('requested_tenure_months', 'Not Available')} months"
            )
            st.write(
                f"**Repayment Frequency:** "
                f"{details.get('repayment_frequency') or 'Not Available'}"
            )
            st.write(
                f"**Financing Cost / Fees:** "
                f"{details.get('financing_cost_amount') if details.get('financing_cost_amount') is not None else 'Not provided'}"
            )
        with detail_columns[1]:
            capacity = details.get("capacity_amount")
            st.write(
                "**Declared Repayment Capacity:** "
                f"{details.get('capacity_currency') or ''} "
                f"{capacity:,.2f} ({details.get('capacity_period') or 'period unavailable'})"
                if isinstance(capacity, (int, float))
                else "**Declared Repayment Capacity:** Not provided"
            )
            st.write(
                f"**Existing Financing:** "
                f"{details.get('existing_financing_answer') or 'Not Available'}"
            )
            if details.get("existing_financing_answer") == "Yes":
                st.write(
                    f"**Provider:** {details.get('obligation_provider') or 'Not provided'}"
                )
                for label, key in (
                    ("Outstanding Balance", "obligation_balance"),
                    ("Monthly Repayment", "obligation_monthly_repayment"),
                    ("Remaining Tenure (months)", "obligation_remaining_tenure"),
                ):
                    st.write(
                        f"**{label}:** "
                        f"{details.get(key) if details.get(key) is not None else 'Not provided'}"
                    )

    documents = application.get("documents", [])
    uploads = application.get("uploaded_file_names", {})
    if not documents:
        documents = [
            {"document_type": document_type, "file_name": file_name}
            for document_type, file_name in uploads.items()
        ]
    document_labels = {
        "invoices": ("Sales Invoices", "Excel workbook (.xlsx)", "invoices"),
        "bank_statement_pdf": (
            "Bank Statements",
            "PDF statement",
            "bank_transactions",
        ),
        "supporting_pdf": (
            "Additional Supporting Document",
            "PDF document",
            None,
        ),
    }
    extraction_results = {
        "bank_statement_pdf": application.get("pdf_extraction_results"),
        "supporting_pdf": application.get("supporting_pdf_extraction_results"),
    }
    invoices = application.get("invoices")
    transactions = application.get("bank_transactions")
    data_frames = {
        "invoices": invoices,
        "bank_transactions": transactions,
    }
    validation = application.get("validation_report")
    validation_reports = validation if isinstance(validation, dict) else {}
    with st.container(border=True):
        st.subheader("Uploaded Documents")
        if not documents:
            st.caption("No uploaded documents are recorded for this application.")
        for document in documents:
            document_type = str(document.get("document_type", "document"))
            label, file_type, validation_key = document_labels.get(
                document_type,
                (document_type.replace("_", " ").title(), "File type unavailable", None),
            )
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.write(f"**File:** {document.get('file_name', 'Not Available')}")
                st.caption(file_type)
                extraction = extraction_results.get(document_type)
                frame = data_frames.get(validation_key)
                if isinstance(frame, pd.DataFrame):
                    st.success(f"Processed · {len(frame):,} data rows extracted.")
                elif isinstance(extraction, dict):
                    st.success(
                        "Processed · "
                        f"{extraction.get('total_pages', 0):,} PDF page(s) extracted."
                    )
                else:
                    st.info("Processing results are not available for this document.")

                if validation_key:
                    report = validation_reports.get(validation_key)
                    if isinstance(report, dict):
                        errors = report.get("errors", [])
                        warnings = report.get("warnings", [])
                        if errors:
                            st.error(f"Validation found {len(errors):,} issue group(s).")
                        elif validation:
                            st.success("No validation errors reported.")
                        if warnings:
                            st.warning(
                                f"Validation warnings: {sum(item.get('count', 0) for item in warnings):,}."
                            )
                        _render_issues(
                            f"{label} validation errors",
                            errors,
                            "error",
                        )
                        _render_issues(
                            f"{label} validation warnings",
                            warnings,
                            "warning",
                        )
                    else:
                        st.caption("Document validation results are unavailable.")

    with st.container(border=True):
        st.subheader("Financial Analysis")
        if all(
            isinstance(application.get(key), dict)
            for key in ("financial_analysis_result", "validation_report")
        ):
            if isinstance(invoices, pd.DataFrame):
                with st.expander("Invoice Analysis"):
                    st.caption(f"{len(invoices):,} invoice row(s) extracted.")
                    st.dataframe(
                        invoices,
                        use_container_width=True,
                        hide_index=True,
                    )
            if isinstance(transactions, pd.DataFrame):
                with st.expander("Bank Transaction Analysis"):
                    st.caption(
                        f"{len(transactions):,} transaction row(s) extracted."
                    )
                    st.dataframe(
                        transactions,
                        use_container_width=True,
                        hide_index=True,
                    )

            matching = application.get("invoice_matching_result")
            if isinstance(matching, dict):
                reconciliation = matching.get("summary", {})
                st.markdown("#### Invoice-to-Bank Reconciliation")
                reconciliation_columns = st.columns(4)
                for column, (label, value) in zip(
                    reconciliation_columns,
                    (
                        ("Invoices", reconciliation.get("total_invoices", 0)),
                        (
                            "Matched Payments",
                            reconciliation.get("matched_payment_transactions", 0),
                        ),
                        (
                            "Unmatched Transactions",
                            reconciliation.get("unmatched_transactions", 0),
                        ),
                        (
                            "Ambiguous Transactions",
                            reconciliation.get("ambiguous_transactions", 0),
                        ),
                    ),
                ):
                    with column:
                        st.metric(label, value)
                with st.expander("Reconciliation Details"):
                    for key, label in (
                        ("invoice_matches", "Invoice matches"),
                        ("unmatched_transactions", "Unmatched transactions"),
                        ("ambiguous_transactions", "Ambiguous transactions"),
                        ("non_payment_transactions", "Non-payment transactions"),
                    ):
                        records = matching.get(key, [])
                        st.markdown(f"**{label} ({len(records):,})**")
                        if records:
                            st.dataframe(
                                pd.DataFrame(records),
                                use_container_width=True,
                                hide_index=True,
                            )
                        else:
                            st.caption("None.")

            _render_client_financial_analysis(
                application,
                title="Financial Summary",
                include_insights=False,
            )
        else:
            st.info(
                "No previously generated financial analysis is available for "
                "this application. Opening this view does not run processing."
            )

def _render_client_analysis_preview() -> None:
    """Render processing results inside the financing request dialog."""
    pending = st.session_state.get("client_pending_application")
    if (
        not pending
        or pending.get("lifecycle_state") != "analysis_ready"
        or pending.get("analysis_stale")
    ):
        st.info("No current analysis-ready draft is available.")
        if st.button(
            "Continue Editing Draft",
            key="client_preview_resume_edit",
        ):
            _open_financing_request_from_dashboard()
        return

    st.subheader("Document Processing Results")
    st.markdown(
        "Documents were processed for review. The financing request has not "
        "been submitted to a bank."
    )

    pdf_extraction = pending.get("pdf_extraction_results", {})
    transactions = pending.get("bank_transactions", pd.DataFrame())
    if pdf_extraction:
        st.success(
            f"Bank statement PDF extracted successfully: "
            f"{pdf_extraction.get('total_pages', 0)} page(s), "
            f"{len(transactions):,} transaction row(s)."
        )
        with st.expander("View extracted bank statement text"):
            st.text(pdf_extraction.get("full_text", ""))
    invoices = pending.get("invoices", pd.DataFrame())
    with st.expander("Invoice Analysis", expanded=True):
        st.caption(f"{len(invoices):,} invoice row(s) extracted.")
        if isinstance(invoices, pd.DataFrame):
            st.dataframe(invoices, use_container_width=True, hide_index=True)
    with st.expander("Bank Transaction Analysis", expanded=True):
        st.caption(f"{len(transactions):,} transaction row(s) extracted.")
        if isinstance(transactions, pd.DataFrame):
            st.dataframe(
                transactions,
                use_container_width=True,
                hide_index=True,
            )

    matching = pending.get("invoice_matching_result", {})
    reconciliation_summary = (
        matching.get("summary", {}) if isinstance(matching, dict) else {}
    )
    with st.container(border=True):
        st.subheader("Invoice-to-Bank Reconciliation")
        reconciliation_columns = st.columns(4)
        for column, (label, value) in zip(
            reconciliation_columns,
            (
                ("Invoices", reconciliation_summary.get("total_invoices", 0)),
                (
                    "Matched Payment Transactions",
                    reconciliation_summary.get("matched_payment_transactions", 0),
                ),
                (
                    "Unmatched Transactions",
                    reconciliation_summary.get("unmatched_transactions", 0),
                ),
                (
                    "Ambiguous Transactions",
                    reconciliation_summary.get("ambiguous_transactions", 0),
                ),
            ),
        ):
            with column:
                st.metric(label, value)

        with st.expander("Reconciliation Details"):
            for key, label in (
                ("invoice_matches", "Invoice matches"),
                ("unmatched_transactions", "Unmatched transactions"),
                ("ambiguous_transactions", "Ambiguous transactions"),
                ("non_payment_transactions", "Non-payment transactions"),
            ):
                records = matching.get(key, [])
                st.markdown(f"**{label} ({len(records):,})**")
                if records:
                    st.dataframe(
                        pd.DataFrame(records),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("None.")

    preview_application = dict(pending)
    preview_application["application_id"] = pending["draft_id"]
    insights = pending.get("financial_insights_result", {})
    _render_client_financial_analysis(
        preview_application,
        title="Financial Summary",
        include_insights=False,
    )
    if isinstance(insights, dict):
        _render_client_financial_insights(insights)

    validation_report = pending.get("validation_report")
    validation_summary = (
        validation_report.get("summary", {})
        if isinstance(validation_report, dict)
        else {}
    )
    validation_passed = validation_summary.get("is_valid") is True
    if validation_passed:
        st.success(
            "Documents were extracted, validated, reconciled, and analyzed."
        )
    else:
        st.error(
            "Required validation checks did not pass. Review the validation "
            "findings before relying on these results."
        )
    if not validation_passed:
        st.info(
            "Resolve the validation issues before submitting. You can save "
            "this request as a draft or edit its details and documents."
        )

    action_columns = st.columns(4)
    if action_columns[0].button(
        "Save as Draft",
        key="client_processing_save_draft",
        use_container_width=True,
    ):
        _finish_pending_client_application(
            "Draft",
            "Financing application saved as a draft.",
        )
        st.rerun()
    if action_columns[1].button(
        "Edit",
        key="client_processing_edit",
        use_container_width=True,
    ):
        _finish_pending_client_application(
            "Draft",
            "Draft saved. Select Edit Draft in the applications list to continue editing.",
        )
        st.rerun()
    if action_columns[2].button(
        "Cancel",
        key="client_processing_cancel",
        use_container_width=True,
    ):
        _finish_pending_client_application(
            "Cancelled",
            "Financing application cancelled.",
        )
        st.rerun()
    if action_columns[3].button(
        "Submit",
        key="client_processing_submit",
        type="primary",
        use_container_width=True,
        disabled=not validation_passed,
    ):
        _submit_pending_client_application()
        if not st.session_state.get("client_pending_application"):
            st.rerun()


def _render_client_applications() -> None:
    """Render the company's applications and the request creation entry point."""
    applications = _client_applications()
    with st.container(key="client-applications-page"):
        with st.container(key="client-applications-hero"):
            title_column, action_column = st.columns(
                [4, 1.65],
                vertical_alignment="center",
            )
            with title_column:
                st.markdown(
                    '<div class="applications-page-header">'
                    '<div class="applications-page-eyebrow">Company workspace</div>'
                    "<h1>Financing Applications</h1>"
                    "<p>Manage and track your company's financing requests.</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
            with action_column:
                st.button(
                    "New Financing Application",
                    key="client_applications_new_financing",
                    type="primary",
                    use_container_width=True,
                    on_click=_open_financing_request_from_dashboard,
                )

            message = st.session_state.pop("client_success_message", None)
            if message:
                st.success(message)

        with st.container(key="client-applications-summary"):
            application_statuses = [
                _client_application_status_label(application)
                for application in applications
            ]
            completed_statuses = {"Approved", "Rejected", "Cancelled"}
            in_progress_statuses = {
                "Draft",
                "Submitted",
                "Received",
                "Under Review",
                "More Information Required",
            }
            summary_cards = (
                ("Total Applications", len(applications)),
                (
                    "In Progress",
                    sum(status in in_progress_statuses for status in application_statuses),
                ),
                (
                    "Completed",
                    sum(status in completed_statuses for status in application_statuses),
                ),
            )
            for column, (label, value) in zip(
                st.columns(3),
                summary_cards,
            ):
                with column:
                    st.markdown(
                        '<div class="applications-summary-card">'
                        f'<div class="applications-page-label">{escape(label)}</div>'
                        f'<div class="applications-summary-value">{value:,}</div>'
                        "</div>",
                        unsafe_allow_html=True,
                    )

        pending = st.session_state.get("client_pending_application")
        current_view = st.session_state.get(
            "client_applications_view",
            "applications",
        )
        if current_view == "analysis_preview":
            st.session_state["client_applications_view"] = "applications"
            st.session_state["client_open_request_dialog"] = True
        if pending and pending.get("lifecycle_state") != "analysis_ready":
            st.markdown(
                '<div class="applications-draft-notice">'
                "<strong>Draft in progress</strong><br>"
                "An unsubmitted draft is saved in this session. Its earlier "
                "analysis is stale and must be run again before submission."
                "</div>",
                unsafe_allow_html=True,
            )
            st.button(
                "Continue Editing Draft",
                key="client_applications_edit_draft",
                on_click=_show_pending_preview,
            )
        elif pending:
            st.markdown(
                '<div class="applications-draft-notice">'
                "<strong>Processing complete</strong><br>"
                "Choose an action in the open request flow to save, edit, cancel, or submit."
                "</div>",
                unsafe_allow_html=True,
            )
            st.button(
                "Continue Request",
                key="client_applications_continue_preview",
                on_click=_show_pending_preview,
            )

        selected_id = st.session_state.get("client_selected_application_id")
        if selected_id:
            selected_application = next(
                (
                    application for application in applications
                    if application.get("application_id") == selected_id
                ),
                None,
            )
            if selected_application is None:
                st.session_state.pop("client_selected_application_id", None)
                st.error(
                    "This application is no longer available in the current session."
                )
            else:
                _render_client_application_detail(selected_application)
            return

        st.markdown(
            '<div class="applications-page-section-title">Your Applications</div>',
            unsafe_allow_html=True,
        )
        filter_column, search_column = st.columns([1, 2])
        with filter_column:
            selected_status = st.selectbox(
                "Filter by status",
                [
                    "All",
                    *[
                        status for status in CLIENT_APPLICATION_STATUSES
                    ],
                ],
                key="client_application_status_filter",
            )
        with search_column:
            search_text = st.text_input(
                "Search by Application ID or Financing Type",
                key="client_application_search",
            ).strip()

        filtered = applications
        if selected_status != "All":
            filtered = [
                application for application in filtered
                if _client_application_status_label(application) == selected_status
            ]
        if search_text:
            query = search_text.casefold()
            filtered = [
                application for application in filtered
                if query in str(application.get("application_id", "")).casefold()
                or query in str(application.get("financing_type", "")).casefold()
            ]
        filtered = sorted(
            filtered,
            key=lambda application: str(
                application.get("submitted_at")
                or application.get("updated_at")
                or application.get("created_at")
                or ""
            ),
            reverse=True,
        )

        def application_badge(status: str) -> str:
            badge_class = {
                "Approved": "approved",
                "Under Review": "review",
                "More Information Required": "review",
                "Submitted": "submitted",
                "Received": "submitted",
                "Rejected": "rejected",
                "Draft": "submitted",
                "Cancelled": "submitted",
            }.get(status, "rejected")
            return (
                f'<span class="applications-status-badge '
                f'applications-status-badge--{badge_class}">'
                f"{escape(status)}</span>"
            )

        if not filtered:
            if not applications:
                st.markdown(
                    '<div class="applications-empty-state">'
                    "<strong>No financing applications yet</strong><br>"
                    "Start a new request to see your applications here."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="applications-empty-state">'
                    "<strong>No matching applications</strong><br>"
                    "Try changing the search text or status filter."
                    "</div>",
                    unsafe_allow_html=True,
                )
            return

        st.caption(f"{len(filtered):,} application(s)")
        for row_start in range(0, len(filtered), 2):
            with st.container(key=f"client-application-row-{row_start}"):
                for column, application in zip(
                    st.columns(2),
                    filtered[row_start:row_start + 2],
                ):
                    application_id = str(
                        application.get("application_id") or "Not Available"
                    )
                    status = _client_application_status_label(application)
                    amount = application.get("requested_amount")
                    amount_text = (
                        f"{escape(str(application.get('requested_currency') or ''))} "
                        f"{amount:,.2f}"
                        if isinstance(amount, (int, float))
                        else "Not Available"
                    )
                    submitted_at = str(
                        application.get("submitted_at")
                        or application.get("updated_at")
                        or application.get("created_at")
                        or "Not Available"
                    )
                    submitted_date = submitted_at.split("T", 1)[0]
                    date_label = (
                        "Created"
                        if status == "Draft"
                        else "Cancelled"
                        if status == "Cancelled"
                        else "Submitted"
                    )
                    with column:
                        st.markdown(
                            '<div class="applications-record-card">'
                            '<div class="applications-record-top">'
                            f'<div class="applications-record-reference">{escape(application_id)}</div>'
                            f"{application_badge(status)}"
                            "</div>"
                            f'<div class="applications-record-type">'
                            f"{escape(str(application.get('financing_type') or 'Not Available'))}"
                            "</div>"
                            '<div class="applications-record-meta">'
                            f"<span><strong>{amount_text}</strong></span>"
                            f"<span>{date_label} {escape(submitted_date)}</span>"
                            "</div>"
                            "</div>",
                            unsafe_allow_html=True,
                        )
                        st.button(
                            "View Application Details",
                            key=f"client_open_application_{application_id}",
                            on_click=lambda app_id=application_id: (
                                st.session_state.__setitem__(
                                    "client_selected_application_id",
                                    app_id,
                                )
                            ),
                            use_container_width=True,
                        )


client_navigation_pages = [
    "Dashboard",
    "Financing Applications",
]
if (
    st.session_state.get("client_navigation") not in client_navigation_pages
):
    st.session_state.pop("client_navigation", None)
if (
    "client_navigation" not in st.session_state
    and st.session_state.get("last_client_navigation") in client_navigation_pages
):
    st.session_state["client_navigation"] = st.session_state[
        "last_client_navigation"
    ]

with st.sidebar:
    st.image(str(LOGO_PATH), width=190)
    st.markdown(
        '<p class="sidebar-caption">SME financing workspace</p>',
        unsafe_allow_html=True,
    )
    st.caption("A clearer path to business financing.")

with st.container(key="portal-navigation"):
    page = st.radio(
        "Client navigation",
        client_navigation_pages,
        format_func=lambda value: (
            "?  Dashboard"
            if value == "Dashboard"
            else "?  Financing Applications"
        ),
        horizontal=True,
        label_visibility="collapsed",
        key="client_navigation",
        on_change=_remember_client_navigation,
    )

if page == "Dashboard":
    _render_client_dashboard()
else:
    _render_client_applications()
    if st.session_state.pop("client_open_request_dialog", False):
        _request_financing_dialog()
