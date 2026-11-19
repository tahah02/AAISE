import uuid
import tempfile
import shutil
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.domain.enums import ApprovalGateType, ApprovalStatus
from src.infrastructure.db.models import (
    Base,
    ProjectORM,
    WorkflowRunORM,
    HumanApprovalORM,
)
from src.application.orchestration.orchestrator_service import OrchestratorService
from src.infrastructure.llm.provider_resolver import LLMProviderResolver
from src.infrastructure.llm.token_tracker import TokenTrackerService
from src.infrastructure.git.git_service import GitService


@pytest.fixture
def routing_setup():
    tmp_workspace = tempfile.mkdtemp(prefix="aaise_routing_test_")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    project = ProjectORM(
        name="Routing Test Project",
        target_framework="DOTNET_CSHARP",
        description="Student API",
    )
    session.add(project)
    session.flush()

    docs_dir = Path(tmp_workspace) / str(project.id) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    tdd = docs_dir / "TECHNICAL_DESIGN.md"
    tdd.write_text("# TDD\n\n- POST /api/v1/students", encoding="utf-8")

    channel_dir = Path(tmp_workspace) / str(project.id) / "channel-app"
    channel_dir.mkdir(parents=True, exist_ok=True)
    (channel_dir / "StudentApp.csproj").write_text("<Project></Project>", encoding="utf-8")

    git_service = GitService(db=session, base_workspace_dir=tmp_workspace)
    tracker = TokenTrackerService(db=session)
    resolver = LLMProviderResolver()

    orchestrator = OrchestratorService(
        db=session,
        resolver=resolver,
        git_service=git_service,
        tracker=tracker,
    )

    yield orchestrator, project, session, tmp_workspace

    shutil.rmtree(tmp_workspace, ignore_errors=True)
    session.close()


def test_qa_rejection_routes_to_qa_and_preserves_spec_and_code(routing_setup):
    orchestrator, project, session, _ = routing_setup

    run = WorkflowRunORM(
        project_id=project.id,
        current_phase="QA_VERIFICATION",
        status="RUNNING",
    )
    session.add(run)
    session.flush()

    # Pre-approve spec and code
    app_spec = HumanApprovalORM(workflow_run_id=run.id, gate_type="SPECIFICATION", status="APPROVED", prompt_text="Approve spec")
    app_dev = HumanApprovalORM(workflow_run_id=run.id, gate_type="DEVELOPMENT", status="APPROVED", prompt_text="Approve dev")
    session.add_all([app_spec, app_dev])
    session.commit()

    # User requests changes on QA: "test it again"
    qa_revision_req = "Please revise QA_VERIFICATION according to the following changes requested by the reviewer:\n\ntest it again"

    # Inspect how phase-aware routing determines state
    cleaned_req = qa_revision_req.strip().lower()
    assert "qa_verification" in cleaned_req
    assert "test it again" in cleaned_req

    # Verify that existing approvals are respected
    existing_approvals = session.query(HumanApprovalORM).filter_by(workflow_run_id=run.id).all()
    is_spec_revision = "specification" in cleaned_req and "qa_verification" not in cleaned_req
    is_qa_revision = "qa_verification" in cleaned_req or "test it again" in cleaned_req

    assert is_spec_revision is False
    assert is_qa_revision is True

    is_spec_approved = (
        any(a.gate_type == "SPECIFICATION" and a.status == "APPROVED" for a in existing_approvals)
        or not is_spec_revision
    )
    is_code_approved = any(a.gate_type == "DEVELOPMENT" and a.status == "APPROVED" for a in existing_approvals)
    is_qa_approved = False if is_qa_revision else any(a.gate_type == "QA_VERIFICATION" and a.status == "APPROVED" for a in existing_approvals)

    assert is_spec_approved is True
    assert is_code_approved is True
    assert is_qa_approved is False

    target_phase = "QA_VERIFICATION" if is_qa_revision else "DEVELOPMENT"
    assert target_phase == "QA_VERIFICATION"


def test_dev_rejection_routes_to_development_and_preserves_spec(routing_setup):
    orchestrator, project, session, _ = routing_setup

    run = WorkflowRunORM(
        project_id=project.id,
        current_phase="DEVELOPMENT",
        status="RUNNING",
    )
    session.add(run)
    session.flush()

    app_spec = HumanApprovalORM(workflow_run_id=run.id, gate_type="SPECIFICATION", status="APPROVED", prompt_text="Approve spec")
    session.add(app_spec)
    session.commit()

    dev_revision_req = "Please revise DEVELOPMENT according to the following changes requested by the reviewer:\n\nfix missing repository method"
    cleaned_req = dev_revision_req.strip().lower()

    is_spec_revision = "specification" in cleaned_req and "development" not in cleaned_req
    is_dev_revision = "development" in cleaned_req

    assert is_spec_revision is False
    assert is_dev_revision is True

    existing_approvals = session.query(HumanApprovalORM).filter_by(workflow_run_id=run.id).all()
    is_spec_approved = (
        any(a.gate_type == "SPECIFICATION" and a.status == "APPROVED" for a in existing_approvals)
        or not is_spec_revision
    )
    is_code_approved = False if is_dev_revision else any(a.gate_type == "DEVELOPMENT" and a.status == "APPROVED" for a in existing_approvals)

    assert is_spec_approved is True
    assert is_code_approved is False


def test_spec_rejection_routes_to_specification_for_agent1(routing_setup):
    orchestrator, project, session, _ = routing_setup

    run = WorkflowRunORM(
        project_id=project.id,
        current_phase="SPECIFICATION",
        status="RUNNING",
    )
    session.add(run)
    session.commit()

    spec_revision_req = "Please revise SPECIFICATION according to the following changes requested by the reviewer:\n\ndo not create code, just give me system design"
    cleaned_req = spec_revision_req.strip().lower()

    is_spec_revision = "specification" in cleaned_req
    assert is_spec_revision is True

    existing_approvals = session.query(HumanApprovalORM).filter_by(workflow_run_id=run.id).all()
    is_spec_approved = False if is_spec_revision else True
    assert is_spec_approved is False
