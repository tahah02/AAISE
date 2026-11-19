import json
import uuid
from datetime import datetime, timezone, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.db.models import Base, ProjectORM, ConversationORM, MessageORM
from src.application.orchestration.history_helper import fetch_conversation_history


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    project = ProjectORM(name="History Test Project", target_framework="DOTNET_CSHARP")
    session.add(project)
    session.flush()

    conv = ConversationORM(project_id=project.id, title="Main Chat")
    session.add(conv)
    session.flush()

    yield session, project, conv
    session.close()


def test_empty_conversation_history(db_session):
    session, project, _ = db_session
    history = fetch_conversation_history(session, project.id)
    assert history == []


def test_fetch_conversation_history_chronological_and_roles(db_session):
    session, project, conv = db_session
    base_time = datetime.now(timezone.utc)

    m1 = MessageORM(
        conversation_id=conv.id,
        sender_type="user",
        content="Create student API only",
        created_date=base_time - timedelta(seconds=20),
    )
    m2 = MessageORM(
        conversation_id=conv.id,
        sender_type="agent1",
        content="Created TDD with POST /api/v1/students",
        created_date=base_time - timedelta(seconds=10),
    )
    m3 = MessageORM(
        conversation_id=conv.id,
        sender_type="user",
        content="Do not create code, just system design",
        created_date=base_time,
    )
    session.add_all([m1, m2, m3])
    session.commit()

    history = fetch_conversation_history(session, project.id, max_turns=6)

    assert len(history) == 3
    assert history[0].role == "user"
    assert history[0].content == "Create student API only"
    assert history[1].role == "assistant"
    assert history[1].content == "Created TDD with POST /api/v1/students"
    assert history[2].role == "user"
    assert history[2].content == "Do not create code, just system design"


def test_fetch_conversation_history_filters_approval_cards_and_transient(db_session):
    session, project, conv = db_session
    base_time = datetime.now(timezone.utc)

    m1 = MessageORM(
        conversation_id=conv.id,
        sender_type="user",
        content="Initial prompt",
        created_date=base_time - timedelta(seconds=30),
    )
    m2 = MessageORM(
        conversation_id=conv.id,
        sender_type="assistant",
        content="Human approval required",
        metadata_json=json.dumps({"isApprovalCard": True}),
        created_date=base_time - timedelta(seconds=20),
    )
    m3 = MessageORM(
        conversation_id=conv.id,
        sender_type="assistant",
        content="Analyzing requested changes for SPECIFICATION. Revising...",
        created_date=base_time - timedelta(seconds=10),
    )
    m4 = MessageORM(
        conversation_id=conv.id,
        sender_type="agent1",
        content="Revised TDD successfully",
        created_date=base_time,
    )
    session.add_all([m1, m2, m3, m4])
    session.commit()

    history = fetch_conversation_history(session, project.id, max_turns=6)

    assert len(history) == 2
    assert history[0].content == "Initial prompt"
    assert history[1].content == "Revised TDD successfully"


def test_fetch_conversation_history_truncates_long_assistant_content(db_session):
    session, project, conv = db_session
    base_time = datetime.now(timezone.utc)

    long_text = "A" * 2000
    m1 = MessageORM(
        conversation_id=conv.id,
        sender_type="user",
        content="Brief request",
        created_date=base_time - timedelta(seconds=10),
    )
    m2 = MessageORM(
        conversation_id=conv.id,
        sender_type="agent3",
        content=long_text,
        created_date=base_time,
    )
    session.add_all([m1, m2])
    session.commit()

    history = fetch_conversation_history(session, project.id, max_turns=4, max_content_chars=500)

    assert len(history) == 2
    assert history[0].content == "Brief request"
    assert len(history[1].content) < 600
    assert "...[truncated for brevity]..." in history[1].content
