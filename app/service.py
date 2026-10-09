from datetime import datetime, timedelta, timezone

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


def as_utc(value: datetime | None) -> datetime | None:
    """Normalize datetimes loaded from SQLite/Postgres to timezone-aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _state(db: Session, phone: str) -> CustomerState:
    state = db.get(CustomerState, phone)
    if state is None:
        state = CustomerState(customer_number=phone)
        db.add(state)
        db.flush()
    return state


def _inbound_event_key(payload: dict) -> str | None:
    uuid = inbound_uuid(payload)
    return f"in:{uuid}" if uuid else None


def _is_duplicate_inbound(db: Session, event_key: str | None) -> bool:
    return bool(event_key and db.get(ProcessedEvent, event_key))


def _mark_inbound_processed(db: Session, event_key: str | None) -> None:
    # Mark only AFTER successful processing. If processing raises, MSG91 can retry it.
    if not event_key:
        return
    db.merge(ProcessedEvent(event_key=event_key))
    db.commit()


async def _show_menu(db: Session, phone: str, state: CustomerState) -> None:

    await msg91.send_menu(db, phone)
    state.menu_sent_at = now_utc()
    state.updated_at = now_utc()
    db.commit()


async def _send_gallery(db: Session, phone: str, photos: list[tuple[str, str]]) -> None:
    for url, caption in photos:
        await msg91.send_image(db, phone, url, caption)
    await msg91.send_text(db, phone, "Send *menu* anytime to view the main menu.")


async def _process_inbound(db: Session, payload: dict, phone: str) -> dict:
    state = _state(db, phone)
    now = now_utc()

    # SQLite can return stored datetimes without tzinfo. Normalize before comparison.
    human_until = as_utc(state.human_until)
    if human_until and human_until > now:
        return {"ok": True, "ignored": "human takeover active"}

    selection = extract_selection(payload)
    text = extract_text(payload).strip()
    lowered = text.lower()

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

    reset_after = timedelta(hours=settings.menu_reset_hours)
    menu_sent_at = as_utc(state.menu_sent_at)
    if menu_sent_at is None or now - menu_sent_at > reset_after:
        await _show_menu(db, phone, state)
        return {"ok": True, "action": "first_message_menu"}

    # Plain free-text after the menu is intentionally silent.
    return {"ok": True, "ignored": "plain text after menu"}


async def handle_inbound(db: Session, payload: dict) -> dict:
    phone = customer_number(payload)
    if not phone:
        return {"ok": True, "ignored": "missing customer number"}

    event_key = _inbound_event_key(payload)
    if _is_duplicate_inbound(db, event_key):
        return {"ok": True, "ignored": "duplicate"}

    try:
        result = await _process_inbound(db, payload, phone)
    except Exception:
        db.rollback()
        raise

    _mark_inbound_processed(db, event_key)
    return result


def handle_outbound(db: Session, payload: dict) -> dict:
    """
    `On Outbound Request Received` webhook.

    Backend-originated outbound messages are ignored. Any other outbound message is
    treated as a human agent reply, muting the bot for HUMAN_TAKEOVER_HOURS.
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
