"""Thin Microsoft Graph REST client for the KT Tracker automation pipeline.

This module talks to Microsoft Graph using application (client-credentials)
permissions so the bot can read Outlook calendars and Teams meeting data
without a signed-in user. It intentionally avoids the msgraph-sdk dependency
and uses ``httpx`` directly against the v1.0 REST surface, which keeps the
footprint small and every call auditable.

Required Azure AD app registration (application permissions, admin consent):
  - Calendars.Read                       (read KT meetings on the KT mailbox)
  - OnlineMeetings.Read.All              (resolve Teams online meeting objects)
  - OnlineMeetingArtifact.Read.All       (attendance reports)
  - OnlineMeetingTranscript.Read.All     (Teams meeting transcripts)

Additional tenant-side requirements:
  - An application access policy must be granted so the app can read the
    organizer's online meetings/transcripts:
      New-CsApplicationAccessPolicy -Identity <policy> -AppIds <clientId> ...
      Grant-CsApplicationAccessPolicy -PolicyName <policy> -Identity <organizer>
  - Transcription must be enabled/allowed by the Teams meeting policy, and the
    meeting must have actually been transcribed for a transcript to exist.

Every call degrades gracefully: on 403/404 (feature disabled, no consent, or
simply no transcript for that meeting) the client returns ``None``/``[]``
instead of raising, so a single missing artifact never breaks the whole sync.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger("kt_tracker.graph_client")

GRAPH_BASE_URL = os.getenv("GRAPH_API_BASE_URL", "https://graph.microsoft.com/v1.0")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("GRAPH_REQUEST_TIMEOUT_SECONDS", "30"))
MAX_RETRIES = int(os.getenv("GRAPH_MAX_RETRIES", "3"))


class GraphAuthError(RuntimeError):
    """Raised when Graph credentials are missing or a token cannot be acquired."""


@dataclass
class GraphToken:
    value: str
    expires_at: float


class GraphClient:
    """Minimal Graph REST client backed by azure-identity client-credentials auth."""

    #: Real Graph has no notion of a "default" expected-topics list; this
    #: stays ``None`` so ``meeting_sync_service`` leaves newly auto-created
    #: activities with an empty list unless a KT plan already supplied one.
    #: ``DemoGraphClient`` overrides this to seed a realistic demo.
    default_expected_topics: list[str] | None = None

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id or os.getenv("AZURE_TENANT_ID", "")
        self.client_id = client_id or os.getenv("AZURE_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("AZURE_CLIENT_SECRET", "")
        self._token: GraphToken | None = None
        self._credential = None

    @property
    def is_configured(self) -> bool:
        return bool(self.tenant_id and self.client_id and self.client_secret)

    def _get_credential(self):
        if self._credential is None:
            from azure.identity import ClientSecretCredential

            self._credential = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
        return self._credential

    def _get_token(self) -> str:
        if not self.is_configured:
            raise GraphAuthError(
                "Microsoft Graph is not configured. Set AZURE_TENANT_ID, "
                "AZURE_CLIENT_ID and AZURE_CLIENT_SECRET."
            )
        if self._token and self._token.expires_at - 60 > time.time():
            return self._token.value
        try:
            credential = self._get_credential()
            result = credential.get_token("https://graph.microsoft.com/.default")
        except Exception as exc:  # pragma: no cover - network/credential errors
            raise GraphAuthError(f"Failed to acquire Graph token: {exc}") from exc
        self._token = GraphToken(value=result.token, expires_at=result.expires_on)
        return self._token.value

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response | None:
        token = self._get_token()
        headers = kwargs.pop("headers", {}) or {}
        headers["Authorization"] = f"Bearer {token}"
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.request(method, url, headers=headers, **kwargs)
                if response.status_code in (403, 404):
                    logger.warning(
                        "Graph call %s %s returned %s (likely missing consent, "
                        "application access policy, or no artifact for this "
                        "meeting) - treating as unavailable.",
                        method,
                        url,
                        response.status_code,
                    )
                    return None
                if response.status_code == 429 and attempt < MAX_RETRIES:
                    retry_after = float(response.headers.get("Retry-After", "2"))
                    time.sleep(retry_after)
                    continue
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                logger.error("Graph call %s %s failed: %s", method, url, exc)
                break
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "Graph call %s %s attempt %s/%s failed: %s",
                    method,
                    url,
                    attempt,
                    MAX_RETRIES,
                    exc,
                )
                time.sleep(min(2 ** attempt, 10))
        if last_error is not None:
            logger.error("Graph call %s %s exhausted retries: %s", method, url, last_error)
        return None

    # ------------------------------------------------------------------
    # Calendar (Outlook)
    # ------------------------------------------------------------------

    def list_calendar_events(
        self,
        mailbox: str,
        start: datetime,
        end: datetime,
        subject_keywords: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List calendar events for ``mailbox`` between start/end (calendarView).

        ``calendarView`` (rather than plain ``/events``) automatically expands
        recurring meeting series into concrete occurrences, which is what we
        need to detect individual KT sessions.
        """
        url = f"{GRAPH_BASE_URL}/users/{quote(mailbox)}/calendarView"
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$select": (
                "id,iCalUId,subject,organizer,start,end,isCancelled,"
                "onlineMeeting,onlineMeetingProvider,seriesMasterId"
            ),
            "$orderby": "start/dateTime",
            "$top": "100",
        }
        response = self._request("GET", url, params=params)
        if response is None:
            return []
        events = response.json().get("value", [])
        if subject_keywords:
            keywords = [k.lower() for k in subject_keywords]
            events = [
                event
                for event in events
                if any(k in (event.get("subject") or "").lower() for k in keywords)
            ]
        return events

    # ------------------------------------------------------------------
    # Online meetings / attendance / transcripts
    # ------------------------------------------------------------------

    def resolve_online_meeting(self, organizer_id: str, join_url: str) -> dict[str, Any] | None:
        """Resolve the Graph onlineMeeting object id from its join URL."""
        url = f"{GRAPH_BASE_URL}/users/{quote(organizer_id)}/onlineMeetings"
        params = {"$filter": f"JoinWebUrl eq '{join_url}'"}
        response = self._request("GET", url, params=params)
        if response is None:
            return None
        values = response.json().get("value", [])
        return values[0] if values else None

    def get_attendance_records(self, organizer_id: str, online_meeting_id: str) -> list[dict[str, Any]]:
        """Return flattened attendance records for the most recent report."""
        base = f"{GRAPH_BASE_URL}/users/{quote(organizer_id)}/onlineMeetings/{online_meeting_id}"
        reports_response = self._request("GET", f"{base}/attendanceReports")
        if reports_response is None:
            return []
        reports = reports_response.json().get("value", [])
        if not reports:
            return []
        latest_report_id = reports[-1]["id"]
        detail_response = self._request(
            "GET",
            f"{base}/attendanceReports/{latest_report_id}",
            params={"$expand": "attendanceRecords"},
        )
        if detail_response is None:
            return []
        return detail_response.json().get("attendanceRecords", [])

    def get_transcript_text(self, organizer_id: str, online_meeting_id: str) -> str | None:
        """Fetch and concatenate the plain-text content of the meeting transcript."""
        base = f"{GRAPH_BASE_URL}/users/{quote(organizer_id)}/onlineMeetings/{online_meeting_id}"
        list_response = self._request("GET", f"{base}/transcripts")
        if list_response is None:
            return None
        transcripts = list_response.json().get("value", [])
        if not transcripts:
            return None
        transcript_id = transcripts[-1]["id"]
        content_response = self._request(
            "GET",
            f"{base}/transcripts/{transcript_id}/content",
            params={"$format": "text/vtt"},
            headers={"Accept": "text/vtt"},
        )
        if content_response is None:
            return None
        return content_response.text

    def has_recording(self, organizer_id: str, online_meeting_id: str) -> bool:
        base = f"{GRAPH_BASE_URL}/users/{quote(organizer_id)}/onlineMeetings/{online_meeting_id}"
        response = self._request("GET", f"{base}/recordings")
        if response is None:
            return False
        return bool(response.json().get("value"))
