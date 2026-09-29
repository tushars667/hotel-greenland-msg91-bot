from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomerState(Base):
    __tablename__ = "customer_states"

    customer_number: Mapped[str] = mapped_column(String(32), primary_key=True)
    menu_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    human_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"

    event_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BotOutbound(Base):
    __tablename__ = "bot_outbound"

    request_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    customer_number: Mapped[str] = mapped_column(String(32), index=True)
    kind: Mapped[str] = mapped_column(String(64), default="bot")
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
