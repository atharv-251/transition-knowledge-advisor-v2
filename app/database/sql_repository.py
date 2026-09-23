import json
import logging
from typing import Any

import pyodbc

from app.database.sql_connection import (
    database_connection,
)


logger = logging.getLogger(
    "transition_knowledge_advisor.database.repository"
)


class DuplicateDocumentError(RuntimeError):
    """
    Raised when identical document content is already indexed
    for the same project.
    """

    def __init__(
        self,
        project_id: str,
        content_hash: str,
        document_id: str = "",
        chunk_count: int = 0,
    ) -> None:
        super().__init__(
            "The identical document is already "
            "indexed for this project."
        )

        self.project_id = project_id
        self.content_hash = content_hash
        self.document_id = document_id
        self.chunk_count = chunk_count


class SqlKnowledgeRepository:
    """Store and retrieve transition knowledge records."""

    def get_or_create_project(
        self,
        *,
        project_name: str,
        project_type: str = "",
        technology: str = "",
        geography: str = "",
        transition_model: str = "",
        transition_stage: str = "",
    ) -> str:
        with database_connection() as connection:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    SELECT
                        project_id
                    FROM dbo.projects
                    WHERE project_name = ?
                    """,
                    project_name,
                )

                existing = cursor.fetchone()

                if existing:
                    return str(
                        existing.project_id
                    )

                cursor.execute(
                    """
                    INSERT INTO dbo.projects
                    (
                        project_name,
                        project_type,
                        technology,
                        geography,
                        transition_model,
                        transition_stage
                    )
                    OUTPUT inserted.project_id
                    VALUES
                    (
                        ?,
                        ?,
                        ?,
                        ?,
                        ?,
                        ?
                    )
                    """,
                    project_name,
                    project_type or None,
                    technology or None,
                    geography or None,
                    transition_model or None,
                    transition_stage or None,
                )

                project_id = str(
                    cursor.fetchone()[0]
                )

                connection.commit()

                return project_id

            finally:
                cursor.close()

    def get_document_by_content_hash(
        self,
        *,
        project_id: str,
        content_hash: str,
    ) -> dict[str, object] | None:
        """
        Return an existing document for a project and content hash.
        """

        if not content_hash.strip():
            return None

        with database_connection() as connection:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    SELECT TOP 1
                        d.document_id,
                        d.project_id,
                        d.original_file_name,
                        d.content_hash,
                        d.ingestion_status,
                        (
                            SELECT COUNT_BIG(1)
                            FROM dbo.knowledge_chunks AS c
                            WHERE c.document_id = d.document_id
                        ) AS chunk_count
                    FROM dbo.documents AS d
                    WHERE d.project_id = ?
                      AND d.content_hash = ?
                    ORDER BY d.created_at DESC
                    """,
                    project_id,
                    content_hash,
                )

                row = cursor.fetchone()

                if row is None:
                    return None

                return {
                    "document_id": str(
                        row.document_id
                        or ""
                    ),
                    "project_id": str(
                        row.project_id
                        or ""
                    ),
                    "original_file_name": str(
                        row.original_file_name
                        or ""
                    ),
                    "content_hash": str(
                        row.content_hash
                        or ""
                    ),
                    "ingestion_status": str(
                        row.ingestion_status
                        or "completed"
                    ),
                    "chunk_count": int(
                        row.chunk_count
                        or 0
                    ),
                }

            finally:
                cursor.close()

    @staticmethod
    def _is_duplicate_document_error(
        error: pyodbc.IntegrityError,
    ) -> bool:
        """
        Identify the unique-index violation used for duplicate files.
        """

        error_text = str(error)

        return (
            "2601" in error_text
            or "2627" in error_text
            or (
                "ux_documents_project_content_hash"
                in error_text
            )
        )

    def _raise_duplicate_document_error(
        self,
        *,
        project_id: str,
        content_hash: str,
        original_error: Exception | None = None,
    ) -> None:
        """
        Retrieve the existing record and raise a domain exception.
        """

        existing_document = (
            self.get_document_by_content_hash(
                project_id=project_id,
                content_hash=content_hash,
            )
        )

        if existing_document is None:
            if original_error is not None:
                raise original_error

            raise RuntimeError(
                "A duplicate document was detected, but the "
                "existing document could not be retrieved."
            )

        logger.info(
            "Duplicate document detected. "
            "project_id=%s document_id=%s "
            "content_hash_prefix=%s",
            project_id,
            existing_document[
                "document_id"
            ],
            content_hash[:12],
        )

        duplicate_error = DuplicateDocumentError(
            project_id=project_id,
            content_hash=content_hash,
            document_id=str(
                existing_document[
                    "document_id"
                ]
            ),
            chunk_count=int(
                existing_document[
                    "chunk_count"
                ]
                or 0
            ),
        )

        if original_error is not None:
            raise duplicate_error from original_error

        raise duplicate_error

    def create_document(
        self,
        *,
        project_id: str,
        title: str,
        document_type: str,
        source_uri: str,
        knowledge_domain: str,
        artifact_type: str,
        original_file_name: str = "",
        storage_type: str = "",
        storage_path: str = "",
        file_size_bytes: int = 0,
        mime_type: str = "",
        content_hash: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a document record.

        Raise DuplicateDocumentError when the same content is already
        indexed for the same project.
        """

        normalized_content_hash = (
            content_hash.strip()
        )

        if normalized_content_hash:
            existing_document = (
                self.get_document_by_content_hash(
                    project_id=project_id,
                    content_hash=(
                        normalized_content_hash
                    ),
                )
            )

            if existing_document is not None:
                logger.info(
                    "Duplicate document detected before insert. "
                    "project_id=%s document_id=%s "
                    "content_hash_prefix=%s",
                    project_id,
                    existing_document[
                        "document_id"
                    ],
                    normalized_content_hash[:12],
                )

                raise DuplicateDocumentError(
                    project_id=project_id,
                    content_hash=(
                        normalized_content_hash
                    ),
                    document_id=str(
                        existing_document[
                            "document_id"
                        ]
                    ),
                    chunk_count=int(
                        existing_document[
                            "chunk_count"
                        ]
                        or 0
                    ),
                )

        try:
            with database_connection() as connection:
                cursor = connection.cursor()

                try:
                    cursor.execute(
                        """
                        INSERT INTO dbo.documents
                        (
                            project_id,
                            title,
                            document_type,
                            source_uri,
                            knowledge_domain,
                            artifact_type,
                            ingestion_status,
                            original_file_name,
                            storage_type,
                            storage_path,
                            file_size_bytes,
                            mime_type,
                            content_hash,
                            metadata_json
                        )
                        OUTPUT inserted.document_id
                        VALUES
                        (
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            N'processing',
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?,
                            ?
                        )
                        """,
                        project_id,
                        title,
                        document_type or None,
                        source_uri or None,
                        knowledge_domain,
                        artifact_type or None,
                        original_file_name or None,
                        storage_type or None,
                        storage_path or None,
                        file_size_bytes or None,
                        mime_type or None,
                        normalized_content_hash or None,
                        json.dumps(
                            metadata or {},
                            ensure_ascii=False,
                        ),
                    )

                    document_id = str(
                        cursor.fetchone()[0]
                    )

                    connection.commit()

                    return document_id

                except pyodbc.IntegrityError:
                    connection.rollback()
                    raise

                finally:
                    cursor.close()

        except pyodbc.IntegrityError as error:
            if (
                normalized_content_hash
                and self._is_duplicate_document_error(
                    error
                )
            ):
                self._raise_duplicate_document_error(
                    project_id=project_id,
                    content_hash=(
                        normalized_content_hash
                    ),
                    original_error=error,
                )

            raise

    def insert_chunks(
        self,
        chunks: list[dict[str, Any]],
    ) -> int:
        if not chunks:
            return 0

        sql = """
            INSERT INTO dbo.knowledge_chunks
            (
                document_id,
                project_id,
                chunk_number,
                section,
                content,
                content_hash,
                metadata_json,
                pii_sanitized
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
        """

        rows = [
            (
                chunk["document_id"],
                chunk["project_id"],
                int(chunk["chunk_number"]),
                chunk.get("section") or None,
                chunk["content"],
                chunk.get("content_hash") or None,
                json.dumps(
                    chunk.get(
                        "metadata",
                        {},
                    ),
                    ensure_ascii=False,
                ),
                1
                if chunk.get(
                    "pii_sanitized",
                    True,
                )
                else 0,
            )
            for chunk in chunks
        ]

        with database_connection() as connection:
            cursor = connection.cursor()
            cursor.fast_executemany = True

            try:
                cursor.executemany(
                    sql,
                    rows,
                )

                connection.commit()

            finally:
                cursor.close()

        return len(rows)

    def complete_document(
        self,
        document_id: str,
    ) -> None:
        with database_connection() as connection:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    UPDATE dbo.documents
                    SET
                        ingestion_status = N'completed',
                        updated_at = SYSUTCDATETIME()
                    WHERE document_id = ?
                    """,
                    document_id,
                )

                connection.commit()

            finally:
                cursor.close()

    def fail_document(
        self,
        document_id: str,
        error_message: str,
    ) -> None:
        with database_connection() as connection:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    UPDATE dbo.documents
                    SET
                        ingestion_status = N'failed',
                        updated_at = SYSUTCDATETIME(),
                        metadata_json = JSON_MODIFY(
                            metadata_json,
                            '$.ingestion_error',
                            ?
                        )
                    WHERE document_id = ?
                    """,
                    error_message[:1000],
                    document_id,
                )

                connection.commit()

            finally:
                cursor.close()
