from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


InviteStatus = Literal["sent", "skipped", "failed", "dry_run"]


class KtScheduleItem(BaseModel):
    """One schedulable KT session parsed from an input source."""

    source_id: str = Field(description="Stable input/source row identifier.")
    session_title: str = Field(min_length=1, max_length=500)
    level: str = Field(default="", max_length=50)
    start_at: datetime
    end_at: datetime
    duration_hours: float | None = Field(default=None, ge=0)
    delivery_mode: str = Field(default="", max_length=100)
    assigned_sme: str = Field(default="", max_length=200)
    assigned_receiver: str = Field(default="", max_length=200)
    required_attendees: list[EmailStr] = Field(default_factory=list)
    optional_attendees: list[EmailStr] = Field(default_factory=list)
    status: str = Field(default="", max_length=100)
    conflicts: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=4000)
    agenda_topics: list[str] = Field(default_factory=list)

    @field_validator("end_at")
    @classmethod
    def validate_end_after_start(cls, end_at: datetime, info):
        start_at = info.data.get("start_at")
        if start_at and end_at <= start_at:
            raise ValueError("end_at must be after start_at")
        return end_at

    @field_validator("required_attendees")
    @classmethod
    def validate_required_attendees(cls, attendees: list[EmailStr]):
        if not attendees:
            raise ValueError("At least one required attendee email is required")
        return attendees

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "source_id": "csv-row-2-2d4c4db1",
                "session_title": "[L1] Dealer HPG Dashboard Power BI sheets",
                "level": "L1",
                "start_at": "2026-09-28T08:00:00+05:30",
                "end_at": "2026-09-28T08:54:00+05:30",
                "delivery_mode": "workshop",
                "assigned_sme": "Athrava Utekar",
                "assigned_receiver": "Vivek Chaurasia",
                "required_attendees": [
                    "vivek.chaurasia@vwgds.in",
                    "atharva.utekar@vwgds.in",
                ],
            }
        }
    )


class InviteResult(BaseModel):
    """Outcome for one attempted meeting invite."""

    source_id: str
    uid: str
    subject: str
    recipients: list[str] = Field(default_factory=list)
    status: InviteStatus
    message: str = ""


class ScheduleRunRequest(BaseModel):
    """API payload to run the scheduler for a file path."""

    input_path: str | None = Field(
        default=None,
        description="Path to CSV/XLSX KT plan input file accessible to the app.",
    )
    dry_run: bool | None = Field(
        default=None,
        description="Override KT_SCHEDULER_DRY_RUN for this run.",
    )
    test_mode: bool | None = Field(
        default=None,
        description="Override KT_SCHEDULER_TEST_MODE for this run.",
    )
    test_recipients: list[EmailStr] | None = Field(
        default=None,
        description="Override test-mode recipients for this run.",
    )
    force_resend: bool = Field(
        default=False,
        description="Send even if the deterministic invite UID exists in state.",
    )


class ScheduleRunResult(BaseModel):
    """Summary of a KT Scheduler execution."""

    total_items: int = 0
    valid_items: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: int = 0
    test_mode: bool = True
    errors: list[str] = Field(default_factory=list)
    results: list[InviteResult] = Field(default_factory=list)
