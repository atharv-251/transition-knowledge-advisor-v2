from typing import Any

from pydantic import (
    BaseModel,
    Field,
)


class ProjectContext(BaseModel):
    project_name: str = ""
    project_type: str = ""
    technology: str = ""
    geography: str = ""
    team_size: int = 0
    transition_model: str = ""
    transition_stage: str = ""


class ConversationMessage(BaseModel):
    role: str
    content: str


class AgentInvokeRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=4000,
    )

    conversation_id: str | None = None
    user_id: str | None = None

    project_context: ProjectContext = Field(
        default_factory=ProjectContext
    )

    conversation_messages: list[
        ConversationMessage
    ] = Field(
        default_factory=list
    )


class SourceRecord(BaseModel):
    source_id: str
    source_agent: str
    document_id: str = ""
    title: str
    section: str = ""
    source_uri: str = ""
    knowledge_domain: str = ""


class AgentInvokeResponse(BaseModel):
    agent_id: str
    specialist: str
    answer: str
    sources: list[SourceRecord]
    suggested_questions: list[str]
    conversation_id: str
    status: str = "completed"


class SearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=4000,
    )

    domains: list[str] = Field(
        default_factory=list
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class SearchResult(BaseModel):
    document_id: str
    project_id: str
    project_name: str
    title: str
    section: str = ""
    content: str
    source_uri: str = ""
    knowledge_domain: str
    artifact_type: str = ""
    score: float = 0


class SearchResponse(BaseModel):
    agent_id: str
    results: list[SearchResult]
    result_count: int


class DocumentUploadResponse(BaseModel):
    project_id: str
    document_id: str
    file_name: str
    chunk_count: int
    ingestion_status: str


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class CapabilitiesResponse(BaseModel):
    agent_id: str
    name: str
    description: str
    supported_intents: list[str]
    supported_domains: list[str]
    supported_file_types: list[str]
    endpoints: dict[str, str]