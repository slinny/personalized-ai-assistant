import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_provider, get_streaming_provider
from app.db.provision import provision
from app.main import create_app
from app.models import MemoryNote
from app.providers import GenerationResult, StreamCompleted, TextDelta
from app.providers.fake import FakeProvider, FakeStreamingProvider
from tests.integration.test_pipeline import Environment, env  # noqa: F401

HEADERS = {"Authorization": "Bearer " + "a" * 32}


def test_memory_cross_conversation_correction_deletion_and_source(env: Environment) -> None:  # noqa: F811
    app = create_app()
    fake = FakeProvider(*(GenerationResult("Sample answer") for _ in range(4)))
    app.dependency_overrides[get_provider] = lambda: fake
    with TestClient(app) as client:
        assert client.post("/memories", json={"content": "No auth"}).status_code == 401
        assert client.get("/memories").status_code == 401
        first = client.post(
            f"/conversations/{env.conversation_id}/messages",
            headers=HEADERS,
            json={"content": "My project is Cedar."},
        ).json()
        note = client.post(
            "/memories",
            headers=HEADERS,
            json={
                "content": "My project is Cedar.",
                "source_message_id": first["user_message"]["id"],
            },
        )
        assert note.status_code == 201
        note_id = note.json()["id"]
        assert note.json()["source_message_id"] == first["user_message"]["id"]
        for source in (first["assistant_message"]["id"], str(uuid4())):
            assert (
                client.post(
                    "/memories", headers=HEADERS, json={"content": "x", "source_message_id": source}
                ).status_code
                == 404
            )
        for expected in ("Cedar", "Birch", None):
            conversation = client.post("/conversations", headers=HEADERS).json()["id"]
            response = client.post(
                f"/conversations/{conversation}/messages",
                headers=HEADERS,
                json={"content": "What is my project?"},
            )
            assert response.status_code == 201
            context = "\n".join(m.content for m in fake.requests[-1].messages)
            if expected:
                assert expected in context
            if expected == "Cedar":
                assert (
                    client.patch(
                        f"/memories/{note_id}",
                        headers=HEADERS,
                        json={"content": "My project is Birch."},
                    ).status_code
                    == 200
                )
            elif expected == "Birch":
                assert "Cedar" not in context
                assert client.delete(f"/memories/{note_id}", headers=HEADERS).status_code == 200
            else:
                assert "Cedar" not in context and "Birch" not in context
        assert client.get("/memories", headers=HEADERS).json() == []
        assert (
            client.get(f"/conversations/{env.conversation_id}/messages", headers=HEADERS).json()[0][
                "content"
            ]
            == "My project is Cedar."
        )


def test_memory_ownership(env: Environment) -> None:  # noqa: F811
    other_id = uuid4()
    with Session(env.engine) as session, session.begin():
        provision(session, other_id)
        other = MemoryNote(user_id=other_id, content="Private note")
        session.add(other)
        session.flush()
        note_id = other.id
    try:
        with TestClient(create_app()) as client:
            assert client.get("/memories", headers=HEADERS).json() == []
            assert (
                client.patch(
                    f"/memories/{note_id}", headers=HEADERS, json={"content": "wrong"}
                ).status_code
                == 404
            )
            assert client.delete(f"/memories/{note_id}", headers=HEADERS).status_code == 404
        with Session(env.engine) as session:
            assert session.get(MemoryNote, note_id).content == "Private note"  # type: ignore[union-attr]
    finally:
        from sqlalchemy import delete

        from app.models import AssistantProfile, User

        with Session(env.engine) as session, session.begin():
            session.execute(delete(AssistantProfile).where(AssistantProfile.user_id == other_id))
            session.execute(delete(User).where(User.id == other_id))


def test_concurrent_memory_cap_and_stream_omission_report(env: Environment) -> None:  # noqa: F811
    with Session(env.engine) as session, session.begin():
        session.add_all(MemoryNote(user_id=env.user_id, content="界" * 300) for _ in range(19))

    def add_note(_: int) -> int:
        with TestClient(create_app()) as client:
            return int(
                client.post("/memories", headers=HEADERS, json={"content": "界" * 300}).status_code
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(add_note, range(2))) == [201, 409]
    with Session(env.engine) as session:
        ids = {
            str(note.id)
            for note in session.scalars(select(MemoryNote).where(MemoryNote.user_id == env.user_id))
        }
    app = create_app()
    fake = FakeStreamingProvider(TextDelta("Hello"), StreamCompleted())
    app.dependency_overrides[get_streaming_provider] = lambda: fake
    with TestClient(app) as client:
        response = client.post(
            f"/conversations/{env.conversation_id}/messages/stream",
            headers=HEADERS,
            json={"content": "Hi"},
        )
    assert response.status_code == 200
    started = json.loads(
        next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
    )
    omitted = set(started["payload"]["omitted_memory_ids"])
    assert len(omitted) == 19 and omitted < ids
    assert fake.requests[0].context is not None
    assert set(fake.requests[0].context.included_memory_ids) == ids - omitted
