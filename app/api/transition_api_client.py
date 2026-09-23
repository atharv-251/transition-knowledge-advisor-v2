import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


load_dotenv()


class TransitionApiError(RuntimeError):
    """
    Raised when a Transition Advisor API request fails.
    """


def get_api_base_url() -> str:
    """
    Return the configured Transition Advisor API base URL.
    """

    base_url = os.getenv(
        "TRANSITION_ADVISOR_API_URL",
        "",
    ).strip()

    if not base_url:
        raise TransitionApiError(
            "TRANSITION_ADVISOR_API_URL "
            "is not configured."
        )

    return base_url.rstrip("/")


def get_api_timeout() -> float:
    """
    Return the configured API timeout in seconds.
    """

    try:
        return float(
            os.getenv(
                "TRANSITION_ADVISOR_API_TIMEOUT",
                "300",
            )
        )

    except ValueError:
        return 300.0


def response_json(
    response: httpx.Response,
) -> dict[str, Any]:
    """
    Validate and return a JSON API response.
    """

    try:
        result = response.json()

    except ValueError as error:
        raise TransitionApiError(
            "The API returned a non-JSON response. "
            f"HTTP {response.status_code}: "
            f"{response.text[:500]}"
        ) from error

    if not response.is_success:
        if isinstance(
            result,
            dict,
        ):
            detail = result.get(
                "detail",
                "The API request failed.",
            )

        else:
            detail = (
                "The API request failed."
            )

        if isinstance(
            detail,
            list,
        ):
            detail_message = "; ".join(
                str(item)
                for item in detail
            )

        else:
            detail_message = str(
                detail
            )

        raise TransitionApiError(
            f"HTTP {response.status_code}: "
            f"{detail_message}"
        )

    if not isinstance(
        result,
        dict,
    ):
        raise TransitionApiError(
            "The API returned an invalid "
            "response structure."
        )

    return result


def check_api_readiness() -> dict[str, Any]:
    """
    Check the deployed API, graph, retriever, and database.
    """

    try:
        response = httpx.get(
            (
                f"{get_api_base_url()}"
                "/api/v1/ready"
            ),
            headers={
                "Accept": (
                    "application/json"
                ),
            },
            timeout=get_api_timeout(),
        )

        return response_json(
            response
        )

    except httpx.TimeoutException as error:
        raise TransitionApiError(
            "The API readiness check exceeded "
            "the configured timeout."
        ) from error

    except httpx.RequestError as error:
        raise TransitionApiError(
            "Could not connect to the "
            "Transition Advisor API. "
            f"{error}"
        ) from error


def invoke_transition_agent(
    *,
    question: str,
    conversation_id: str,
    user_id: str,
    project_context: dict[str, Any],
    conversation_messages: list[
        dict[str, str]
    ],
) -> dict[str, Any]:
    """
    Call POST /api/v1/agent/invoke.
    """

    normalized_question = (
        question.strip()
    )

    if not normalized_question:
        raise TransitionApiError(
            "The question cannot be empty."
        )

    payload = {
        "question": (
            normalized_question
        ),
        "conversation_id": (
            conversation_id
        ),
        "user_id": user_id,
        "project_context": (
            project_context
            or {}
        ),
        "conversation_messages": (
            conversation_messages[-20:]
        ),
    }

    try:
        response = httpx.post(
            (
                f"{get_api_base_url()}"
                "/api/v1/agent/invoke"
            ),
            json=payload,
            headers={
                "Accept": (
                    "application/json"
                ),
                "Content-Type": (
                    "application/json"
                ),
            },
            timeout=get_api_timeout(),
        )

        return response_json(
            response
        )

    except httpx.TimeoutException as error:
        raise TransitionApiError(
            "The agent request exceeded "
            "the configured timeout."
        ) from error

    except httpx.RequestError as error:
        raise TransitionApiError(
            "Could not call the Transition "
            "Advisor API. "
            f"{error}"
        ) from error


def extract_and_index_kt_profile(
    *,
    files: list[
        tuple[
            str,
            bytes,
            str,
        ]
    ],
    project_name: str = "",
    knowledge_domain: str = (
        "historical_transitions"
    ),
    artifact_type: str = (
        "knowledge_document"
    ),
) -> dict[str, Any]:
    """
    Upload multiple project documents, extract a KT profile,
    and index every document into the Knowledgebase.

    Each file item must have this structure:

    (
        file_name,
        file_bytes,
        content_type,
    )
    """

    if not files:
        raise TransitionApiError(
            "At least one project document "
            "must be supplied."
        )

    multipart_files: list[
        tuple[
            str,
            tuple[
                str,
                bytes,
                str,
            ],
        ]
    ] = []

    for file_record in files:
        if (
            not isinstance(
                file_record,
                tuple,
            )
            or len(file_record) != 3
        ):
            raise TransitionApiError(
                "Every file entry must contain "
                "file_name, file_bytes, and "
                "content_type."
            )

        (
            file_name,
            file_bytes,
            content_type,
        ) = file_record

        safe_file_name = Path(
            str(
                file_name
                or ""
            )
        ).name.strip()

        if not safe_file_name:
            raise TransitionApiError(
                "Every uploaded document "
                "requires a file name."
            )

        if not isinstance(
            file_bytes,
            bytes,
        ):
            raise TransitionApiError(
                "File content must be supplied "
                "as bytes for "
                f"{safe_file_name}."
            )

        if not file_bytes:
            raise TransitionApiError(
                "The uploaded document is empty: "
                f"{safe_file_name}."
            )

        resolved_content_type = str(
            content_type
            or mimetypes.guess_type(
                safe_file_name
            )[0]
            or (
                "application/"
                "octet-stream"
            )
        )

        multipart_files.append(
            (
                "files",
                (
                    safe_file_name,
                    file_bytes,
                    resolved_content_type,
                ),
            )
        )

    normalized_domain = (
        knowledge_domain
        .strip()
        .lower()
    )

    normalized_artifact_type = (
        artifact_type
        .strip()
        .lower()
    )

    if not normalized_domain:
        normalized_domain = (
            "historical_transitions"
        )

    if not normalized_artifact_type:
        normalized_artifact_type = (
            "knowledge_document"
        )

    form_data = {
        "project_name": (
            project_name.strip()
        ),
        "knowledge_domain": (
            normalized_domain
        ),
        "artifact_type": (
            normalized_artifact_type
        ),
    }

    try:
        with httpx.Client(
            timeout=get_api_timeout(),
        ) as client:
            response = client.post(
                (
                    f"{get_api_base_url()}"
                    "/api/v1/knowledge/"
                    "kt-profile/extract"
                ),
                headers={
                    "Accept": (
                        "application/json"
                    ),
                },
                data=form_data,
                files=multipart_files,
            )

        return response_json(
            response
        )

    except httpx.TimeoutException as error:
        raise TransitionApiError(
            "KT profile extraction and "
            "document indexing exceeded "
            "the configured timeout."
        ) from error

    except httpx.RequestError as error:
        raise TransitionApiError(
            "Could not extract the KT profile "
            "or index the project documents. "
            f"{error}"
        ) from error