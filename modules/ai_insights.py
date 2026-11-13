"""Evidence-based, rule-only financial insights for financing applications.

Expected ``application_context`` keys:

* ``application_id``
* ``requested_amount``, ``requested_currency``, ``requested_tenure_months``
* ``financial_currency``: currency of the supplied financial analysis
* ``financing_purpose_code`` and optional ``financing_purpose_description``
* ``repayment_schedule`` and ``financing_cost`` (optional supplied details)
* ``repayment_capacity``: optional mapping with ``amount``, ``currency``,
  ``measurement_period``, ``verification_status``, and ``source``
* ``existing_financing``: mapping with ``declared``, ``exists``,
  ``outstanding_balance``, ``monthly_repayment``, ``provider``,
  ``remaining_tenure_months``, ``verification_status``, and
  ``supporting_evidence``
* ``uploaded_documents``: optional list of document-type strings or mappings
  containing ``document_type``

Expected ``policy`` key:

* ``purpose_document_requirements``: mapping from a purpose code to a list of
  required document-type strings. These are configuration supplied by the
  caller, not built-in requirements.

Financial comparisons are descriptive only. This module does not determine
eligibility, approve or decline applications, authenticate documents, or call
an external AI service.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


RULE_SET_VERSION = "1.0.0"

_CATEGORIES = {
    "financial_strength": ("Financial strength", "نقطة قوة مالية"),
    "potential_risk": ("Potential financial risk", "مخاطر مالية محتملة"),
    "financing_request": ("Financing request assessment", "تقييم طلب التمويل"),
    "existing_obligations": ("Existing financial obligations", "الالتزامات المالية القائمة"),
    "data_quality": ("Data quality", "جودة البيانات"),
    "missing_information": ("Missing information", "معلومات ناقصة"),
    "recommended_action": ("Recommended action", "إجراء موصى به"),
    "limitation": ("Limitation", "قيد"),
}

_STATUSES = {
    "observed": ("Observed", "تم رصدها"),
    "attention": ("Review required", "تتطلب المراجعة"),
    "missing": ("Missing", "مفقود"),
    "configuration_missing": ("Configuration missing", "إعداد المتطلبات غير متوفر"),
    "borrower_declared": ("Borrower-declared", "مصرح به من مقدم الطلب"),
    "verified": ("Marked as verified", "محدد على أنه متحقق منه"),
    "not_reviewed": ("Not reviewed by a bank employee", "لم يراجعه موظف بنك"),
    "not_applicable": ("Not applicable based on declaration", "غير منطبق وفقاً للإقرار"),
}

_TITLES = {
    "FS-01": ("Sales Growth", "نمو المبيعات"),
    "FS-02": ("Positive Net Cash Flow", "صافي تدفق نقدي موجب"),
    "FS-03": ("Invoice Collection Coverage", "تغطية تحصيل الفواتير"),
    "FS-04": ("Fully Collected Invoices", "فواتير محصلة بالكامل"),
    "FR-01": ("Declining Sales", "تراجع المبيعات"),
    "FR-02": ("Negative Net Cash Flow", "صافي تدفق نقدي سالب"),
    "FR-03": ("Outstanding Receivables", "ذمم مدينة مستحقة"),
    "FR-04": ("Unmatched Bank Credits", "إيداعات بنكية غير مطابقة"),
    "FR-05": ("Ambiguous Transactions", "معاملات ملتبسة"),
    "FR-06": ("Payment Status Discrepancies", "اختلافات حالة السداد"),
    "FA-01": ("Requested Amount vs Annual Sales", "مبلغ التمويل المطلوب مقارنة بالمبيعات السنوية"),
    "FA-02": ("Requested Amount vs Confirmed Collections", "مبلغ التمويل المطلوب مقارنة بالتحصيلات المؤكدة"),
    "FA-03": ("Requested Amount vs Net Cash Flow", "مبلغ التمويل المطلوب مقارنة بصافي التدفق النقدي"),
    "FA-04": ("Outstanding Receivables and Request", "الذمم المدينة مقارنة بطلب التمويل"),
    "FT-01": ("Requested Tenure", "مدة التمويل المطلوبة"),
    "FT-02": ("Repayment Schedule Availability", "توفر جدول السداد"),
    "FT-03": ("Financing Cost Availability", "توفر تكلفة التمويل"),
    "FT-04": ("Repayment Capacity Data Availability", "توفر بيانات القدرة على السداد"),
    "FP-01": ("Financing Purpose Documentation", "مستندات غرض التمويل"),
    "FO-01": ("Existing Financing Disclosure", "الإفصاح عن التمويل القائم"),
    "FO-02": ("Outstanding Balance Review", "مراجعة الرصيد القائم"),
    "FO-03": ("Monthly Obligations", "الالتزامات الشهرية"),
    "FO-04": ("Missing Obligation Details", "تفاصيل الالتزامات الناقصة"),
    "FO-05": ("Obligation Data Verification", "التحقق من بيانات الالتزامات"),
    "DQ-01": ("Missing Required Fields", "حقول مطلوبة ناقصة"),
    "DQ-02": ("Duplicate Invoice IDs", "معرفات فواتير مكررة"),
    "DQ-03": ("Invalid Financial Values", "قيم مالية غير صالحة"),
    "DQ-04": ("Invoice Total Mismatch", "عدم تطابق إجمالي الفاتورة"),
    "DQ-05": ("Payment Status Discrepancies", "اختلافات حالة السداد"),
    "DQ-06": ("Ambiguous Transactions", "معاملات ملتبسة"),
    "DQ-07": ("Unmatched Transactions", "معاملات غير مطابقة"),
    "DQ-08": ("Purpose Document Requirements", "متطلبات مستندات الغرض"),
    "MI-01": ("Annual Sales Period Unavailable", "فترة المبيعات السنوية غير متاحة"),
    "MI-02": ("Financial Currency Unavailable", "عملة البيانات المالية غير متاحة"),
    "MI-03": ("Financial Metric Unavailable", "مؤشر مالي غير متاح"),
    "MI-04": ("Application Information Missing", "معلومات الطلب ناقصة"),
    "LIMIT-01": ("No Invoice Due Date", "لا يتوفر تاريخ استحقاق الفاتورة"),
    "LIMIT-02": ("No Financing Decision", "لا يصدر قرار تمويلي"),
    "LIMIT-03": ("No Repayment Affordability Calculation", "لا يتم احتساب القدرة على تحمل السداد"),
    "LIMIT-04": ("Verification Is Not Performed", "لا يتم إجراء تحقق مستقل"),
    "LIMIT-05": ("No External AI Service", "لا توجد خدمة ذكاء اصطناعي خارجية"),
}


def _text(language: str, english: str, arabic: str) -> str:
    """Choose localized text without changing IDs or numeric values."""
    return english if language == "en" else arabic


def _field_label(field: str, language: str) -> str:
    """Translate known schema field labels while preserving source values."""
    labels = {
        "application_id": ("application identifier", "معرف الطلب"),
        "requested_amount": ("requested amount", "مبلغ التمويل المطلوب"),
        "requested_currency": ("requested currency", "عملة الطلب"),
        "financial_currency": ("financial-data currency", "عملة البيانات المالية"),
        "requested_tenure_months": ("requested tenure", "مدة التمويل المطلوبة"),
        "financing_purpose_code": ("financing purpose", "غرض التمويل"),
        "repayment_schedule": ("repayment schedule", "جدول السداد"),
        "financing_cost": ("financing cost", "تكلفة التمويل"),
        "amount": ("amount", "المبلغ"),
        "currency": ("currency", "العملة"),
        "measurement_period": ("measurement period", "الفترة الزمنية"),
        "outstanding_balance": ("outstanding balance", "الرصيد القائم"),
        "monthly_repayment": ("monthly repayment", "القسط الشهري"),
        "provider": ("financing provider", "الجهة الممولة"),
        "remaining_tenure_months": ("remaining tenure", "المدة المتبقية"),
    }
    english, arabic = labels.get(field, (field.replace("_", " "), field))
    return _text(language, english, arabic)


def _is_missing(value: Any) -> bool:
    """Return whether a supplied scalar is absent or a blank string."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, bool):
        return False
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _number(value: Any) -> float | None:
    """Convert a finite numeric value without treating booleans as numbers."""
    if _is_missing(value) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _count(value: Any) -> int | None:
    """Return a non-negative integral count when the value is well formed."""
    numeric = _number(value)
    if numeric is None or numeric < 0 or not numeric.is_integer():
        return None
    return int(numeric)


def _mapping(value: Any) -> dict[str, Any]:
    """Return a mapping input or an empty mapping for optional nested data."""
    return value if isinstance(value, dict) else {}


def _is_empty_collection(value: Any) -> bool:
    """Return whether an optional collection was explicitly supplied empty."""
    return isinstance(value, (dict, list, tuple, set)) and len(value) == 0


def _has_supplied_content(value: Any) -> bool:
    """Check that optional structured data contains at least one real value."""
    if _is_missing(value) or value is False:
        return False
    if isinstance(value, dict):
        return any(_has_supplied_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_supplied_content(item) for item in value)
    return True


