from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.content import (
    CALL_TEXT,
    DELUXE_PHOTOS,
    DELUXE_RATE_TEXT,
    LOCATION_TEXT,
    SUPER_DELUXE_PHOTOS,
    SUPER_DELUXE_RATE_TEXT,
    WEBSITE_TEXT,
)
from app.models import BotOutbound, CustomerState, ProcessedEvent
from app.msg91 import msg91
from app.webhook_parser import customer_number, extract_selection, extract_text, inbound_uuid


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _state(db: Session, phone: str) -> CustomerState:
    state = db.get(CustomerState, phone)
    if state is None:
        state = CustomerState(customer_number=phone)
        db.add(state)
        db.flush()
    return state


def _dedupe_inbound(db: Session, payload: dict) -> bool:
    uuid = inbound_uuid(payload)
    if not uuid:
        # If MSG91 omitted a stable ID, do not risk dropping a legitimate message.
        return False
    key = f"in:{uuid}"
    if db.get(ProcessedEvent, key):
        return True
    db.add(ProcessedEvent(event_key=key))
    db.commit()
    return False


async def _show_menu(db: Session, phone: str, state: CustomerState) -> None:
    # Greeting and menu are separate messages so the visual style matches your old bot.
    await msg91.send_text(
        db,
        phone,
        "*HOTEL GREEN LAND*\n\nWelcome.\nA comfortable stay, thoughtfully arranged.\n\nHow may we assist you today?",
    )
    await msg91.send_menu(db, phone)
    state.menu_sent_at = now_utc()
    state.updated_at = now_utc()
    db.commit()


async def _send_gallery(db: Session, phone: str, photos: list[tuple[str, str]]) -> None:
    for url, caption in photos:
        await msg91.send_image(db, phone, url, caption)
    await msg91.send_text(db, phone, "Send *menu* anytime to view the main menu.")


async def handle_inbound(db: Session, payload: dict) -> dict:
    phone = customer_number(payload)
    if not phone:
        return {"ok": True, "ignored": "missing customer number"}

    if _dedupe_inbound(db, payload):
        return {"ok": True, "ignored": "duplicate"}

    state = _state(db, phone)
    now = now_utc()

    # Human takes precedence. Backend remains completely silent during takeover.
    if state.human_until and state.human_until > now:
        return {"ok": True, "ignored": "human takeover active"}

    selection = extract_selection(payload)
    text = extract_text(payload).strip()
    lowered = text.lower()

    # Explicit customer request to reopen menu.
    if lowered in {"menu", "main menu"} or selection == "main_menu":
        await _show_menu(db, phone, state)
        return {"ok": True, "action": "menu"}

    if selection == "deluxe_photos":
        await _send_gallery(db, phone, DELUXE_PHOTOS)
        return {"ok": True, "action": selection}

    if selection == "super_deluxe_photos":
        await _send_gallery(db, phone, SUPER_DELUXE_PHOTOS)
        return {"ok": True, "action": selection}

    if selection == "property_location":
        await msg91.send_text(db, phone, LOCATION_TEXT)
        return {"ok": True, "action": selection}

    if selection == "hourly_stays":
        await msg91.send_hourly_buttons(db, phone)
        return {"ok": True, "action": selection}

    if selection == "hourly_deluxe":
        await msg91.send_text(db, phone, DELUXE_RATE_TEXT)
        return {"ok": True, "action": selection}

    if selection == "hourly_super":
        await msg91.send_text(db, phone, SUPER_DELUXE_RATE_TEXT)
        return {"ok": True, "action": selection}

    if selection == "call_reception":
        await msg91.send_text(db, phone, CALL_TEXT)
        return {"ok": True, "action": selection}

    if selection == "visit_website":
        await msg91.send_text(db, phone, WEBSITE_TEXT)
        return {"ok": True, "action": selection}

    # First inbound message of a new/expired bot session: show the menu regardless of wording.
    reset_after = timedelta(hours=settings.menu_reset_hours)
    if state.menu_sent_at is None or now - state.menu_sent_at > reset_after:
        await _show_menu(db, phone, state)
        return {"ok": True, "action": "first_message_menu"}

    # This is the behavior we wanted from the beginning:
    # arbitrary normal text after the menu gets NO bot reply.
    return {"ok": True, "ignored": "plain text after menu"}


def handle_outbound(db: Session, payload: dict) -> dict:
    """
    Configure MSG91's `On Outbound Request Received` webhook to hit this endpoint.

    If the outbound request belongs to our backend, ignore it.
    Any other outbound message is assumed to be a human agent replying from Hello,
    so the bot is muted for HUMAN_TAKEOVER_HOURS.
    """
    phone = customer_number(payload)
    if not phone:
        return {"ok": True, "ignored": "missing customer number"}

    request_id = str(payload.get("requestId") or payload.get("request_id") or "").strip()
    crqid = str(payload.get("crqid") or "").strip()

    if crqid.startswith("hotelbot:"):
        return {"ok": True, "ignored": "our bot outbound"}

    if request_id and db.get(BotOutbound, request_id):
        return {"ok": True, "ignored": "our bot outbound"}

    state = _state(db, phone)
    state.human_until = now_utc() + timedelta(hours=settings.human_takeover_hours)
    state.updated_at = now_utc()
    db.commit()
    return {"ok": True, "action": "human takeover", "until": state.human_until.isoformat()}
