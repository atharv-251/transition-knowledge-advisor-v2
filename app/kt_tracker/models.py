from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

KtStatus = Literal[
    "not_started",
    "planned",
    "in_progress",
    "completed",
    "on_hold",
    "cancelled",
    "descoped",
    "overdue",
]

KtReadiness = Literal[
    "not_assessed",
    "at_risk",
    "partially_ready",
    "ready",
    "accepted",
]

KtMeetingStatus = Literal[
    "scheduled",
    "ongoing",
    "completed",
    "cancelled",
    "rescheduled",
]

MeetingParticipantRole = Literal[
    "organizer",
    "attendee",
]


class HealthResponse(BaseModel):
    """Basic service health or readiness response."""

    status: str = Field(description="Current service status.")
    service: str = Field(description="Stable bot identifier.")
    version: str = Field(description="API version.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "service": "kt-tracker-bot",
                "version": "0.1.0",
            }
        }
    )


class CapabilitiesResponse(BaseModel):
    """Capability card exposed to users and future mesh orchestrators."""

    agent_id: str
    name: str
    description: str
    supported_intents: list[str] = Field(default_factory=list)
    supported_domains: list[str] = Field(default_factory=list)
    supported_file_types: list[str] = Field(default_factory=list)
    endpoints: dict[str, str] = Field(default_factory=dict)


class KtActivityCreateRequest(BaseModel):
    """Payload used to create one trackable KT activity."""

    activity_id: str | None = Field(
        default=None,
        description="Optional external activity ID from KT Planner.",
        examples=["act-2001"],
    )
    activity_name: str = Field(
        min_length=1,
        max_length=300,
        description="Short business name of the KT activity.",
        examples=["Access provisioning"],
    )
    description: str = Field(
        default="",
        max_length=2000,
        description="Detailed activity description.",
    )
    owner: str = Field(
        default="",
        max_length=200,
        description="Owning team or role.",
        examples=["IAM"],
    )
    assignee: str = Field(
        default="",
        max_length=200,
        description="Person or group currently responsible.",
        examples=["R. Kumar"],
    )
    category: str = Field(
        default="general",
        max_length=100,
        description="Activity category, for example planning, access, operations, or knowledge.",
        examples=["access"],
    )
    status: KtStatus = Field(
        default="not_started",
        description="Current KT activity status.",
    )
    readiness: KtReadiness = Field(
        default="not_assessed",
        description="Readiness assessment for this activity.",
    )
    due_date: date | None = Field(
        default=None,
        description="Planned due date for the activity.",
        examples=["2026-02-15"],
    )
    actual_start_date: date | None = Field(
        default=None,
        description="Actual start date, if known.",
    )
    actual_end_date: date | None = Field(
        default=None,
        description="Actual completion date, if known.",
    )
    progress_percent: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Manual progress percentage for this activity.",
        examples=[65],
    )
    blocker: str = Field(
        default="",
        max_length=2000,
        description="Active blocker text, if any.",
    )
    risk: str = Field(
        default="",
        max_length=2000,
        description="Active risk text, if any.",
    )
    notes: str = Field(
        default="",
        max_length=4000,
        description="Additional tracker notes.",
    )
    source: str = Field(
        default="bot_api",
        max_length=100,
        description="Source system for the activity.",
    )
    source_transition_id: str | None = Field(
        default=None,
        description="Optional KT Planner Transition ID that originated this activity.",
    )
    source_session_id: str | None = Field(
        default=None,
        description="Optional KT Planner KT Session ID linked to this activity.",
    )
    source_knowledge_node_id: str | None = Field(
        default=None,
        description="Optional KT Planner Knowledge Node ID covered by this activity.",
    )
    source_stakeholder_id: str | None = Field(
        default=None,
        description="Optional KT Planner Stakeholder ID for the activity owner or receiver.",
    )
    contract_version: str | None = Field(
        default=None,
        max_length=50,
        description="Optional version of the KT Planner integration contract.",
    )
    expected_topics: list[str] = Field(
        default_factory=list,
        description=(
            "Topics/modules that must be covered during the linked KT "
            "meeting. Used to compare against the meeting transcript."
        ),
        examples=[["Architecture", "Database", "API integration", "Batch jobs"]],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "activity_name": "Access provisioning",
                "description": "Grant application access for support and operations teams.",
                "owner": "IAM",
                "assignee": "R. Kumar",
                "category": "access",
                "status": "in_progress",
                "readiness": "partially_ready",
                "due_date": "2026-02-15",
                "progress_percent": 65,
                "blocker": "Waiting on final approval matrix.",
                "risk": "Access delay may impact go-live.",
            }
        }
    )


