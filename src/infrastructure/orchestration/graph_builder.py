import uuid
from typing import Any, Callable
from langgraph.graph import END, StateGraph

from src.domain.enums import AgentType
from src.domain.workflow_state import WorkflowState


def _is_agent_enabled(state: WorkflowState, agent_num: int) -> bool:
    enabled = state.get("enabled_agents") or {}
    if agent_num == 1:
        return bool(
            enabled.get("AGENT_1", enabled.get("DOC_REVIEWER", enabled.get(AgentType.DOC_REVIEWER.name, True)))
        )
    if agent_num == 2:
        return bool(
            enabled.get("AGENT_2", enabled.get("MOCK_DEVELOPER", enabled.get(AgentType.MOCK_DEVELOPER.name, True)))
        )
    if agent_num == 3:
        return bool(
            enabled.get("AGENT_3", enabled.get("MAIN_CODING", enabled.get(AgentType.MAIN_CODING.name, True)))
        )
    if agent_num == 4:
        return bool(
            enabled.get("AGENT_4", enabled.get("QA_ENGINEER", enabled.get(AgentType.QA_ENGINEER.name, True)))
        )
    if agent_num == 5:
        return bool(
            enabled.get("AGENT_5", enabled.get("SECURITY_REVIEWER", enabled.get(AgentType.SECURITY_REVIEWER.name, True)))
        )
    return True


def route_entry(state: WorkflowState) -> str:
    if state.get("is_cancelled"):
        return END
    # If security is already approved or project is at release stage, go straight to release
    if state.get("security_approved") or state.get("current_phase") == "RELEASE":
        return "release_approval_gate"
    if state.get("qa_approved") and not state.get("security_approved"):
        return "check_security"
    if _is_agent_enabled(state, 1) and not state.get("spec_approved"):
        return "doc_reviewer"
    if _is_agent_enabled(state, 2) and state.get("requires_mock_vendor", True) and not state.get("mock_approved"):
        return "mock_developer"
    if _is_agent_enabled(state, 3) and not state.get("code_approved"):
        return "main_coder"
    if _is_agent_enabled(state, 4) and not state.get("qa_approved"):
        return "qa_engineer"
    return "check_security"


def route_after_spec_approval(state: WorkflowState) -> str:
    if state.get("is_cancelled"):
        return END
    # If human approval has not been granted yet:
    # If revision feedback comments were provided, loop back to doc_reviewer to revise the spec;
    # otherwise stop workflow and wait for human approval (interrupt/END).
    if not state.get("spec_approved", False):
        comments = state.get("spec_approval_comments")
        if comments:
            req = state.get("user_requirement", "")
            if "Human Revision Request" not in req:
                state["user_requirement"] = f"{req}\n\n[Human Revision Request]: {comments}"
            # Clear comments so doc_reviewer executes once for this revision and pauses at END
            state["spec_approval_comments"] = None
            return "doc_reviewer" if _is_agent_enabled(state, 1) else END
        return END

    if _is_agent_enabled(state, 2) and state.get("requires_mock_vendor", True):
        return "mock_developer"
    if _is_agent_enabled(state, 3):
        return "main_coder"
    if _is_agent_enabled(state, 4):
        return "qa_engineer"
    return "check_security"


def route_after_mock_approval(state: WorkflowState) -> str:
    if state.get("is_cancelled"):
        return END
    if not state.get("mock_approved", False):
        comments = state.get("mock_approval_comments")
        if comments:
            state["mock_approval_comments"] = None
            return "mock_developer" if _is_agent_enabled(state, 2) else END
        return END

    if _is_agent_enabled(state, 3):
        return "main_coder"
    if _is_agent_enabled(state, 4):
        return "qa_engineer"
    return "check_security"


def route_after_code_approval(state: WorkflowState) -> str:
    if state.get("is_cancelled"):
        return END
    if not state.get("code_approved", False):
        comments = state.get("code_approval_comments")
        if comments:
            state["code_approval_comments"] = None
            return "main_coder" if _is_agent_enabled(state, 3) else END
        return END

    if _is_agent_enabled(state, 4):
        return "qa_engineer"
    return "check_security"


def route_after_qa_approval(state: WorkflowState) -> str:
    if state.get("is_cancelled"):
        return END
    qa_status = state.get("qa_status", "PASSED")
    remediation_count = state.get("defect_remediation_count", 0)

    # Remediation loop: strictly capped at maximum 2 cycles (attempts 1 and 2 only)
    if str(qa_status).startswith("FAILED") and remediation_count < 2 and _is_agent_enabled(state, 3):
        return "remediate_defect"

    if not state.get("qa_approved", False):
        comments = state.get("qa_approval_comments")
        if comments:
            state["qa_approval_comments"] = None
            return "main_coder" if _is_agent_enabled(state, 3) else END
        return END

    return "check_security"


def route_after_security_approval(state: WorkflowState) -> str:
    if state.get("is_cancelled"):
        return END
    if not state.get("security_approved", False):
        comments = state.get("security_approval_comments")
        if comments:
            state["security_approval_comments"] = None
            return "main_coder" if _is_agent_enabled(state, 3) else END
        return END

    return "release_approval_gate"


def route_check_security(state: WorkflowState) -> str:
    if _is_agent_enabled(state, 5):
        return "security_reviewer"
    return "release_approval_gate"


def audit_qa_skip_node(state: WorkflowState) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if not state.get("qa_status"):
        updates["qa_status"] = "SKIPPED"
        updates["qa_passed_count"] = 0
        updates["qa_failed_count"] = 0
    if not state.get("security_status"):
        if not _is_agent_enabled(state, 5):
            updates["security_status"] = "NOT_SCANNED"
            updates["security_findings_count"] = 0
    return updates


