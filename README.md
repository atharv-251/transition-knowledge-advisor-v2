# KT Tracker Bot

This repository is now focused on the KT Tracker Bot, a governed AI service for tracking knowledge-transfer activities across KT plans and activities.

## What this bot does

- Imports a KT plan from a KT Planner payload or demo data
- Creates trackable KT activities
- Updates activity state and metadata
- Tracks blockers and risks
- Detects overdue activities
- Calculates overall progress and readiness
- Produces a summary of KT status for a plan
- **Automatically** discovers KT meetings from Outlook/Teams via Microsoft
  Graph, retrieves attendance and transcripts, runs AI topic-coverage
  analysis, and updates KT activities without any manual API calls

## Architecture

- API layer: `app/api/main.py`
- KT core business logic: `app/kt_tracker/service.py`
- Data models: `app/kt_tracker/models.py`
- Microsoft Graph REST client (calendar, attendance, transcripts): `app/kt_tracker/graph_client.py`
- Meeting discovery/dedupe + analysis orchestration: `app/kt_tracker/meeting_sync_service.py`
- Transcript / topic-coverage analyzer (heuristic, pluggable LLM hook): `app/kt_tracker/transcript_analyzer.py`
- Background sync scheduler: `app/kt_tracker/scheduler.py`
- Legacy Graph auth/config check: `app/kt_tracker/graph_sync.py`
- Azure SQL connection support: `app/database/sql_connection.py`
- Governance configuration: `app/governance/configuration.py`

## Local setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and fill in the Azure SQL / Graph values
3. Run the API locally with `python run_local.py`

## Azure deployment

- Host the API in Azure App Service or Azure Container Apps
- Set `DATABASE_MODE=azure_sql` for Azure SQL connectivity
- Use Managed Identity or a service principal for SQL and Graph access
- Keep Microsoft Graph access read-only at first

## Core APIs

- `POST /api/v1/kt-tracker/plan/import`
- `POST /api/v1/kt-tracker/activities`
- `GET /api/v1/kt-tracker/activities`
- `GET /api/v1/kt-tracker/activities/{activity_id}`
- `PUT /api/v1/kt-tracker/activities/{activity_id}`
- `DELETE /api/v1/kt-tracker/activities/{activity_id}`
- `GET /api/v1/kt-tracker/summary`
- `GET /api/v1/kt-tracker/overdue`
- `POST /api/v1/kt-tracker/sync-graph`
- `POST /api/v1/kt-tracker/meetings/sync` - on-demand trigger for the automated Outlook/Teams sync
- `GET /api/v1/kt-tracker/meetings` - meetings discovered from Outlook/Teams
- `GET /api/v1/kt-tracker/activities/{activity_id}/analysis` - the AI transcript/attendance analysis behind an activity's status
- `GET /api/v1/kt-tracker/activities/{activity_id}/analysis` - the AI transcript/attendance analysis behind an activity's status
- `POST /api/v1/kt-scheduler/run` - parse CSV/XLSX KT schedule input and generate/send SMTP `.ics` meeting invitations
- `GET /api/v1/transitions`, `GET /api/v1/transitions/latest`, `GET /api/v1/transitions/{id}` - transition documents (master plan/schedule/availability) backing the Transition Workspace UI
- `POST /api/v1/transitions/upload` - upload a new transition's master plan/schedule documents
- `POST /api/v1/transitions/{id}/teams-transcript` - attach a Teams transcript file to a transition

## KT Scheduler Bot

`app/kt_scheduler` is a separate bot package that follows the same patterns as
KT Tracker while staying loosely coupled. It reads a KT schedule from CSV/XLSX
today, generates Outlook-compatible iCalendar invitations, and sends them via
SMTP. Test mode and dry-run are enabled by default so the first run redirects
all invites to `appsupport@vwgds.in` and sends nothing unless explicitly
requested.

See `docs/KT_SCHEDULER.md` for configuration and run/test commands.

## Transition Workspace UI

A lightweight browser dashboard is served at `/` (`app/static/index.html`,
`app.js`, `styles.css`) backed by the `/api/v1/transitions*` endpoints and
`app/kt_tracker/transition_documents.py`. It lets you upload or select a
transition and browse its master plan, schedule, and availability tables in
one place, with pagination and summary tiles (topic count, session count,
capacity, approval status). `app/kt_tracker/transition_documents.py` currently
reads local `Transition_Docs` files as a stand-in for the KT Planner bot's
output - see `docs/KT_PLANNER_COMPATIBILITY.md` for the field-mapping contract
that keeps this additive and forward-compatible with the real KT Planner API.

## Automated Microsoft 365 KT lifecycle

The bot can run end-to-end without anyone manually creating or updating a KT
activity:

```
Outlook Calendar + Microsoft Teams
        -> Microsoft Graph API                (app/kt_tracker/graph_client.py)
        -> Identify meeting & lifecycle state  (app/kt_tracker/meeting_sync_service.py)
        -> Upsert KT activity, dedupe by iCalUId
        -> Retrieve attendance + transcript
        -> AI transcript analysis              (app/kt_tracker/transcript_analyzer.py)
        -> Compare against expected_topics
        -> Auto-update KT Activities backend
        -> Auto-create follow-up activities for missed/partial topics
```

