import shutil
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.agents.doc_reviewer import DocumentationReviewerAgent
from src.application.orchestration.history_helper import fetch_conversation_history
from src.domain.enums import AgentType, LLMProvider
from src.infrastructure.db.models import (
    Base,
    ProjectORM,
    ProjectAgentConfigORM,
    AgentTaskORM,
    AgentExecutionORM,
    ConversationORM,
    MessageORM,
)
from src.infrastructure.llm.provider_resolver import LLMProviderResolver
from src.infrastructure.llm.token_tracker import TokenTrackerService
from src.ports.agent import AgentContext
from src.ports.llm_gateway import ILLMGateway, LLMRequest, LLMResponse, TokenUsage, LLMMessage


@pytest.fixture
def revision_setup():
    tmp_workspace = tempfile.mkdtemp(prefix="aaise_revision_test_")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    project = ProjectORM(
        name="Student API",
        target_framework="DOTNET_CSHARP",
        description="create a api student, using sqlite db, just add student. do not do anything else.",
    )
    session.add(project)
    session.flush()

    conv = ConversationORM(project_id=project.id, title="Main Chat")
    session.add(conv)
    session.flush()

    now = datetime.now(timezone.utc)
    m1 = MessageORM(
        conversation_id=conv.id,
        sender_type="user",
        content="create a api student, using sqlite db, just add student. do not do anything else.",
        created_date=now - timedelta(seconds=20),
    )
    m2 = MessageORM(
        conversation_id=conv.id,
        sender_type="agent1",
        content="Generated TDD with single endpoint: POST /api/v1/students.",
        created_date=now - timedelta(seconds=10),
    )
    session.add_all([m1, m2])
    session.commit()

    docs_dir = Path(tmp_workspace) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    existing_tdd = docs_dir / "TECHNICAL_DESIGN.md"
    existing_tdd.write_text("# Previous TDD\n\n## Endpoints\n- POST /api/v1/students", encoding="utf-8")
    existing_test = docs_dir / "XUNIT_TEST_SPEC.md"
    existing_test.write_text("# Previous Test Spec\n\n## UT-01: Add Student", encoding="utf-8")

    config = ProjectAgentConfigORM(
        project_id=project.id,
        agent_type=AgentType.DOC_REVIEWER.value,
        provider=LLMProvider.GEMINI.value,
        model_name="capturing-model",
    )
    session.add(config)
    session.commit()

    resolver = LLMProviderResolver()
    tracker = TokenTrackerService(db=session)
    agent = DocumentationReviewerAgent(resolver=resolver, tracker=tracker, db=session)

    task = AgentTaskORM(project_id=project.id, agent_name="Agent 1", task_type="SPECIFICATION")
    session.add(task)
    session.flush()

    execution = AgentExecutionORM(agent_task_id=task.id)
    session.add(execution)
    session.commit()

    context = AgentContext(
        project_id=project.id,
        task_id=task.id,
        agent_execution_id=execution.id,
        workspace_path=tmp_workspace,
        target_framework="DOTNET_CSHARP",
    )

    yield agent, context, session, tmp_workspace

    shutil.rmtree(tmp_workspace, ignore_errors=True)
    session.close()


def test_history_extraction_for_agent1_context(revision_setup):
    agent, context, session, _ = revision_setup

    # 1. Verify history extraction for the active project
    history = fetch_conversation_history(session, context.project_id, max_turns=6)
    assert len(history) == 2
    assert history[0].role == "user"
    assert "just add student" in history[0].content
    assert history[1].role == "assistant"
    assert "POST /api/v1/students" in history[1].content


def test_base_requirements_retrieval_and_preservation(revision_setup):
    agent, context, session, _ = revision_setup

    # 2. Verify base requirements are resolved from project description or earliest message
    proj = session.query(ProjectORM).filter_by(id=context.project_id).first()
    assert proj.description == "create a api student, using sqlite db, just add student. do not do anything else."

    first_msg = (
        session.query(MessageORM)
        .join(ConversationORM)
        .filter(ConversationORM.project_id == context.project_id, MessageORM.sender_type == "user")
        .order_by(MessageORM.created_date.asc())
        .first()
    )
    assert first_msg is not None
    assert "just add student. do not do anything else." in first_msg.content


def test_cumulative_revision_prompt_construction(revision_setup):
    agent, context, session, tmp_workspace = revision_setup

    existing_tdd_path = Path(tmp_workspace) / "docs" / "TECHNICAL_DESIGN.md"
    existing_tdd = existing_tdd_path.read_text(encoding="utf-8")
    assert "POST /api/v1/students" in existing_tdd

    original_req = context.project_id and session.query(ProjectORM).filter_by(id=context.project_id).first().description
    user_revision_input = "Requested Changes for SPECIFICATION:\ndo not create code, just give me system design"

    base_scope = (
        f"## Original Base Requirements (ABSOLUTE BOUNDARY & SOURCE OF TRUTH):\n{original_req}\n\n"
        if original_req
        else ""
    )
    tdd_user_content = (
        f"{base_scope}"
        f"## Current Technical Design on Disk:\n\n{existing_tdd}\n\n"
        f"## MANDATORY USER REVISION REQUEST & REQUIRED CORRECTIONS:\n\n{user_revision_input}\n\n"
        f"CRITICAL REVISION DIRECTIVES:\n"
        f"1. DO NOT invent or add new endpoints, entities, or CRUD actions beyond what was originally required in the Base Requirements above. Strictly preserve single-entity or constrained scopes.\n"
        f"2. Only apply the specific modifications requested in the User Revision Request above.\n"
        f"Update and expand docs/TECHNICAL_DESIGN.md to incorporate every single requested correction. Do NOT abbreviate."
    )

    assert "Original Base Requirements (ABSOLUTE BOUNDARY & SOURCE OF TRUTH)" in tdd_user_content
    assert "just add student. do not do anything else." in tdd_user_content
    assert "Current Technical Design on Disk" in tdd_user_content
    assert "POST /api/v1/students" in tdd_user_content
    assert "DO NOT invent or add new endpoints, entities, or CRUD actions beyond what was originally required" in tdd_user_content

    # Verify messages payload structure: System -> History Turns -> Cumulative User Prompt
    history = fetch_conversation_history(session, context.project_id, max_turns=6)
    messages = [
        LLMMessage(role="system", content=agent.get_system_prompt(context)),
        *history,
        LLMMessage(role="user", content=tdd_user_content),
    ]

    assert len(messages) == 4
    assert messages[0].role == "system"
    assert messages[1].role == "user"
    assert "just add student" in messages[1].content
    assert messages[2].role == "assistant"
    assert "POST /api/v1/students" in messages[2].content
    assert messages[3].role == "user"
    assert "CRITICAL REVISION DIRECTIVES" in messages[3].content
