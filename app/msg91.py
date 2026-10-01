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
                    "body": {
                        "text": (
                            "How may we assist you today?\n\n"
                            "Nearby landmarks\n"
                            "City Palace · Doodh Talai · Karni Mata · Fateh Sagar"
                        )
                    },
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
        """Send an in-session WhatsApp image using MSG91's single-message media shape.

        Live API validation from this account showed the endpoint expects the same
        top-level recipient/integrated-number fields as text/interactive messages,
        plus a top-level ``attachment_url`` for media.
        """
        payload: dict[str, Any] = {
            "recipient_number": to,
            "integrated_number": settings.msg91_integrated_number,
            "content_type": "image",
            "attachment_url": url,
        }
        if caption:
            payload["caption"] = caption

        return await self._send(db, to, payload, "image")



msg91 = Msg91Client()
