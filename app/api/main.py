import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Body, FastAPI, HTTPException, Path, Query, status

from app.database.sql_connection import database_connection
from app.kt_scheduler.models import ScheduleRunRequest, ScheduleRunResult
from app.kt_scheduler.service import run_scheduler as run_kt_scheduler
from app.kt_tracker.models import (
    ActivityUpdateRequest,
    CapabilitiesResponse,
    DeleteActivityResponse,
    GraphSyncResult,
    HealthResponse,
    KtActivity,
    KtActivityCreateRequest,
    KtMeeting,
    KtPlanImportRequest,
    KtPlanImportResponse,
    KtSummaryResponse,
    MeetingAnalysisResult,
    MeetingSyncResult,
)
from app.kt_tracker.meeting_sync_service import ANALYSIS_STORE, MEETING_STORE, sync_all
from app.kt_tracker.scheduler import scheduler
from app.kt_tracker.service import (
    create_activity,
    delete_activity,
    detect_overdue_activities,
    generate_status_summary,
    get_activity,
    get_all_activities,
    import_kt_plan,
    sync_with_graph,
    update_activity,
)

logger = logging.getLogger("kt_tracker.api")
AGENT_ID = "kt-tracker-bot"
AGENT_VERSION = "0.1.0"
API_BUILD = "kt-tracker-bot-2026-09-17"

TAGS_METADATA = [
    {
        "name": "Service",
        "description": (
            "Operational endpoints for checking whether the KT Tracker Bot "
            "is running and whether required dependencies are reachable."
        ),
    },
    {
        "name": "Capabilities",
        "description": (
            "Capability-card endpoint for users and future Agentic Mesh "
            "orchestrators."
        ),
    },
    {
        "name": "KT Plans",
        "description": (
            "Import an approved KT plan. Today this accepts dummy/demo "
            "payloads; later the same contract can receive data from the KT Planner API."
        ),
    },
    {
        "name": "KT Activities",
        "description": (
            "Create, read, update, and delete trackable KT activities."
        ),
    },
    {
        "name": "KT Reporting",
        "description": (
            "Calculate progress, identify overdue activities, track blockers "
            "and risks, and calculate readiness."
        ),
    },
    {
        "name": "Microsoft Graph",
        "description": (
            "Automated Outlook/Teams integration: discovers KT meetings, "
            "retrieves attendance and transcripts, runs AI topic-coverage "
            "analysis, and automatically updates KT Activities so no one "
            "has to manually mark a KT session complete."
        ),
    },
    {
        "name": "KT Scheduler",
        "description": (
            "Schedules KT sessions from a modular plan input source. The "
            "current source is CSV/XLSX, and invitations are sent through "
            "SMTP as Outlook-compatible iCalendar (.ics) requests."
        ),
    },
]


def check_database_readiness() -> None:
    """Verify that the configured SQL database is reachable."""
    with database_connection() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            if row is None or int(row[0]) != 1:
                raise RuntimeError("Azure SQL returned an unexpected readiness result.")
        finally:
            cursor.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting KT Tracker API. build=%s", API_BUILD)
    scheduler.start()
    yield
    await scheduler.stop()
    logger.info("KT Tracker API shutting down.")


app = FastAPI(
    title="KT Tracker Bot API",
    summary="Governed API for tracking Knowledge Transfer plans and activities.",
    description=(
        "The KT Tracker Bot imports approved KT plans, creates trackable KT "
        "activities, updates status, calculates progress and readiness, "
        "detects overdue activities, tracks blockers/risks, and exposes a "
        "Microsoft Graph integration surface for future Teams and Outlook "
        "status polling.\n\n"
        "Current mode: demo/in-memory KT data. Future mode: KT Planner API "
        "as source plus Azure SQL persistence."
    ),
    version=AGENT_VERSION,
    contact={
        "name": "KT Tracker Bot Team",
    },
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    swagger_ui_parameters={
        "tryItOutEnabled": True,
        "displayRequestDuration": True,
        "defaultModelsExpandDepth": 2,
        "defaultModelExpandDepth": 3,
        "docExpansion": "none",
        "filter": True,
        "persistAuthorization": True,
    },
)


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["Service"],
    summary="Check API health",
    description=(
        "Returns a lightweight health response. This endpoint does not check "
        "Azure SQL or Microsoft Graph."
    ),
)
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service=AGENT_ID,
        version=AGENT_VERSION,
    )


