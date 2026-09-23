# KT Scheduler Bot

The KT Scheduler Bot is a separate, independent bot package under
`app/kt_scheduler`. It follows the same lightweight architecture used by
KT Tracker:

- `models.py` - Pydantic request/response/domain models
- `config.py` - environment-driven configuration; no credentials in code
- `input_sources.py` - modular KT plan input adapters (`CSV`, `XLSX`, future bot/API)
- `invite_generator.py` - iCalendar (`.ics`) generation
- `email_service.py` - SMTP delivery
- `state_store.py` - duplicate-invite prevention
- `service.py` - orchestration/business logic
- `governance.py` - Agentic Blueprint wrapper metadata for this bot
- `scripts/run_kt_scheduler.py` - local CLI runner

The current input file attached during development was a CSV export, not an
actual `.xlsx`; the bot supports both `.csv` and `.xlsx`/`.xlsm`.

## KT Planner drop-folder

For demos, place the latest KT Planner output here:

```text
data/kt_scheduler/input/KT_Schedule.csv
```

This path is controlled by:

```env
KT_SCHEDULER_DEFAULT_INPUT_PATH=data/kt_scheduler/input/KT_Schedule.csv
```

The API and CLI both use this default path when no explicit `input_path` is
provided. That gives the demo flow you wanted:

1. Receive/export a new KT schedule from KT Planner.
2. Replace `data/kt_scheduler/input/KT_Schedule.csv`.
3. Call `POST /api/v1/kt-scheduler/run`.
4. Scheduler reads the latest file and generates/sends invitations.

## Default recipient behavior

The scheduler now defaults to **recipients from the KT schedule file**:

- `dry_run=true` means no SMTP connection is made; invites are only generated
  and reported.
- `test_mode=false` means recipients come from the uploaded/default KT
  schedule file:
  - `Required Attendees`
  - `Optional Attendees`
- Set `test_mode=true` only when you explicitly want to redirect every invite
  to `KT_SCHEDULER_TEST_RECIPIENTS` (default `appsupport@vwgds.in`).

So, for the real demo, keep `test_mode=false`.

## Required local configuration

Use `.env` or Azure App Service application settings. Do not commit real
passwords/secrets.

```env
KT_SCHEDULER_TIMEZONE=Asia/Kolkata
KT_SCHEDULER_DEFAULT_INPUT_PATH=data/kt_scheduler/input/KT_Schedule.csv
KT_SCHEDULER_TEST_MODE=false
KT_SCHEDULER_DRY_RUN=true
KT_SCHEDULER_TEST_RECIPIENTS=appsupport@vwgds.in
KT_SCHEDULER_STATE_PATH=data/kt_scheduler/sent_invites.json

KT_SCHEDULER_SMTP_SERVER=mxiblk.relay.vw.vwg
KT_SCHEDULER_SMTP_PORT=25
KT_SCHEDULER_SENDER_EMAIL=vivek.chaurasia@vwgds.in
KT_SCHEDULER_ORGANIZER_NAME=Vivek Chaurasia
KT_SCHEDULER_SMTP_USERNAME=SX6MPPG
KT_SCHEDULER_SMTP_PASSWORD=<set locally or in Azure App Settings>
# The VW relay only advertises SMTP AUTH after STARTTLS is negotiated.
# If username/password are set, this must be true or sends fail with
# "SMTP AUTH extension not supported by server."
KT_SCHEDULER_SMTP_STARTTLS=true
KT_SCHEDULER_SMTP_TIMEOUT_SECONDS=30
```

If your platform team provides a real base64-encoded password, use
`KT_SCHEDULER_SMTP_PASSWORD_B64` instead of `KT_SCHEDULER_SMTP_PASSWORD`.
Do not put the password in source code, documentation, or Git.

## Local testing

From the repo root:

```powershell
.\.venv\Scripts\python.exe scripts\run_kt_scheduler.py
```

With no `--send`/`--dry-run` flag, the CLI defers entirely to
`KT_SCHEDULER_DRY_RUN` and `KT_SCHEDULER_TEST_MODE` from `.env` — it does
**not** force dry-run by itself. Expected result with the defaults above
(`KT_SCHEDULER_DRY_RUN=true`):

- `total_items=4`
- `valid_items=4`
- `dry_run=4`
- recipients shown from the uploaded KT file
- no SMTP email sent

To force a specific behavior for one run regardless of `.env`, pass an
explicit flag:

- `--dry-run` — force dry-run for this run only.
- `--send` — force a real SMTP send for this run only.

`--dry-run` and `--send` are mutually exclusive.

## Send to participants from the KT file

Set `KT_SCHEDULER_DRY_RUN=false` in `.env` (or pass `--send` explicitly),
then confirm SMTP configuration (server/port/STARTTLS/username/password) is
correct:

```powershell
.\.venv\Scripts\python.exe scripts\run_kt_scheduler.py --send
```

This sends to attendees from the KT file, not to `appsupport@vwgds.in`.

## Send to the test mailbox only

Use this only when you intentionally want to redirect all invites to
`appsupport@vwgds.in`:

```powershell
.\.venv\Scripts\python.exe scripts\run_kt_scheduler.py --send --test-mode
```


## Troubleshooting

**"Invite generated but not sent because dry-run is enabled" even though
`.env` has `KT_SCHEDULER_DRY_RUN=false`.**

- If you're calling the CLI, make sure you're on the current version:
  older versions always passed `dry_run=not args.send`, which forced
  dry-run unless `--send` was given, ignoring `.env` entirely. The CLI now
  only forces a value when you explicitly pass `--send` or `--dry-run`;
  with neither flag, it defers to `KT_SCHEDULER_DRY_RUN`.
- If you're calling the API, check the request body: an explicit
  `"dry_run": true` (or `"test_mode": true`) in the JSON payload always
  overrides `.env` for that call. Omit the field, or set it to `false`, to
  use the `.env` value.
- If you're running the FastAPI server as a long-lived process (locally or
  on Azure App Service), `.env`/App Settings changes only take effect after
  a **restart** — `load_dotenv()` runs once at process start.

**"SMTP AUTH extension not supported by server."**

- The VW relay (`mxiblk.relay.vw.vwg`) only advertises `AUTH` after
  STARTTLS is negotiated. If `KT_SCHEDULER_SMTP_USERNAME`/`PASSWORD` are
  set, also set `KT_SCHEDULER_SMTP_STARTTLS=true`.

**"Need to authenticate via SMTP-AUTH"**

- The relay is rejecting an anonymous/unauthenticated send. Set
  `KT_SCHEDULER_SMTP_USERNAME` and `KT_SCHEDULER_SMTP_PASSWORD`/
  `KT_SCHEDULER_SMTP_PASSWORD_B64`.

## Duplicate prevention

Each invite receives a deterministic UID based on the source row, title, start
time, and end time. Sent UIDs are stored in
`data/kt_scheduler/sent_invites.json`, which is ignored by Git. Re-running the
scheduler skips invites that were already sent unless `--force-resend` is
used.

## API endpoint

The existing FastAPI app also exposes:

```http
POST /api/v1/kt-scheduler/run
```

Example body:

```json
{
  "dry_run": true,
  "test_mode": false,
  "test_recipients": ["appsupport@vwgds.in"],
  "force_resend": false
}
```

`input_path` is optional. Omit it to use
`KT_SCHEDULER_DEFAULT_INPUT_PATH`. For real participant sends, use
`"test_mode": false`.
