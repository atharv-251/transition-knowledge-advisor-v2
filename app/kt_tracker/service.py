from __future__ import annotations

import itertools
import uuid
from datetime import date, datetime
from typing import Any

from app.kt_tracker.graph_sync import MicrosoftGraphSyncService
from app.kt_tracker.models import (
    ActivityUpdateRequest,
    GraphSyncResult,
    KtActivity,
    KtActivityCreateRequest,
    KtMeeting,
    KtPlan,
    KtPlanImportRequest,
    KtReadiness,
    KtSummaryResponse,
    MeetingAnalysisResult,
)

PLAN_STORE: dict[str, KtPlan] = {}
_activity_id_sequence = itertools.count(1)


def _now_date() -> date:
    return datetime.utcnow().date()


def _generate_activity_id() -> str:
    """Generate a collision-free KT activity ID.

    Must never repeat, even when several activities are created within the
    same microsecond (e.g. back-to-back Microsoft Graph meeting upserts) -
    a timestamp-hash-based ID previously used here could collide in that
    case, silently causing analysis results to be applied to the wrong
    activity (lookups match on the first activity found with that ID).
    """
    return f"act-{next(_activity_id_sequence):06d}-{uuid.uuid4().hex[:6]}"


def _activity_counts(activities: list[KtActivity]) -> dict[str, int]:
    counts = {status: 0 for status in [
        "not_started",
        "planned",
        "in_progress",
        "completed",
        "on_hold",
        "cancelled",
        "descoped",
        "overdue",
    ]}
    for activity in activities:
        counts[activity.status] = counts.get(activity.status, 0) + 1
    return counts


def _seed_demo_data() -> None:
    if PLAN_STORE:
        return

    plan = KtPlan(
        plan_id="kt-plan-demo-001",
        project_name="Core Platform Transition",
        knowledge_domain="transition",
        due_date=date(2026, 12, 31),
        owner="KT Office",
        status="active",
        activities=[
            KtActivity(
                activity_id="act-1001",
                plan_id="kt-plan-demo-001",
                activity_name="Kickoff & scope signoff",
                description="Finalize transition scope and responsibilities.",
                owner="PMO",
                assignee="A. Singh",
                category="planning",
                status="completed",
                readiness="ready",
                due_date=date(2026, 1, 10),
                actual_end_date=date(2026, 1, 9),
                progress_percent=100,
            ),
            KtActivity(
                activity_id="act-1002",
                plan_id="kt-plan-demo-001",
                activity_name="Role-based access provisioning",
                description="Grant application access for support and operations teams.",
                owner="IAM",
                assignee="R. Kumar",
                category="access",
                status="in_progress",
                readiness="partially_ready",
                due_date=date(2026, 2, 15),
                actual_start_date=date(2026, 1, 18),
                progress_percent=65,
                blocker="Waiting on final approval matrix.",
                risk="Access delay may impact go-live.",
            ),
            KtActivity(
                activity_id="act-1003",
                plan_id="kt-plan-demo-001",
                activity_name="Support runbook validation",
                description="Validate runbooks with support leads and service owners.",
                owner="Operations",
                assignee="M. Patel",
                category="operations",
                status="overdue",
                readiness="at_risk",
                due_date=date(2026, 1, 25),
                actual_start_date=date(2026, 1, 12),
                progress_percent=40,
                blocker="Runbook feedback still pending from service owners.",
                risk="Operational readiness may be delayed.",
            ),
            KtActivity(
                activity_id="act-1004",
                plan_id="kt-plan-demo-001",
                activity_name="Knowledge transfer workshop",
                description="Deliver final hands-on KT sessions to support teams.",
                owner="Knowledge Lead",
                assignee="S. Lee",
                category="knowledge",
                status="planned",
                readiness="not_assessed",
                due_date=date(2026, 3, 5),
                progress_percent=20,
            ),
        ],
    )
    PLAN_STORE[plan.plan_id] = plan


_seed_demo_data()