@app.get(
    "/api/v1/ready",
    response_model=HealthResponse,
    tags=["Service"],
    summary="Check API and database readiness",
    description=(
        "Checks whether the API is ready and the configured SQL database can "
        "be reached. This may fail locally until Azure SQL or local SQL "
        "configuration is completed."
    ),
    responses={
        503: {
            "description": "Database dependency is not reachable.",
        }
    },
)
async def readiness() -> HealthResponse:
    try:
        await asyncio.to_thread(check_database_readiness)
    except Exception as error:
        logger.exception("Database readiness failed. error=%s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The database is not ready.",
        ) from error

    return HealthResponse(
        status="ready",
        service=AGENT_ID,
        version=AGENT_VERSION,
    )


@app.get(
    "/api/v1/capabilities",
    response_model=CapabilitiesResponse,
    tags=["Capabilities"],
    summary="Get KT Tracker Bot capability card",
    description=(
        "Returns the bot capability card so a user, portal, or future mesh "
        "orchestrator can discover supported functions and endpoints."
    ),
)
async def capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        agent_id=AGENT_ID,
        name="KT Tracker Bot",
        description=(
            "Tracks KT activities, readiness, blockers, risks, and overdue "
            "actions for transition plans."
        ),
        supported_intents=[
            "plan_import",
            "activity_tracking",
            "status_summary",
            "readiness",
            "overdue_detect",
            "meeting_auto_sync",
            "transcript_analysis",
            "meeting_invite_scheduling",
        ],
        supported_domains=[
            "kt_plan",
            "kt_activity",
            "teams",
            "outlook",
            "smtp",
            "calendar_invites",
        ],
        supported_file_types=["json", "csv", "xlsx", "xlsm"],
        endpoints={
            "plan_import": "/api/v1/kt-tracker/plan/import",
            "activities": "/api/v1/kt-tracker/activities",
            "summary": "/api/v1/kt-tracker/summary",
            "overdue": "/api/v1/kt-tracker/overdue",
            "sync_graph": "/api/v1/kt-tracker/sync-graph",
            "meetings_sync": "/api/v1/kt-tracker/meetings/sync",
            "meetings": "/api/v1/kt-tracker/meetings",
            "activity_analysis": "/api/v1/kt-tracker/activities/{activity_id}/analysis",
            "scheduler_run": "/api/v1/kt-scheduler/run",
        },
    )


