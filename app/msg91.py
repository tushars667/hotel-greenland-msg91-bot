import json
import logging
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BotOutbound

logger = logging.getLogger(__name__)

MSG91_URL = "https://control.msg91.com/api/v5/whatsapp/whatsapp-outbound-message/"


class Msg91Error(RuntimeError):
    pass


class Msg91Client:
    def __init__(self) -> None:
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authkey": settings.msg91_authkey,
        }

    async def _send(self, db: Session, to: str, payload: dict[str, Any], kind: str) -> dict[str, Any]:
        marker = f"hotelbot:{uuid4().hex}"
        payload["crqid"] = marker

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(MSG91_URL, headers=self.headers, json=payload)

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        if response.status_code >= 400:
            raise Msg91Error(f"MSG91 {response.status_code}: {body}")

        # MSG91 responses can vary by endpoint/version, so capture common forms.
        request_id = (
            body.get("requestId")
            or body.get("request_id")
            or body.get("request-id")
            or body.get("id")
            or marker
        )
        request_id = str(request_id)

        db.merge(
            BotOutbound(
                request_id=request_id,
                customer_number=to,
                kind=kind,
                payload_json=json.dumps(payload, ensure_ascii=False),
            )
        )
        db.commit()
        return body

    async def send_text(self, db: Session, to: str, text: str) -> dict[str, Any]:
        return await self._send(
            db,
            to,
            {
                "recipient_number": to,
                "integrated_number": settings.msg91_integrated_number,
                "content_type": "text",
                "text": text,
            },
            "text",
        )

    async def send_menu(self, db: Session, to: str) -> dict[str, Any]:
        rows = [
            {"id": "deluxe_photos", "title": "Deluxe Room Photos", "description": "View Deluxe room gallery"},
            {"id": "super_deluxe_photos", "title": "Super Deluxe Photos", "description": "View Super Deluxe room gallery"},
            {"id": "property_location", "title": "Property Location", "description": "Address & directions"},
            {"id": "hourly_stays", "title": "Hourly Stays", "description": "Short stays from 2 hours"},
            {"id": "call_reception", "title": "Call Representative", "description": "Speak directly with reception"},
            {"id": "visit_website", "title": "Visit Website", "description": "Explore Hotel Green Land online"},
        ]
        return await self._send(
            db,
            to,
            {
                "recipient_number": to,
                "integrated_number": settings.msg91_integrated_number,
                "content_type": "interactive",
                "interactive": {
                    "type": "list",
                    "header": {"type": "text", "text": "EXPLORE"},
                    "body": {"text": "How may we assist you today?"},
                    "footer": {"text": "Hotel Green Land · Udaipur"},
                    "action": {
                        "button": "View Menu",
                        "sections": [{"title": "Explore", "rows": rows}],
                    },
                },
            },
            "menu",
        )

    async def send_hourly_buttons(self, db: Session, to: str) -> dict[str, Any]:
        return await self._send(
            db,
            to,
            {
                "recipient_number": to,
                "integrated_number": settings.msg91_integrated_number,
                "content_type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": "*HOURLY STAYS*\n\nChoose your room category."},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": "hourly_deluxe", "title": "Deluxe Room"}},
                            {"type": "reply", "reply": {"id": "hourly_super", "title": "Super Deluxe"}},
                            {"type": "reply", "reply": {"id": "main_menu", "title": "Main Menu"}},
                        ]
                    },
                },
            },
            "hourly_buttons",
        )

    async def send_image(self, db: Session, to: str, url: str, caption: str = "") -> dict[str, Any]:
        """Send an in-session WhatsApp image.

        MSG91 has exposed more than one accepted shape for the single-message endpoint
        over time. The current SDK/API family wraps ordinary WhatsApp messages inside
        `payload`, while interactive messages use the top-level interactive shape.
        Try the current wrapped form first, then two compatibility forms.
        """
        image = {"link": url}
        if caption:
            image["caption"] = caption

        variants = [
            {
                "integrated_number": settings.msg91_integrated_number,
                "content_type": "image",
                "payload": {
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "image",
                    "image": image,
                },
            },
            {
                "integrated_number": settings.msg91_integrated_number,
                "content_type": "image",
                "payload": {
                    "to": to,
                    "type": "image",
                    "image": image,
                },
            },
            {
                "recipient_number": to,
                "integrated_number": settings.msg91_integrated_number,
                "content_type": "image",
                "image": image,
            },
        ]

        errors: list[str] = []
        for index, payload in enumerate(variants, start=1):
            try:
                return await self._send(db, to, payload, "image")
            except Msg91Error as exc:
                errors.append(f"variant {index}: {exc}")
                logger.warning("MSG91 image payload variant %s rejected: %s", index, exc)

        # Do not dump ugly S3 links into the customer chat. Log the exact API errors
        # so we can lock the account-specific media shape if MSG91 rejects all forms.
        logger.error("All MSG91 image payload variants failed for %s: %s", to, " | ".join(errors))
        return await self.send_text(
            db,
            to,
            "Room photos are temporarily unavailable. Please try again shortly.",
        )


msg91 = Msg91Client()