def import_kt_plan(payload: KtPlanImportRequest) -> KtPlan:
    """Create or replace a KT plan. This will later map to Azure SQL and KT Planner API."""
    activities: list[KtActivity] = []
    for item in payload.activities:
        item_data = item.model_dump(exclude_none=True)
        activity = KtActivity(
            activity_id=item_data.get("activity_id") or _generate_activity_id(),
            plan_id=payload.plan_id,
            activity_name=item_data.get("activity_name") or "Unnamed activity",
            description=item_data.get("description") or "",
            owner=item_data.get("owner") or payload.owner,
            assignee=item_data.get("assignee") or "",
            category=item_data.get("category") or "general",
            status=item_data.get("status") or "not_started",
            readiness=item_data.get("readiness") or "not_assessed",
            due_date=item_data.get("due_date"),
            actual_start_date=item_data.get("actual_start_date"),
            actual_end_date=item_data.get("actual_end_date"),
            progress_percent=int(item_data.get("progress_percent") or 0),
            blocker=item_data.get("blocker") or "",
            risk=item_data.get("risk") or "",
            notes=item_data.get("notes") or "",
            source=item_data.get("source") or "kt_planner_api",
            expected_topics=item_data.get("expected_topics") or [],
        )
        activities.append(activity)

    plan = KtPlan(
        plan_id=payload.plan_id,
        project_name=payload.project_name,
        knowledge_domain=payload.knowledge_domain,
        due_date=payload.due_date,
        owner=payload.owner,
        status="active",
        activities=activities,
    )
    PLAN_STORE[plan.plan_id] = plan
    return plan


def get_all_activities(plan_id: str | None = None) -> list[KtActivity]:
    activities: list[KtActivity] = []
    for plan in PLAN_STORE.values():
        if plan_id and plan.plan_id != plan_id:
            continue
        activities.extend(plan.activities)
    return activities


def get_activity(activity_id: str) -> KtActivity | None:
    for plan in PLAN_STORE.values():
        for activity in plan.activities:
            if activity.activity_id == activity_id:
                return activity
    return None


def create_activity(plan_id: str, payload: KtActivityCreateRequest) -> KtActivity:
    plan = PLAN_STORE.get(plan_id)
    if plan is None:
        raise KeyError(f"KT plan {plan_id} was not found.")
    item_data = payload.model_dump(exclude_none=True)
    activity = KtActivity(
        activity_id=item_data.get("activity_id") or _generate_activity_id(),
        plan_id=plan_id,
        activity_name=item_data.get("activity_name") or "New activity",
        description=item_data.get("description") or "",
        owner=item_data.get("owner") or plan.owner,
        assignee=item_data.get("assignee") or "",
        category=item_data.get("category") or "general",
        status=item_data.get("status") or "not_started",
        readiness=item_data.get("readiness") or "not_assessed",
        due_date=item_data.get("due_date"),
        actual_start_date=item_data.get("actual_start_date"),
        actual_end_date=item_data.get("actual_end_date"),
        progress_percent=int(item_data.get("progress_percent") or 0),
        blocker=item_data.get("blocker") or "",
        risk=item_data.get("risk") or "",
        notes=item_data.get("notes") or "",
        source=item_data.get("source") or "bot_api",
        expected_topics=item_data.get("expected_topics") or [],
    )
    plan.activities.append(activity)
    return activity


def update_activity(activity_id: str, payload: ActivityUpdateRequest) -> KtActivity:
    activity = get_activity(activity_id)
    if activity is None:
        raise KeyError(f"Activity {activity_id} was not found.")
    update_data = payload.model_dump(exclude_none=True)
    for field_name, value in update_data.items():
        setattr(activity, field_name, value)
    if payload.status == "completed":
        activity.progress_percent = 100
        activity.actual_end_date = activity.actual_end_date or _now_date()
    if payload.status == "overdue" and activity.due_date and activity.due_date < _now_date():
        activity.progress_percent = min(activity.progress_percent, 99)
    return activity


def delete_activity(activity_id: str) -> bool:
    for plan in PLAN_STORE.values():
        original_length = len(plan.activities)
        plan.activities = [t for t in plan.activities if t.activity_id != activity_id]
        if len(plan.activities) != original_length:
            return True
    return False


def calculate_progress(plan_id: str | None = None) -> int:
    activities = get_all_activities(plan_id)
    if not activities:
        return 0
    total = len(activities)
    completed = sum(1 for a in activities if a.status == "completed")
    return int(round((completed / total) * 100))


def detect_overdue_activities(plan_id: str | None = None) -> list[KtActivity]:
    today = _now_date()
    results: list[KtActivity] = []
    for activity in get_all_activities(plan_id):
        if activity.due_date and activity.due_date < today and activity.status not in {"completed", "cancelled", "descoped"}:
            results.append(activity)
    return results