def _path(mapping: dict[str, Any], dotted_path: str) -> Any:
    """Read an existing nested key without fabricating a default value."""
    current: Any = mapping
    for key in dotted_path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _evidence(
    source: str,
    metric_path: str,
    value: Any,
    currency: str | None = None,
    measurement_period: str | None = None,
) -> dict[str, Any]:
    """Build a traceable evidence item from an actual input path."""
    item: dict[str, Any] = {
        "source": source,
        "metric_path": metric_path,
        "value": value,
    }
    if isinstance(currency, str) and currency.strip():
        item["currency"] = currency
    if isinstance(measurement_period, str) and measurement_period.strip():
        item["measurement_period"] = measurement_period
    return item


def _finding(
    rule_id: str,
    category: str,
    status: str,
    explanation: str,
    evidence: list[dict[str, Any]],
    recommended_action: str | None,
    language: str,
) -> dict[str, Any]:
    """Create the common localized finding structure."""
    title = _TITLES.get(rule_id, (rule_id, rule_id))
    category_text = _CATEGORIES[category]
    status_text = _STATUSES[status]
    return {
        "rule_id": rule_id,
        "category": _text(language, *category_text),
        "status": _text(language, *status_text),
        "title": _text(language, *title),
        "explanation": explanation,
        "evidence": evidence,
        "recommended_action": recommended_action,
        "review_status": _text(language, *_STATUSES["not_reviewed"]),
    }


def _append_finding(
    destination: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    finding: dict[str, Any],
    language: str,
) -> None:
    """Append a finding and expose its suggested action as a separate item."""
    destination.append(finding)
    action = finding.get("recommended_action")
    if action:
        actions.append({
            "rule_id": finding["rule_id"],
            "category": _text(language, *_CATEGORIES["recommended_action"]),
            "status": _text(language, *_STATUSES["attention"]),
            "title": finding["title"],
            "explanation": action,
            "evidence": finding["evidence"],
            "recommended_action": action,
            "review_status": _text(language, *_STATUSES["not_reviewed"]),
        })


def _month(value: Any) -> str | None:
    """Validate an analyzer month value in YYYY-MM format."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m")


def _period(months: list[str], language: str = "en") -> str | None:
    """Describe the first and last known months when both are available."""
    valid_months = sorted({month for item in months if (month := _month(item))})
    if not valid_months:
        return None
    if len(valid_months) == 1:
        return valid_months[0]
    separator = " to " if language == "en" else " إلى "
    return f"{valid_months[0]}{separator}{valid_months[-1]}"


def _quality_count(
    analysis: dict[str, Any],
    group: str,
    path: str,
) -> int | None:
    """Read a finite, non-negative count from analyzer quality details."""
    value = _path(
        _mapping(_path(analysis, "data_quality.missing_or_invalid_financial_values")),
        f"{group}.{path}",
    )
    return _count(value)


def _invoice_totals_valid(
    analysis: dict[str, Any],
    validation: dict[str, Any],
) -> bool:
    """Require complete, non-negative invoice totals for total-based rules."""
    fields = (
        ("missing", "missing"),
        ("non_numeric_or_non_finite", "non_numeric_or_non_finite"),
        ("negative", "negative"),
    )
    for analyzer_key, _ in fields:
        count = _quality_count(
            analysis, "invoices", f"amount_columns.total_amount.{analyzer_key}"
        )
        if count is None or count:
            return False
    invoice_report = _mapping(validation.get("invoices"))
    if _count(invoice_report.get("duplicate_invoice_ids")) not in (0,):
        return False
    validation_missing = _mapping(invoice_report.get("missing_values"))
    if _count(validation_missing.get("total_amount")) not in (0,):
        return False
    for key in ("non_numeric_amounts", "negative_amounts"):
        values = _mapping(invoice_report.get(key))
        if _count(values.get("total_amount")) not in (0,):
            return False
    return True


def _bank_values_valid(
    analysis: dict[str, Any],
    validation: dict[str, Any],
    columns: tuple[str, ...] = ("credit", "debit"),
) -> bool:
    """Require complete, finite, non-negative bank amounts for cash rules."""
    for column in columns:
        for key in (
            f"missing_{column}",
            f"non_numeric_or_non_finite_{column}",
            f"negative_{column}",
        ):
            count = _quality_count(analysis, "bank_transactions", key)
            if count is None or count:
                return False
        bank_report = _mapping(validation.get("bank_transactions"))
        if _count(_mapping(bank_report.get("missing_values")).get(column)) not in (0,):
            return False
        for report_key in ("non_numeric_values", "negative_values"):
            if _count(_mapping(bank_report.get(report_key)).get(column)) not in (0,):
                return False
    return True


def _currency_pair(
    context: dict[str, Any],
) -> tuple[str | None, str | None, bool]:
    """Return requested/financial currency labels and whether they match."""
    requested = context.get("requested_currency")
    financial = context.get("financial_currency")
    requested_text = requested.strip() if isinstance(requested, str) else None
    financial_text = financial.strip() if isinstance(financial, str) else None
    matches = bool(
        requested_text
        and financial_text
        and requested_text.casefold() == financial_text.casefold()
    )
    return requested_text, financial_text, matches


def _monthly_sales(
    analysis: dict[str, Any],
) -> list[tuple[str, float]]:
    """Read only valid month/amount pairs from analyzer sales output."""
    records = _path(analysis, "sales.monthly_invoiced_sales")
    result: list[tuple[str, float]] = []
    if not isinstance(records, list):
        return result
    for record in records:
        if not isinstance(record, dict):
            continue
        month = _month(record.get("month"))
        amount = _number(record.get("amount"))
        if month is not None and amount is not None:
            result.append((month, amount))
    return sorted(result)


def _months_are_consecutive(months: list[str]) -> bool:
    """Check that the supplied unique month labels have no calendar gaps."""
    if not months or len(set(months)) != len(months):
        return False
    parsed = [datetime.strptime(month, "%Y-%m") for month in months]
    return all(
        (right.year - left.year) * 12 + right.month - left.month == 1
        for left, right in zip(parsed, parsed[1:])
    )


def _annual_sales(
    analysis: dict[str, Any],
    validation: dict[str, Any],
    language: str,
    currency: str | None,
) -> tuple[float | None, str | None, list[dict[str, Any]]]:
    """Sum the latest 12 consecutive reported months, if all are usable."""
    if not _invoice_totals_valid(analysis, validation):
        return None, None, []
    invoice_quality = _mapping(
        _path(analysis, "data_quality.missing_or_invalid_financial_values.invoices")
    )
    for key in ("missing_invoice_date", "invalid_invoice_date"):
        count = _count(invoice_quality.get(key))
        if count is None or count:
            return None, None, []
    monthly = _monthly_sales(analysis)
    if len(monthly) < 12:
        return None, None, []
    latest = monthly[-12:]
    months = [month for month, _ in latest]
    if not _months_are_consecutive(months):
        return None, None, []
    total = sum(amount for _, amount in latest)
    period = _period(months, language)
    evidence = [
        _evidence(
            "financial_analysis",
            "sales.monthly_invoiced_sales",
            [{"month": month, "amount": amount} for month, amount in latest],
            currency=currency,
            measurement_period=period,
        )
    ]
    return total, period, evidence


def _bank_period(analysis: dict[str, Any], language: str) -> str | None:
    """Return a bank period only when every transaction date is usable."""
    quality = _mapping(
        _path(analysis, "data_quality.missing_or_invalid_financial_values.bank_transactions")
    )
    for key in ("missing_transaction_date", "invalid_transaction_date"):
        count = _count(quality.get(key))
        if count is None or count:
            return None
    monthly = _path(analysis, "cash_flow.monthly_net_cash_flow")
    if not isinstance(monthly, list):
        return None
    return _period([
        record.get("month")
        for record in monthly
        if isinstance(record, dict) and isinstance(record.get("month"), str)
    ], language)


def _invoice_period(analysis: dict[str, Any], language: str) -> str | None:
    """Return invoice months only when all invoice dates are usable."""
    quality = _mapping(
        _path(analysis, "data_quality.missing_or_invalid_financial_values.invoices")
    )
    for key in ("missing_invoice_date", "invalid_invoice_date"):
        count = _count(quality.get(key))
        if count is None or count:
            return None
    return _period(
        [month for month, _ in _monthly_sales(analysis)],
        language,
    )


def _missing_finding(
    rule_id: str,
    explanation: str,
    evidence: list[dict[str, Any]],
    action: str,
    missing: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    language: str,
) -> None:
    """Record unavailable evidence without substituting a numeric value."""
    finding = _finding(
        rule_id,
        "missing_information",
        "missing",
        explanation,
        evidence,
        action,
        language,
    )
    _append_finding(missing, actions, finding, language)


def _data_quality_finding(
    rule_id: str,
    evidence: list[dict[str, Any]],
    explanation: str,
    action: str,
    issues: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    language: str,
) -> None:
    """Add an issue only when its input evidence records a positive count."""
    if not evidence:
        return
    finding = _finding(
        rule_id, "data_quality", "attention", explanation, evidence, action, language
    )
    _append_finding(issues, actions, finding, language)


def _validation_missing_evidence(
    validation: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collect absent required application and dataset fields from real inputs."""
    evidence: list[dict[str, Any]] = []
    for key in ("application_id", "requested_amount", "requested_currency",
                "financial_currency", "requested_tenure_months",
                "financing_purpose_code"):
        if key not in context or _is_missing(context.get(key)):
            evidence.append(_evidence(
                "application_context", key, context.get(key)
            ))

    required_columns = {
        "invoices": (
            "invoice_id", "invoice_date", "customer_name", "net_amount",
            "vat_amount", "total_amount", "payment_status",
        ),
        "bank_transactions": (
            "transaction_id", "transaction_date", "description", "debit",
            "credit", "balance",
        ),
    }
    for section, required in required_columns.items():
        report = _mapping(validation.get(section))
        missing_columns = report.get("missing_columns")
        if isinstance(missing_columns, list):
            for column in missing_columns:
                if column in required:
                    evidence.append(_evidence(
                        "validation_report",
                        f"{section}.missing_columns",
                        column,
                    ))
        missing_values = _mapping(report.get("missing_values"))
        for column in required:
            if section == "bank_transactions" and column in {"debit", "credit"}:
                continue
            count = _count(missing_values.get(column))
            if count is not None and count > 0:
                evidence.append(_evidence(
                    "validation_report",
                    f"{section}.missing_values.{column}",
                    count,
                ))
    return evidence