class KtPlanImportRequest(BaseModel):
    """Import request for a KT plan from KT Planner API or a demo payload."""

    plan_id: str = Field(
        default_factory=lambda: "plan-" + str(abs(hash(str(datetime.utcnow())))),
        description="Unique KT plan ID. In future this will come from KT Planner.",
        examples=["kt-plan-demo-001"],
    )
    project_name: str = Field(
        min_length=1,
        max_length=300,
        description="Transition project name.",
        examples=["Core Platform Transition"],
    )
    knowledge_domain: str = Field(
        default="transition",
        max_length=100,
        description="Knowledge domain or workstream for the plan.",
    )
    due_date: date | None = Field(
        default=None,
        description="Overall plan due date.",
        examples=["2026-12-31"],
    )
    owner: str = Field(
        default="",
        max_length=200,
        description="Overall plan owner.",
        examples=["KT Office"],
    )
    source_transition_id: str | None = Field(
        default=None,
        description="Optional KT Planner Transition ID that originated this plan.",
    )
    contract_version: str | None = Field(
        default=None,
        max_length=50,
        description="Optional version of the KT Planner integration contract.",
    )
    activities: list[KtActivityCreateRequest] = Field(
        default_factory=list,
        description="Activities imported from the KT Planner plan.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "kt-plan-demo-001",
                "project_name": "Core Platform Transition",
                "knowledge_domain": "transition",
                "due_date": "2026-12-31",
                "owner": "KT Office",
                "activities": [
                    {
                        "activity_name": "Access provisioning",
                        "owner": "IAM",
                        "assignee": "R. Kumar",
                        "category": "access",
                        "status": "in_progress",
                        "readiness": "partially_ready",
                        "due_date": "2026-02-15",
                        "progress_percent": 65,
                        "blocker": "Waiting on final approval matrix.",
                        "risk": "Access delay may impact go-live.",
                    }
                ],
            }
        }
    )


class ActivityUpdateRequest(BaseModel):
    """Partial update payload for activity status, progress, blockers, and readiness."""

    activity_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
        description="Updated activity name.",
    )
    status: KtStatus | None = Field(
        default=None,
        description="New activity status.",
    )
    owner: str | None = Field(
        default=None,
        max_length=200,
        description="Updated owning team or role.",
    )
    assignee: str | None = Field(
        default=None,
        max_length=200,
        description="Updated person or group currently responsible.",
    )
    due_date: date | None = Field(
        default=None,
        description="Updated due date.",
    )
    actual_end_date: date | None = Field(
        default=None,
        description="Actual completion date.",
    )
    progress_percent: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Updated progress percentage.",
    )
    blocker: str | None = Field(
        default=None,
        max_length=2000,
        description="Updated blocker text.",
    )
    risk: str | None = Field(
        default=None,
        max_length=2000,
        description="Updated risk text.",
    )
    readiness: KtReadiness | None = Field(
        default=None,
        description="Updated readiness assessment.",
    )
    notes: str | None = Field(
        default=None,
        max_length=4000,
        description="Updated notes.",
    )
    expected_topics: list[str] | None = Field(
        default=None,
        description="Updated list of topics expected for the linked KT meeting.",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "completed",
                "progress_percent": 100,
                "readiness": "ready",
                "notes": "Completed and validated by support lead.",
            }
        }
    )


class MeetingParticipant(BaseModel):
    """One participant recorded on a Teams meeting, from Graph attendance data."""

    participant_id: str | None = Field(
        default=None,
        description="Stable Microsoft Graph user ID, if supplied by attendance data.",
    )
    name: str = Field(description="Participant display name.")
    email: str = Field(default="", description="Participant email/UPN, if available.")
    role: MeetingParticipantRole = Field(
        default="attendee",
        description="Whether the participant organized or attended the meeting.",
    )
    joined_at: datetime | None = Field(
        default=None,
        description="Join timestamp from the Teams attendance report.",
    )
    left_at: datetime | None = Field(
        default=None,
        description="Leave timestamp from the Teams attendance report.",
    )
    duration_minutes: float | None = Field(
        default=None,
        description="Total attended minutes for this participant.",
    )