def determine_readiness(plan_id: str | None = None) -> KtReadiness:
    activities = get_all_activities(plan_id)
    if not activities:
        return "not_assessed"
    counts = _activity_counts(activities)
    if counts["completed"] == len(activities):
        return "accepted"
    if counts["overdue"] or counts["on_hold"] or counts["cancelled"]:
        return "at_risk"
    if counts["in_progress"] or counts["planned"]:
        return "partially_ready"
    return "ready" if counts["completed"] else "not_assessed"


def generate_status_summary(plan_id: str | None = None) -> KtSummaryResponse:
    plan = next(iter(PLAN_STORE.values()), None)
    if plan_id:
        plan = PLAN_STORE.get(plan_id)
    if plan is None:
        raise KeyError(f"KT plan {plan_id} was not found.")

    activities = plan.activities
    counts = _activity_counts(activities)
    overdue = detect_overdue_activities(plan_id)
    blocked = [a for a in activities if a.blocker.strip()]
    at_risk = [a for a in activities if a.risk.strip()]
    progress = calculate_progress(plan_id)
    readiness = determine_readiness(plan_id)

    summary = (
        f"{progress}% of activities are complete. "
        f"{len(overdue)} activities are overdue, "
        f"{len(blocked)} are blocked, and "
        f"{len(at_risk)} have active risk flags."
    )

    return KtSummaryResponse(
        plan_id=plan.plan_id,
        project_name=plan.project_name,
        progress_percent=progress,
        total_activities=len(activities),
        completed_activities=counts["completed"],
        overdue_activities=len(overdue),
        blocked_activities=len(blocked),
        risk_activities=len(at_risk),
        readiness=readiness,
        summary=summary,
    )


def sync_with_graph(plan_id: str | None = None) -> GraphSyncResult:
    activities = get_all_activities(plan_id)
    return MicrosoftGraphSyncService().sync_kt_status(activities)


# ---------------------------------------------------------------------------
# Microsoft 365 meeting automation
#
# The functions below are the backend hooks used by
# app.kt_tracker.meeting_sync_service to turn Outlook/Teams meetings into KT
# activities and to fold transcript analysis results back into the tracker,
# without any manual API calls from an end user.
# ---------------------------------------------------------------------------


def find_activity_by_external_meeting_id(external_meeting_id: str) -> KtActivity | None:
    """Look up an activity already linked to a Graph meeting (dedupe key)."""
    for plan in PLAN_STORE.values():
        for activity in plan.activities:
            if activity.external_meeting_id == external_meeting_id:
                return activity
    return None


def upsert_activity_from_meeting(
    plan_id: str,
    meeting: KtMeeting,
    default_owner: str = "",
    default_expected_topics: list[str] | None = None,
) -> tuple[KtActivity, bool]:
    """Create or update the KT activity linked to a discovered meeting.

    Returns (activity, created). Idempotent on ``meeting.external_meeting_id`` so
    the same Outlook occurrence is never turned into two activities, and a
    reschedule/cancellation just updates the existing record in place.

    ``default_expected_topics`` seeds a brand-new activity's expected topic
    list when nothing else (e.g. a matching KT Planner import) has already
    defined one, so transcript analysis has something concrete to compare
    against instead of an empty list.
    """
    plan = PLAN_STORE.get(plan_id)
    if plan is None:
        raise KeyError(f"KT plan {plan_id} was not found.")

    existing = find_activity_by_external_meeting_id(meeting.external_meeting_id)
    if existing is not None:
        existing.meeting_subject = meeting.subject or existing.meeting_subject
        existing.meeting_start = meeting.start_time
        existing.meeting_end = meeting.end_time
        existing.meeting_status = meeting.status
        existing.organizer = meeting.organizer_email or meeting.organizer_name
        if meeting.status == "cancelled":
            existing.status = "cancelled"
        existing.last_synced_at = datetime.utcnow()
        return existing, False

    # Only ever auto-create for meetings that are not already in the past
    # cancelled, and never mark a brand-new activity "completed" purely
    # because a meeting occurred - completion is decided by transcript
    # analysis in apply_meeting_analysis().
    initial_status: Any = "planned"
    if meeting.status == "cancelled":
        initial_status = "cancelled"
    elif meeting.status in ("ongoing", "completed"):
        initial_status = "in_progress"

    activity = KtActivity(
        activity_id=_generate_activity_id(),
        plan_id=plan_id,
        activity_name=meeting.subject or "KT session",
        description=f"Auto-created from Outlook/Teams meeting '{meeting.subject}'.",
        owner=default_owner or plan.owner,
        assignee=meeting.organizer_name or meeting.organizer_email,
        category="knowledge",
        status=initial_status,
        readiness="not_assessed",
        due_date=meeting.end_time.date() if meeting.end_time else None,
        actual_start_date=meeting.start_time.date() if meeting.start_time else None,
        progress_percent=0,
        source="ms365_graph_sync",
        expected_topics=list(default_expected_topics or []),
        external_meeting_id=meeting.external_meeting_id,
        meeting_subject=meeting.subject,
        meeting_start=meeting.start_time,
        meeting_end=meeting.end_time,
        meeting_status=meeting.status,
        organizer=meeting.organizer_email or meeting.organizer_name,
        last_synced_at=datetime.utcnow(),
    )
    plan.activities.append(activity)
    return activity, True