def _validation_numeric_evidence(
    validation: dict[str, Any],
    analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    """Collect exact non-numeric and negative amount counters."""
    evidence: list[dict[str, Any]] = []
    sections = (
        ("invoices", ("non_numeric_amounts", "negative_amounts")),
        ("bank_transactions", ("non_numeric_values", "negative_values")),
    )
    for section, keys in sections:
        report = _mapping(validation.get(section))
        for key in keys:
            counts = _mapping(report.get(key))
            for column, value in counts.items():
                count = _count(value)
                if count:
                    evidence.append(_evidence(
                        "validation_report",
                        f"{section}.{key}.{column}",
                        count,
                    ))

    amount_data = _mapping(
        _path(analysis, "data_quality.missing_or_invalid_financial_values")
    )
    for group in ("invoices", "bank_transactions"):
        detail = _mapping(amount_data.get(group))
        if group == "invoices":
            detail = _mapping(detail.get("amount_columns"))
            for column, metrics in detail.items():
                metrics = _mapping(metrics)
                for key in ("non_numeric_or_non_finite", "negative"):
                    count = _count(metrics.get(key))
                    if count:
                        evidence.append(_evidence(
                            "financial_analysis",
                            f"data_quality.missing_or_invalid_financial_values.invoices.amount_columns.{column}.{key}",
                            count,
                        ))
        else:
            for key, value in detail.items():
                if key.startswith((
                    "non_numeric_or_non_finite_",
                    "negative_",
                    "missing_credit",
                    "missing_debit",
                )):
                    count = _count(value)
                    if count:
                        evidence.append(_evidence(
                            "financial_analysis",
                            f"data_quality.missing_or_invalid_financial_values.bank_transactions.{key}",
                            count,
                        ))
    return evidence


def _existing_obligation_findings(
    context: dict[str, Any],
    language: str,
    missing: list[dict[str, Any]],
    actions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Assess declared obligations while retaining their verification state."""
    findings: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    obligations = context.get("existing_financing")
    if not isinstance(obligations, dict) or obligations.get("declared") is not True:
        _missing_finding(
            "FO-01",
            _text(
                language,
                "No existing-financing declaration was supplied; this does not mean obligations are zero.",
                "لم يتم تقديم إقرار بالتمويل القائم؛ ولا يعني ذلك أن الالتزامات تساوي صفراً.",
            ),
            [_evidence("application_context", "existing_financing.declared",
                       obligations.get("declared") if isinstance(obligations, dict) else None)],
            _text(language, "Request an explicit existing-financing declaration.",
                  "اطلب إقراراً صريحاً بالتمويل القائم."),
            missing,
            actions,
            language,
        )
        return findings, evidence_records

    exists = obligations.get("exists")
    declaration_status = obligations.get("verification_status")
    verified = declaration_status == "verified"
    declaration_state = "verified" if verified else "borrower_declared"
    evidence_records.append(_evidence(
        "application_context",
        "existing_financing.declared",
        obligations.get("declared"),
    ))
    evidence_records.append(_evidence(
        "application_context",
        "existing_financing.exists",
        exists,
    ))
    finding = _finding(
        "FO-01",
        "existing_obligations",
        declaration_state,
        _text(
            language,
            "The applicant supplied an existing-financing declaration. Its verification state is shown separately.",
            "قدم مقدم الطلب إقراراً بالتمويل القائم، وتُعرض حالة التحقق منه بشكل منفصل.",
        ),
        evidence_records[:],
        _text(language, "Review the declaration and its supporting evidence.",
              "راجع الإقرار والمستندات الداعمة له."),
        language,
    )
    _append_finding(findings, actions, finding, language)

    if exists is False:
        not_applicable = _finding(
            "FO-02",
            "existing_obligations",
            "not_applicable",
            _text(
                language,
                "The borrower declared that no existing financing exists; this is a declaration, not independent verification.",
                "أفاد مقدم الطلب بعدم وجود تمويل قائم؛ وهذا إقرار وليس تحققاً مستقلاً.",
            ),
            [_evidence("application_context", "existing_financing.exists", False)],
            _text(language, "Retain the declaration and verify it under bank procedures if required.",
                  "احتفظ بالإقرار وتحقق منه وفق إجراءات البنك عند الحاجة."),
            language,
        )
        _append_finding(findings, actions, not_applicable, language)
        return findings, evidence_records

    if exists is not True:
        _missing_finding(
            "FO-04",
            _text(language, "The declaration does not state whether existing financing exists.",
                  "لا يوضح الإقرار ما إذا كان هناك تمويل قائم."),
            [_evidence("application_context", "existing_financing.exists", exists)],
            _text(language, "Clarify the existing-financing declaration.",
                  "اطلب توضيحاً بشأن الإقرار بالتمويل القائم."),
            missing,
            actions,
            language,
        )
        return findings, evidence_records

    required_details = (
        ("outstanding_balance", "FO-02"),
        ("monthly_repayment", "FO-03"),
        ("provider", "FO-04"),
        ("remaining_tenure_months", "FO-04"),
    )
    missing_details: list[str] = []
    for key, rule_id in required_details:
        value = obligations.get(key)
        if key == "provider":
            valid_value = isinstance(value, str) and bool(value.strip())
        elif key == "remaining_tenure_months":
            valid_value = (_count(value) or 0) > 0
        elif key in {"outstanding_balance", "monthly_repayment"}:
            number = _number(value)
            valid_value = number is not None and number >= 0
        else:
            valid_value = not _is_missing(value)
        if not valid_value:
            missing_details.append(key)
            continue
        if key in {"outstanding_balance", "monthly_repayment"}:
            number = _number(value)
            if number is None or number < 0:
                missing_details.append(key)
                continue
            evidence = [_evidence(
                "application_context",
                f"existing_financing.{key}",
                value,
                currency=obligations.get("currency") or context.get("financial_currency"),
                measurement_period=(
                    "monthly" if key == "monthly_repayment" else None
                ),
            )]
        else:
            evidence = [_evidence(
                "application_context", f"existing_financing.{key}", value,
                measurement_period=(
                    "months" if key == "remaining_tenure_months" else None
                ),
            )]
        if rule_id in {"FO-02", "FO-03"}:
            title_finding = _finding(
                rule_id,
                "existing_obligations",
                declaration_state,
                _text(
                    language,
                    f"The borrower reported {_field_label(key, language)}; the value is not independently verified by this engine.",
                    f"أفاد مقدم الطلب بقيمة {_field_label(key, language)}؛ ولا يتحقق هذا المحرك منها بشكل مستقل.",
                ),
                evidence,
                _text(language, "Review the reported amount and supporting evidence.",
                      "راجع المبلغ المبلغ عنه والمستندات الداعمة."),
                language,
            )
            _append_finding(findings, actions, title_finding, language)

    if missing_details:
        detail_evidence = [
            _evidence(
                "application_context",
                f"existing_financing.{key}",
                obligations.get(key),
            )
            for key in missing_details
        ]
        _missing_finding(
            "FO-04",
            _text(
                language,
                "Some declared financing details are missing or invalid: "
                + ", ".join(_field_label(key, language) for key in missing_details) + ".",
                "بعض تفاصيل التمويل المصرح به ناقصة أو غير صالحة: "
                + "، ".join(_field_label(key, language) for key in missing_details) + ".",
            ),
            detail_evidence,
            _text(language, "Request the missing provider, balance, monthly commitment, or remaining-tenure details.",
                  "اطلب بيانات الجهة الممولة أو الرصيد أو الالتزام الشهري أو المدة المتبقية."),
            missing,
            actions,
            language,
        )

    supporting = obligations.get("supporting_evidence")
    verification_evidence = [
        _evidence(
            "application_context",
            "existing_financing.verification_status",
            declaration_status,
        ),
        _evidence(
            "application_context",
            "existing_financing.supporting_evidence",
            supporting,
        ),
    ]
    verified_finding = _finding(
        "FO-05",
        "existing_obligations",
        "verified" if verified else "borrower_declared",
        _text(
            language,
            "Verification status reflects supplied application metadata; this engine does not authenticate the evidence.",
            "تعكس حالة التحقق بيانات الطلب المقدمة؛ ولا يتحقق هذا المحرك من صحة المستندات.",
        ),
        verification_evidence,
        None if verified else _text(
            language,
            "Obtain and review supporting evidence before treating the obligation details as verified.",
            "احصل على المستندات الداعمة وراجعها قبل اعتبار تفاصيل الالتزام متحققاً منها.",
        ),
        language,
    )
    _append_finding(findings, actions, verified_finding, language)
    return findings, evidence_records


def generate_financial_insights(
    financial_analysis: dict,
    matching_result: dict,
    validation_report: dict,
    application_context: dict,
    language: str = "en",
    policy: dict | None = None,
) -> dict:
    """Generate evidence-based findings from already-computed assessment data.

    The function does not rerun validation, invoice matching, or financial
    analysis. It accepts ``language`` values ``"en"`` and ``"ar"`` only.

    ``application_context`` and ``policy`` follow the schemas documented in
    this module's docstring. ``financial_currency`` must be supplied from a
    trusted source; the existing analyzer does not return currency metadata.
    """
    for name, value in (
        ("financial_analysis", financial_analysis),
        ("matching_result", matching_result),
        ("validation_report", validation_report),
        ("application_context", application_context),
    ):
        if not isinstance(value, dict):
            raise TypeError(f"{name} must be a dictionary")
    if policy is not None and not isinstance(policy, dict):
        raise TypeError("policy must be a dictionary or None")
    if not isinstance(language, str) or language not in {"en", "ar"}:
        raise ValueError("language must be 'en' or 'ar'")

    policy_data = policy or {}
    context = application_context
    validation = validation_report
    analysis = financial_analysis
    missing_information: list[dict[str, Any]] = []
    recommended_actions: list[dict[str, Any]] = []
    financial_strengths: list[dict[str, Any]] = []
    potential_risks: list[dict[str, Any]] = []
    financing_request_assessment: list[dict[str, Any]] = []
    data_quality_issues: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    matching_summary = _mapping(matching_result.get("summary"))
    ambiguous_records = matching_result.get("ambiguous_transactions")
    ambiguous_count = (
        len(ambiguous_records)
        if isinstance(ambiguous_records, list)
        else _count(matching_summary.get("ambiguous_transactions"))
    )
    unmatched_records = matching_result.get("unmatched_transactions")
    unmatched_count = (
        len(unmatched_records)
        if isinstance(unmatched_records, list)
        else _count(matching_summary.get("unmatched_transactions"))
    )

    app_id = context.get("application_id")
    if _is_missing(app_id):
        _missing_finding(
            "MI-04",
            _text(language, "The application identifier is not available.",
                  "معرف الطلب غير متوفر."),
            [_evidence("application_context", "application_id", app_id)],
            _text(language, "Associate this assessment with an application record.",
                  "اربط هذا التقييم بسجل طلب التمويل."),
            missing_information,
            recommended_actions,
            language,
        )

    # Data quality: missing application and validator-required values/columns.
    missing_evidence = _validation_missing_evidence(validation, context)
    _data_quality_finding(
        "DQ-01",
        missing_evidence,
        _text(
            language,
            "Required application or dataset fields are missing; calculations that depend on them may be unavailable.",
            "توجد حقول مطلوبة ناقصة في الطلب أو البيانات؛ وقد لا تتوفر الحسابات المعتمدة عليها.",
        ),
        _text(language, "Supply the missing required fields and correct the source documents.",
              "أكمل الحقول المطلوبة وصحح المستندات المصدرية."),
        data_quality_issues,
        recommended_actions,
        language,
    )
    if missing_evidence:
        _missing_finding(
            "DQ-01",
            _text(language, "The required fields listed in the data-quality evidence are missing.",
                  "الحقول المطلوبة الموضحة في أدلة جودة البيانات ناقصة."),
            missing_evidence,
            _text(language, "Provide the missing fields before relying on dependent findings.",
                  "قدم الحقول الناقصة قبل الاعتماد على النتائج المرتبطة بها."),
            missing_information,
            recommended_actions,
            language,
        )

    invoice_validation = _mapping(validation.get("invoices"))
    duplicate_invoice_count = _count(invoice_validation.get("duplicate_invoice_ids"))
    if duplicate_invoice_count:
        _data_quality_finding(
            "DQ-02",
            [_evidence("validation_report", "invoices.duplicate_invoice_ids",
                       duplicate_invoice_count)],
            _text(language, "The invoice validation report identifies duplicate invoice IDs.",
                  "يشير تقرير التحقق من الفواتير إلى وجود معرفات فواتير مكررة."),
            _text(language, "Resolve duplicate invoice IDs and re-run validation and matching.",
                  "عالج معرفات الفواتير المكررة ثم أعد التحقق والمطابقة."),
            data_quality_issues,
            recommended_actions,
            language,
        )

    numeric_evidence = _validation_numeric_evidence(validation, analysis)
    _data_quality_finding(
        "DQ-03",
        numeric_evidence,
        _text(language, "The supplied reports identify missing, non-numeric, non-finite, or negative financial values.",
              "تحدد التقارير المقدمة قيماً مالية مفقودة أو غير رقمية أو غير منتهية أو سالبة."),
        _text(language, "Correct the identified financial values in the source records and reprocess them.",
              "صحح القيم المالية المحددة في السجلات المصدرية ثم أعد معالجتها."),
        data_quality_issues,
        recommended_actions,
        language,
    )

    mismatch_count = _count(invoice_validation.get("total_mismatch_count"))
    if mismatch_count:
        _data_quality_finding(
            "DQ-04",
            [_evidence("validation_report", "invoices.total_mismatch_count",
                       mismatch_count)],
            _text(language, "Invoice totals differ from net amount plus VAT in the validation report.",
                  "تختلف إجماليات بعض الفواتير عن صافي المبلغ مضافاً إليه ضريبة القيمة المضافة وفق تقرير التحقق."),
            _text(language, "Review the affected invoice calculations and correct source records.",
                  "راجع حسابات الفواتير المعنية وصحح السجلات المصدرية."),
            data_quality_issues,
            recommended_actions,
            language,
        )

    discrepancies = _count(_path(
        analysis, "data_quality.payment_status_discrepancies"
    ))
    if discrepancies is None:
        discrepancies = _count(_path(
            matching_result, "summary.payment_status_discrepancies"
        ))
    if discrepancies:
        evidence = [_evidence(
            "financial_analysis" if _path(
                analysis, "data_quality.payment_status_discrepancies"
            ) is not None else "matching_result",
            "data_quality.payment_status_discrepancies"
            if _path(analysis, "data_quality.payment_status_discrepancies") is not None
            else "summary.payment_status_discrepancies",
            discrepancies,
        )]
        _data_quality_finding(
            "DQ-05", evidence,
            _text(language, "Recorded invoice payment statuses conflict with calculated collection statuses.",
                  "تتعارض حالات سداد الفواتير المسجلة مع حالات التحصيل المحسوبة."),
            _text(language, "Review the affected payment statuses against bank evidence.",
                  "راجع حالات السداد المعنية مقارنة بأدلة البنك."),
            data_quality_issues,
            recommended_actions,
            language,
        )

    if ambiguous_count:
        ambiguous_path = (
            "summary.ambiguous_transactions"
            if _count(matching_summary.get("ambiguous_transactions")) is not None
            else "ambiguous_transactions"
        )
        ambiguous_value = (
            matching_summary.get("ambiguous_transactions")
            if ambiguous_path.startswith("summary.")
            else ambiguous_records
        )
        _data_quality_finding(
            "DQ-06",
            [_evidence("matching_result", ambiguous_path,
                       ambiguous_value)],
            _text(language, "Some bank transactions could not be assigned to one unique invoice.",
                  "تعذر إسناد بعض المعاملات البنكية إلى فاتورة واحدة فريدة."),
            _text(language, "Review transaction references; ambiguous credits are not confirmed invoice collections.",
                  "راجع مراجع المعاملات؛ ولا تعد الإيداعات الملتبسة تحصيلات فواتير مؤكدة."),
            data_quality_issues,
            recommended_actions,
            language,
        )

    if unmatched_count:
        unmatched_path = (
            "summary.unmatched_transactions"
            if _count(matching_summary.get("unmatched_transactions")) is not None
            else "unmatched_transactions"
        )
        unmatched_value = (
            matching_summary.get("unmatched_transactions")
            if unmatched_path.startswith("summary.")
            else unmatched_records
        )
        _data_quality_finding(
            "DQ-07",
            [_evidence("matching_result", unmatched_path,
                       unmatched_value)],
            _text(language, "Some transactions do not reference a recognized invoice ID.",
                  "لا تتضمن بعض المعاملات مرجعاً لمعرف فاتورة معروف."),
            _text(language, "Review unmatched transactions and classify them using supporting records.",
                  "راجع المعاملات غير المطابقة وصنفها بالاستناد إلى السجلات الداعمة."),
            data_quality_issues,
            recommended_actions,
            language,
        )

    # Strengths and risks use actual analyzer fields only.
    sales_quality = _mapping(
        _path(analysis, "data_quality.missing_or_invalid_financial_values.invoices")
    )
    monthly_trend = _path(analysis, "sales.monthly_sales_trend")
    valid_sales_trend = (
        isinstance(monthly_trend, list)
        and _invoice_totals_valid(analysis, validation)
        and all(_count(sales_quality.get(key)) == 0
                for key in ("missing_invoice_date", "invalid_invoice_date"))
    )
    trend_records = [
        record for record in monthly_trend
        if isinstance(record, dict)
        and _month(record.get("month")) is not None
        and _number(record.get("sales")) is not None
    ] if isinstance(monthly_trend, list) else []
    if valid_sales_trend and len(trend_records) >= 2:
        previous, latest = trend_records[-2], trend_records[-1]
        previous_month = _month(previous.get("month"))
        latest_month = _month(latest.get("month"))
        if previous_month and latest_month and _months_are_consecutive(
            [previous_month, latest_month]
        ):
            change = _number(latest.get("change_from_previous_month"))
            period = f"{previous_month} to {latest_month}"
            evidence = [_evidence(
                "financial_analysis",
                "sales.monthly_sales_trend",
                [
                    {"month": previous_month, "sales": previous.get("sales")},
                    {"month": latest_month, "sales": latest.get("sales")},
                    {"change_from_previous_month": change},
                ],
                currency=context.get("financial_currency"),
                measurement_period=period,
            )]
            if change is not None and change > 0:
                _append_finding(
                    financial_strengths,
                    recommended_actions,
                    _finding(
                        "FS-01", "financial_strength", "observed",
                        _text(language,
                              f"Invoiced sales increased by {change:,.2f} between the latest two consecutive reported months. This is a historical observation, not a forecast.",
                              f"زادت المبيعات المفوترة بمقدار {change:,.2f} بين أحدث شهرين متتاليين مُبلغ عنهما. هذه ملاحظة تاريخية وليست توقعاً."),
                        evidence,
                        _text(language, "Review the monthly sales records and confirm the trend.",
                              "راجع سجلات المبيعات الشهرية وتحقق من الاتجاه."),
                        language,
                    ),
                    language,
                )
            elif change is not None and change < 0:
                _append_finding(
                    potential_risks,
                    recommended_actions,
                    _finding(
                        "FR-01", "potential_risk", "attention",
                        _text(language,
                              f"Invoiced sales decreased by {abs(change):,.2f} between the latest two consecutive reported months. This is a historical observation, not a forecast.",
                              f"انخفضت المبيعات المفوترة بمقدار {abs(change):,.2f} بين أحدث شهرين متتاليين مُبلغ عنهما. هذه ملاحظة تاريخية وليست توقعاً."),
                        evidence,
                        _text(language, "Review the underlying sales records and ask the applicant for relevant context.",
                              "راجع سجلات المبيعات واطلب من مقدم الطلب توضيح السياق ذي الصلة."),
                        language,
                    ),
                    language,
                )

    net_cash_flow = _number(_path(analysis, "cash_flow.net_cash_flow"))
    cash_valid = _bank_values_valid(analysis, validation)
    bank_period = _bank_period(analysis, language)
    if net_cash_flow is not None and cash_valid:
        cash_evidence = [_evidence(
            "financial_analysis",
            "cash_flow.net_cash_flow",
            _path(analysis, "cash_flow.net_cash_flow"),
            currency=context.get("financial_currency"),
            measurement_period=bank_period,
        )]
        if net_cash_flow > 0:
            _append_finding(
                financial_strengths,
                recommended_actions,
                _finding(
                    "FS-02", "financial_strength", "observed",
                    _text(language,
                          (
                              f"The reported bank cash-flow total is positive for {bank_period}; historical cash flow does not establish future repayment capacity."
                              if bank_period else
                              "The reported bank cash-flow total is positive, but its transaction-date period is incomplete or unavailable."
                          ),
                          (
                              f"إجمالي التدفق النقدي البنكي المبلغ عنه موجب للفترة {bank_period}؛ ولا يثبت التدفق التاريخي القدرة المستقبلية على السداد."
                              if bank_period else
                              "إجمالي التدفق النقدي البنكي المبلغ عنه موجب، لكن فترة تواريخ المعاملات غير مكتملة أو غير متاحة."
                          )),
                    cash_evidence,
                    _text(language, "Review the bank statement period and consider other verified obligations and cash-flow information.",
                          "راجع فترة كشف الحساب وخذ في الاعتبار الالتزامات الأخرى ومعلومات التدفق النقدي المتحقق منها."),
                    language,
                ),
                language,
            )
        elif net_cash_flow < 0:
            _append_finding(
                potential_risks,
                recommended_actions,
                _finding(
                    "FR-02", "potential_risk", "attention",
                    _text(language,
                          (
                              f"The reported bank cash-flow total is negative for {bank_period}."
                              if bank_period else
                              "The reported bank cash-flow total is negative, but its transaction-date period is incomplete or unavailable."
                          ),
                          (
                              f"إجمالي التدفق النقدي البنكي المبلغ عنه سالب للفترة {bank_period}."
                              if bank_period else
                              "إجمالي التدفق النقدي البنكي المبلغ عنه سالب، لكن فترة تواريخ المعاملات غير مكتملة أو غير متاحة."
                          )),
                    cash_evidence,
                    _text(language, "Review the underlying credits and debits with the applicant; this historical total is not a forecast.",
                          "راجع الإيداعات والخصومات مع مقدم الطلب؛ فهذا الإجمالي التاريخي ليس توقعاً."),
                    language,
                ),
                language,
            )
    elif _path(analysis, "cash_flow.net_cash_flow") is None:
        _missing_finding(
            "MI-03",
            _text(language, "Net cash flow is not available in the financial analysis.",
                  "صافي التدفق النقدي غير متاح في التحليل المالي."),
            [_evidence("financial_analysis", "cash_flow.net_cash_flow",
                       _path(analysis, "cash_flow.net_cash_flow"),
                       currency=context.get("financial_currency"))],
            _text(language, "Provide a complete financial analysis with bank cash-flow metrics.",
                  "قدم تحليلاً مالياً مكتملاً يتضمن مؤشرات التدفق النقدي البنكي."),
            missing_information,
            recommended_actions,
            language,
        )

    coverage = _number(_path(
        analysis, "receivables.invoice_collection_coverage_percent"
    ))
    if (coverage is not None and 0 <= coverage <= 100
            and _invoice_totals_valid(analysis, validation)):
        if coverage > 0:
            _append_finding(
                financial_strengths,
                recommended_actions,
                _finding(
                    "FS-03", "financial_strength", "observed",
                    _text(language,
                          f"Invoice collection coverage is {coverage:.2f}% of invoiced sales. This is descriptive and is not a target or eligibility threshold.",
                          f"تبلغ تغطية تحصيل الفواتير {coverage:.2f}% من المبيعات المفوترة. وهذه قيمة وصفية وليست معياراً مستهدفاً أو شرط أهلية."),
                    [_evidence(
                        "financial_analysis",
                        "receivables.invoice_collection_coverage_percent",
                        _path(analysis, "receivables.invoice_collection_coverage_percent"),
                        measurement_period=_invoice_period(analysis, language),
                    )],
                    _text(language, "Review the invoice-level collection records and period.",
                          "راجع سجلات التحصيل على مستوى الفاتورة والفترة."),
                    language,
                ),
                language,
            )
    elif _path(analysis, "receivables.invoice_collection_coverage_percent") is None:
        _missing_finding(
            "MI-03",
            _text(language, "Invoice collection coverage is unavailable.",
                  "تغطية تحصيل الفواتير غير متاحة."),
            [_evidence(
                "financial_analysis",
                "receivables.invoice_collection_coverage_percent",
                _path(analysis, "receivables.invoice_collection_coverage_percent"),
            )],
            _text(language, "Provide valid invoice totals and matcher-based collection results.",
                  "قدم إجماليات فواتير صالحة ونتائج تحصيل مستندة إلى المطابقة."),
            missing_information,
            recommended_actions,
            language,
        )

    fully_collected = _count(_path(
        analysis, "receivables.fully_collected_invoice_count"
    ))
    if fully_collected and _invoice_totals_valid(analysis, validation):
        _append_finding(
            financial_strengths,
            recommended_actions,
            _finding(
                "FS-04", "financial_strength", "observed",
                _text(language,
                      f"{fully_collected} invoice(s) are classified as fully collected by the matcher.",
                      f"صنف نظام المطابقة {fully_collected} فاتورة على أنها محصلة بالكامل."),
                [_evidence(
                    "financial_analysis",
                    "receivables.fully_collected_invoice_count",
                    _path(analysis, "receivables.fully_collected_invoice_count"),
                )],
                _text(language, "Review the underlying matched credits and invoice statuses.",
                      "راجع الإيداعات المطابقة وحالات الفواتير ذات الصلة."),
                language,
            ),
            language,
        )

    outstanding = _number(_path(
        analysis, "receivables.outstanding_receivables"
    ))
    if outstanding is not None and outstanding > 0 and _invoice_totals_valid(
        analysis, validation
    ):
        _append_finding(
            potential_risks,
            recommended_actions,
            _finding(
                "FR-03", "potential_risk", "attention",
                _text(language,
                      "The analysis reports outstanding receivables; no aging or days-past-due conclusion is available.",
                      "يشير التحليل إلى وجود ذمم مدينة قائمة؛ ولا تتوفر نتيجة لتقادمها أو عدد أيام التأخر."),
                [_evidence(
                    "financial_analysis",
                    "receivables.outstanding_receivables",
                    _path(analysis, "receivables.outstanding_receivables"),
                    currency=context.get("financial_currency"),
                )],
                _text(language, "Review invoice-level balances and obtain due-date data separately if aging is required.",
                      "راجع الأرصدة على مستوى الفاتورة واطلب بيانات تواريخ الاستحقاق بشكل منفصل عند الحاجة إلى تحليل التقادم."),
                language,
            ),
            language,
        )

    unmatched_credits = _number(_path(
        analysis, "unclassified_transactions.unmatched_positive_credit_total"
    ))
    if unmatched_credits is not None and unmatched_credits > 0 and _bank_values_valid(
        analysis, validation, ("credit",)
    ):
        _append_finding(
            potential_risks,
            recommended_actions,
            _finding(
                "FR-04", "potential_risk", "attention",
                _text(language,
                      "Positive bank credits without a recognized invoice reference were reported; they are not treated as confirmed invoice collections.",
                      "تم رصد إيداعات بنكية موجبة دون مرجع فاتورة معروف؛ ولا تُعامل على أنها تحصيلات فواتير مؤكدة."),
                [_evidence(
                    "financial_analysis",
                    "unclassified_transactions.unmatched_positive_credit_total",
                    _path(analysis, "unclassified_transactions.unmatched_positive_credit_total"),
                    currency=context.get("financial_currency"),
                )],
                _text(language, "Review the transactions and obtain supporting records before classifying them.",
                      "راجع المعاملات واحصل على السجلات الداعمة قبل تصنيفها."),
                language,
            ),
            language,
        )
    elif unmatched_credits is None and isinstance(unmatched_records, list):
        _missing_finding(
            "MI-03",
            _text(language, "The unmatched positive-credit total is unavailable.",
                  "إجمالي الإيداعات الموجبة غير المطابقة غير متاح."),
            [],
            _text(language, "Provide the analyzer output for unclassified transaction totals.",
                  "قدم مخرجات التحليل الخاصة بإجماليات المعاملات غير المصنفة."),
            missing_information,
            recommended_actions,
            language,
        )

    if ambiguous_count:
        ambiguous_credit = _number(_path(
            analysis, "unclassified_transactions.ambiguous_positive_credit_total"
        ))
        risk_evidence = [
            _evidence(
                "matching_result",
                "summary.ambiguous_transactions"
                if _count(matching_summary.get("ambiguous_transactions")) is not None
                else "ambiguous_transactions",
                matching_summary.get("ambiguous_transactions")
                if _count(matching_summary.get("ambiguous_transactions")) is not None
                else ambiguous_records,
            )
        ]
        if ambiguous_credit is not None:
            risk_evidence.append(_evidence(
                "financial_analysis",
                "unclassified_transactions.ambiguous_positive_credit_total",
                _path(analysis, "unclassified_transactions.ambiguous_positive_credit_total"),
                currency=context.get("financial_currency"),
            ))
        _append_finding(
            potential_risks,
            recommended_actions,
            _finding(
                "FR-05", "potential_risk", "attention",
                _text(language,
                      "Transactions referencing multiple invoices or duplicated invoice IDs remain ambiguous and are excluded from confirmed collections.",
                      "تظل المعاملات التي تشير إلى عدة فواتير أو معرفات مكررة ملتبسة، وتُستبعد من التحصيلات المؤكدة."),
                risk_evidence,
                _text(language, "Resolve invoice references and duplicate identifiers before treating any such credit as collected.",
                      "عالج مراجع الفواتير والمعرفات المكررة قبل اعتبار أي إيداع منها تحصيلاً."),
                language,
            ),
            language,
        )

    if discrepancies:
        _append_finding(
            potential_risks,
            recommended_actions,
            _finding(
                "FR-06", "potential_risk", "attention",
                _text(language,
                      f"{discrepancies} recorded payment status(es) conflict with matcher-calculated collection status.",
                      f"تتعارض حالة سداد مسجلة لعدد {discrepancies} مع حالة التحصيل المحسوبة بالمطابقة."),
                evidence,
                _text(language, "Review payment statuses against confirmed bank credits; the recorded status alone is not proof of collection.",
                      "راجع حالات السداد مقارنة بالإيداعات البنكية المؤكدة؛ فالحالة المسجلة وحدها لا تثبت التحصيل."),
                language,
            ),
            language,
        )

    # Request comparisons are made only when currencies are explicitly equal.
    requested_amount = _number(context.get("requested_amount"))
    requested_currency, financial_currency, same_currency = _currency_pair(context)
    request_valid = requested_amount is not None and requested_amount > 0
    annual_sales, annual_period, annual_evidence = _annual_sales(
        analysis, validation, language, financial_currency
    )
    if request_valid and same_currency and annual_sales is not None:
        ratio = requested_amount / annual_sales if annual_sales > 0 else None
        evidence = [
            _evidence("application_context", "requested_amount",
                      context.get("requested_amount"), requested_currency),
            *annual_evidence,
        ]
        if ratio is not None:
            evidence.append(_evidence(
                "derived_from_inputs",
                "FA-01.requested_amount_to_annual_sales_ratio",
                ratio,
                measurement_period=annual_period,
            ))
        explanation = _text(
            language,
            (
                f"The request is {ratio:.4f} times the reported sales for "
                f"{annual_period}; this ratio is descriptive only and does "
                "not determine eligibility."
                if ratio is not None else
                f"Annual sales for {annual_period} are zero, so a ratio is not defined; no eligibility conclusion is made."
            ),
            (
                f"يعادل الطلب {ratio:.4f} مرة من المبيعات المبلغ عنها للفترة "
                f"{annual_period}؛ وهذه النسبة وصفية فقط ولا تحدد الأهلية."
                if ratio is not None else
                f"المبيعات السنوية للفترة {annual_period} تساوي صفراً، لذا لا يمكن حساب النسبة؛ ولا يصدر حكم على الأهلية."
            ),
        )
        _append_finding(
            financing_request_assessment,
            recommended_actions,
            _finding(
                "FA-01", "financing_request", "observed", explanation, evidence,
                _text(language, "Review the comparison alongside the complete application and bank policy.",
                      "راجع المقارنة إلى جانب الطلب الكامل وسياسة البنك."),
                language,
            ),
            language,
        )
    else:
        reason = (
            "A positive requested amount is required."
            if not request_valid else
            "Requested and financial currencies must be explicitly supplied and match."
            if not same_currency else
            "A complete, valid 12-consecutive-month sales period is unavailable."
        )
        reason_ar = (
            "يلزم تقديم مبلغ تمويل مطلوب موجب."
            if not request_valid else
            "يجب تقديم عملة الطلب وعملة البيانات المالية صراحةً وأن تكونا متطابقتين."
            if not same_currency else
            "لا تتوفر فترة مبيعات مكتملة وصالحة من 12 شهراً متتالياً."
        )
        _missing_finding(
            "FA-01", _text(language, reason, reason_ar),
            [
                _evidence("application_context", "requested_amount",
                          context.get("requested_amount"), requested_currency),
                *annual_evidence,
                _evidence(
                    "financial_analysis",
                    "sales.monthly_invoiced_sales",
                    _path(analysis, "sales.monthly_invoiced_sales"),
                    currency=financial_currency,
                ),
            ],
            _text(language, "Provide a valid request amount, matching currency labels, and 12 consecutive valid months of invoice sales.",
                  "قدم مبلغ طلب صالحاً وعملتين متطابقتين وبيانات مبيعات فواتير صالحة لمدة 12 شهراً متتالياً."),
            missing_information,
            recommended_actions,
            language,
        )

    confirmed_collections = _number(_path(
        analysis, "collections.total_confirmed_collections"
    ))
    collection_valid = (
        confirmed_collections is not None
        and _invoice_totals_valid(analysis, validation)
        and _bank_values_valid(analysis, validation, ("credit",))
        and isinstance(matching_result.get("invoice_matches"), list)
    )
    if request_valid and same_currency and collection_valid:
        ratio = (
            requested_amount / confirmed_collections
            if confirmed_collections > 0 else None
        )
        evidence = [
            _evidence("application_context", "requested_amount",
                      context.get("requested_amount"), requested_currency),
            _evidence("financial_analysis", "collections.total_confirmed_collections",
                      _path(analysis, "collections.total_confirmed_collections"),
                      financial_currency, _bank_period(analysis, language)),
        ]
        if ratio is not None:
            evidence.append(_evidence(
                "derived_from_inputs",
                "FA-02.requested_amount_to_confirmed_collections_ratio",
                ratio,
                measurement_period=_bank_period(analysis, language),
            ))
        _append_finding(
            financing_request_assessment,
            recommended_actions,
            _finding(
                "FA-02", "financing_request", "observed",
                _text(
                    language,
                    f"Requested amount compared with confirmed invoice collections{f' is {ratio:.4f} times' if ratio is not None else ' has no ratio because confirmed collections are zero'}. This is descriptive only and is not a repayment-capacity measure.",
                    f"مقارنة مبلغ الطلب بالتحصيلات المؤكدة{f' تساوي {ratio:.4f} مرة' if ratio is not None else ' لا تنتج نسبة لأن التحصيلات المؤكدة تساوي صفراً'}. وهذه مقارنة وصفية وليست مقياساً للقدرة على السداد.",
                ),
                evidence,
                _text(language, "Review the confirmed-collection period and underlying invoice matches.",
                      "راجع فترة التحصيلات المؤكدة ومطابقات الفواتير الأساسية."),
                language,
            ),
            language,
        )
    else:
        _missing_finding(
            "FA-02",
            _text(language,
                  "A valid requested amount, matching currencies, and valid matcher-based confirmed collections are required for this comparison.",
                  "تتطلب هذه المقارنة مبلغاً مطلوباً صالحاً وعملتين متطابقتين وتحصيلات مؤكدة صالحة مستندة إلى المطابقة."),
            [
                _evidence("application_context", "requested_amount",
                          context.get("requested_amount"), requested_currency),
                _evidence("financial_analysis",
                          "collections.total_confirmed_collections",
                          _path(analysis, "collections.total_confirmed_collections"),
                          financial_currency),
                _evidence("matching_result", "invoice_matches",
                          matching_result.get("invoice_matches")),
            ],
            _text(language, "Supply the missing request/currency data or resolve invalid invoice and bank amounts.",
                  "قدم بيانات الطلب أو العملة الناقصة أو عالج مبالغ الفواتير والبنك غير الصالحة."),
            missing_information,
            recommended_actions,
            language,
        )

    if request_valid and same_currency and net_cash_flow is not None and cash_valid and bank_period:
        ratio = requested_amount / net_cash_flow if net_cash_flow > 0 else None
        evidence = [
            _evidence("application_context", "requested_amount",
                      context.get("requested_amount"), requested_currency),
            _evidence("financial_analysis", "cash_flow.net_cash_flow",
                      _path(analysis, "cash_flow.net_cash_flow"),
                      financial_currency, bank_period),
        ]
        if ratio is not None:
            evidence.append(_evidence(
                "derived_from_inputs",
                "FA-03.requested_amount_to_net_cash_flow_ratio",
                ratio,
                measurement_period=bank_period,
            ))
        _append_finding(
            financing_request_assessment,
            recommended_actions,
            _finding(
                "FA-03", "financing_request", "observed",
                _text(
                    language,
                    f"The request is compared with historical net cash flow for {bank_period}. This comparison does not establish future repayment affordability.",
                    f"تتم مقارنة الطلب بصافي التدفق النقدي التاريخي للفترة {bank_period}. ولا تثبت هذه المقارنة القدرة المستقبلية على تحمل السداد.",
                ),
                evidence,
                _text(language, "Review the period and obtain verified forward-looking repayment information; do not treat historical cash flow as affordability.",
                      "راجع الفترة واحصل على معلومات موثقة عن السداد المستقبلي؛ ولا تعتبر التدفق التاريخي دليلاً على القدرة على السداد."),
                language,
            ),
            language,
        )
    else:
        _missing_finding(
            "FA-03",
            _text(language,
                  "A matching currency, valid bank amounts, and a complete transaction-date period are required to compare the request with net cash flow.",
                  "تتطلب مقارنة الطلب بصافي التدفق النقدي عملة متطابقة ومبالغ بنكية صالحة وفترة تواريخ معاملات مكتملة."),
            [
                _evidence("financial_analysis", "cash_flow.net_cash_flow",
                          _path(analysis, "cash_flow.net_cash_flow"),
                          financial_currency, bank_period),
            ] if _path(analysis, "cash_flow.net_cash_flow") is not None else [],
            _text(language, "Provide matching currency information and complete dated bank transaction data.",
                  "قدم معلومات عملة متطابقة وبيانات معاملات بنكية مؤرخة ومكتملة."),
            missing_information,
            recommended_actions,
            language,
        )

    if request_valid and same_currency and outstanding is not None and _invoice_totals_valid(
        analysis, validation
    ):
        ratio = outstanding / requested_amount
        evidence = [
            _evidence("application_context", "requested_amount",
                      context.get("requested_amount"), requested_currency),
            _evidence("financial_analysis", "receivables.outstanding_receivables",
                      _path(analysis, "receivables.outstanding_receivables"),
                      financial_currency),
            _evidence(
                "derived_from_inputs",
                "FA-04.outstanding_receivables_to_requested_amount_ratio",
                ratio,
            ),
        ]
        _append_finding(
            financing_request_assessment,
            recommended_actions,
            _finding(
                "FA-04", "financing_request", "observed",
                _text(language,
                      f"Outstanding receivables are compared descriptively with the request (ratio {ratio:.4f}); no aging or collectability conclusion is inferred.",
                      f"تتم مقارنة الذمم المدينة القائمة بالطلب بشكل وصفي (النسبة {ratio:.4f})؛ ولا يُستنتج تقادمها أو إمكانية تحصيلها."),
                evidence,
                _text(language, "Review invoice-level balances and supporting collection evidence.",
                      "راجع الأرصدة على مستوى الفاتورة وأدلة التحصيل الداعمة."),
                language,
            ),
            language,
        )
    else:
        _missing_finding(
            "FA-04",
            _text(language, "Valid outstanding-receivables data, a positive request, and matching currencies are required.",
                  "يلزم توفر بيانات صالحة للذمم المدينة ومبلغ طلب موجب وعملتين متطابقتين."),
            [
                _evidence("application_context", "requested_amount",
                          context.get("requested_amount"), requested_currency),
                _evidence("financial_analysis",
                          "receivables.outstanding_receivables",
                          _path(analysis, "receivables.outstanding_receivables"),
                          financial_currency),
            ],
            _text(language, "Provide the missing request or financial data.",
                  "قدم بيانات الطلب أو البيانات المالية الناقصة."),
            missing_information,
            recommended_actions,
            language,
        )

    # Terms availability is reported, not used to calculate installments.
    tenure = _count(context.get("requested_tenure_months"))
    if tenure is not None and tenure > 0:
        _append_finding(
            financing_request_assessment,
            recommended_actions,
            _finding(
                "FT-01", "financing_request", "observed",
                _text(language,
                      f"The applicant requested a tenure of {tenure} month(s); no bank-defined tenure assessment is applied.",
                      f"طلب مقدم الطلب مدة تمويل قدرها {tenure} شهراً؛ ولا يطبق هذا المحرك تقييماً لمدة التمويل وفق سياسة البنك."),
                [_evidence("application_context", "requested_tenure_months",
                           context.get("requested_tenure_months"),
                           measurement_period="months")],
                _text(language, "Review the requested tenure against the applicable bank product terms.",
                      "راجع مدة التمويل المطلوبة وفق شروط منتج البنك المعني."),
                language,
            ),
            language,
        )
    else:
        _missing_finding(
            "FT-01",
            _text(language, "A positive requested tenure in months is not available.",
                  "مدة التمويل المطلوبة بالأشهر غير متاحة أو غير موجبة."),
            [_evidence("application_context", "requested_tenure_months",
                       context.get("requested_tenure_months"),
                       measurement_period="months")],
            _text(language, "Provide the requested financing tenure.",
                  "قدم مدة التمويل المطلوبة."),
            missing_information,
            recommended_actions,
            language,
        )

    for rule_id, key, english, arabic in (
        ("FT-02", "repayment_schedule",
         "A repayment schedule is supplied, but this engine does not evaluate its terms.",
         "تم تقديم جدول سداد، لكن هذا المحرك لا يقيّم شروطه."),
        ("FT-03", "financing_cost",
         "Financing-cost information is supplied; no cost or installment calculation is performed.",
         "تم تقديم معلومات تكلفة التمويل؛ ولا يتم احتساب التكلفة أو الأقساط."),
    ):
        value = context.get(key)
        if not _has_supplied_content(value) or _is_empty_collection(value):
            label = _field_label(key, language)
            _missing_finding(
                rule_id,
                _text(language, f"{label.capitalize()} was not supplied.",
                      f"لم يتم تقديم {label}."),
                [_evidence("application_context", key, value)],
                _text(language, f"Provide {label} if it is required for review.",
                      f"قدم {label} إذا كان مطلوباً للمراجعة."),
                missing_information,
                recommended_actions,
                language,
            )
        else:
            _append_finding(
                financing_request_assessment,
                recommended_actions,
                _finding(
                    rule_id, "financing_request", "observed",
                    _text(language, english, arabic),
                    [_evidence("application_context", key, value,
                               currency=context.get("requested_currency"))],
                    _text(language, "Have an authorized bank employee review the supplied terms.",
                          "اطلب من موظف بنك مخول مراجعة الشروط المقدمة."),
                    language,
                ),
                language,
            )

    capacity = context.get("repayment_capacity")
    if isinstance(capacity, dict) and capacity:
        capacity_missing = []
        if _number(capacity.get("amount")) is None:
            capacity_missing.append("amount")
        if _is_missing(capacity.get("currency")):
            capacity_missing.append("currency")
        if _is_missing(capacity.get("measurement_period")):
            capacity_missing.append("measurement_period")
        verification = capacity.get("verification_status")
        capacity_status = "verified" if verification == "verified" else "borrower_declared"
        capacity_evidence = [
            _evidence("application_context", f"repayment_capacity.{key}", value,
                      currency=capacity.get("currency"),
                      measurement_period=capacity.get("measurement_period"))
            for key, value in capacity.items()
        ]
        if capacity_missing:
            _missing_finding(
                "FT-04",
                _text(
                    language,
                    "Repayment-capacity details are incomplete: "
                    + ", ".join(_field_label(key, language) for key in capacity_missing) + ".",
                    "تفاصيل القدرة على السداد غير مكتملة: "
                    + "، ".join(_field_label(key, language) for key in capacity_missing) + ".",
                ),
                capacity_evidence,
                _text(
                    language,
                    "Provide the amount, currency, and measurement period for the declared capacity data.",
                    "قدم مبلغ بيانات القدرة المصرح بها وعملتها وفترتها الزمنية.",
                ),
                missing_information,
                recommended_actions,
                language,
            )
        else:
            _append_finding(
                financing_request_assessment,
                recommended_actions,
                _finding(
                    "FT-04", "financing_request", capacity_status,
                    _text(language,
                          "Repayment-capacity information was supplied. Its presence does not establish affordability, and this engine does not calculate DSCR.",
                          "تم تقديم معلومات عن القدرة على السداد. ولا يثبت توفرها القدرة على تحمل السداد، ولا يحتسب هذا المحرك نسبة تغطية خدمة الدين."),
                    capacity_evidence,
                    _text(language, "Review the source, period, currency, verification, and completeness of this information.",
                          "راجع مصدر هذه المعلومات وفترتها وعملتها والتحقق منها واكتمالها."),
                    language,
                ),
                language,
            )
    else:
        _missing_finding(
            "FT-04",
            _text(language, "No repayment-capacity data was supplied in the application context.",
                  "لم تُقدم بيانات عن القدرة على السداد ضمن سياق الطلب."),
            [_evidence("application_context", "repayment_capacity", capacity)],
            _text(language, "Request relevant verified repayment-capacity information; historical cash flow alone is insufficient.",
                  "اطلب معلومات موثقة وذات صلة بالقدرة على السداد؛ فالتدفق النقدي التاريخي وحده غير كافٍ."),
            missing_information,
            recommended_actions,
            language,
        )

    # Purpose documentation is governed solely by caller-supplied policy.
    purpose = context.get("financing_purpose_code")
    requirements = _mapping(policy_data.get("purpose_document_requirements"))
    configured = purpose in requirements if isinstance(purpose, str) else False
    required_documents = requirements.get(purpose) if configured else None
    valid_requirements = (
        isinstance(required_documents, list)
        and all(isinstance(item, str) and item.strip() for item in required_documents)
    )
    if not valid_requirements:
        configuration_finding = _finding(
            "DQ-08", "data_quality", "configuration_missing",
            _text(language,
                  "Required-document configuration is missing or invalid for the supplied purpose; application completeness is not determined.",
                  "إعداد المستندات المطلوبة لهذا الغرض غير متوفر أو غير صالح؛ ولا يتم تحديد اكتمال الطلب."),
            [
                _evidence(
                    "application_context", "financing_purpose_code", purpose
                ),
                _evidence(
                    "policy",
                    "purpose_document_requirements",
                    policy_data.get("purpose_document_requirements"),
                ),
            ],
            _text(language, "Configure purpose-specific required documents through the applicable bank policy.",
                  "حدد المستندات المطلوبة حسب الغرض ضمن سياسة البنك المعمول بها."),
            language,
        )
        _append_finding(
            data_quality_issues,
            recommended_actions,
            configuration_finding,
            language,
        )
        _missing_finding(
            "FP-01",
            _text(language,
                  "Purpose-specific required-document configuration is unavailable; no official document list can be inferred.",
                  "إعداد المستندات المطلوبة حسب الغرض غير متوفر؛ ولا يمكن استنتاج قائمة رسمية للمستندات."),
            [_evidence("application_context", "financing_purpose_code", purpose),
             _evidence("policy", "purpose_document_requirements", policy_data.get("purpose_document_requirements"))],
            _text(language, "Provide the applicable policy configuration and review purpose documentation manually.",
                  "قدم إعدادات السياسة المعمول بها وراجع مستندات الغرض يدوياً."),
            missing_information,
            recommended_actions,
            language,
        )
    else:
        uploaded = context.get("uploaded_documents")
        uploaded_types: set[str] = set()
        if isinstance(uploaded, list):
            for item in uploaded:
                if isinstance(item, str) and item.strip():
                    uploaded_types.add(item.strip().casefold())
                elif isinstance(item, dict):
                    doc_type = item.get("document_type")
                    if isinstance(doc_type, str) and doc_type.strip():
                        uploaded_types.add(doc_type.strip().casefold())
        missing_documents = [
            item for item in required_documents
            if item.strip().casefold() not in uploaded_types
        ]
        purpose_evidence = [
            _evidence("application_context", "financing_purpose_code", purpose),
            _evidence("policy", f"purpose_document_requirements.{purpose}",
                      required_documents),
            _evidence("application_context", "uploaded_documents",
                      uploaded if isinstance(uploaded, list) else None),
        ]
        if missing_documents:
            _data_quality_finding(
                "DQ-08",
                [
                    _evidence(
                        "policy",
                        f"purpose_document_requirements.{purpose}",
                        required_documents,
                    ),
                    _evidence(
                        "application_context",
                        "uploaded_documents",
                        uploaded if isinstance(uploaded, list) else None,
                    ),
                    _evidence(
                        "derived_from_inputs",
                        "DQ-08.missing_required_documents",
                        missing_documents,
                    ),
                ],
                _text(language,
                      "Some policy-configured purpose documents are not listed as uploaded; no completeness decision is made.",
                      "بعض المستندات المحددة في السياسة لهذا الغرض غير مدرجة كمستندات مرفوعة؛ ولا يصدر حكم باكتمال الطلب."),
                _text(language, "Request the listed documents and have an authorized employee review them.",
                      "اطلب المستندات المذكورة واطلب من موظف مخول مراجعتها."),
                data_quality_issues,
                recommended_actions,
                language,
            )
            _missing_finding(
                "FP-01",
                _text(language,
                      "Policy-configured documents are not all listed as uploaded: "
                      + ", ".join(missing_documents) + ".",
                      "ليست جميع المستندات المحددة في السياسة مدرجة كمستندات مرفوعة: "
                      + ", ".join(missing_documents) + "."),
                purpose_evidence,
                _text(language, "Request the missing documents; uploaded status does not establish verification or application completeness.",
                      "اطلب المستندات الناقصة؛ ولا يثبت تسجيل الرفع صحة المستندات أو اكتمال الطلب."),
                missing_information,
                recommended_actions,
                language,
            )
        _append_finding(
            financing_request_assessment,
            recommended_actions,
            _finding(
                "FP-01",
                "financing_request",
                "attention" if missing_documents else "observed",
                _text(language,
                      "Purpose documentation is compared only with caller-configured policy; listed uploads are not treated as verified or as proof of application completion.",
                      "تتم مقارنة مستندات الغرض فقط بالسياسة التي يقدمها المستدعي؛ ولا تعتبر المستندات المدرجة مرفوعة متحققاً منها أو دليلاً على اكتمال الطلب."),
                purpose_evidence,
                _text(language, "Have an authorized employee verify the required documents and their relevance.",
                      "اطلب من موظف مخول التحقق من المستندات المطلوبة ومدى صلتها."),
                language,
            ),
            language,
        )

    existing_obligations, _ = _existing_obligation_findings(
        context, language, missing_information, recommended_actions
    )

    limitation_texts = (
        ("LIMIT-01",
         "Invoice due_date is not available; overdue aging and days past due are not calculated.",
         "لا يتوفر حقل due_date للفواتير؛ لذلك لا يتم احتساب تقادم الذمم أو أيام التأخر."),
        ("LIMIT-02",
         "This assessment does not approve, decline, or classify financing eligibility; the decision remains with an authorized bank employee.",
         "لا يوافق هذا التقييم على التمويل أو يرفضه ولا يصنف الأهلية؛ ويظل القرار لموظف بنك مخول."),
        ("LIMIT-03",
         "Historical sales, collections, and cash flow alone do not establish future repayment affordability; no installment or DSCR is calculated.",
         "لا تثبت المبيعات أو التحصيلات أو التدفقات النقدية التاريخية وحدها القدرة المستقبلية على السداد؛ ولا يتم احتساب قسط أو نسبة تغطية خدمة الدين."),
        ("LIMIT-04",
         "The engine does not authenticate uploaded files or independently verify borrower declarations.",
         "لا يتحقق المحرك من صحة الملفات المرفوعة أو من إقرارات مقدم الطلب بشكل مستقل."),
        ("LIMIT-05",
         "All findings are generated by deterministic rules; no LLM or external AI API is used.",
         "تُنشأ جميع النتائج بواسطة قواعد حتمية؛ ولا يتم استخدام نموذج لغوي كبير أو واجهة ذكاء اصطناعي خارجية."),
    )
    for rule_id, english, arabic in limitation_texts:
        limitations.append(_finding(
            rule_id,
            "limitation",
            "observed",
            _text(language, english, arabic),
            [],
            None,
            language,
        ))

    return {
        "application_id": app_id,
        "assessment_type": "rule_based",
        "rule_set_version": RULE_SET_VERSION,
        "language": language,
        "financial_strengths": financial_strengths,
        "potential_risks": potential_risks,
        "financing_request_assessment": financing_request_assessment,
        "existing_obligations": existing_obligations,
        "data_quality_issues": data_quality_issues,
        "missing_information": missing_information,
        "recommended_actions": recommended_actions,
        "limitations": limitations,
        "decision": {
            "status": "not_made",
            "decision_maker": "bank_employee",
        },
    }