class KtActivity(BaseModel):
    """One trackable KT activity."""

    activity_id: str = Field(
        default_factory=lambda: f"act-{uuid.uuid4().hex[:12]}",
        description="Unique KT activity ID.",
    )
    plan_id: str = Field(description="Parent KT plan ID.")
    activity_name: str = Field(description="Short business name of the KT activity.")
    description: str = ""
    owner: str = ""
    assignee: str = ""
    category: str = "general"
    status: KtStatus = "not_started"
    readiness: KtReadiness = "not_assessed"
    due_date: date | None = None
    actual_start_date: date | None = None
    actual_end_date: date | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)
    blocker: str = ""
    risk: str = ""
    notes: str = ""
    source: str = "kt_planner_api"
    source_transition_id: str | None = None
    source_session_id: str | None = None
    source_knowledge_node_id: str | None = None
    source_stakeholder_id: str | None = None
    contract_version: str | None = None

    # --- Expected KT content for this activity's meeting(s) ---
    expected_topics: list[str] = Field(
        default_factory=list,
        description="Topics/modules expected to be covered for this KT activity.",
    )

    # --- Microsoft 365 meeting linkage (populated automatically) ---
    external_meeting_id: str | None = Field(
        default=None,
        description=(
            "Outlook iCalUId used as the idempotency key so the same "
            "meeting never creates a duplicate KT activity."
        ),
    )
    meeting_subject: str = Field(default="", description="Outlook meeting subject.")
    meeting_start: datetime | None = Field(default=None, description="Meeting start time.")
    meeting_end: datetime | None = Field(default=None, description="Meeting end time.")
    meeting_status: KtMeetingStatus | None = Field(
        default=None,
        description="Meeting lifecycle state detected from Outlook/Teams.",
    )
    organizer: str = Field(default="", description="Meeting organizer name or email.")

    # --- Automated meeting analysis outputs ---
    participants: list[MeetingParticipant] = Field(
        default_factory=list,
        description="Actual attendees identified from Teams attendance data.",
    )
    topics_covered: list[str] = Field(default_factory=list)
    topics_partially_covered: list[str] = Field(default_factory=list)
    topics_missed: list[str] = Field(default_factory=list)
    questions_raised: int = Field(default=0, ge=0)
    questions_unresolved: int = Field(default=0, ge=0)
    action_items: list[str] = Field(default_factory=list)
    follow_up_required: bool = Field(default=False)
    follow_up_topics: list[str] = Field(default_factory=list)
    transcript_summary: str = Field(default="", max_length=4000)
    analysis_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score from the transcript analysis (0-1).",
    )
    last_synced_at: datetime | None = Field(
        default=None,
        description="When this activity was last updated by the Graph sync pipeline.",
    )

    @field_validator("status")
    @classmethod
    def ensure_status_is_known(cls, value: KtStatus) -> KtStatus:
        allowed = {
            "not_started",
            "planned",
            "in_progress",
            "completed",
            "on_hold",
            "cancelled",
            "descoped",
            "overdue",
        }
        if value not in allowed:
            raise ValueError(f"Unsupported KT status: {value}")
        return value


class KtPlan(BaseModel):
    """Imported KT plan and its activities."""

    plan_id: str
    project_name: str
    knowledge_domain: str
    due_date: date | None = None
    owner: str = ""
    status: str = "draft"
    source_transition_id: str | None = None
    contract_version: str | None = None
    activities: list[KtActivity] = Field(default_factory=list)


class KtPlanUpdateRequest(BaseModel):
    """Partial update payload for a demo KT plan."""

    project_name: str | None = Field(default=None, min_length=1, max_length=300)
    knowledge_domain: str | None = Field(default=None, max_length=100)
    due_date: date | None = None
    owner: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=100)


class KtPlanImportResponse(BaseModel):
    """Response returned after a plan import."""

    plan_id: str
    project_name: str
    knowledge_domain: str
    source_transition_id: str | None = None
    contract_version: str | None = None
    activities: list[KtActivity] = Field(default_factory=list)


class DeleteActivityResponse(BaseModel):
    """Response returned after deleting one activity."""

    deleted: bool
    activity_id: str


