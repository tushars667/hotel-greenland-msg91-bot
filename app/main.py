import logging

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import CustomerState
from app.service import handle_inbound, handle_outbound, now_utc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Hotel Green Land WhatsApp Bot", version="1.0.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_webhook_secret(x_webhook_secret: str | None) -> None:
    if not x_webhook_secret or x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/webhooks/msg91/inbound")
async def msg91_inbound(
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None),
):
    verify_webhook_secret(x_webhook_secret)
    payload = await request.json()
    return await handle_inbound(db, payload)


@app.post("/webhooks/msg91/outbound")
async def msg91_outbound(
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_secret: str | None = Header(default=None),
):
    verify_webhook_secret(x_webhook_secret)
    payload = await request.json()
    return handle_outbound(db, payload)


@app.post("/admin/resume/{customer_number}")
def resume_bot(
    customer_number: str,
    db: Session = Depends(get_db),
    x_admin_secret: str | None = Header(default=None),
):
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="invalid admin secret")

    state = db.get(CustomerState, customer_number)
    if state is None:
        return {"ok": True, "customer_number": customer_number, "state": "new"}

    state.human_until = None
    state.menu_sent_at = None
    state.updated_at = now_utc()
    db.commit()
    return {"ok": True, "customer_number": customer_number, "state": "bot resumed"}


@app.get("/admin/state/{customer_number}")
def state(
    customer_number: str,
    db: Session = Depends(get_db),
    x_admin_secret: str | None = Header(default=None),
):
    if x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=401, detail="invalid admin secret")

    item = db.get(CustomerState, customer_number)
    if item is None:
        return {"customer_number": customer_number, "state": "new"}

    return {
        "customer_number": customer_number,
        "menu_sent_at": item.menu_sent_at,
        "human_until": item.human_until,
        "updated_at": item.updated_at,
    }
