"""Client-side orchestration for sending analyzed financing requests to a bank API."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from modules.mock_bank_api import MockBankError


class SubmissionBlockedError(ValueError):
    """Raised when a draft is stale or has not passed document validation."""


def submit_client_application(
    bank_api: Any,
    pending: dict[str, Any],
    applications: list[dict[str, Any]],
) -> tuple[dict[str, Any], bool]:
    """Submit an analysis-ready client draft and return (record, duplicate)."""
    if (
        not isinstance(pending, dict)
        or pending.get("lifecycle_state") != "analysis_ready"
        or pending.get("analysis_stale")
    ):
        raise SubmissionBlockedError("The application analysis is missing or stale.")

    report = pending.get("validation_report")
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    if summary.get("is_valid") is not True:
        raise SubmissionBlockedError(
            "Resolve the required document validation errors before submitting."
        )

    existing = next((
        item for item in applications
        if item.get("draft_id") == pending.get("draft_id")
        and item.get("lifecycle_state") == "submitted"
    ), None)
    if existing is not None:
        return existing, True

    # Keep this reference on the pending draft before the API call. If the call
    # fails, retrying uses the same idempotency key.
    application_id = pending.get("application_id")
    if not application_id:
        application_id = f"APP-{uuid4().hex[:12].upper()}"
        pending["application_id"] = application_id

    application_context = deepcopy(pending.get("application_context") or {})
    application_context["application_id"] = application_id
    company = pending.get("company_profile_snapshot") or {}
    application_payload = {
        "application_id": application_id,
        "company_name": pending.get("company_name") or company.get("company_name"),
        "financing_type": pending.get("financing_type"),
        "requested_amount": pending.get("requested_amount"),
        "requested_currency": pending.get("requested_currency"),
        "submitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    package = _build_financing_package(pending, application_context)

    try:
        acknowledgment = bank_api.submit_application(application_payload, package)
    except MockBankError:
        raise
    except Exception as exc:
        raise MockBankError(f"Mock bank submission failed: {exc}") from exc

    if not isinstance(acknowledgment, Mapping):
        raise MockBankError("Mock bank returned an invalid acknowledgment response.")
    required_ack_fields = ("acknowledged", "bank_reference", "status", "received_at")
    if (
        acknowledgment.get("acknowledged") is not True
        or any(not acknowledgment.get(field) for field in required_ack_fields[1:])
    ):
        raise MockBankError("Mock bank did not acknowledge the application.")

    record = deepcopy(pending)
    submitted_at = str(acknowledgment["received_at"])
    record.update({
        "application_id": application_id,
        "application_context": application_context,
        "status": str(acknowledgment["status"]).casefold(),
        "lifecycle_state": "submitted",
        "analysis_stale": False,
        "source": "Client Submission",
        "submitted_at": submitted_at,
        "bank_reference": str(acknowledgment["bank_reference"]),
        "bank_acknowledgment": deepcopy(dict(acknowledgment)),
        "bank_status_updated_at": submitted_at,
        "status_history": [
            {
                "event_id": f"QWF-{uuid4().hex[:12].upper()}",
                "previous_status": "Draft",
                "new_status": str(acknowledgment["status"]).casefold(),
                "recorded_at": submitted_at,
                "source": "Mock Bank API",
            }
        ],
        "review_history": [],
        "review_notes": [],
        "financing_package": package,
    })
    record["financial_insights_result"] = _refresh_insights(record)
    applications.append(record)
    return record, False


def apply_bank_status_events(
    application: dict[str, Any],
    current_status: Mapping[str, Any],
    events: list[Mapping[str, Any]],
) -> None:
    """Update the client record from API-originated status data and history."""
    status = current_status.get("status")
    if isinstance(status, str) and status.strip():
        application["status"] = status.strip().casefold()
    application["bank_status_updated_at"] = current_status.get("updated_at")
    application["bank_reference"] = current_status.get("bank_reference") or application.get("bank_reference")

    existing = [
        event for event in application.get("status_history", [])
        if isinstance(event, dict) and event.get("source") != "Mock Bank API"
    ]
    api_events = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        api_events.append({
            "event_id": event.get("event_id"),
            "previous_status": event.get("previous_status") or "draft",
            "new_status": event.get("status"),
            "recorded_at": event.get("recorded_at"),
            "source": "Mock Bank API",
            "note": event.get("note", ""),
        })
    application["status_history"] = sorted(
        existing + api_events,
        key=lambda event: str(event.get("recorded_at", "")),
    )


def _build_financing_package(
    pending: Mapping[str, Any],
    application_context: dict[str, Any],
) -> dict[str, Any]:
    """Select structured applicant, document, validation, and analysis data."""
    return {
        "application_context": application_context,
        "company_profile": deepcopy(pending.get("company_profile_snapshot") or {}),
        "documents": deepcopy(pending.get("documents") or []),
        "uploaded_document_names": deepcopy(pending.get("uploaded_file_names") or {}),
        "validation_report": deepcopy(pending.get("validation_report") or {}),
        "invoice_matching": deepcopy(pending.get("invoice_matching_result") or {}),
        "financial_analysis": deepcopy(pending.get("financial_analysis_result") or {}),
        "financial_insights": deepcopy(pending.get("financial_insights_result") or {}),
    }


def _refresh_insights(application: dict[str, Any]) -> Any:
    """Recompute insight references with the final Qawafel application ID."""
    from modules.ai_insights import generate_financial_insights

    return generate_financial_insights(
        application.get("financial_analysis_result", {}),
        application.get("invoice_matching_result", {}),
        application.get("validation_report", {}),
        application.get("application_context", {}),
    )


__all__ = [
    "SubmissionBlockedError",
    "apply_bank_status_events",
    "submit_client_application",
]