def remediate_defect_node(state: WorkflowState) -> dict[str, Any]:
    count = state.get("defect_remediation_count", 0) + 1
    return {
        "defect_remediation_count": count,
        "iteration": count,
        "current_phase": "DEFECT_REMEDIATION",
    }


class WorkflowGraphBuilder:
    def __init__(
        self,
        doc_reviewer_fn: Callable[[WorkflowState], WorkflowState] | None = None,
        mock_developer_fn: Callable[[WorkflowState], WorkflowState] | None = None,
        main_coder_fn: Callable[[WorkflowState], WorkflowState] | None = None,
        qa_engineer_fn: Callable[[WorkflowState], WorkflowState] | None = None,
        security_reviewer_fn: Callable[[WorkflowState], WorkflowState] | None = None,
        release_gate_fn: Callable[[WorkflowState], WorkflowState] | None = None,
    ) -> None:
        self.doc_reviewer_fn = doc_reviewer_fn or (lambda s: {**s, "current_phase": "SPECIFICATION"})
        self.mock_developer_fn = mock_developer_fn or (lambda s: {**s, "current_phase": "MOCK_DEVELOPMENT"})
        self.main_coder_fn = main_coder_fn or (lambda s: {**s, "current_phase": "DEVELOPMENT"})
        self.qa_engineer_fn = qa_engineer_fn or (lambda s: {**s, "current_phase": "QA_VERIFICATION"})
        self.security_reviewer_fn = security_reviewer_fn or (lambda s: {**s, "current_phase": "SECURITY_AUDIT"})
        self.release_gate_fn = release_gate_fn or (lambda s: {**s, "current_phase": "RELEASE", "is_completed": True})

    def build_graph(self) -> Any:
        workflow = StateGraph(WorkflowState)

        # 1. Add Nodes
        workflow.add_node("doc_reviewer", self.doc_reviewer_fn)
        workflow.add_node("spec_approval_gate", lambda s: {**s, "current_phase": "SPEC_APPROVAL"})
        workflow.add_node("mock_developer", self.mock_developer_fn)
        workflow.add_node("mock_approval_gate", lambda s: {**s, "current_phase": "MOCK_APPROVAL"})
        workflow.add_node("main_coder", self.main_coder_fn)
        workflow.add_node("code_approval_gate", lambda s: {**s, "current_phase": "CODE_APPROVAL"})
        workflow.add_node("qa_engineer", self.qa_engineer_fn)
        workflow.add_node("qa_approval_gate", lambda s: {**s, "current_phase": "QA_APPROVAL"})
        workflow.add_node("remediate_defect", remediate_defect_node)
        workflow.add_node("security_reviewer", self.security_reviewer_fn)
        workflow.add_node("security_approval_gate", lambda s: {**s, "current_phase": "SECURITY_APPROVAL"})
        workflow.add_node("release_approval_gate", self.release_gate_fn)

        # Audit node for honest status recording when QA or Security are skipped
        workflow.add_node("check_security", audit_qa_skip_node)

        # 2. Add Edges & Conditional Routing
        workflow.set_conditional_entry_point(
            route_entry,
            {
                "doc_reviewer": "doc_reviewer",
                "mock_developer": "mock_developer",
                "main_coder": "main_coder",
                "qa_engineer": "qa_engineer",
                "check_security": "check_security",
            },
        )
        workflow.add_edge("doc_reviewer", "spec_approval_gate")

        # Dynamic routing after Agent 1 Spec Approval Gate
        workflow.add_conditional_edges(
            "spec_approval_gate",
            route_after_spec_approval,
            {
                "doc_reviewer": "doc_reviewer",
                "mock_developer": "mock_developer",
                "main_coder": "main_coder",
                "qa_engineer": "qa_engineer",
                "check_security": "check_security",
                END: END,
            },
        )

        # Dynamic routing after Agent 2 Mock Approval Gate
        workflow.add_edge("mock_developer", "mock_approval_gate")
        workflow.add_conditional_edges(
            "mock_approval_gate",
            route_after_mock_approval,
            {
                "mock_developer": "mock_developer",
                "main_coder": "main_coder",
                "qa_engineer": "qa_engineer",
                "check_security": "check_security",
                END: END,
            },
        )

        # Dynamic routing after Agent 3 Main Coder Approval Gate
        workflow.add_edge("main_coder", "code_approval_gate")
        workflow.add_conditional_edges(
            "code_approval_gate",
            route_after_code_approval,
            {
                "main_coder": "main_coder",
                "qa_engineer": "qa_engineer",
                "check_security": "check_security",
                END: END,
            },
        )

        # Dynamic routing after Agent 4 QA Approval Gate
        workflow.add_edge("qa_engineer", "qa_approval_gate")
        workflow.add_conditional_edges(
            "qa_approval_gate",
            route_after_qa_approval,
            {
                "remediate_defect": "remediate_defect",
                "main_coder": "main_coder",
                "check_security": "check_security",
                END: END,
            },
        )
        workflow.add_edge("remediate_defect", "main_coder")

        # Dynamic routing to Security or Release Gate
        workflow.add_conditional_edges(
            "check_security",
            route_check_security,
            {
                "security_reviewer": "security_reviewer",
                "release_approval_gate": "release_approval_gate",
            },
        )

        # Dynamic routing after Agent 5 Security Reviewer Approval Gate
        workflow.add_edge("security_reviewer", "security_approval_gate")
        workflow.add_conditional_edges(
            "security_approval_gate",
            route_after_security_approval,
            {
                "main_coder": "main_coder",
                "release_approval_gate": "release_approval_gate",
                END: END,
            },
        )

        workflow.add_edge("release_approval_gate", END)

        return workflow.compile()