def apply_meeting_analysis(activity_id: str, analysis: MeetingAnalysisResult) -> KtActivity:
    """Fold an AI transcript/attendance analysis result into a KT activity.

    Status/readiness are derived from what was *actually* covered, never from
    the mere fact that the scheduled meeting time has elapsed:
      - all expected topics covered, no unresolved questions -> completed
      - anything partially covered/missed, or unresolved questions -> stays
        in_progress with follow_up_required=True so it surfaces as pending
        work instead of being silently marked done.
      - no transcript/attendance data could be retrieved -> status is left
        untouched and a low confidence score is recorded so the activity
        shows up for manual review instead of auto-completing.
    """
    activity = get_activity(activity_id)
    if activity is None:
        raise KeyError(f"Activity {activity_id} was not found.")

    activity.participants = analysis.participants
    activity.topics_covered = analysis.topics_covered
    activity.topics_partially_covered = analysis.topics_partially_covered
    activity.topics_missed = analysis.topics_missed
    activity.questions_raised = analysis.questions_raised
    activity.questions_unresolved = analysis.questions_unresolved
    activity.action_items = analysis.action_items
    activity.follow_up_required = analysis.follow_up_required
    activity.follow_up_topics = analysis.follow_up_topics
    activity.transcript_summary = analysis.transcript_summary
    activity.analysis_confidence = analysis.confidence
    activity.last_synced_at = datetime.utcnow()

    if not analysis.transcript_available and not analysis.participants:
        # No Microsoft 365 evidence at all - do not touch status/readiness.
        return activity

    has_gaps = bool(analysis.topics_missed or analysis.topics_partially_covered)
    has_unresolved_questions = analysis.questions_unresolved > 0

    if not has_gaps and not has_unresolved_questions and activity.expected_topics:
        activity.status = "completed"
        activity.readiness = "ready"
        activity.progress_percent = 100
        activity.actual_end_date = activity.actual_end_date or _now_date()
    elif has_gaps or has_unresolved_questions:
        activity.status = "in_progress"
        activity.readiness = "at_risk" if analysis.topics_missed else "partially_ready"
        covered = len(analysis.topics_covered)
        expected = max(len(activity.expected_topics), 1)
        activity.progress_percent = min(99, int(round((covered / expected) * 100)))
    return activity


def create_follow_up_activity(source_activity: KtActivity) -> KtActivity | None:
    """Auto-create a follow-up KT activity for topics missed/partially covered.

    Idempotent: if a follow-up activity already exists for this source
    activity (tracked via description tag), it is not duplicated on the next
    sync cycle.
    """
    if not source_activity.follow_up_topics:
        return None

    tag = f"[follow-up:{source_activity.activity_id}]"
    for activity in get_all_activities(source_activity.plan_id):
        if tag in activity.description:
            # Already created - keep its topic list current instead of duplicating.
            activity.expected_topics = source_activity.follow_up_topics
            return activity

    follow_up = KtActivity(
        activity_id=_generate_activity_id(),
        plan_id=source_activity.plan_id,
        activity_name=f"Follow-up KT: {source_activity.activity_name}",
        description=(
            f"{tag} Auto-created because these topics were missed or only "
            f"partially covered: {', '.join(source_activity.follow_up_topics)}."
        ),
        owner=source_activity.owner,
        assignee=source_activity.assignee,
        category=source_activity.category,
        status="planned",
        readiness="not_assessed",
        expected_topics=list(source_activity.follow_up_topics),
        source="ms365_graph_sync",
    )
    plan = PLAN_STORE.get(source_activity.plan_id)
    if plan is not None:
        plan.activities.append(follow_up)
    return follow_up
