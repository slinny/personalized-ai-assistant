"""One owned SSE connection, with bounded delivery and short database operations."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import UUID

import anyio
from sqlalchemy.orm import Session
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from app.core.config import Settings
from app.providers import (
    ProviderError,
    ProviderTimeout,
    StreamCompleted,
    StreamingProvider,
    TextDelta,
)
from app.schemas.conversation import MessageResponse
from app.schemas.streaming import Delta, FailureCode, Started, StreamError, StreamEvent, Terminal
from app.services.conversation import ReservedTurn, update_turn

logger = logging.getLogger(__name__)


class OutputLimit(ProviderError):
    pass


class TurnStream(Response):
    """The response owns all tasks, including cleanup when headers fail to send.

    A one-frame queue isolates network delivery. Both queue insertion and actual
    ASGI sends have deadlines, so a slow consumer cannot retain work indefinitely.
    """

    media_type = "text/event-stream"

    def __init__(
        self,
        turn: ReservedTurn,
        user_id: UUID,
        factory: Callable[[], Session],
        provider: StreamingProvider,
        settings: Settings,
    ) -> None:
        super().__init__(
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}
        )
        del self.headers["content-length"]
        self.turn = turn
        self.user_id = user_id
        self.factory = factory
        self.provider = provider
        self.settings = settings.model_copy(deep=True)
        self.text = ""
        self.sequence = 0
        self.terminal = False
        self.outcome = "outcome_unknown"
        self.started_at = monotonic()
        self.first_delta_seconds: float | None = None
        self.cancellation_observed_seconds: float | None = None
        self.cleanup_status: Literal["cancelled", "failed"] = "cancelled"

    async def save(
        self,
        status: Literal["in_progress", "completed", "failed", "cancelled"],
        content: str | None = None,
    ) -> MessageResponse:
        def operation() -> MessageResponse:
            with self.factory() as session:
                return update_turn(
                    session,
                    self.user_id,
                    self.turn.assistant_message.conversation_id,
                    self.turn.assistant_message.id,
                    self.settings,
                    status=status,
                    content=content,
                )

        # Do not abandon an in-flight DB transaction when the network disconnects.
        return await anyio.to_thread.run_sync(operation)

    def event(
        self,
        name: Literal[
            "turn.started",
            "message.delta",
            "message.completed",
            "message.cancelled",
            "message.failed",
            "stream.error",
        ],
        payload: Started | Delta | Terminal | StreamError,
    ) -> bytes:
        self.sequence += 1
        return StreamEvent(
            event=name,
            message_id=self.turn.assistant_message.id,
            sequence=self.sequence,
            payload=payload,
        ).encode()

    def terminal_event(self, message: MessageResponse, code: FailureCode | None = None) -> bytes:
        self.terminal = True
        self.outcome = message.status
        if message.status == "cancelled":
            self.cancellation_observed_seconds = max(
                0, (datetime.now(UTC) - message.updated_at).total_seconds()
            )
        name: Literal["message.completed", "message.cancelled", "message.failed"]
        if message.status == "completed":
            name = "message.completed"
        elif message.status == "cancelled":
            name = "message.cancelled"
        else:
            name = "message.failed"
            code = code or "lease_expired"
        return self.event(
            name, Terminal(message=message, error_code=code if name == "message.failed" else None)
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        outgoing, incoming = anyio.create_memory_object_stream[bytes](1)
        iterator: AsyncIterator[TextDelta | StreamCompleted] | None = None
        next_event: asyncio.Task[TextDelta | StreamCompleted] | None = None

        async def pull() -> TextDelta | StreamCompleted:
            assert iterator is not None
            return await anext(iterator)

        async def stop_upstream() -> None:
            nonlocal next_event
            if next_event is not None:
                next_event.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    with anyio.fail_after(self.settings.stream_send_timeout_seconds):
                        await next_event
                next_event = None
            close = getattr(iterator, "aclose", None)
            if close is not None:
                with suppress(Exception):
                    with anyio.fail_after(self.settings.stream_send_timeout_seconds):
                        await close()

        async def emit(frame: bytes, *, terminal: bool = False) -> None:
            remaining = self.settings.stream_deadline_seconds - (monotonic() - self.started_at)
            deadline_limited = (
                not terminal and remaining <= self.settings.stream_send_timeout_seconds
            )
            try:
                with anyio.fail_after(
                    max(0, remaining)
                    if deadline_limited
                    else self.settings.stream_send_timeout_seconds
                ):
                    await outgoing.send(frame)
            except TimeoutError:
                if deadline_limited:
                    raise ProviderTimeout("Generation timed out") from None
                raise

        async def deliver() -> None:
            try:
                with anyio.fail_after(self.settings.stream_send_timeout_seconds):
                    await send(
                        {"type": "http.response.start", "status": 200, "headers": self.raw_headers}
                    )
                async with incoming:
                    async for frame in incoming:
                        with anyio.fail_after(self.settings.stream_send_timeout_seconds):
                            await send(
                                {"type": "http.response.body", "body": frame, "more_body": True}
                            )
                with anyio.fail_after(self.settings.stream_send_timeout_seconds):
                    await send({"type": "http.response.body", "body": b"", "more_body": False})
            finally:
                group.cancel_scope.cancel()

        async def disconnected() -> None:
            while True:
                if (await receive())["type"] == "http.disconnect":
                    group.cancel_scope.cancel()
                    return

        async def generate() -> None:
            nonlocal next_event, iterator
            loop = asyncio.get_running_loop()
            start = self.started_at
            last_activity = last_save = last_poll = last_heartbeat = start
            size = 0
            try:
                await emit(
                    self.event(
                        "turn.started",
                        Started(
                            user_message=self.turn.user_message,
                            assistant_message=self.turn.assistant_message,
                        ),
                    )
                )
                iterator = self.provider.stream(self.turn.request)
                next_event = asyncio.create_task(pull())
                while True:
                    now = loop.time()
                    if (
                        now - start >= self.settings.stream_deadline_seconds
                        or now - last_activity >= self.settings.stream_idle_seconds
                    ):
                        raise ProviderTimeout("Generation timed out")
                    if now - last_poll >= self.settings.stream_poll_seconds:
                        checkpoint = now - last_save >= self.settings.stream_checkpoint_seconds
                        saved = await self.save("in_progress", self.text if checkpoint else None)
                        last_poll = now
                        if checkpoint:
                            last_save = now
                        if saved.status != "in_progress":
                            await stop_upstream()
                            await emit(self.terminal_event(saved), terminal=True)
                            break
                    if now - last_heartbeat >= self.settings.stream_heartbeat_seconds:
                        await emit(b": keepalive\n\n")
                        last_heartbeat = now
                    wait = min(
                        self.settings.stream_poll_seconds,
                        self.settings.stream_heartbeat_seconds,
                        max(0, self.settings.stream_deadline_seconds - (now - start)),
                        max(0, self.settings.stream_idle_seconds - (now - last_activity)),
                    )
                    ready, _ = await asyncio.wait({next_event}, timeout=wait)
                    if not ready:
                        continue
                    if loop.time() - start >= self.settings.stream_deadline_seconds:
                        raise ProviderTimeout("Generation timed out")
                    try:
                        event = next_event.result()
                    except StopAsyncIteration:
                        raise ProviderError("Stream ended without completion") from None
                    next_event = None
                    last_activity = loop.time()
                    if isinstance(event, StreamCompleted):
                        if not self.text.strip():
                            raise ProviderError("Generation returned no text")
                        await stop_upstream()
                        saved = await self.save("completed", self.text)
                        await emit(self.terminal_event(saved), terminal=True)
                        break
                    size += len(event.text.encode("utf-8"))
                    if size > self.settings.stream_max_output_bytes:
                        raise OutputLimit("Output limit reached")
                    self.text += event.text
                    if event.text:
                        if self.first_delta_seconds is None:
                            self.first_delta_seconds = monotonic() - self.started_at
                        await emit(self.event("message.delta", Delta(text=event.text)))
                    next_event = asyncio.create_task(pull())
            except TimeoutError:
                # Delivery backpressure cancels this turn in the response cleanup.
                raise
            except Exception as error:
                self.cleanup_status = "failed"
                await stop_upstream()
                # No exception messages are exposed, including unexpected adapter failures.
                code: FailureCode = (
                    "generation_timeout"
                    if isinstance(error, ProviderTimeout)
                    else "output_limit"
                    if isinstance(error, OutputLimit)
                    else "generation_failed"
                )
                try:
                    saved = await self.save("failed", self.text)
                    await emit(self.terminal_event(saved, code), terminal=True)
                except Exception:
                    await emit(self.event("stream.error", StreamError()), terminal=True)
            finally:
                await outgoing.aclose()

        try:
            async with anyio.create_task_group() as group:
                group.start_soon(deliver)
                group.start_soon(disconnected)
                group.start_soon(generate)
        except* (OSError, TimeoutError, anyio.BrokenResourceError):
            pass
        finally:
            # Shield cleanup from the request's cancellation scope, not from process death.
            with anyio.CancelScope(shield=True):
                await stop_upstream()
                if not self.terminal:
                    try:
                        saved = await self.save(self.cleanup_status, self.text)
                        self.outcome = saved.status
                    except Exception:
                        logger.warning("Streaming cleanup could not persist outcome")
                logger.info(
                    "Streaming turn ended",
                    extra={
                        "stream_metrics": {
                            "outcome": self.outcome,
                            "duration_seconds": monotonic() - self.started_at,
                            "first_delta_seconds": self.first_delta_seconds,
                            "cancellation_observed_seconds": self.cancellation_observed_seconds,
                        }
                    },
                )
