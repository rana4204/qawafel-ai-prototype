from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4


class MockBankError(RuntimeError):
    """Base error for a rejected or failed mock bank operation."""


class InvalidRequestError(MockBankError, ValueError):
    """Raised when an application or financing package is invalid."""


class DuplicateSubmissionError(MockBankError):
    """Raised when an existing application reference is reused with new data."""


class SimulatedBankError(MockBankError):
    """Raised when a caller requests a simulated bank-side failure."""


class MockBankAPI:
    """In-process mock of the partner bank's application API.

    Each instance owns an isolated in-memory data store. Submitting the same
    Qawafel application reference and identical payload is idempotent: the
    original acknowledgment is returned. Reusing that reference for different
    data raises :class:`DuplicateSubmissionError`.
    """

    RECEIVED_STATUS = "received"
    ALLOWED_STATUSES = frozenset({
        RECEIVED_STATUS,
        "under_review",
        "more_information_required",
        "approved",
        "rejected",
    })

    def __init__(self) -> None:
        self._applications: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def submit_application(
        self,
        application: Mapping[str, Any],
        financing_package: Mapping[str, Any],
        *,
        simulate_error: bool = False,
    ) -> dict[str, Any]:
        """Receive an application/package and return a bank acknowledgment."""
        if simulate_error:
            raise SimulatedBankError("Mock bank rejected the request (simulated error).")

        normalized_application = self._validate_application(application)
        normalized_package = self._validate_package(financing_package)
        fingerprint = self._fingerprint(normalized_application, normalized_package)
        application_reference = normalized_application["application_id"]

        with self._lock:
            existing = self._applications.get(application_reference)
            if existing is not None:
                if existing["fingerprint"] != fingerprint:
                    raise DuplicateSubmissionError(
                        f"Application {application_reference!r} was already received "
                        "with different data."
                    )
                acknowledgment = deepcopy(existing["acknowledgment"])
                acknowledgment["duplicate"] = True
                return acknowledgment

            bank_reference = f"MB-{uuid4().hex[:12].upper()}"
            received_at = self._now()
            acknowledgment = {
                "acknowledged": True,
                "application_reference": application_reference,
                "bank_reference": bank_reference,
                "status": self.RECEIVED_STATUS,
                "received_at": received_at,
                "duplicate": False,
            }
            record = {
                "application_reference": application_reference,
                "bank_reference": bank_reference,
                "application": deepcopy(normalized_application),
                "financing_package": deepcopy(normalized_package),
                "status": self.RECEIVED_STATUS,
                "updated_at": received_at,
                "status_events": [{
                    "event_id": f"EVT-{uuid4().hex[:12].upper()}",
                    "application_reference": application_reference,
                    "bank_reference": bank_reference,
                    "previous_status": None,
                    "status": self.RECEIVED_STATUS,
                    "recorded_at": received_at,
                    "source": "mock_bank_api",
                    "note": "Application received by the mock bank.",
                }],
                "fingerprint": fingerprint,
                "acknowledgment": deepcopy(acknowledgment),
            }
            self._applications[application_reference] = record
            return deepcopy(acknowledgment)

    def get_application_status(self, application_reference: str) -> dict[str, Any]:
        """Return the bank's current status and bank reference for an application."""
        reference = self._validate_reference(application_reference)
        with self._lock:
            record = self._applications.get(reference)
            if record is None:
                raise InvalidRequestError(
                    f"No bank application found for reference {reference!r}."
                )
            return {
                "application_reference": reference,
                "bank_reference": record["bank_reference"],
                "status": record["status"],
                "updated_at": record["updated_at"],
            }

    def generate_status_update(
        self,
        application_reference: str,
        status: str,
        *,
        note: str = "",
    ) -> dict[str, Any]:
        """Record and return a status event for Qawafel to consume."""
        reference = self._validate_reference(application_reference)
        normalized_status = status.strip().casefold() if isinstance(status, str) else ""
        if normalized_status not in self.ALLOWED_STATUSES:
            choices = ", ".join(sorted(self.ALLOWED_STATUSES))
            raise InvalidRequestError(f"Unsupported status. Expected one of: {choices}.")
        if not isinstance(note, str):
            raise InvalidRequestError("Status update note must be a string.")

        with self._lock:
            record = self._applications.get(reference)
            if record is None:
                raise InvalidRequestError(
                    f"No bank application found for reference {reference!r}."
                )
            previous_status = record["status"]
            recorded_at = self._now()
            event = {
                "event_id": f"EVT-{uuid4().hex[:12].upper()}",
                "application_reference": reference,
                "bank_reference": record["bank_reference"],
                "previous_status": previous_status,
                "status": normalized_status,
                "recorded_at": recorded_at,
                "source": "mock_bank_api",
                "note": note.strip(),
            }
            record["status"] = normalized_status
            record["updated_at"] = recorded_at
            record["status_events"].append(event)
            return deepcopy(event)

    def get_status_events(self, application_reference: str) -> list[dict[str, Any]]:
        """Return a copy of all status events in recorded order."""
        reference = self._validate_reference(application_reference)
        with self._lock:
            record = self._applications.get(reference)
            if record is None:
                raise InvalidRequestError(
                    f"No bank application found for reference {reference!r}."
                )
            return deepcopy(record["status_events"])

    def get_application(self, application_reference: str) -> dict[str, Any]:
        """Return a copy of the stored application and financing package."""
        reference = self._validate_reference(application_reference)
        with self._lock:
            record = self._applications.get(reference)
            if record is None:
                raise InvalidRequestError(
                    f"No bank application found for reference {reference!r}."
                )
            return deepcopy({key: value for key, value in record.items() if key != "fingerprint"})

    @staticmethod
    def _validate_application(application: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(application, Mapping):
            raise InvalidRequestError("Application must be a mapping/object.")
        normalized = dict(application)
        reference = normalized.get("application_id") or normalized.get("application_reference")
        if not isinstance(reference, str) or not reference.strip():
            raise InvalidRequestError(
                "Application must include a non-empty application_id or application_reference."
            )
        normalized["application_id"] = reference.strip()
        for field in ("company_name", "financing_type", "requested_currency"):
            value = normalized.get(field)
            if not isinstance(value, str) or not value.strip():
                raise InvalidRequestError(f"Application must include a non-empty {field}.")
            normalized[field] = value.strip()
        amount = normalized.get("requested_amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise InvalidRequestError("Application requested_amount must be a positive number.")
        if not math.isfinite(float(amount)) or float(amount) <= 0:
            raise InvalidRequestError("Application requested_amount must be a positive finite number.")
        return MockBankAPI._ensure_json_mapping(normalized, "Application")

    @staticmethod
    def _validate_package(financing_package: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(financing_package, Mapping) or not financing_package:
            raise InvalidRequestError("Financing package must be a non-empty mapping/object.")
        return MockBankAPI._ensure_json_mapping(dict(financing_package), "Financing package")

    @staticmethod
    def _ensure_json_mapping(value: dict[str, Any], label: str) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, allow_nan=False)
            decoded = json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise InvalidRequestError(f"{label} must contain JSON-compatible values: {exc}") from exc
        return decoded

    @staticmethod
    def _validate_reference(reference: str) -> str:
        if not isinstance(reference, str) or not reference.strip():
            raise InvalidRequestError("Application reference must be a non-empty string.")
        return reference.strip()

    @staticmethod
    def _fingerprint(application: dict[str, Any], package: dict[str, Any]) -> str:
        canonical = json.dumps(
            {"application": application, "financing_package": package},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "DuplicateSubmissionError",
    "InvalidRequestError",
    "MockBankAPI",
    "MockBankError",
    "SimulatedBankError",
]
