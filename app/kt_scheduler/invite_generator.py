from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.kt_scheduler.config import SmtpConfig
from app.kt_scheduler.models import KtScheduleItem


def invite_uid(item: KtScheduleItem) -> str:
    fingerprint = hashlib.sha256(
        "|".join([
            item.source_id,
            item.session_title,
            item.start_at.isoformat(),
            item.end_at.isoformat(),
        ]).encode("utf-8")
    ).hexdigest()[:20]
    return f"kt-scheduler-{fingerprint}@kt-scheduler-bot"


def build_ics(item: KtScheduleItem, smtp_config: SmtpConfig) -> tuple[str, str]:
    """Build a standards-compatible iCalendar REQUEST payload."""

    uid = invite_uid(item)
    required = [
        _attendee_line(str(email), required=True)
        for email in item.required_attendees
    ]
    optional = [
        _attendee_line(str(email), required=False)
        for email in item.optional_attendees
    ]
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//VW//KT Scheduler Bot//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_utc(datetime.now(timezone.utc))}",
        f"DTSTART:{_utc(item.start_at)}",
        f"DTEND:{_utc(item.end_at)}",
        f"SUMMARY:{_escape(item.session_title)}",
        f"DESCRIPTION:{_escape(item.description)}",
        f"ORGANIZER;CN={_escape_param(smtp_config.organizer_name)}:MAILTO:{smtp_config.sender_email}",
        *required,
        *optional,
        "STATUS:CONFIRMED",
        "SEQUENCE:0",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return uid, "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _attendee_line(email: str, required: bool) -> str:
    role = "REQ-PARTICIPANT" if required else "OPT-PARTICIPANT"
    return (
        f"ATTENDEE;CN={_escape_param(email)};ROLE={role};PARTSTAT=NEEDS-ACTION;"
        f"RSVP=TRUE:MAILTO:{email}"
    )


def _utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _escape_param(value: str) -> str:
    return value.replace('"', "")


def _fold(line: str) -> str:
    if len(line) <= 75:
        return line
    chunks = [line[:75]]
    remainder = line[75:]
    while remainder:
        chunks.append(" " + remainder[:74])
        remainder = remainder[74:]
    return "\r\n".join(chunks)

