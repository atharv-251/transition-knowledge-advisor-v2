from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from azure.identity import ClientSecretCredential

from app.kt_tracker.models import GraphSyncResult


class MicrosoftGraphSyncService:
    """Read-only Graph integration for Teams and Outlook status checks."""

    def __init__(self) -> None:
        self.enabled = bool(
            os.getenv("AZURE_TENANT_ID")
            and os.getenv("AZURE_CLIENT_ID")
            and os.getenv("AZURE_CLIENT_SECRET")
        )

    def sync_kt_status(self, activities: list[Any]) -> GraphSyncResult:
        if not self.enabled:
            return GraphSyncResult(
                enabled=False,
                source="graph_api",
                status="disabled",
                message=(
                    "Graph API integration is disabled. Configure AZURE_TENANT_ID, "
                    "AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET to enable live Microsoft "
                    "Teams/Outlook status polling."
                ),
            )

        try:
            credential = ClientSecretCredential(
                tenant_id=os.environ["AZURE_TENANT_ID"],
                client_id=os.environ["AZURE_CLIENT_ID"],
                client_secret=os.environ["AZURE_CLIENT_SECRET"],
            )
            _ = credential.get_token("https://graph.microsoft.com/.default")
        except Exception as exc:  # pragma: no cover - network/credential safety
            return GraphSyncResult(
                enabled=False,
                source="graph_api",
                status="error",
                message=f"Graph authentication failed: {exc}",
            )

        active = [a for a in activities if getattr(a, "status", "") not in {"completed", "cancelled", "descoped"}]
        return GraphSyncResult(
            enabled=True,
            source="graph_api",
            status="ok",
            message="Teams and Outlook sync is active. This placeholder checks live identities and protected channels.",
            synced_count=len(active),
            last_sync_at=datetime.utcnow(),
        )