class KtSummaryResponse(BaseModel):
    """Calculated plan-level progress, risks, blockers, and readiness."""

    plan_id: str
    project_name: str
    progress_percent: int
    total_activities: int
    completed_activities: int
    overdue_activities: int
    blocked_activities: int
    risk_activities: int
    readiness: KtReadiness
    summary: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class GraphSyncResult(BaseModel):
    """Microsoft Graph sync status for Teams and Outlook tracking."""

    enabled: bool
    source: str
    status: str
    message: str
    synced_count: int = 0
    last_sync_at: datetime | None = None


class KtMeeting(BaseModel):
    """A KT-related Outlook/Teams meeting discovered via Microsoft Graph."""

    external_meeting_id: str = Field(
        description="Outlook iCalUId. Stable across reschedules; used for dedupe."
    )
    graph_event_id: str = Field(default="", description="Graph calendar event ID.")
    online_meeting_id: str | None = Field(
        default=None, description="Graph onlineMeeting ID, once resolved."
    )
    subject: str = ""
    organizer_name: str = ""
    organizer_email: str = ""
    start_time: datetime
    end_time: datetime
    status: KtMeetingStatus = "scheduled"
    plan_id: str | None = None
    activity_id: str | None = Field(
        default=None, description="Linked KT activity ID once upserted."
    )
    source_transition_id: str | None = Field(
        default=None,
        description="Optional KT Planner Transition ID linked to this session.",
    )
    source_session_id: str | None = Field(
        default=None,
        description="Optional KT Planner KT Session ID represented by this meeting.",
    )
    contract_version: str | None = Field(
        default=None,
        description="Optional version of the KT Planner integration contract.",
    )
    last_synced_at: datetime | None = None


class KtMeetingCreateRequest(BaseModel):
    """Payload used to add a local demo KT meeting."""

    subject: str = Field(min_length=1, max_length=300)
    organizer_name: str = Field(default="", max_length=200)
    start_time: datetime
    end_time: datetime
    plan_id: str | None = None
    activity_id: str | None = None


class KtMeetingUpdateRequest(BaseModel):
    """Partial update payload for a local demo KT meeting."""

    subject: str | None = Field(default=None, min_length=1, max_length=300)
    organizer_name: str | None = Field(default=None, max_length=200)
    start_time: datetime | None = None
    end_time: datetime | None = None
    activity_id: str | None = None


class MeetingAnalysisResult(BaseModel):
    """Structured output of AI/transcript analysis for one completed KT meeting."""

    activity_id: str
    external_meeting_id: str
    meeting_subject: str = ""
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)
    participants: list[MeetingParticipant] = Field(default_factory=list)
    transcript_available: bool = False
    recording_available: bool = False
    topics_covered: list[str] = Field(default_factory=list)
    topics_partially_covered: list[str] = Field(default_factory=list)
    topics_missed: list[str] = Field(default_factory=list)
    questions_raised: int = 0
    questions_unresolved: int = 0
    action_items: list[str] = Field(default_factory=list)
    follow_up_required: bool = False
    follow_up_topics: list[str] = Field(default_factory=list)
    transcript_summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "activity_id": "act-1002",
                "external_meeting_id": "040000008200E00074C5B7101A82E00...",
                "meeting_subject": "Application KT - Session 3",
                "participants": [
                    {"name": "A. Sharma", "role": "organizer", "duration_minutes": 58.0}
                ],
                "transcript_available": True,
                "recording_available": True,
                "topics_covered": ["Architecture", "Database", "API integration"],
                "topics_partially_covered": ["Error handling"],
                "topics_missed": ["Batch jobs", "Production support"],
                "questions_raised": 5,
                "questions_unresolved": 1,
                "action_items": ["Share batch job runbook before next session"],
                "follow_up_required": True,
                "follow_up_topics": ["Batch jobs", "Production support"],
                "transcript_summary": "Team covered architecture, DB and API integration in depth...",
                "confidence": 0.89,
            }
        }
    )


class MeetingSyncResult(BaseModel):
    """Result of one Microsoft Graph meeting-discovery + analysis sync run."""

    enabled: bool
    mailbox: str = ""
    demo_mode: bool = Field(
        default=False,
        description=(
            "True when this sync ran against sample Microsoft 365 data "
            "(KT_GRAPH_MODE=demo) instead of a real tenant, e.g. while Entra "
            "ID/Graph access is still being provisioned."
        ),
    )
    meetings_discovered: int = 0
    activities_created: int = 0
    activities_updated: int = 0
    meetings_analyzed: int = 0
    follow_up_activities_created: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str = ""
    synced_at: datetime = Field(default_factory=datetime.utcnow)
