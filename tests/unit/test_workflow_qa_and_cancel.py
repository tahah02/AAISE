import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.infrastructure.db.models import Base, ProjectORM, WorkflowRunORM, ConversationORM, MessageORM
from src.api.routes.workflow import (
    is_qa_explanation_query,
    is_explicit_build_command,
    handle_qa_explanation_intent,
    start_workflow_multipart_endpoint,
    cancel_workflow_run,
    cancel_workflow_for_project,
)
from src.infrastructure.orchestration.graph_builder import (
    route_entry,
    route_after_spec_approval,
    route_after_mock_approval,
    route_after_code_approval,
    route_after_qa_approval,
    route_after_security_approval,
    END,
)
from src.ports.llm_gateway import LLMResponse, TokenUsage
from src.domain.enums import LLMProvider


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    project = ProjectORM(name="E-Commerce API", target_framework="fastapi")
    session.add(project)
    session.flush()

    run = WorkflowRunORM(
        project_id=project.id,
        current_phase="DEVELOPMENT",
        status="RUNNING",
    )
    session.add(run)
    session.commit()

    yield session
    session.close()


def test_is_qa_explanation_query_classification():
    # True cases: Questions, explanations, point references
    assert is_qa_explanation_query("explain point 9 of SRS") is True
    assert is_qa_explanation_query("what database schema is being used?") is True
    assert is_qa_explanation_query("why did the integration tests fail?") is True
    assert is_qa_explanation_query("how does authentication work here?") is True
    assert is_qa_explanation_query("can you explain section 4?") is True
    assert is_qa_explanation_query("summarize the API contracts") is True
    assert is_qa_explanation_query("tell me about the architecture") is True
    assert is_qa_explanation_query("is the database using SQLite or PostgreSQL?") is True
    assert is_qa_explanation_query("point 3 explanation") is True

    # False cases: Imperative implementation directives, greetings, git commands
    assert is_qa_explanation_query("hello") is False
    assert is_qa_explanation_query("hi there") is False
    assert is_qa_explanation_query("build an e-commerce backend in fastapi") is False
    assert is_qa_explanation_query("create an endpoint POST /orders") is False
    assert is_qa_explanation_query("implement JWT auth middleware") is False
    assert is_qa_explanation_query("git push https://github.com/org/repo.git") is False


@pytest.mark.asyncio
async def test_handle_qa_explanation_intent_answers_without_triggering_build(db_session):
    project = db_session.query(ProjectORM).first()

    mock_llm_response = LLMResponse(
        provider=LLMProvider.GEMINI,
        model="gemini-3.5-flash-lite",
        finish_reason="stop",
        content="Point 9 of the SRS specifies that all entity DateTime timestamps must use UTC roundtrip conversion.",
        usage=TokenUsage(prompt_tokens=450, completion_tokens=85, total_tokens=535),
        latency_ms=1100,
    )

    with patch("src.api.routes.workflow.LLMProviderResolver") as MockResolverClass:
        mock_adapter = AsyncMock()
        mock_adapter.complete.return_value = mock_llm_response
        mock_config = MagicMock()
        mock_config.adapter = mock_adapter
        mock_config.provider = LLMProvider.GEMINI
        mock_config.model = "gemini-3.5-flash-lite"
        mock_config.fallback_provider = None
        mock_config.fallback_model = None
        mock_instance = MockResolverClass.return_value
        mock_instance.resolve_agent_config.return_value = mock_config

        resp = await handle_qa_explanation_intent(
            user_text="explain point 9 of SRS",
            project_id=str(project.id),
            db=db_session,
        )

        assert resp is not None
        assert resp.is_greeting is True
        assert resp.status == "CONVERSATION"
        assert "Point 9" in resp.assistant_reply
        assert resp.project_id == project.id

        # Verify chat messages were durably recorded with telemetry
        conv = db_session.query(ConversationORM).filter_by(project_id=project.id).first()
        assert conv is not None
        msgs = db_session.query(MessageORM).filter_by(conversation_id=conv.id).all()
        assert len(msgs) == 2
        assert msgs[0].sender_type == "user"
        assert msgs[1].sender_type == "agent1"
        assert "telemetry" in (msgs[1].metadata_json or "")


@pytest.mark.asyncio
async def test_cancel_workflow_run_endpoint(db_session):
    run = db_session.query(WorkflowRunORM).first()
    assert run.status == "RUNNING"

    resp = await cancel_workflow_run(run_id=run.id, db=db_session)
    assert resp["status"] == "CANCELLED"

    db_session.refresh(run)
    assert run.status == "CANCELLED"