@app.post(
    "/api/v1/kt-scheduler/run",
    response_model=ScheduleRunResult,
    tags=["KT Scheduler"],
    summary="Run the KT Scheduler Bot",
    description=(
        "Parses a CSV/XLSX KT plan, generates Outlook-compatible .ics "
        "meeting invitations, and sends them through SMTP. By default the "
        "scheduler should be used in dry-run/test mode first so invites are "
        "previewed or redirected to a test mailbox instead of all plan "
        "participants."
    ),
)
async def run_scheduler_endpoint(
    payload: Annotated[
        ScheduleRunRequest,
        Body(description="Scheduler input file and safe-mode overrides."),
    ],
) -> ScheduleRunResult:
    try:
        return await asyncio.to_thread(
            run_kt_scheduler,
            payload.input_path,
            dry_run=payload.dry_run,
            test_mode=payload.test_mode,
            test_recipients=[
                str(recipient)
                for recipient in (payload.test_recipients or [])
            ] or None,
            force_resend=payload.force_resend,
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@app.post(
    "/api/v1/kt-tracker/plan/import",
    response_model=KtPlanImportResponse,
    tags=["KT Plans"],
    status_code=status.HTTP_201_CREATED,
    summary="Import an approved KT plan",
    description=(
        "Imports or replaces a KT plan and creates the plan's trackable "
        "activities. For now this accepts demo payloads. Later the KT Planner "
        "Bot/API can call this endpoint with the same contract."
    ),
)
async def import_tracker_plan(
    payload: Annotated[
        KtPlanImportRequest,
        Body(
            description="KT plan payload received from KT Planner or demo data.",
        ),
    ],
) -> KtPlanImportResponse:
    plan = import_kt_plan(payload)
    return KtPlanImportResponse(
        plan_id=plan.plan_id,
        project_name=plan.project_name,
        knowledge_domain=plan.knowledge_domain,
        activities=plan.activities,
    )


@app.post(
    "/api/v1/kt-tracker/activities",
    response_model=KtActivity,
    tags=["KT Activities"],
    status_code=status.HTTP_201_CREATED,
    summary="Create a KT activity",
    description=(
        "Creates one trackable KT activity under an existing KT plan."
    ),
    responses={
        404: {
            "description": "KT plan was not found.",
        }
    },
)
async def create_tracker_activity(
    plan_id: Annotated[
        str,
        Query(
            min_length=1,
            description="Parent KT plan ID.",
            examples=["kt-plan-demo-001"],
        ),
    ],
    payload: Annotated[
        KtActivityCreateRequest,
        Body(description="Activity details to create."),
    ],
) -> KtActivity:
    try:
        return create_activity(plan_id, payload)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@app.get(
    "/api/v1/kt-tracker/activities",
    response_model=list[KtActivity],
    tags=["KT Activities"],
    summary="List KT activities",
    description=(
        "Returns all KT activities, or only activities belonging to the "
        "specified plan."
    ),
)
async def list_tracker_activities(
    plan_id: Annotated[
        str | None,
        Query(
            description="Optional plan ID filter.",
            examples=["kt-plan-demo-001"],
        ),
    ] = None,
) -> list[KtActivity]:
    return get_all_activities(plan_id)


@app.get(
    "/api/v1/kt-tracker/activities/{activity_id}",
    response_model=KtActivity,
    tags=["KT Activities"],
    summary="Get a KT activity by ID",
    description="Returns one activity by its tracker activity ID.",
    responses={
        404: {
            "description": "KT activity was not found.",
        }
    },
)
async def get_tracker_activity(
    activity_id: Annotated[
        str,
        Path(
            min_length=1,
            description="KT activity ID.",
            examples=["act-1002"],
        ),
    ],
) -> KtActivity:
    activity = get_activity(activity_id)
    if activity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KT activity not found.",
        )
    return activity


@app.put(
    "/api/v1/kt-tracker/activities/{activity_id}",
    response_model=KtActivity,
    tags=["KT Activities"],
    summary="Update KT activity status and tracking fields",
    description=(
        "Updates activity status, progress, due date, readiness, blocker, "
        "risk, and notes. Submit only the fields that need to change."
    ),
    responses={
        404: {
            "description": "KT activity was not found.",
        }
    },
)
async def update_tracker_activity(
    activity_id: Annotated[
        str,
        Path(
            min_length=1,
            description="KT activity ID.",
            examples=["act-1002"],
        ),
    ],
    payload: Annotated[
        ActivityUpdateRequest,
        Body(description="Partial activity update payload."),
    ],
) -> KtActivity:
    try:
        return update_activity(activity_id, payload)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@app.delete(
    "/api/v1/kt-tracker/activities/{activity_id}",
    response_model=DeleteActivityResponse,
    tags=["KT Activities"],
    summary="Delete a KT activity",
    description=(
        "Deletes one KT activity from the tracker. Future Azure SQL storage "
        "may convert this to a soft delete if audit requirements need it."
    ),
    responses={
        404: {
            "description": "KT activity was not found.",
        }
    },
)
async def delete_tracker_activity(
    activity_id: Annotated[
        str,
        Path(
            min_length=1,
            description="KT activity ID.",
            examples=["act-1002"],
        ),
    ],
) -> DeleteActivityResponse:
    deleted = delete_activity(activity_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KT activity not found.",
        )
    return DeleteActivityResponse(
        deleted=True,
        activity_id=activity_id,
    )


