"""Orchestrates the end-to-end Microsoft 365 KT meeting automation pipeline.

Flow (matches the target architecture requested for KT Tracker Bot):

  Outlook Calendar + Microsoft Teams
    -> Microsoft Graph API                 (app.kt_tracker.graph_client)
    -> Identify meeting & lifecycle state  (discover_meetings / _meeting_status)
    -> Upsert KT activity, dedupe by iCalUId (app.kt_tracker.service)
    -> Retrieve attendance + transcript     (graph_client)
    -> AI transcript analysis               (app.kt_tracker.transcript_analyzer)
    -> Compare against expected KT topics
    -> Auto-update KT Activities backend    (service.apply_meeting_analysis)
    -> Auto-create follow-up activities for missed/partial topics

No step here ever sets an activity to "completed" purely because the
meeting's end time has passed; completion is only derived from analysis of
who attended and what was actually discussed.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from app.kt_tracker import service
from app.kt_tracker.demo_graph_client import DemoGraphClient
from app.kt_tracker.graph_client import GraphClient
from app.kt_tracker.models import (
    KtMeeting,
    KtMeetingStatus,
    MeetingAnalysisResult,
    MeetingParticipant,
    MeetingSyncResult,
)
from app.kt_tracker.transcript_analyzer import analyze_transcript

logger = logging.getLogger("kt_tracker.meeting_sync")

DEFAULT_SUBJECT_KEYWORDS = [
    kw.strip()
    for kw in os.getenv("KT_GRAPH_SUBJECT_KEYWORDS", "KT,Knowledge Transfer").split(",")
    if kw.strip()
]
LOOKBACK_DAYS = int(os.getenv("KT_GRAPH_LOOKBACK_DAYS", "14"))
LOOKAHEAD_DAYS = int(os.getenv("KT_GRAPH_LOOKAHEAD_DAYS", "30"))


def build_graph_client() -> GraphClient | DemoGraphClient:
    """Return the configured Graph client, real or demo.

    ``KT_GRAPH_MODE=demo`` forces the in-memory :class:`DemoGraphClient` so
    the full pipeline can be demonstrated before Entra ID/Graph access has
    been provisioned. ``KT_GRAPH_MODE=live`` (the default) uses the real
    :class:`GraphClient`. Switching later is a one-line env var change - no
    code in this module or the API layer needs to change.
    """
    mode = os.getenv("KT_GRAPH_MODE", "live").strip().lower()
    if mode == "demo":
        return DemoGraphClient()
    return GraphClient()


def _meeting_status(event: dict, now: datetime) -> KtMeetingStatus:
    if event.get("isCancelled"):
        return "cancelled"
    start = _parse_graph_datetime(event["start"])
    end = _parse_graph_datetime(event["end"])
    if now < start:
        return "scheduled"
    if start <= now <= end:
        return "ongoing"
    return "completed"


def _parse_graph_datetime(value: dict) -> datetime:
    # Graph returns {"dateTime": "...", "timeZone": "UTC"} for calendarView results.
    raw = value["dateTime"]
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def discover_meetings(
    client: GraphClient | DemoGraphClient,
    mailbox: str,
    subject_keywords: list[str] | None = None,
) -> list[KtMeeting]:
    """Read the Outlook calendar and return candidate KT meetings."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=LOOKBACK_DAYS)
    window_end = now + timedelta(days=LOOKAHEAD_DAYS)
    events = client.list_calendar_events(
        mailbox=mailbox,
        start=window_start,
        end=window_end,
        subject_keywords=subject_keywords or DEFAULT_SUBJECT_KEYWORDS,
    )
    meetings: list[KtMeeting] = []
    for event in events:
        organizer = (event.get("organizer") or {}).get("emailAddress") or {}
        meetings.append(
            KtMeeting(
                external_meeting_id=event.get("iCalUId") or event["id"],
                graph_event_id=event["id"],
                subject=event.get("subject") or "",
                organizer_name=organizer.get("name") or "",
                organizer_email=organizer.get("address") or "",
                start_time=_parse_graph_datetime(event["start"]),
                end_time=_parse_graph_datetime(event["end"]),
                status=_meeting_status(event, now),
            )
        )
    return meetings


def _resolve_online_meeting_id(client: GraphClient | DemoGraphClient, meeting: KtMeeting, mailbox: str) -> str | None:
    # Attendance/transcripts are addressed by Graph onlineMeeting id, which we
    # resolve lazily only for meetings that actually need analysis.
    join_url = None
    event_lookup = client.list_calendar_events(
        mailbox=mailbox,
        start=meeting.start_time - timedelta(minutes=1),
        end=meeting.end_time + timedelta(minutes=1),
    )
    for event in event_lookup:
        if event["id"] == meeting.graph_event_id:
            online_meeting = event.get("onlineMeeting") or {}
            join_url = online_meeting.get("joinUrl")
            break
    if not join_url:
        return None
    resolved = client.resolve_online_meeting(mailbox, join_url)
    return resolved.get("id") if resolved else None


def _to_participants(records: list[dict]) -> list[MeetingParticipant]:
    participants = []
    for record in records:
        identity = (record.get("identity") or {}).get("user") or {}
        intervals = record.get("attendanceIntervals") or []
        total_seconds = sum(i.get("durationInSeconds", 0) for i in intervals)
        joined_at = None
        left_at = None
        if intervals:
            joined_at = _safe_parse(intervals[0].get("joinDateTime"))
            left_at = _safe_parse(intervals[-1].get("leaveDateTime"))
        participants.append(
            MeetingParticipant(
                name=record.get("identity", {}).get("displayName") or identity.get("displayName") or "Unknown",
                email=identity.get("id") or "",
                role=record.get("role", "attendee") if record.get("role") in ("organizer", "attendee") else "attendee",
                joined_at=joined_at,
                left_at=left_at,
                duration_minutes=round(total_seconds / 60, 1) if total_seconds else None,
            )
        )
    return participants


