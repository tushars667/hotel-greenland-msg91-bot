from app.webhook_parser import extract_selection, extract_text


def test_text_from_msg91_payload():
    payload = {"text": "Details send kijiye"}
    assert extract_text(payload) == "Details send kijiye"


def test_list_reply_from_interactive_string():
    payload = {
        "interactive": '{"type":"list_reply","list_reply":{"id":"deluxe_photos","title":"Deluxe Room Photos"}}'
    }
    assert extract_selection(payload) == "deluxe_photos"


def test_button_reply_from_messages():
    payload = {
        "messages": '[{"interactive":{"type":"button_reply","button_reply":{"id":"hourly_super","title":"Super Deluxe"}}}]'
    }
    assert extract_selection(payload) == "hourly_super"


def test_title_fallback():
    payload = {"button": '{"payload":"","text":"Property Location"}'}
    assert extract_selection(payload) == "property_location"
