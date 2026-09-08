"""Bounded, newest-first database history scans."""

from collections.abc import Iterator
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message
from app.services.context import HistoryMessage

HISTORY_BATCH_SIZE = 100


def iter_history(
    session: Session,
    conversation_id: UUID,
    scan_limit: int,
    *,
    batch_size: int = HISTORY_BATCH_SIZE,
) -> Iterator[HistoryMessage]:
    """Keyset pagination, without materializing ORM objects or the whole conversation.

    The caller holds the owned conversation lock, so application writes cannot
    change its history between pages. A scan limit bounds work on failed turns.
    """
    if scan_limit < 2 or batch_size < 1:
        raise ValueError("History scan limit must be at least two and batch size positive")
    before: int | None = None
    remaining = scan_limit
    while remaining:
        size = min(batch_size, remaining)
        query = select(Message.position, Message.role, Message.content, Message.status).where(
            Message.conversation_id == conversation_id
        )
        if before is not None:
            query = query.where(Message.position < before)
        rows = session.execute(query.order_by(Message.position.desc()).limit(size)).all()
        for row in rows:
            yield HistoryMessage(row.position, row.role, row.content, row.status)
        if len(rows) < size:
            return
        remaining -= len(rows)
        before = rows[-1].position
