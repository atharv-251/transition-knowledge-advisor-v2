"""Standalone Microsoft Graph connectivity diagnostic — Phase 1 testing only.

This script is intentionally independent of the KT Tracker application code
(app/kt_tracker/*). Its only purpose is to prove, step by step, that the
Azure AD app registration, Graph permissions, admin consent, and Teams
Application Access Policy are all correctly configured BEFORE the KT bot
integration is exercised.

Usage (run one step at a time, in order):

    python scripts/graph_connectivity_check.py auth
    python scripts/graph_connectivity_check.py calendar --mailbox kt-office@yourtenant.com
    python scripts/graph_connectivity_check.py find-meeting --mailbox kt-office@yourtenant.com --subject "KT - Dealer Portal"
    python scripts/graph_connectivity_check.py online-meeting --mailbox kt-office@yourtenant.com --join-url "<joinUrl from find-meeting output>"
    python scripts/graph_connectivity_check.py attendance --mailbox kt-office@yourtenant.com --meeting-id <id from online-meeting output>
    python scripts/graph_connectivity_check.py transcripts --mailbox kt-office@yourtenant.com --meeting-id <id>
    python scripts/graph_connectivity_check.py transcript-content --mailbox kt-office@yourtenant.com --meeting-id <id> --transcript-id <id>

Requires AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET in the
environment (or a .env file, loaded via python-dotenv if present).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import quote

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from azure.identity import ClientSecretCredential

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def get_token() -> str:
    tenant_id = os.environ["AZURE_TENANT_ID"]
    client_id = os.environ["AZURE_CLIENT_ID"]
    client_secret = os.environ["AZURE_CLIENT_SECRET"]
    credential = ClientSecretCredential(tenant_id, client_id, client_secret)
    token = credential.get_token("https://graph.microsoft.com/.default")
    return token.token


def pretty(response: httpx.Response) -> None:
    print(f"HTTP {response.status_code}")
    try:
        print(json.dumps(response.json(), indent=2)[:4000])
    except ValueError:
        print(response.text[:2000])


def step_auth(_args) -> None:
    token = get_token()
    print("SUCCESS: acquired app-only Graph token.")
    print(f"Token starts with: {token[:25]}...")


def step_calendar(args) -> None:
    token = get_token()
    url = f"{GRAPH_BASE}/users/{quote(args.mailbox)}/calendarView"
    params = {
        "startDateTime": args.start,
        "endDateTime": args.end,
        "$select": "id,iCalUId,subject,organizer,start,end,isCancelled,onlineMeeting",
        "$orderby": "start/dateTime",
    }
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(url, params=params, headers=headers, timeout=30)
    pretty(response)


def step_find_meeting(args) -> None:
    token = get_token()
    url = f"{GRAPH_BASE}/users/{quote(args.mailbox)}/calendarView"
    params = {
        "startDateTime": args.start,
        "endDateTime": args.end,
        "$select": "id,iCalUId,subject,organizer,start,end,onlineMeeting",
    }
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(url, params=params, headers=headers, timeout=30)
    if response.status_code != 200:
        pretty(response)
        return
    events = response.json().get("value", [])
    matches = [e for e in events if args.subject.lower() in (e.get("subject") or "").lower()]
    print(f"Found {len(matches)} matching event(s):")
    for event in matches:
        print(json.dumps(event, indent=2))


def step_online_meeting(args) -> None:
    token = get_token()
    url = f"{GRAPH_BASE}/users/{quote(args.mailbox)}/onlineMeetings"
    params = {"$filter": f"JoinWebUrl eq '{args.join_url}'"}
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(url, params=params, headers=headers, timeout=30)
    pretty(response)


def step_attendance(args) -> None:
    token = get_token()
    base = f"{GRAPH_BASE}/users/{quote(args.mailbox)}/onlineMeetings/{args.meeting_id}"
    headers = {"Authorization": f"Bearer {token}"}
    reports = httpx.get(f"{base}/attendanceReports", headers=headers, timeout=30)
    pretty(reports)
    if reports.status_code == 200:
        values = reports.json().get("value", [])
        if values:
            report_id = values[-1]["id"]
            detail = httpx.get(
                f"{base}/attendanceReports/{report_id}",
                params={"$expand": "attendanceRecords"},
                headers=headers,
                timeout=30,
            )
            print("--- Attendance detail ---")
            pretty(detail)


def step_transcripts(args) -> None:
    token = get_token()
    url = f"{GRAPH_BASE}/users/{quote(args.mailbox)}/onlineMeetings/{args.meeting_id}/transcripts"
    headers = {"Authorization": f"Bearer {token}"}
    response = httpx.get(url, headers=headers, timeout=30)
    pretty(response)


def step_transcript_content(args) -> None:
    token = get_token()
    url = (
        f"{GRAPH_BASE}/users/{quote(args.mailbox)}/onlineMeetings/"
        f"{args.meeting_id}/transcripts/{args.transcript_id}/content"
    )
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/vtt"}
    response = httpx.get(url, params={"$format": "text/vtt"}, headers=headers, timeout=30)
    print(f"HTTP {response.status_code}")
    print(response.text[:3000])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth").set_defaults(func=step_auth)

    p = sub.add_parser("calendar")
    p.add_argument("--mailbox", required=True)
    p.add_argument("--start", default="2026-09-01T00:00:00Z")
    p.add_argument("--end", default="2026-10-01T00:00:00Z")
    p.set_defaults(func=step_calendar)

    p = sub.add_parser("find-meeting")
    p.add_argument("--mailbox", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--start", default="2026-09-01T00:00:00Z")
    p.add_argument("--end", default="2026-10-01T00:00:00Z")
    p.set_defaults(func=step_find_meeting)

    p = sub.add_parser("online-meeting")
    p.add_argument("--mailbox", required=True)
    p.add_argument("--join-url", required=True)
    p.set_defaults(func=step_online_meeting)

    p = sub.add_parser("attendance")
    p.add_argument("--mailbox", required=True)
    p.add_argument("--meeting-id", required=True)
    p.set_defaults(func=step_attendance)

    p = sub.add_parser("transcripts")
    p.add_argument("--mailbox", required=True)
    p.add_argument("--meeting-id", required=True)
    p.set_defaults(func=step_transcripts)

    p = sub.add_parser("transcript-content")
    p.add_argument("--mailbox", required=True)
    p.add_argument("--meeting-id", required=True)
    p.add_argument("--transcript-id", required=True)
    p.set_defaults(func=step_transcript_content)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyError as exc:
        print(f"Missing required environment variable: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