@pytest.mark.asyncio
async def test_cancel_workflow_for_project_endpoint(db_session):
    project = db_session.query(ProjectORM).first()
    run = db_session.query(WorkflowRunORM).filter_by(project_id=project.id).first()
    run.status = "RUNNING"
    db_session.commit()

    resp = await cancel_workflow_for_project(project_id=project.id, db=db_session)
    assert resp["status"] == "CANCELLED"

    db_session.refresh(run)
    assert run.status == "CANCELLED"


def test_graph_builder_routes_halt_immediately_when_cancelled():
    cancelled_state = {
        "is_cancelled": True,
        "enabled_agents": {"AGENT_1": True, "AGENT_2": True, "AGENT_3": True, "AGENT_4": True, "AGENT_5": True},
        "spec_approved": True,
        "mock_approved": True,
        "code_approved": True,
        "qa_approved": True,
        "security_approved": True,
    }

    assert route_entry(cancelled_state) == END
    assert route_after_spec_approval(cancelled_state) == END
    assert route_after_mock_approval(cancelled_state) == END
    assert route_after_code_approval(cancelled_state) == END
    assert route_after_qa_approval(cancelled_state) == END
    assert route_after_security_approval(cancelled_state) == END


def test_is_explicit_build_command_classification():
    # Build commands
    assert is_explicit_build_command("") is True
    assert is_explicit_build_command("Please implement the attached software requirements document.") is True
    assert is_explicit_build_command("build this application") is True
    assert is_explicit_build_command("implement student registration module") is True
    assert is_explicit_build_command("generate tdd and test specifications") is True

    # Questions and Q&A (NOT build commands)
    assert is_explicit_build_command("Can you explain point number 5?") is False
    assert is_explicit_build_command("Can you explain point no 5") is False
    assert is_explicit_build_command("explain point 5") is False
    assert is_explicit_build_command("what does section 4 require?") is False
    assert is_explicit_build_command("summarize this document") is False
    assert is_explicit_build_command("review the requirements") is False


@pytest.mark.asyncio
async def test_multipart_upload_with_question_answers_without_triggering_tdd_or_specs(db_session):
    from fastapi import BackgroundTasks
    import io

    project = db_session.query(ProjectORM).first()

    mock_llm_response = LLMResponse(
        provider=LLMProvider.GEMINI,
        model="gemini-3.5-flash-lite",
        finish_reason="stop",
        content="Point 5 requires students to submit a valid email address and verified phone number before enrollment.",
        usage=TokenUsage(prompt_tokens=600, completion_tokens=90, total_tokens=690),
        latency_ms=1200,
    )

    class DummyUploadFile:
        def __init__(self, filename: str, content: bytes):
            self.filename = filename
            self._content = content

        async def read(self):
            return self._content

    fake_file = DummyUploadFile(
        filename="Student_Registration_SRS_v2_AAISE.txt",
        content=b"5. Student Registration Verification: Valid email and phone number required.",
    )

    bg_tasks = BackgroundTasks()

    with patch("src.api.routes.workflow.LLMProviderResolver") as MockResolverClass:
        mock_adapter = AsyncMock()
        mock_adapter.complete.return_value = mock_llm_response
        mock_config = MagicMock()
        mock_config.adapter = mock_adapter
        mock_config.provider = LLMProvider.GEMINI
        mock_config.model = "gemini-3.5-flash-lite"
        mock_config.fallback_provider = None
        mock_config.fallback_model = None
        mock_instance = MockResolverClass.return_value
        mock_instance.resolve_agent_config.return_value = mock_config

        resp = await start_workflow_multipart_endpoint(
            background_tasks=bg_tasks,
            project_id=str(project.id),
            project_name=None,
            user_requirement="Can you explain point no 5",
            files=[fake_file],
            db=db_session,
        )

        # 1. Assert response is conversational Q&A without starting background workflow
        assert resp.status == "CONVERSATION"
        assert resp.is_greeting is True
        assert "Point 5 requires" in resp.assistant_reply

        # 2. Assert zero background tasks were queued (meaning zero TDD / Spec creation jobs)
        assert len(bg_tasks.tasks) == 0

        # 3. Assert no new RUNNING workflow run was created
        running_runs = (
            db_session.query(WorkflowRunORM)
            .filter_by(project_id=project.id, current_phase="SPECIFICATION")
            .all()
        )
        assert len(running_runs) == 0

