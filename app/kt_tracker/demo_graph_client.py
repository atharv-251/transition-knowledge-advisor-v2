"""A drop-in stand-in for :class:`GraphClient` used to demo the full KT
Tracker automation pipeline before real Microsoft Graph/Entra ID access has
been provisioned.

This exists because the KT Tracker Bot's real value is the end-to-end
pipeline (Outlook -> Teams -> transcript analysis -> KT activity update), and
that pipeline should be demonstrable *today* without waiting on IT to grant
Entra ID app registration access. It implements exactly the same public
surface as :class:`app.kt_tracker.graph_client.GraphClient`
(``list_calendar_events``, ``resolve_online_meeting``,
``get_attendance_records``, ``get_transcript_text``, ``has_recording``) so
``meeting_sync_service.py`` runs unmodified against it.

The synthetic meetings are generated relative to "now" (not fixed dates) so
the demo behaves sensibly no matter when it's run:
  - one meeting completed a few days ago with a transcript that fully covers
    its expected topics -> ends up "completed" / "ready"
  - one meeting completed recently with a transcript that only partially
    covers its expected topics -> ends up "in_progress" / "at_risk" plus an
    auto-created follow-up activity
  - one meeting scheduled a few days in the future -> stays untouched until
    it actually happens

Switching to real Microsoft Graph later requires **no code change** anywhere
else in the app: set ``KT_GRAPH_MODE=live`` (or provide real
``AZURE_TENANT_ID``/``AZURE_CLIENT_ID``/``AZURE_CLIENT_SECRET`` and leave the
default), and ``meeting_sync_service.build_graph_client()`` will return the
real :class:`GraphClient` instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

DEMO_ORGANIZER_NAME = "Priya Sharma"
DEMO_ORGANIZER_EMAIL = "priya.sharma@vwgroup-demo.com"

_ATTENDEES = [
    ("Priya Sharma", "priya.sharma@vwgroup-demo.com", "organizer"),
    ("Arjun Mehta", "arjun.mehta@vwgroup-demo.com", "attendee"),
    ("Sofia Weber", "sofia.weber@vwgroup-demo.com", "attendee"),
    ("Daniel Wagner", "daniel.wagner@vwgroup-demo.com", "attendee"),
]

# A realistic Teams-style transcript where every expected topic is discussed
# substantively -> should be classified "covered" by the analyzer.
_TRANSCRIPT_FULL_COVERAGE = """
Priya Sharma: Good morning everyone, thanks for joining today's Dealer Portal
knowledge transfer session, we have a full agenda so let's get started right
away with the application architecture overview for the platform.

Priya Sharma: The application architecture for the Dealer Portal consists of
a React front end, a Spring Boot API layer, and an Oracle database, deployed
redundantly across two Azure regions to guarantee high availability for all
dealers nationwide.

Arjun Mehta: Great, now let's move on to the database structure, which is the
second topic on our agenda for today's session.

Arjun Mehta: The database structure uses a normalized schema with twelve
core tables, and the dealer master table is the central entity that every
other table references through foreign key relationships across the whole
schema.

Sofia Weber: Next let's cover API integration, since that's the third item
we planned to walk through together this morning.

Sofia Weber: Our API integration exposes REST endpoints consumed by the
mobile app and by three downstream partner systems, using OAuth2 client
credentials for service calls and JWT tokens for authenticated user
sessions.

Daniel Wagner: Moving on, I'd like to walk everyone through the batch jobs
that keep the Dealer Portal data synchronized every night.

Daniel Wagner: We run four scheduled batch jobs every night, covering dealer
synchronization, inventory reconciliation, invoice generation, and the
compliance report extract, and each batch job alerts the on call channel
automatically if it fails twice.

Priya Sharma: Let's now spend some time on error handling, which is an
important part of how the platform stays reliable for everyone.

Priya Sharma: Our error handling strategy wraps every API error in a
standard envelope containing an error code, a correlation id, and a
friendly message, with automatic retries and circuit breakers protecting
all downstream partner integrations.

Arjun Mehta: Finally, let's close out with the production support process
so everyone understands how incidents get handled after go live.

Arjun Mehta: The production support process follows a weekly on call
rotation with escalation from level one through level three, and every
incident triggers a documented retrospective within forty eight hours of
resolution.

Sofia Weber: That covers everything on today's agenda, does anyone have
questions before we finish up?

Daniel Wagner: Just one question, who do we contact if the compliance batch
job fails over a weekend?

Priya Sharma: Good question, we will share their escalation contact right
after this call, that resolves it.
""".strip()

# A transcript where only some topics are discussed - error handling is
# mentioned but explicitly deferred, batch jobs and production support are
# never reached -> should be classified "partial"/"missed" by the analyzer.
_TRANSCRIPT_PARTIAL_COVERAGE = """
Priya Sharma: Let's continue the Dealer Portal KT series for folks who
joined late.

Arjun Mehta: Quickly, application architecture is a three tier app, that's
it for today.

Arjun Mehta: Database structure - dealer master table is the central
entity, twelve tables.

Sofia Weber: API integration briefly - OAuth2 and JWT for mobile and
partner systems.

Priya Sharma: We touched on error handling briefly last time.

