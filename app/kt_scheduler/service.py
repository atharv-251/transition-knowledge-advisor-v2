from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from app.kt_scheduler.config import (
    SchedulerConfig,
    SmtpConfig,
    load_scheduler_config,
    load_smtp_config,
)
from app.kt_scheduler.email_service import SmtpInviteService
from app.kt_scheduler.input_sources import input_source_for
from app.kt_scheduler.invite_generator import build_ics
from app.kt_scheduler.models import InviteResult, ScheduleRunResult
from app.kt_scheduler.state_store import InviteStateStore

logger = logging.getLogger("kt_scheduler.service")


def run_scheduler(
    input_path: str | Path | None = None,
    *,
    dry_run: bool | None = None,
    test_mode: bool | None = None,
    test_recipients: list[str] | None = None,
    force_resend: bool = False,
    scheduler_config: SchedulerConfig | None = None,
    smtp_config: SmtpConfig | None = None,
) -> ScheduleRunResult:
    """Parse a KT plan and send/test meeting invitations.

    Defaults are intentionally safe:
    - test mode defaults to enabled, redirecting all recipients to
      ``KT_SCHEDULER_TEST_RECIPIENTS``.
    - dry-run defaults to enabled, generating ICS payloads and duplicate-state
      decisions without connecting to SMTP.
    """

    scheduler_config = scheduler_config or load_scheduler_config()
    smtp_config = smtp_config or load_smtp_config()
    if dry_run is not None or test_mode is not None or test_recipients is not None:
        scheduler_config = replace(
            scheduler_config,
            dry_run=scheduler_config.dry_run if dry_run is None else dry_run,
            test_mode=scheduler_config.test_mode if test_mode is None else test_mode,
            test_recipients=(
                scheduler_config.test_recipients
                if test_recipients is None
                else [str(item) for item in test_recipients]
            ),
        )

    resolved_input_path = Path(input_path) if input_path else scheduler_config.default_input_path
    source = input_source_for(resolved_input_path, scheduler_config.timezone_name)
    items = source.load()
    state = InviteStateStore(scheduler_config.state_path)
    already_sent = state.load()
    invite_service = SmtpInviteService(smtp_config)

    result = ScheduleRunResult(
        total_items=len(items),
        valid_items=len(items),
        test_mode=scheduler_config.test_mode,
    )

    for item in items:
        uid, ics_content = build_ics(item, smtp_config)
        recipients = _resolve_recipients(item, scheduler_config)
        state_key = _delivery_state_key(uid, recipients)

        if state_key in already_sent and not force_resend:
            logger.info("Skipping duplicate invite %s (%s)", uid, item.session_title)
            result.skipped += 1
            result.results.append(InviteResult(
                source_id=item.source_id,
                uid=uid,
                subject=item.session_title,
                recipients=recipients,
                status="skipped",
                message="Invite UID already exists in scheduler state.",
            ))
            continue

        try:
            invite_service.send_invite(
                item=item,
                recipients=recipients,
                ics_content=ics_content,
                dry_run=scheduler_config.dry_run,
            )
        except Exception as exc:
            logger.exception("Failed to send invite %s", uid)
            result.failed += 1
            result.errors.append(f"{item.source_id}: {exc}")
            result.results.append(InviteResult(
                source_id=item.source_id,
                uid=uid,
                subject=item.session_title,
                recipients=recipients,
                status="failed",
                message=str(exc),
            ))
            continue

        if scheduler_config.dry_run:
            result.dry_run += 1
            status = "dry_run"
            message = "Invite generated but not sent because dry-run is enabled."
        else:
            state.add(state_key)
            already_sent.add(state_key)
            result.sent += 1
            status = "sent"
            message = "Invite sent through SMTP."

        result.results.append(InviteResult(
            source_id=item.source_id,
            uid=uid,
            subject=item.session_title,
            recipients=recipients,
            status=status,
            message=message,
        ))

    return result


def _resolve_recipients(item, scheduler_config: SchedulerConfig) -> list[str]:
    if scheduler_config.test_mode:
        return list(scheduler_config.test_recipients)
    return [str(email) for email in item.required_attendees + item.optional_attendees]


def _delivery_state_key(uid: str, recipients: list[str]) -> str:
    normalized_recipients = ",".join(sorted(recipient.lower() for recipient in recipients))
    return f"{uid}|{normalized_recipients}"
