import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from src.infrastructure.db.session import get_db
from src.infrastructure.db.models import (
    ProjectORM,
    WorkflowRunORM,
    TokenUsageORM,
    LLMInvocationORM,
    AgentExecutionORM,
    AgentTaskORM,
    HumanApprovalORM,
    TestRunORM,
    TestCaseORM,
    TestResultORM,
    SecurityScanORM,
    SecurityFindingORM,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def get_analytics_overview(
    project_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    project_query = db.query(ProjectORM)
    if project_id:
        project_query = project_query.filter(ProjectORM.id == project_id)
    total_projects = project_query.count()

    run_query = db.query(WorkflowRunORM)
    if project_id:
        run_query = run_query.filter(WorkflowRunORM.project_id == project_id)
    total_runs = run_query.count()

    # Invocations & Token usage
    token_base = (
        db.query(
            func.coalesce(func.sum(TokenUsageORM.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsageORM.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(TokenUsageORM.completion_tokens), 0).label("completion_tokens"),
            func.coalesce(func.sum(TokenUsageORM.estimated_cost_usd), 0.0).label("total_cost"),
        )
        .select_from(TokenUsageORM)
        .join(LLMInvocationORM, TokenUsageORM.llm_invocation_id == LLMInvocationORM.id)
    )
    if project_id:
        token_base = (
            token_base.join(AgentExecutionORM, LLMInvocationORM.agent_execution_id == AgentExecutionORM.id)
            .join(AgentTaskORM, AgentExecutionORM.agent_task_id == AgentTaskORM.id)
            .filter(AgentTaskORM.project_id == project_id)
        )
    token_row = token_base.first()
    total_tokens = int(token_row.total_tokens) if token_row else 0
    prompt_tokens = int(token_row.prompt_tokens) if token_row else 0
    completion_tokens = int(token_row.completion_tokens) if token_row else 0
    total_cost = float(token_row.total_cost) if token_row else 0.0

    # Invocations count & latency
    inv_base = db.query(
        func.count(LLMInvocationORM.id).label("inv_count"),
        func.coalesce(func.avg(LLMInvocationORM.latency_ms), 0.0).label("avg_latency"),
    )
    if project_id:
        inv_base = (
            inv_base.join(AgentExecutionORM, LLMInvocationORM.agent_execution_id == AgentExecutionORM.id)
            .join(AgentTaskORM, AgentExecutionORM.agent_task_id == AgentTaskORM.id)
            .filter(AgentTaskORM.project_id == project_id)
        )
    inv_row = inv_base.first()
    total_invocations = int(inv_row.inv_count) if inv_row else 0
    avg_latency_ms = round(float(inv_row.avg_latency), 1) if inv_row else 0.0

    # QA Test runs
    qa_run_base = db.query(TestRunORM)
    if project_id:
        qa_run_base = qa_run_base.filter(TestRunORM.project_id == project_id)
    qa_runs = qa_run_base.all()
    qa_total_runs = len(qa_runs)
    qa_passed_runs = sum(1 for r in qa_runs if r.status == "PASSED")
    qa_failed_runs = sum(1 for r in qa_runs if r.status == "FAILED")

    # QA Test results
    res_base = db.query(TestResultORM).join(TestRunORM, TestResultORM.test_run_id == TestRunORM.id)
    if project_id:
        res_base = res_base.filter(TestRunORM.project_id == project_id)
    all_results = res_base.all()
    qa_total_tests = len(all_results)
    qa_passed_tests = sum(1 for r in all_results if r.status == "PASSED")
    qa_failed_tests = sum(1 for r in all_results if r.status == "FAILED")
    qa_pass_rate = round((qa_passed_tests / qa_total_tests * 100), 1) if qa_total_tests > 0 else 0.0

    # Security
    sec_base = db.query(SecurityScanORM)
    if project_id:
        sec_base = sec_base.filter(SecurityScanORM.project_id == project_id)
    scans = sec_base.all()
    sec_total_scans = len(scans)
    sec_passed_scans = sum(1 for s in scans if s.status == "PASSED")

    finding_base = db.query(SecurityFindingORM).join(SecurityScanORM, SecurityFindingORM.security_scan_id == SecurityScanORM.id)
    if project_id:
        finding_base = finding_base.filter(SecurityScanORM.project_id == project_id)
    all_findings = finding_base.all()
    sec_critical = sum(1 for f in all_findings if f.severity.upper() == "CRITICAL")
    sec_high = sum(1 for f in all_findings if f.severity.upper() == "HIGH")
    sec_medium = sum(1 for f in all_findings if f.severity.upper() == "MEDIUM")
    sec_low = sum(1 for f in all_findings if f.severity.upper() == "LOW")

    # Approvals
    app_base = db.query(HumanApprovalORM).join(WorkflowRunORM, HumanApprovalORM.workflow_run_id == WorkflowRunORM.id)
    if project_id:
        app_base = app_base.filter(WorkflowRunORM.project_id == project_id)
    approvals = app_base.all()
    app_total = len(approvals)
    app_pending = sum(1 for a in approvals if a.status == "PENDING")
    app_approved = sum(1 for a in approvals if a.status == "APPROVED")
    app_rejected = sum(1 for a in approvals if a.status == "REJECTED")

    return {
        "total_projects": total_projects,
        "total_runs": total_runs,
        "tokens": {
            "total": total_tokens,
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "cost_usd": round(total_cost, 6),
            "invocations": total_invocations,
            "avg_latency_ms": avg_latency_ms,
            "avg_latency_sec": round(avg_latency_ms / 1000.0, 2),
        },
        "qa": {
            "total_runs": qa_total_runs,
            "passed_runs": qa_passed_runs,
            "failed_runs": qa_failed_runs,
            "total_tests": qa_total_tests,
            "passed_tests": qa_passed_tests,
            "failed_tests": qa_failed_tests,
            "pass_rate_pct": qa_pass_rate,
        },
        "security": {
            "total_scans": sec_total_scans,
            "passed_scans": sec_passed_scans,
            "total_findings": len(all_findings),
            "critical": sec_critical,
            "high": sec_high,
            "medium": sec_medium,
            "low": sec_low,
        },
        "approvals": {
            "total": app_total,
            "pending": app_pending,
            "approved": app_approved,
            "rejected": app_rejected,
        },
    }


@router.get("/tokens")
def get_analytics_tokens(
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    # Query all joined rows
    q = (
        db.query(
            LLMInvocationORM.id.label("inv_id"),
            LLMInvocationORM.provider,
            LLMInvocationORM.model_name,
            LLMInvocationORM.latency_ms,
            LLMInvocationORM.success,
            LLMInvocationORM.error_message,
            LLMInvocationORM.invoked_at,
            TokenUsageORM.prompt_tokens,
            TokenUsageORM.completion_tokens,
            TokenUsageORM.total_tokens,
            TokenUsageORM.estimated_cost_usd,
            AgentTaskORM.agent_name,
            AgentTaskORM.task_type,
            ProjectORM.id.label("project_id"),
            ProjectORM.name.label("project_name"),
        )
        .select_from(LLMInvocationORM)
        .outerjoin(TokenUsageORM, LLMInvocationORM.id == TokenUsageORM.llm_invocation_id)
        .outerjoin(AgentExecutionORM, LLMInvocationORM.agent_execution_id == AgentExecutionORM.id)
        .outerjoin(AgentTaskORM, AgentExecutionORM.agent_task_id == AgentTaskORM.id)
        .outerjoin(ProjectORM, AgentTaskORM.project_id == ProjectORM.id)
    )

    if project_id:
        q = q.filter(ProjectORM.id == project_id)

    q = q.order_by(desc(LLMInvocationORM.invoked_at))
    rows = q.limit(limit).all()

    # Aggregations
    by_provider: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    by_agent: dict[str, dict[str, Any]] = {}

    invocations = []
    tot_prompt = 0
    tot_completion = 0
    tot_tokens = 0
    tot_cost = 0.0

    for r in rows:
        p_toks = r.prompt_tokens or 0
        c_toks = r.completion_tokens or 0
        t_toks = r.total_tokens or (p_toks + c_toks)
        cost = float(r.estimated_cost_usd or 0.0)
        provider = r.provider or "unknown"
        model = r.model_name or "unknown"
        agent = r.agent_name or "AAISE Platform"

        tot_prompt += p_toks
        tot_completion += c_toks
        tot_tokens += t_toks
        tot_cost += cost

        # Provider group
        if provider not in by_provider:
            by_provider[provider] = {"provider": provider, "tokens": 0, "cost_usd": 0.0, "calls": 0, "total_latency_ms": 0}
        by_provider[provider]["tokens"] += t_toks
        by_provider[provider]["cost_usd"] += cost
        by_provider[provider]["calls"] += 1
        by_provider[provider]["total_latency_ms"] += (r.latency_ms or 0)

        # Model group
        if model not in by_model:
            by_model[model] = {"model": model, "provider": provider, "tokens": 0, "cost_usd": 0.0, "calls": 0}
        by_model[model]["tokens"] += t_toks
        by_model[model]["cost_usd"] += cost
        by_model[model]["calls"] += 1

        # Agent group
        if agent not in by_agent:
            by_agent[agent] = {"agent_name": agent, "tokens": 0, "cost_usd": 0.0, "calls": 0}
        by_agent[agent]["tokens"] += t_toks
        by_agent[agent]["cost_usd"] += cost
        by_agent[agent]["calls"] += 1

        invocations.append({
            "id": str(r.inv_id),
            "provider": provider,
            "model_name": model,
            "latency_ms": r.latency_ms or 0,
            "latency_sec": round((r.latency_ms or 0) / 1000.0, 2),
            "success": r.success,
            "error_message": r.error_message,
            "prompt_tokens": p_toks,
            "completion_tokens": c_toks,
            "total_tokens": t_toks,
            "cost_usd": round(cost, 6),
            "invoked_at": r.invoked_at.isoformat() if r.invoked_at else None,
            "agent_name": agent,
            "task_type": r.task_type,
            "project_id": str(r.project_id) if r.project_id else None,
            "project_name": r.project_name or "N/A",
        })

    # Finalize provider averages
    provider_list = []
    for p_data in by_provider.values():
        calls = p_data["calls"]
        provider_list.append({
            "provider": p_data["provider"],
            "tokens": p_data["tokens"],
            "cost_usd": round(p_data["cost_usd"], 6),
            "calls": calls,
            "avg_latency_ms": round(p_data["total_latency_ms"] / calls, 1) if calls > 0 else 0,
        })

    model_list = [
        {
            "model": m["model"],
            "provider": m["provider"],
            "tokens": m["tokens"],
            "cost_usd": round(m["cost_usd"], 6),
            "calls": m["calls"],
        }
        for m in by_model.values()
    ]

    agent_list = [
        {
            "agent_name": a["agent_name"],
            "tokens": a["tokens"],
            "cost_usd": round(a["cost_usd"], 6),
            "calls": a["calls"],
        }
        for a in by_agent.values()
    ]

    return {
        "totals": {
            "prompt_tokens": tot_prompt,
            "completion_tokens": tot_completion,
            "total_tokens": tot_tokens,
            "cost_usd": round(tot_cost, 6),
            "calls": len(rows),
        },
        "by_provider": sorted(provider_list, key=lambda x: x["tokens"], reverse=True),
        "by_model": sorted(model_list, key=lambda x: x["tokens"], reverse=True),
        "by_agent": sorted(agent_list, key=lambda x: x["tokens"], reverse=True),
        "invocations": invocations,
    }


@router.get("/qa-reports")
def get_analytics_qa_reports(
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    q = (
        db.query(TestRunORM, ProjectORM.name.label("project_name"))
        .outerjoin(ProjectORM, TestRunORM.project_id == ProjectORM.id)
    )
    if project_id:
        q = q.filter(TestRunORM.project_id == project_id)

    runs = q.order_by(desc(TestRunORM.executed_at)).limit(limit).all()

    run_list = []
    for run, proj_name in runs:
        # Load results with test case info
        results = (
            db.query(TestResultORM, TestCaseORM)
            .outerjoin(TestCaseORM, TestResultORM.test_case_id == TestCaseORM.id)
            .filter(TestResultORM.test_run_id == run.id)
            .all()
        )
        res_list = []
        for res, tc in results:
            res_list.append({
                "id": str(res.id),
                "test_key": tc.test_key if tc else "TC",
                "category": tc.category if tc else "API",
                "endpoint": tc.endpoint if tc else "N/A",
                "http_method": tc.http_method if tc else "GET",
                "expected_status": tc.expected_status if tc else 200,
                "actual_status_code": res.actual_status_code,
                "status": res.status,
                "response_body": res.response_body,
            })

        run_list.append({
            "id": str(run.id),
            "project_id": str(run.project_id),
            "project_name": proj_name or "AAISE Project",
            "execution_type": run.execution_type,
            "passed_count": run.passed_count,
            "failed_count": run.failed_count,
            "total_count": run.passed_count + run.failed_count,
            "status": run.status,
            "executed_at": run.executed_at.isoformat() if run.executed_at else None,
            "results": res_list,
        })

    return {"test_runs": run_list}


@router.get("/security")
def get_analytics_security(
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    q = (
        db.query(SecurityScanORM, ProjectORM.name.label("project_name"))
        .outerjoin(ProjectORM, SecurityScanORM.project_id == ProjectORM.id)
    )
    if project_id:
        q = q.filter(SecurityScanORM.project_id == project_id)

    scans = q.order_by(desc(SecurityScanORM.scanned_at)).limit(limit).all()

    scan_list = []
    for scan, proj_name in scans:
        findings = (
            db.query(SecurityFindingORM)
            .filter(SecurityFindingORM.security_scan_id == scan.id)
            .order_by(SecurityFindingORM.severity.asc())
            .all()
        )
        findings_list = [
            {
                "id": str(f.id),
                "severity": f.severity,
                "vulnerability_type": f.vulnerability_type,
                "target_repo": f.target_repo,
                "file_path": f.file_path,
                "line_number": f.line_number,
                "description": f.description,
                "remediation_advice": f.remediation_advice,
                "status": f.status,
                "discovered_at": f.discovered_at.isoformat() if f.discovered_at else None,
            }
            for f in findings
        ]

        scan_list.append({
            "id": str(scan.id),
            "project_id": str(scan.project_id),
            "project_name": proj_name or "AAISE Project",
            "scanner_type": scan.scanner_type,
            "status": scan.status,
            "scanned_at": scan.scanned_at.isoformat() if scan.scanned_at else None,
            "findings_count": len(findings_list),
            "findings": findings_list,
        })

    return {"scans": scan_list}


@router.get("/approvals")
def get_analytics_approvals(
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, le=100),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    q = (
        db.query(
            HumanApprovalORM,
            WorkflowRunORM.project_id,
            ProjectORM.name.label("project_name"),
        )
        .join(WorkflowRunORM, HumanApprovalORM.workflow_run_id == WorkflowRunORM.id)
        .outerjoin(ProjectORM, WorkflowRunORM.project_id == ProjectORM.id)
    )
    if project_id:
        q = q.filter(WorkflowRunORM.project_id == project_id)

    apps = q.order_by(desc(HumanApprovalORM.requested_at)).limit(limit).all()

    approval_list = []
    for app, proj_id, proj_name in apps:
        approval_list.append({
            "id": str(app.id),
            "workflow_run_id": str(app.workflow_run_id),
            "project_id": str(proj_id) if proj_id else None,
            "project_name": proj_name or "AAISE Project",
            "gate_type": app.gate_type,
            "status": app.status,
            "prompt_text": app.prompt_text,
            "reviewer_comments": app.reviewer_comments,
            "requested_at": app.requested_at.isoformat() if app.requested_at else None,
            "resolved_at": app.resolved_at.isoformat() if app.resolved_at else None,
        })

    return {"approvals": approval_list}
