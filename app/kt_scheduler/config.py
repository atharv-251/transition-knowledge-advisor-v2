from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass, field
from pathlib import Path


def _csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class SmtpConfig:
    """SMTP configuration loaded from environment variables.

    Credentials are deliberately not hard-coded. For local testing, put values
    in ``.env`` or set them as App Service application settings in Azure.
    """

    server: str = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_SMTP_SERVER",
        "mxiblk.relay.vw.vwg",
    ).strip())
    port: int = field(default_factory=lambda: int(os.getenv(
        "KT_SCHEDULER_SMTP_PORT",
        "25",
    )))
    sender_email: str = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_SENDER_EMAIL",
        "vivek.chaurasia@vwgds.in",
    ).strip())
    organizer_name: str = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_ORGANIZER_NAME",
        "Vivek Chaurasia",
    ).strip())
    username: str = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_SMTP_USERNAME",
        "",
    ).strip())
    password: str = field(default_factory=lambda: _read_password())
    use_starttls: bool = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_SMTP_STARTTLS",
        "false",
    ).strip().lower() in ("1", "true", "yes"))
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv(
        "KT_SCHEDULER_SMTP_TIMEOUT_SECONDS",
        "30",
    )))


@dataclass(frozen=True)
class SchedulerConfig:
    """Runtime behavior for the KT Scheduler Bot."""

    default_input_path: Path = field(default_factory=lambda: Path(os.getenv(
        "KT_SCHEDULER_DEFAULT_INPUT_PATH",
        "data/kt_scheduler/input/KT_Schedule.csv",
    )))
    timezone_name: str = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_TIMEZONE",
        "Asia/Kolkata",
    ).strip())
    test_mode: bool = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_TEST_MODE",
        "false",
    ).strip().lower() in ("1", "true", "yes"))
    dry_run: bool = field(default_factory=lambda: os.getenv(
        "KT_SCHEDULER_DRY_RUN",
        "true",
    ).strip().lower() in ("1", "true", "yes"))
    test_recipients: list[str] = field(default_factory=lambda: _csv_list(os.getenv(
        "KT_SCHEDULER_TEST_RECIPIENTS",
        "appsupport@vwgds.in",
    )))
    state_path: Path = field(default_factory=lambda: Path(os.getenv(
        "KT_SCHEDULER_STATE_PATH",
        "data/kt_scheduler/sent_invites.json",
    )))


def _read_password() -> str:
    password = os.getenv("KT_SCHEDULER_SMTP_PASSWORD", "")
    if password:
        return password

    encoded = os.getenv("KT_SCHEDULER_SMTP_PASSWORD_B64", "")
    if not encoded:
        return ""

    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError(
            "KT_SCHEDULER_SMTP_PASSWORD_B64 is set but is not valid base64. "
            "Use KT_SCHEDULER_SMTP_PASSWORD for plain local testing, or "
            "provide a real base64-encoded value."
        ) from exc


def load_smtp_config() -> SmtpConfig:
    return SmtpConfig()


def load_scheduler_config() -> SchedulerConfig:
    return SchedulerConfig()