**Key guarantee:** an activity is only marked `completed` when the transcript
and attendance analysis shows every `expected_topics` entry was actually
covered. A meeting whose scheduled end time has simply passed, with no
transcript/attendance evidence, is left untouched rather than auto-completed.

### Demo mode (no Entra ID/Graph access required)

Real Entra ID app registration and Graph admin consent can take time to
provision (see `docs/IT_ACCESS_REQUEST.md`). To demo the **entire** pipeline
end-to-end before that access exists, set:

```
KT_GRAPH_MODE=demo
```

This swaps in `app/kt_tracker/demo_graph_client.py` - an in-memory stand-in
implementing the exact same interface as the real `GraphClient` - seeded
with three realistic sample KT meetings (one fully covered, one partially
covered, one still upcoming) and matching Teams-style transcripts. Every
downstream step (dedupe/upsert, attendance parsing, transcript analysis,
topic comparison, status/readiness derivation, follow-up creation) runs
unmodified against this sample data, so the demo proves the real logic, not
a canned response.

Switching to a real tenant later is a **one-line change**: set
`KT_GRAPH_MODE=live` (or simply remove the variable, since `live` is the
default) once `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET`
are populated with real values. No application code changes are required.

### Required Azure AD app registration (application permissions, admin consent)

| Permission | Purpose |
|---|---|
| `Calendars.Read` | Read KT meetings on the configured mailbox(es) |
| `OnlineMeetings.Read.All` | Resolve the Teams online meeting object |
| `OnlineMeetingArtifact.Read.All` | Read attendance reports |
| `OnlineMeetingTranscript.Read.All` | Read meeting transcripts |

Additional tenant setup:

- Grant the app a Teams **application access policy** for each organizer mailbox:
  `New-CsApplicationAccessPolicy` + `Grant-CsApplicationAccessPolicy`
- Ensure the Teams meeting policy **allows transcription**, and that the
  meeting was actually transcribed (participant consent required) - if no
  transcript exists, the sync records `transcript_available: false` and
  leaves the activity's status untouched instead of guessing.

### Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `KT_GRAPH_MODE` | `demo` (sample data, no Graph access needed) or `live` (default, real Graph) |
| `AZURE_TENANT_ID` / `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` | Graph app-only credentials (only needed for `live`) |
| `KT_GRAPH_SYNC_ENABLED` | `true` to start the background scheduler |
| `KT_GRAPH_SYNC_INTERVAL_SECONDS` | Poll interval (default 900s) |
| `KT_GRAPH_MAILBOXES` | Comma-separated mailboxes/UPNs to scan (any placeholder value works in demo mode) |
| `KT_GRAPH_SUBJECT_KEYWORDS` | Subject keywords used to detect KT meetings |
| `KT_GRAPH_LOOKBACK_DAYS` / `KT_GRAPH_LOOKAHEAD_DAYS` | Calendar window to scan |

The sync is disabled by default; it stays a manual on-demand trigger
(`POST /api/v1/kt-tracker/meetings/sync`) until Graph credentials and
mailboxes are configured and `KT_GRAPH_SYNC_ENABLED=true` is set.

### Error handling, logging, and security

- Every Graph call is wrapped individually; a missing attendance report or
  transcript (403/404) degrades to "unavailable" instead of failing the
  whole sync, and per-meeting failures are isolated and collected in
  `MeetingSyncResult.errors` instead of aborting the run.
- 429 responses are retried with backoff; other transient network errors are
  retried up to `GRAPH_MAX_RETRIES` times.
- All Graph/meeting-sync activity is logged via the standard `logging` module
  (`kt_tracker.graph_client`, `kt_tracker.meeting_sync`, `kt_tracker.scheduler`).
- Only derived analysis (summary, topic classifications, counts) is
  persisted - the raw transcript text itself is not stored, to minimize
  retained personal/meeting content.
- Client credentials are read from environment variables / Key Vault-backed
  configuration only; least-privilege, read-only Graph permissions are used
  throughout.

### Topic-coverage analysis

`app/kt_tracker/transcript_analyzer.py` ships a deterministic keyword/heuristic
analyzer so the pipeline works without any external AI dependency:

- Requires multiple substantive sentences (not a single keyword hit) before
  marking a topic `covered`.
- Detects negated mentions ("we did not get to batch jobs", "ran out of
  time") so a topic that was merely *raised but skipped* is never counted as
  covered.
- Extracts unresolved questions and action items from the transcript.

Call `transcript_analyzer.set_llm_backend(fn)` to plug in a real LLM (for
example the internal LLMAAS endpoint already configured via the `LLMAAS_*`
environment variables) for higher-quality topic/question extraction without
changing any other code.

## Supported KT status values

- `not_started`
- `planned`
- `in_progress`
- `completed`
- `on_hold`
- `cancelled`
- `descoped`
- `overdue`

## Supported readiness values

- `not_assessed`
- `at_risk`
- `partially_ready`
- `ready`
- `accepted`

The tracker currently uses in-memory demo data so the bot can be developed and tested before Azure SQL and the KT Planner API are fully connected.