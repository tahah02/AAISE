import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.infrastructure.db.models import (
    Base,
    ProjectORM,
    AgentTaskORM,
    AgentExecutionORM,
    LLMInvocationORM,
    TokenUsageORM,
    WorkflowRunORM,
    TestRunORM,
    TestCaseORM,
    TestResultORM,
    HumanApprovalORM,
)
from src.api.routes.analytics import (
    get_analytics_overview,
    get_analytics_tokens,
    get_analytics_qa_reports,
    get_analytics_security,
    get_analytics_approvals,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_analytics_endpoints_empty_db(in_memory_db):
    ov = get_analytics_overview(None, in_memory_db)
    assert ov["total_projects"] == 0
    assert ov["tokens"]["total"] == 0
    assert ov["qa"]["total_runs"] == 0
    assert ov["security"]["total_scans"] == 0
    assert ov["approvals"]["total"] == 0

    tok = get_analytics_tokens(None, 100, in_memory_db)
    assert tok["totals"]["total_tokens"] == 0
    assert len(tok["invocations"]) == 0

    qa = get_analytics_qa_reports(None, 20, in_memory_db)
    assert len(qa["test_runs"]) == 0

    sec = get_analytics_security(None, 20, in_memory_db)
    assert len(sec["scans"]) == 0

    app = get_analytics_approvals(None, 20, in_memory_db)
    assert len(app["approvals"]) == 0


def test_analytics_with_seeded_data_and_dual_duration(in_memory_db):
    proj = ProjectORM(name="SRS2", target_framework="DOTNET_CSHARP")
    in_memory_db.add(proj)
    in_memory_db.flush()

    task = AgentTaskORM(
        project_id=proj.id,
        agent_name="Agent 3: Main Coding Agent",
        task_type="IMPLEMENTATION",
        status="COMPLETED",
    )
    in_memory_db.add(task)
    in_memory_db.flush()

    start_time = datetime.datetime(2026, 11, 18, 14, 0, 0)
    finish_time = datetime.datetime(2026, 11, 18, 14, 3, 42)  # 222s = 3m 42s
    execution = AgentExecutionORM(
        agent_task_id=task.id,
        status="SUCCESS",
        started_at=start_time,
        finished_at=finish_time,
    )
    in_memory_db.add(execution)
    in_memory_db.flush()

    inv = LLMInvocationORM(
        agent_execution_id=execution.id,
        provider="Gemini",
        model_name="gemini-3.5-flash-lite",
        latency_ms=16000,  # 16s raw LLM latency
        success=True,
        invoked_at=start_time,
    )
    in_memory_db.add(inv)
    in_memory_db.flush()

    tok = TokenUsageORM(
        llm_invocation_id=inv.id,
        prompt_tokens=5000,
        completion_tokens=1500,
        total_tokens=6500,
        estimated_cost_usd=0.0015,
    )
    in_memory_db.add(tok)

    test_run = TestRunORM(
        project_id=proj.id,
        execution_type="CONTRACT",
        passed_count=0,
        failed_count=1,
        status="FAILED",
    )
    in_memory_db.add(test_run)

    in_memory_db.commit()

    # Query overview
    ov = get_analytics_overview(proj.id, in_memory_db)
    assert ov["total_projects"] == 1
    assert ov["tokens"]["total"] == 6500
    assert ov["tokens"]["invocations"] == 1
    assert ov["tokens"]["avg_latency_sec"] == 16.0
    assert ov["qa"]["total_runs"] == 1
    assert ov["qa"]["failed_runs"] == 1

    # Query tokens and verify dual duration
    tok_res = get_analytics_tokens(proj.id, 100, in_memory_db)
    assert tok_res["totals"]["total_tokens"] == 6500
    assert len(tok_res["invocations"]) == 1
    inv_item = tok_res["invocations"][0]
    assert inv_item["llm_latency_sec"] == 16.0
    assert inv_item["task_duration_sec"] == 222.0
    assert inv_item["task_duration_label"] == "3m 42s"