@app.get(
    "/api/v1/kt-tracker/summary",
    response_model=KtSummaryResponse,
    tags=["KT Reporting"],
    summary="Generate KT status summary",
    description=(
        "Calculates plan progress, overdue count, blocker count, risk count, "
        "and readiness. If no plan_id is supplied, the demo service uses the "
        "first available plan."
    ),
    responses={
        404: {
            "description": "KT plan was not found.",
        }
    },
)
async def kt_tracker_summary(
    plan_id: Annotated[
        str | None,
        Query(
            description="Optional KT plan ID.",
            examples=["kt-plan-demo-001"],
        ),
    ] = None,
) -> KtSummaryResponse:
    try:
        return generate_status_summary(plan_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error


@app.get(
    "/api/v1/kt-tracker/overdue",
    response_model=list[KtActivity],
    tags=["KT Reporting"],
    summary="List overdue KT activities",
    description=(
        "Returns activities with a due date earlier than today and a status "
        "that is not completed, cancelled, or descoped."
    ),
)
async def kt_tracker_overdue(
    plan_id: Annotated[
        str | None,
        Query(
            description="Optional KT plan ID.",
            examples=["kt-plan-demo-001"],
        ),
    ] = None,
) -> list[KtActivity]:
    return detect_overdue_activities(plan_id)


@app.post(
    "/api/v1/kt-tracker/sync-graph",
    response_model=GraphSyncResult,
    tags=["Microsoft Graph"],
    summary="Check Teams and Outlook sync readiness",
    description=(
        "Checks whether Microsoft Graph credentials are configured and returns "
        "the current Graph sync status. This is the placeholder integration "
        "surface for future automatic Teams and Outlook status polling."
    ),
)
async def kt_tracker_sync_graph(
    plan_id: Annotated[
        str | None,
        Query(
            description="Optional KT plan ID to scope the Graph sync.",
            examples=["kt-plan-demo-001"],
        ),
    ] = None,
) -> GraphSyncResult:
    return sync_with_graph(plan_id)


@app.post(
    "/api/v1/kt-tracker/meetings/sync",
    response_model=MeetingSyncResult,
    tags=["Microsoft Graph"],
    summary="Run the automated Outlook/Teams KT meeting sync",
    description=(
        "Reads the configured mailbox's Outlook calendar, identifies KT "
        "meetings, upserts the matching KT activity (deduped by Outlook "
        "iCalUId so reschedules never create duplicates), and for any "
        "meeting that has completed, retrieves Teams attendance and the "
        "meeting transcript, runs AI topic-coverage analysis against the "
        "activity's expected_topics, and automatically updates the KT "
        "Activity - status is only set to 'completed' when the analysis "
        "shows every expected topic was actually covered. This is the same "
        "logic the background scheduler runs automatically; use this "
        "endpoint to trigger it on demand or to test with a specific "
        "mailbox."
    ),
)
async def kt_tracker_meetings_sync(
    mailbox: Annotated[
        str,
        Query(
            min_length=3,
            description="Mailbox/UPN whose Outlook calendar and Teams meetings should be scanned.",
            examples=["kt-office@contoso.com"],
        ),
    ],
    plan_id: Annotated[
        str | None,
        Query(
            description="KT plan to attach newly discovered meetings to. Defaults to the first available plan.",
            examples=["kt-plan-demo-001"],
        ),
    ] = None,
) -> MeetingSyncResult:
    return await asyncio.to_thread(sync_all, mailbox, plan_id)


@app.get(
    "/api/v1/kt-tracker/meetings",
    response_model=list[KtMeeting],
    tags=["Microsoft Graph"],
    summary="List KT meetings discovered from Outlook/Teams",
    description=(
        "Returns the meetings discovered by the most recent sync run, "
        "including their lifecycle status (scheduled/ongoing/completed/"
        "cancelled/rescheduled) and the KT activity each one is linked to."
    ),
)
async def kt_tracker_list_meetings() -> list[KtMeeting]:
    return list(MEETING_STORE.values())


@app.get(
    "/api/v1/kt-tracker/activities/{activity_id}/analysis",
    response_model=MeetingAnalysisResult,
    tags=["Microsoft Graph"],
    summary="Get the transcript/attendance analysis behind an activity's status",
    description=(
        "Returns the full AI transcript analysis (participants, topics "
        "covered/partially covered/missed, questions raised/unresolved, "
        "action items, follow-up topics, transcript summary, and confidence "
        "score) that produced the activity's current status. Use this to "
        "audit why an activity was or was not marked completed."
    ),
    responses={
        404: {
            "description": "No meeting analysis has been recorded for this activity yet.",
        }
    },
)
async def kt_tracker_activity_analysis(
    activity_id: Annotated[
        str,
        Path(
            min_length=1,
            description="KT activity ID.",
            examples=["act-1002"],
        ),
    ],
) -> MeetingAnalysisResult:
    analysis = ANALYSIS_STORE.get(activity_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No meeting analysis recorded for this activity yet.",
        )
    return analysis