def _safe_parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def analyze_completed_meeting(
    client: GraphClient | DemoGraphClient,
    mailbox: str,
    meeting: KtMeeting,
    expected_topics: list[str],
) -> MeetingAnalysisResult:
    """Retrieve attendance + transcript for one completed meeting and analyze it."""
    online_meeting_id = _resolve_online_meeting_id(client, meeting, mailbox)
    participants: list[MeetingParticipant] = []
    transcript_text: str | None = None
    recording_available = False

    if online_meeting_id:
        try:
            records = client.get_attendance_records(mailbox, online_meeting_id)
            participants = _to_participants(records)
        except Exception:
            logger.exception("Failed to retrieve attendance for meeting %s", meeting.external_meeting_id)
        try:
            transcript_text = client.get_transcript_text(mailbox, online_meeting_id)
        except Exception:
            logger.exception("Failed to retrieve transcript for meeting %s", meeting.external_meeting_id)
        try:
            recording_available = client.has_recording(mailbox, online_meeting_id)
        except Exception:
            logger.exception("Failed to check recording for meeting %s", meeting.external_meeting_id)

    analysis = analyze_transcript(transcript_text or "", expected_topics)
    follow_up_topics = list(analysis.topics.partially_covered) + list(analysis.topics.missed)

    return MeetingAnalysisResult(
        activity_id="",  # filled in by caller once the activity is known
        external_meeting_id=meeting.external_meeting_id,
        meeting_subject=meeting.subject,
        participants=participants,
        transcript_available=bool(transcript_text),
        recording_available=recording_available,
        topics_covered=analysis.topics.covered,
        topics_partially_covered=analysis.topics.partially_covered,
        topics_missed=analysis.topics.missed,
        questions_raised=analysis.questions_raised,
        questions_unresolved=analysis.questions_unresolved,
        action_items=analysis.action_items,
        follow_up_required=bool(follow_up_topics),
        follow_up_topics=follow_up_topics,
        transcript_summary=analysis.summary,
        confidence=analysis.confidence,
    )


# In-memory store of the latest analysis per activity, exposed via the API
# for transparency into "why" an activity's status changed.
ANALYSIS_STORE: dict[str, MeetingAnalysisResult] = {}
MEETING_STORE: dict[str, KtMeeting] = {}


def sync_all(mailbox: str, plan_id: str | None = None) -> MeetingSyncResult:
    """Run one full discover -> upsert -> analyze -> update cycle."""
    demo_mode = os.getenv("KT_GRAPH_MODE", "live").strip().lower() == "demo"
    result = MeetingSyncResult(enabled=False, mailbox=mailbox, demo_mode=demo_mode)
    client = build_graph_client()
    if not client.is_configured:
        result.message = (
            "Microsoft Graph is not configured (missing AZURE_TENANT_ID / "
            "AZURE_CLIENT_ID / AZURE_CLIENT_SECRET). No meetings were synced. "
            "Set KT_GRAPH_MODE=demo to run the pipeline against sample data "
            "while real Graph access is pending."
        )
        return result
    result.enabled = True

    target_plan_id = plan_id or next(iter(service.PLAN_STORE), None)
    if target_plan_id is None:
        result.message = "No KT plan exists yet to attach discovered meetings to."
        return result

    try:
        meetings = discover_meetings(client, mailbox)
    except Exception as exc:  # pragma: no cover - defensive top-level guard
        logger.exception("Meeting discovery failed for mailbox %s", mailbox)
        result.errors.append(f"discovery_failed: {exc}")
        return result

    result.meetings_discovered = len(meetings)

    default_expected_topics = getattr(client, "default_expected_topics", None)

    for meeting in meetings:
        try:
            MEETING_STORE[meeting.external_meeting_id] = meeting
            activity, created = service.upsert_activity_from_meeting(
                target_plan_id,
                meeting,
                default_expected_topics=default_expected_topics,
            )
            meeting.activity_id = activity.activity_id
            meeting.plan_id = target_plan_id
            if created:
                result.activities_created += 1
            else:
                result.activities_updated += 1

            already_analyzed = activity.analysis_confidence is not None
            if meeting.status == "completed" and not already_analyzed:
                analysis = analyze_completed_meeting(
                    client, mailbox, meeting, activity.expected_topics
                )
                analysis.activity_id = activity.activity_id
                ANALYSIS_STORE[activity.activity_id] = analysis
                service.apply_meeting_analysis(activity.activity_id, analysis)
                result.meetings_analyzed += 1

                refreshed = service.get_activity(activity.activity_id)
                if refreshed and refreshed.follow_up_required:
                    follow_up = service.create_follow_up_activity(refreshed)
                    if follow_up is not None:
                        result.follow_up_activities_created += 1
        except Exception as exc:  # pragma: no cover - per-meeting isolation
            logger.exception("Failed to process meeting %s", meeting.external_meeting_id)
            result.errors.append(f"{meeting.external_meeting_id}: {exc}")

    result.message = (
        f"Synced {result.meetings_discovered} meeting(s): "
        f"{result.activities_created} created, {result.activities_updated} updated, "
        f"{result.meetings_analyzed} analyzed, "
        f"{result.follow_up_activities_created} follow-up activities created."
    )
    return result
