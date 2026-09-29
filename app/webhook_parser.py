import json
from typing import Any


def _jsonish(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    value = value.strip()
    if not value:
        return value
    if value[0] not in "[{":
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def customer_number(payload: dict[str, Any]) -> str:
    return str(payload.get("customerNumber") or payload.get("customer_number") or "").strip()


def inbound_uuid(payload: dict[str, Any]) -> str:
    direct = payload.get("uuid")
    if direct:
        return str(direct)

    messages = _jsonish(payload.get("messages"))
    if isinstance(messages, list) and messages:
        return str(messages[0].get("id") or "")
    return ""


def extract_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if text:
        return str(text).strip()

    content = _jsonish(payload.get("content"))
    if isinstance(content, dict):
        maybe = content.get("text")
        if isinstance(maybe, str):
            return maybe.strip()
        if isinstance(maybe, dict):
            return str(maybe.get("body") or "").strip()

    messages = _jsonish(payload.get("messages"))
    if isinstance(messages, list) and messages:
        msg = messages[0]
        t = msg.get("text")
        if isinstance(t, dict):
            return str(t.get("body") or "").strip()
        if isinstance(t, str):
            return t.strip()
    return ""


def extract_selection(payload: dict[str, Any]) -> str:
    """
    Returns a stable action id when possible.
    Handles MSG91's stringified `interactive`, `button`, and raw `messages` payloads.
    """
    candidates: list[str] = []

    interactive = _jsonish(payload.get("interactive"))
    if isinstance(interactive, dict):
        for key in ("list_reply", "button_reply"):
            block = interactive.get(key)
            if isinstance(block, dict):
                candidates.extend([str(block.get("id") or ""), str(block.get("title") or "")])

    button = _jsonish(payload.get("button"))
    if isinstance(button, dict):
        candidates.extend([str(button.get("payload") or ""), str(button.get("text") or "")])

    messages = _jsonish(payload.get("messages"))
    if isinstance(messages, list) and messages:
        msg = messages[0]
        inter = msg.get("interactive")
        if isinstance(inter, dict):
            for key in ("list_reply", "button_reply"):
                block = inter.get(key)
                if isinstance(block, dict):
                    candidates.extend([str(block.get("id") or ""), str(block.get("title") or "")])

        btn = msg.get("button")
        if isinstance(btn, dict):
            candidates.extend([str(btn.get("payload") or ""), str(btn.get("text") or "")])

    mapping = {
        "deluxe_photos": "deluxe_photos",
        "deluxe room photos": "deluxe_photos",
        "super_deluxe_photos": "super_deluxe_photos",
        "super deluxe photos": "super_deluxe_photos",
        "property_location": "property_location",
        "property location": "property_location",
        "hourly_stays": "hourly_stays",
        "hourly stays": "hourly_stays",
        "call_reception": "call_reception",
        "call representative": "call_reception",
        "visit_website": "visit_website",
        "visit website": "visit_website",
        "hourly_deluxe": "hourly_deluxe",
        "deluxe room": "hourly_deluxe",
        "hourly_super": "hourly_super",
        "super deluxe": "hourly_super",
        "main_menu": "main_menu",
        "main menu": "main_menu",
    }

    for item in candidates:
        key = item.strip().lower()
        if key in mapping:
            return mapping[key]
    return ""