Daniel Wagner: We did not get to batch jobs today, we ran out of time.

Priya Sharma: We also did not get to production support process today.

Priya Sharma: Let's plan to properly finish the remaining agenda items in
our next session. Thanks everyone.
""".strip()


def _demo_expected_topics() -> list[str]:
    return [
        "Application architecture",
        "Database structure",
        "API integration",
        "Batch jobs",
        "Error handling",
        "Production support process",
    ]


class DemoGraphClient:
    """In-memory stand-in for GraphClient producing realistic KT meeting data."""

    #: Always reports as configured so ``meeting_sync_service`` proceeds.
    is_configured = True

    def __init__(self) -> None:
        self._now = datetime.now(timezone.utc)
        self._events = self._build_demo_events()
        self.default_expected_topics = _demo_expected_topics()

    # ------------------------------------------------------------------
    # Fixture construction
    # ------------------------------------------------------------------

    def _build_demo_events(self) -> list[dict[str, Any]]:
        now = self._now

        def event(
            key: str,
            subject: str,
            start: datetime,
            duration_minutes: int,
            cancelled: bool = False,
        ) -> dict[str, Any]:
            end = start + timedelta(minutes=duration_minutes)
            return {
                "id": f"demo-event-{key}",
                "iCalUId": f"demo-ical-{key}",
                "subject": subject,
                "organizer": {
                    "emailAddress": {
                        "name": DEMO_ORGANIZER_NAME,
                        "address": DEMO_ORGANIZER_EMAIL,
                    }
                },
                "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
                "isCancelled": cancelled,
                "onlineMeeting": {
                    "joinUrl": f"https://teams.microsoft.com/l/meetup-join/demo-{key}"
                },
                "onlineMeetingProvider": "teamsForBusiness",
                "seriesMasterId": None,
                "_demo_key": key,
            }

        return [
            event(
                "session1-full",
                "KT - Dealer Portal Architecture (Session 1)",
                now - timedelta(days=5, hours=1),
                60,
            ),
            event(
                "session2-partial",
                "KT - Dealer Portal Architecture (Session 2)",
                now - timedelta(days=1, hours=2),
                45,
            ),
            event(
                "session3-upcoming",
                "KT - Dealer Portal Architecture (Session 3, follow-up)",
                now + timedelta(days=3),
                60,
            ),
        ]

    def _transcript_for(self, demo_key: str) -> str | None:
        if demo_key == "session1-full":
            return _TRANSCRIPT_FULL_COVERAGE
        if demo_key == "session2-partial":
            return _TRANSCRIPT_PARTIAL_COVERAGE
        return None

    def _attendance_for(self, demo_key: str) -> list[dict[str, Any]]:
        if demo_key not in ("session1-full", "session2-partial"):
            return []
        records = []
        base_join = self._now - timedelta(minutes=5)
        attendees = _ATTENDEES if demo_key == "session1-full" else _ATTENDEES[:3]
        for idx, (name, email, role) in enumerate(attendees):
            joined = base_join + timedelta(minutes=idx)
            left = joined + timedelta(minutes=50 - idx * 3)
            records.append(
                {
                    "identity": {
                        "displayName": name,
                        "user": {"id": email},
                    },
                    "role": role,
                    "attendanceIntervals": [
                        {
                            "joinDateTime": joined.isoformat(),
                            "leaveDateTime": left.isoformat(),
                            "durationInSeconds": int((left - joined).total_seconds()),
                        }
                    ],
                }
            )
        return records

    # ------------------------------------------------------------------
    # GraphClient-compatible surface
    # ------------------------------------------------------------------

    def list_calendar_events(
        self,
        mailbox: str,
        start: datetime,
        end: datetime,
        subject_keywords: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        del mailbox  # demo data is not actually mailbox-scoped
        events = [e for e in self._events if start <= _event_start(e) <= end]
        if subject_keywords:
            keywords = [k.lower() for k in subject_keywords]
            events = [
                e for e in events if any(k in e["subject"].lower() for k in keywords)
            ]
        return events

    def resolve_online_meeting(self, organizer_id: str, join_url: str) -> dict[str, Any] | None:
        del organizer_id
        for event in self._events:
            if event["onlineMeeting"]["joinUrl"] == join_url:
                return {"id": f"demo-online-{event['_demo_key']}"}
        return None

    def get_attendance_records(self, organizer_id: str, online_meeting_id: str) -> list[dict[str, Any]]:
        del organizer_id
        demo_key = online_meeting_id.replace("demo-online-", "")
        return self._attendance_for(demo_key)

    def get_transcript_text(self, organizer_id: str, online_meeting_id: str) -> str | None:
        del organizer_id
        demo_key = online_meeting_id.replace("demo-online-", "")
        return self._transcript_for(demo_key)

    def has_recording(self, organizer_id: str, online_meeting_id: str) -> bool:
        del organizer_id
        demo_key = online_meeting_id.replace("demo-online-", "")
        return demo_key in ("session1-full", "session2-partial")


def _event_start(event: dict[str, Any]) -> datetime:
    raw = event["start"]["dateTime"]
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def demo_expected_topics() -> list[str]:
    """Expected KT topics used to seed a demo KT activity's ``expected_topics``."""
    return _demo_expected_topics()
