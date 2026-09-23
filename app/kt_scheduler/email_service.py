from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.kt_scheduler.config import SmtpConfig
from app.kt_scheduler.models import KtScheduleItem

logger = logging.getLogger("kt_scheduler.email_service")


class SmtpInviteService:
    """Sends Outlook-compatible meeting invites with an ICS attachment."""

    def __init__(self, config: SmtpConfig) -> None:
        self.config = config

    def send_invite(
        self,
        item: KtScheduleItem,
        recipients: list[str],
        ics_content: str,
        dry_run: bool,
    ) -> None:
        if dry_run:
            logger.info(
                "DRY RUN: would send invite %r to %s",
                item.session_title,
                recipients,
            )
            return

        message = EmailMessage()
        message["From"] = self.config.sender_email
        message["To"] = ", ".join(recipients)
        message["Subject"] = item.session_title
        message["Content-Class"] = "urn:content-classes:calendarmessage"
        message.set_content(_plain_body(item))
        message.add_alternative(ics_content, subtype="calendar", params={
            "method": "REQUEST",
            "name": "invite.ics",
        })
        message.add_attachment(
            ics_content.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename="invite.ics",
            params={"method": "REQUEST"},
        )

        with smtplib.SMTP(
            self.config.server,
            self.config.port,
            timeout=self.config.timeout_seconds,
        ) as smtp:
            if self.config.use_starttls:
                smtp.starttls()
            if self.config.username and self.config.password:
                smtp.login(self.config.username, self.config.password)
            smtp.send_message(message)

        logger.info("Sent invite %r to %s", item.session_title, recipients)


def _plain_body(item: KtScheduleItem) -> str:
    return "\n".join([
        item.session_title,
        "",
        f"Start: {item.start_at}",
        f"End: {item.end_at}",
        f"Delivery mode: {item.delivery_mode}",
        "",
        item.description,
    ])

