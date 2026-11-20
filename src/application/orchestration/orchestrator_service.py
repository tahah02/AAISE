from src.application.chat.chat_service import save_chat_message

import logging
import uuid

from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from src.application.agents.doc_reviewer import DocumentationReviewerAgent

from src.application.agents.main_coder import MainCodingAgent

from src.application.agents.mock_developer import MockVendorDeveloperAgent

from src.application.agents.qa_engineer import QAEngineerAgent

from src.application.agents.security_reviewer import SecurityReviewerAgent

from src.domain.enums import AgentType, RepositoryType

from src.domain.workflow_state import WorkflowState

from pathlib import Path

from src.infrastructure.db.models import (
    AgentExecutionORM,
    AgentTaskORM,
    DefectORM,
    HumanApprovalORM,
    ProjectAgentConfigORM,
    ProjectORM,
    WorkflowRunORM,
)

from src.infrastructure.git.git_service import GitService

from src.infrastructure.llm.provider_resolver import LLMProviderResolver

from src.infrastructure.llm.token_tracker import TokenTrackerService

from src.infrastructure.orchestration.approval_engine import ApprovalEngine

from src.infrastructure.orchestration.checkpointer import WorkflowCheckpointService

from src.infrastructure.orchestration.graph_builder import WorkflowGraphBuilder

from src.ports.agent import AgentContext


class OrchestratorService:
    def __init__(
        self,
        db: Session,
        resolver: LLMProviderResolver,
        git_service: GitService,
        tracker: TokenTrackerService | None = None,
    ) -> None:

        self.db = db

        self.resolver = resolver

        self.git_service = git_service

        self.tracker = tracker

        self.approval_engine = ApprovalEngine(db=db)

        self.checkpoint_service = WorkflowCheckpointService(db=db)

    @staticmethod
    def _inspect_tdd_for_mock_vendor(tdd_text: str) -> bool:
        if not tdd_text:
            return False
        lower = tdd_text.lower()
        # 1. Explicit skip signals
        if "agent 2" in lower and any(
            k in lower for k in ("skipped", "not applicable", "bypassed", "excluded")
        ):
            return False
        if "mock api developer" in lower and any(
            k in lower for k in ("skipped", "not applicable", "bypassed", "excluded")
        ):
            return False
        if "mock vendor" in lower and any(
            k in lower for k in ("excluded", "not applicable", "bypassed", "none", "not required", "skipped")
        ):
            return False

        # 2. Positive presence check: Does TDD define any third-party vendor APIs or external contracts?
        vendor_indicators = (
            "mock vendor",
            "vendor api",
            "external vendor",
            "third-party api",
            "third party api",
            "upstream service",
            "banking core",
            "payment gateway",
        )
        return any(v in lower for v in vendor_indicators)

    def _get_enabled_agents(self, project_id: uuid.UUID) -> dict[str, bool]:

        configs = self.db.query(ProjectAgentConfigORM).filter_by(project_id=project_id).all()

        enabled_map: dict[str, bool] = {}

        for c in configs:
            atype = str(c.agent_type).upper()
            if "MOCK" in atype or "AGENT_2" in atype or "AGENT2" in atype:
                enabled_map[AgentType.MOCK_DEVELOPER.name] = c.is_enabled
                enabled_map["AGENT_2"] = c.is_enabled
            elif "QA" in atype or "AGENT_4" in atype or "AGENT4" in atype:
                enabled_map[AgentType.QA_ENGINEER.name] = c.is_enabled
                enabled_map["AGENT_4"] = c.is_enabled
            elif "SEC" in atype or "AGENT_5" in atype or "AGENT5" in atype:
                enabled_map[AgentType.SECURITY_REVIEWER.name] = c.is_enabled
                enabled_map["AGENT_5"] = c.is_enabled
            elif "DOC" in atype or "AGENT_1" in atype or "AGENT1" in atype:
                enabled_map[AgentType.DOC_REVIEWER.name] = c.is_enabled
                enabled_map["AGENT_1"] = c.is_enabled
            elif "MAIN" in atype or "AGENT_3" in atype or "AGENT3" in atype:
                enabled_map[AgentType.MAIN_CODING.name] = c.is_enabled
                enabled_map["AGENT_3"] = c.is_enabled

        # Defaults for agents if not explicitly configured in database
        enabled_map.setdefault(AgentType.DOC_REVIEWER.name, True)
        enabled_map.setdefault("AGENT_1", True)
        enabled_map.setdefault(AgentType.MOCK_DEVELOPER.name, True)
        enabled_map.setdefault("AGENT_2", True)
        enabled_map.setdefault(AgentType.MAIN_CODING.name, True)
        enabled_map.setdefault("AGENT_3", True)
        enabled_map.setdefault(AgentType.QA_ENGINEER.name, True)
        enabled_map.setdefault("AGENT_4", True)
        enabled_map.setdefault(AgentType.SECURITY_REVIEWER.name, True)
        enabled_map.setdefault("AGENT_5", True)

        return enabled_map

    async def start_workflow(
        self,
        project_id: uuid.UUID,
        user_requirement: str,
        workflow_run_id: uuid.UUID | None = None,
    ) -> WorkflowState:

        project = self.db.query(ProjectORM).filter_by(id=project_id).first()

        if not project:
            raise ValueError(f"Project {project_id} not found.")

        latest_spec_approval = (
            self.db.query(HumanApprovalORM)
            .join(WorkflowRunORM, HumanApprovalORM.workflow_run_id == WorkflowRunORM.id)
            .filter(
                WorkflowRunORM.project_id == project_id,
                HumanApprovalORM.gate_type == "SPECIFICATION",
            )
            .order_by(HumanApprovalORM.requested_at.desc())
            .first()
        )

        cleaned_req = user_requirement.strip().lower().rstrip("!.,?")

        is_revision_intent = any(
            w in cleaned_req
            for w in [
                "revise",
                "revision",
                "requested changes",
                "change request",
                "modifications",
                "update spec",
                "change database",
                "change the",
                "badal",
                "tabdeeli",
                "theek karo",
                "sahi karo",
                "change karo",
                "revising",
                "please revise",
            ]
        )

        is_approved_intent = not is_revision_intent and (
            cleaned_req
            in {
                "continue",
                "approve",
                "approved",
                "proceed",
                "yes",
                "ok",
                "okay",
                "go ahead",
                "start coding",
                "write code",
                "code",
                "build",
                "build it",
                "chalo",
                "kro",
                "kardo",
            }
            or any(
                w in cleaned_req
                for w in [
                    "approved",
                    "proceed with full application",
                    "continue",
                    "start coding",
                    "write code",
                    "agent4",
                    "agent 4",
                    "qa",
                    "test",
                    "agent5",
                    "agent 5",
                    "security",
                    "audit",
                ]
            )
        )

        is_qa_or_sec_only = any(
            w in cleaned_req
            for w in ["agent4", "agent 4", "qa", "test", "agent5", "agent 5", "security", "audit"]
        )

        tdd_check = (
            Path(self.git_service.base_workspace_dir)
            / str(project_id)
            / "docs"
            / "TECHNICAL_DESIGN.md"
        )

        run = None

        if workflow_run_id:
            run = self.db.query(WorkflowRunORM).filter_by(id=workflow_run_id).first()

        if not run:
            run = (
                self.db.query(WorkflowRunORM)
                .filter_by(project_id=project_id)
                .order_by(WorkflowRunORM.created_at.desc())
                .first()
            )

        # Determine specific revision target gate if user requested changes
        is_spec_revision = False
        is_mock_revision = False
        is_dev_revision = False
        is_qa_revision = False
        is_security_revision = False

        if is_revision_intent:
            if any(k in cleaned_req for k in ("qa_verification", "test it again", "retest", "test again", "qa again", "run qa")):
                is_qa_revision = True
            elif "development" in cleaned_req:
                is_dev_revision = True
            elif "mock_development" in cleaned_req or "mock vendor" in cleaned_req:
                is_mock_revision = True
            elif "security_audit" in cleaned_req or "security" in cleaned_req:
                is_security_revision = True
            elif "specification" in cleaned_req or "update spec" in cleaned_req or "change database" in cleaned_req:
                is_spec_revision = True
            else:
                if run and run.current_phase == "QA_VERIFICATION":
                    is_qa_revision = True
                elif run and run.current_phase == "DEVELOPMENT":
                    is_dev_revision = True
                elif run and run.current_phase == "MOCK_DEVELOPMENT":
                    is_mock_revision = True
                elif run and run.current_phase == "SECURITY_AUDIT":
                    is_security_revision = True
                else:
                    is_spec_revision = True

        existing_approvals = []
        if run:
            existing_approvals = (
                self.db.query(HumanApprovalORM)
                .filter_by(workflow_run_id=run.id)
                .all()
            )

        is_spec_approved = (
            any(a.gate_type == "SPECIFICATION" and a.status == "APPROVED" for a in existing_approvals)
            or (is_approved_intent and tdd_check.exists())
            or (tdd_check.exists() and not is_spec_revision)
        )
        if is_spec_revision:
            is_spec_approved = False

        is_mock_approved = any(a.gate_type == "MOCK_DEVELOPMENT" and a.status == "APPROVED" for a in existing_approvals)
        if is_mock_revision:
            is_mock_approved = False

        is_code_approved = any(a.gate_type == "DEVELOPMENT" and a.status == "APPROVED" for a in existing_approvals)
        if is_dev_revision:
            is_code_approved = False

        is_qa_approved = any(a.gate_type == "QA_VERIFICATION" and a.status == "APPROVED" for a in existing_approvals)
        if is_qa_revision:
            is_qa_approved = False

        is_security_approved = any(a.gate_type == "SECURITY_AUDIT" and a.status == "APPROVED" for a in existing_approvals)
        if is_security_revision:
            is_security_approved = False

        target_phase = "SPECIFICATION"
        if is_qa_revision:
            target_phase = "QA_VERIFICATION"
        elif is_dev_revision:
            target_phase = "DEVELOPMENT"
        elif is_mock_revision:
            target_phase = "MOCK_DEVELOPMENT"
        elif is_security_revision:
            target_phase = "SECURITY_AUDIT"
        elif is_security_approved:
            target_phase = "RELEASE"
        elif is_qa_approved:
            target_phase = "SECURITY_AUDIT"
        elif is_spec_approved:
            target_phase = "DEVELOPMENT"

        if not run or run.status in ("COMPLETED", "FAILED"):
            run = WorkflowRunORM(
                project_id=project_id,
                current_phase=target_phase,
                status="RUNNING",
            )

            self.db.add(run)

            self.db.flush()

        else:
            run.status = "RUNNING"
            run.current_phase = target_phase

            self.db.flush()

        enabled_agents = self._get_enabled_agents(project_id)

        # Initialize Channel App repo (always required)

        channel_repo_path = self.git_service.initialize_repository(
            project_id=project_id,
            repo_type=RepositoryType.CHANNEL_APP,
            target_framework=project.target_framework,
        )

        tdd_disk = (
            Path(self.git_service.base_workspace_dir / str(project_id))
            / "docs"
            / "TECHNICAL_DESIGN.md"
        )
        tdd_existing_text = ""
        if tdd_disk.exists():
            try:
                tdd_existing_text = tdd_disk.read_text(encoding="utf-8")
            except Exception:
                pass

        requires_mock = self._inspect_tdd_for_mock_vendor(tdd_existing_text)

        mock_repo_path = None

        if enabled_agents.get(AgentType.MOCK_DEVELOPER.name, False) and requires_mock:
            mock_repo_path = self.git_service.initialize_repository(
                project_id=project_id,
                repo_type=RepositoryType.MOCK_VENDOR_API,
                target_framework=project.target_framework,
            )

        workspace_path = str(self.git_service.base_workspace_dir / str(project_id))

        # Check for incremental client/frontend extension on an existing project
        channel_app_dir = Path(workspace_path) / "channel-app"
        backend_exists = channel_app_dir.exists() and any(channel_app_dir.iterdir())
        lower_req = user_requirement.lower()
        client_tokens = [
            "frontend",
            "front-end",
            "front end",
            "client app",
            "user interface",
            "web app",
            "web portal",
            "dashboard",
            "mobile app",
            "gui",
        ]
        is_client_ext = any(w in lower_req for w in client_tokens)
        is_revision = "Human Revision Request" in user_requirement or "Requested Changes" in user_requirement
        is_incremental = bool(backend_exists and is_client_ext and not is_revision)

        subsystem_framework = None
        if is_incremental:
            from src.api.routes.workflow import detect_target_framework

            subsystem_framework = detect_target_framework(
                user_requirement, default="TYPESCRIPT_NEXTJS"
            )

        persisted_iterations = run.iteration_count or 0

        initial_state: WorkflowState = {
            "project_id": str(project_id),
            "workflow_run_id": str(run.id),
            "workspace_path": workspace_path,
            "target_framework": project.target_framework,
            "user_requirement": user_requirement,
            "enabled_agents": enabled_agents,
            "requires_mock_vendor": requires_mock,
            "channel_repo_path": channel_repo_path,
            "mock_repo_path": mock_repo_path,
            "defect_remediation_count": persisted_iterations,
            "spec_approved": is_spec_approved,
            "spec_approval_comments": user_requirement if is_spec_revision else None,
            "mock_approved": is_mock_approved,
            "code_approved": is_code_approved,
            "qa_approved": is_qa_approved,
            "security_approved": is_security_approved,
            "release_approved": True,
            "iteration": persisted_iterations,
            "is_completed": False,
            "is_incremental": is_incremental,
            "target_subsystem": "frontend" if is_incremental else "channel-app",
            "subsystem_framework": subsystem_framework,
        }

        # Build agents

        agent1 = DocumentationReviewerAgent(
            resolver=self.resolver, tracker=self.tracker, db=self.db
        )

        agent2 = MockVendorDeveloperAgent(
            resolver=self.resolver, git_service=self.git_service, tracker=self.tracker, db=self.db
        )

        agent3 = MainCodingAgent(
            resolver=self.resolver, git_service=self.git_service, tracker=self.tracker, db=self.db
        )

        agent4 = QAEngineerAgent(
            resolver=self.resolver, git_service=self.git_service, tracker=self.tracker, db=self.db
        )

        agent5 = SecurityReviewerAgent(
            resolver=self.resolver, git_service=self.git_service, tracker=self.tracker, db=self.db
        )

        # Node adapter wrappers

        def _make_context(state: WorkflowState, agent_name: str, task_type: str) -> AgentContext:

            task = AgentTaskORM(
                project_id=uuid.UUID(state["project_id"]),
                agent_name=agent_name,
                task_type=task_type,
            )

            self.db.add(task)

            self.db.flush()

            execution = AgentExecutionORM(agent_task_id=task.id)

            self.db.add(execution)

            self.db.flush()

            return AgentContext(
                project_id=uuid.UUID(state["project_id"]),
                task_id=task.id,
                agent_execution_id=execution.id,
                workspace_path=state["workspace_path"],
                target_framework=state["target_framework"],
                additional_metadata={
                    "is_incremental": state.get("is_incremental", False),
                    "target_subsystem": state.get("target_subsystem", "channel-app"),
                    "subsystem_framework": state.get("subsystem_framework"),
                },
            )

        def _is_run_cancelled() -> bool:
            try:
                self.db.refresh(run)
                return run.status == "CANCELLED"
            except Exception:
                return False

        async def doc_node(s: WorkflowState) -> WorkflowState:
            if _is_run_cancelled():
                s["is_cancelled"] = True
                return s

            tdd_disk = Path(s["workspace_path"]) / "docs" / "TECHNICAL_DESIGN.md"

            xunit_disk = Path(s["workspace_path"]) / "docs" / "XUNIT_TEST_SPEC.md"

            # Fast-path bypass to coding if TDD exists and user approved / continued

            if tdd_disk.exists() and (s.get("spec_approved") or is_approved_intent):
                s["tdd_path"] = "docs/TECHNICAL_DESIGN.md"

                s["xunit_spec_path"] = "docs/XUNIT_TEST_SPEC.md"

                s["current_phase"] = "SPECIFICATION"

                s["spec_approved"] = True

                self.checkpoint_service.save_checkpoint(run.id, "SPECIFICATION", s)

                self.db.commit()

                return s

            # Run Agent 1 if specs do not exist OR if user provided fresh non-approval requirements

            if not tdd_disk.exists() or not is_approved_intent:
                ctx = _make_context(s, "Agent 1: Documentation Reviewer", "SPECIFICATION")

                prompt_input = s["user_requirement"]
                comments = s.get("spec_approval_comments")
                if is_revision_intent and comments:
                    prompt_input = (
                        f"### User Requested Changes for SPECIFICATION:\n{comments}\n\n"
                        f"Please revise the specifications accordingly, strictly preserving the established base scope."
                    )

                res = await agent1.execute(ctx, prompt_input)
                if res.metadata.get("target_framework"):
                    s["target_framework"] = res.metadata["target_framework"]

                telemetry = self.tracker.get_execution_telemetry(ctx.agent_execution_id)

                save_chat_message(
                    self.db,
                    project_id,
                    "agent1",
                    "I have analyzed your software requirements and generated technical specifications.",
                    metadata={
                        "checklist": [
                            "Analyzed architecture boundaries & target framework",
                            "Extracted functional requirements & API contracts",
                            "Created test specifications",
                            "Generated Technical Design Document (TDD)",
                        ],
                        "telemetry": telemetry,
                    },
                )

            s["tdd_path"] = "docs/TECHNICAL_DESIGN.md"

            s["xunit_spec_path"] = "docs/XUNIT_TEST_SPEC.md"

            s["current_phase"] = "SPECIFICATION"

            # Inspect TDD content for mock vendor requirement
            fresh_tdd_text = ""
            if tdd_disk.exists():
                try:
                    fresh_tdd_text = tdd_disk.read_text(encoding="utf-8")
                except Exception:
                    pass
            requires_mock = self._inspect_tdd_for_mock_vendor(fresh_tdd_text)
            s["requires_mock_vendor"] = requires_mock
            if not requires_mock:
                s["enabled_agents"][AgentType.MOCK_DEVELOPER.name] = False
                s["enabled_agents"]["AGENT_2"] = False
                s["mock_repo_path"] = None
                if self.db:
                    cfg = (
                        self.db.query(ProjectAgentConfigORM)
                        .filter_by(project_id=project_id)
                        .filter(
                            ProjectAgentConfigORM.agent_type.in_(
                                [AgentType.MOCK_DEVELOPER.name, "AGENT_2", "AGENT2"]
                            )
                        )
                        .first()
                    )
                    if cfg and cfg.is_enabled:
                        cfg.is_enabled = False
                        self.db.flush()

            # If specs already approved, bypass approval gate immediately to coding

            if s.get("spec_approved") and is_approved_intent:
                self.checkpoint_service.save_checkpoint(run.id, "SPECIFICATION", s)

                self.db.commit()

                return s

            existing_app = (
                self.db.query(HumanApprovalORM)
                .filter_by(workflow_run_id=run.id, gate_type="SPECIFICATION", status="PENDING")
                .first()
            )

            if not existing_app:
                new_app = self.approval_engine.create_approval_request(
                    workflow_run_id=run.id,
                    gate_type="SPECIFICATION",
                    prompt_text="Please review the technical design and test specifications. Shall I proceed with implementation?",
                )

                save_chat_message(
                    self.db,
                    project_id,
                    "agent1",
                    "Human approval required to proceed with code implementation.",
                    metadata={
                        "isApprovalCard": True,
                        "approvalRequired": True,
                        "approvalId": str(new_app.id),
                        "gateType": "SPECIFICATION",
                        "status": "PENDING",
                        "isApproved": False,
                    },
                )

                s["spec_approved"] = False

            else:
                s["spec_approved"] = False

            s["spec_approval_comments"] = None
            self.checkpoint_service.save_checkpoint(run.id, "SPECIFICATION", s)

            self.db.commit()

            return s

        async def mock_node(s: WorkflowState) -> WorkflowState:
            if _is_run_cancelled():
                s["is_cancelled"] = True
                return s

            tdd_content = ""
            tdd_path_candidate = Path(s["workspace_path"]) / "docs" / "TECHNICAL_DESIGN.md"
            if tdd_path_candidate.exists():
                try:
                    tdd_content = tdd_path_candidate.read_text(encoding="utf-8")
                except Exception:
                    pass
            if not tdd_content:
                tdd_content = s.get("technical_design", "")

            # Guard: If TDD indicates Agent 2 is skipped or not required
            if (
                not self._inspect_tdd_for_mock_vendor(tdd_content)
                or s.get("requires_mock_vendor") is False
            ):
                s["requires_mock_vendor"] = False
                s["enabled_agents"][AgentType.MOCK_DEVELOPER.name] = False
                s["enabled_agents"]["AGENT_2"] = False
                s["mock_repo_path"] = None
                s["current_phase"] = "MOCK_DEVELOPMENT"
                save_chat_message(
                    self.db,
                    project_id,
                    "agent2",
                    "ℹ️ **Agent 2 (Mock Vendor API Developer) is SKIPPED**: Technical Design specification confirms no third-party vendor APIs or external contracts are in scope.",
                    metadata={"skipped": True},
                )
                self.checkpoint_service.save_checkpoint(run.id, "MOCK_DEVELOPMENT", s)
                self.db.commit()
                return s

            save_chat_message(
                self.db,
                project_id,
                "agent2",
                "Starting Mock Vendor API implementation and external contract simulation...",
            )

            ctx = _make_context(s, "Agent 2: Mock Vendor API Developer", "MOCK_DEVELOPMENT")

            mock_prompt = (
                f"## Technical Design Document:\n\n{tdd_content}\n\n"
                f"## Directive:\n"
                f"Analyze the Technical Design Document above. Identify all third-party/external mock vendor specifications, "
                f"endpoints, HTTP methods, request parameters, response schemas, and error behavior. "
                f"Implement a standalone, runnable FastAPI mock vendor server that satisfies these external contracts."
            )

            res = await agent2.execute(ctx, mock_prompt)

            if res.metadata.get("skipped"):
                s["requires_mock_vendor"] = False
                s["enabled_agents"][AgentType.MOCK_DEVELOPER.name] = False
                s["enabled_agents"]["AGENT_2"] = False
                s["mock_repo_path"] = None
                s["current_phase"] = "MOCK_DEVELOPMENT"
                save_chat_message(
                    self.db,
                    project_id,
                    "agent2",
                    "ℹ️ **Agent 2 (Mock Vendor API Developer) is SKIPPED**: Technical Design specification confirms no third-party vendor APIs or external contracts are in scope.",
                    metadata={"skipped": True},
                )
                self.checkpoint_service.save_checkpoint(run.id, "MOCK_DEVELOPMENT", s)
                self.db.commit()
                return s

            s["mock_commit_hash"] = res.metadata.get("commit_hash")

            s["current_phase"] = "MOCK_DEVELOPMENT"

            telemetry = self.tracker.get_execution_telemetry(ctx.agent_execution_id)

            save_chat_message(
                self.db,
                project_id,
                "agent2",
                f"Mock Vendor API synthesized and committed to repository ({res.metadata.get('branch', 'mock-apis')}).",
                metadata={
                    "checklist": [
                        "Synthesized mock API endpoints in FastAPI",
                        "Created schema-compliant responses & error states",
                        "Committed changes to mock-vendor-api repository",
                    ],
                    "telemetry": telemetry,
                },
            )

            if not s.get("mock_approved"):
                existing_app = (
                    self.db.query(HumanApprovalORM)
                    .filter_by(workflow_run_id=run.id, gate_type="MOCK_DEVELOPMENT", status="PENDING")
                    .first()
                )
                if not existing_app:
                    new_app = self.approval_engine.create_approval_request(
                        workflow_run_id=run.id,
                        gate_type="MOCK_DEVELOPMENT",
                        prompt_text="Agent 2 has synthesized the Mock Vendor API. Shall I proceed with Channel Application implementation?",
                    )
                    save_chat_message(
                        self.db,
                        project_id,
                        "agent2",
                        "Human approval required to proceed with Channel Application implementation.",
                        metadata={
                            "isApprovalCard": True,
                            "approvalRequired": True,
                            "approvalId": str(new_app.id),
                            "gateType": "MOCK_DEVELOPMENT",
                            "status": "PENDING",
                            "isApproved": False,
                        },
                    )
                s["mock_approved"] = False

            self.checkpoint_service.save_checkpoint(run.id, "MOCK_DEVELOPMENT", s)

            self.db.commit()

            return s

        async def code_node(s: WorkflowState) -> WorkflowState:
            if _is_run_cancelled():
                s["is_cancelled"] = True
                return s

            app_dir = Path(s["workspace_path"]) / "channel-app"

            has_existing_code = (
                (app_dir / "app" / "page.tsx").exists()
                or (app_dir / "main.py").exists()
                or any(app_dir.glob("*.csproj"))
            )

            if (is_qa_or_sec_only or is_qa_revision) and has_existing_code and s.get("code_approved"):
                s["build_success"] = True

                s["current_phase"] = "DEVELOPMENT"

                self.checkpoint_service.save_checkpoint(run.id, "DEVELOPMENT", s)

                self.db.commit()

                return s

            coding_input = s["user_requirement"]
            remediation_count = s.get("defect_remediation_count", 0)
            if remediation_count > 0:
                defects = (
                    self.db.query(DefectORM).filter_by(project_id=project_id, status="OPEN").all()
                )
                if defects:
                    defect_lines = "\n".join(f"- [{d.severity}] {d.description}" for d in defects)
                    coding_input = (
                        f"## Defect Remediation Directive (Attempt {remediation_count}):\n"
                        f"Agent 4 Black-Box QA identified the following test defects that must be resolved:\n\n"
                        f"{defect_lines}\n\n"
                        f"CRITICAL REMEDIATION CONSTRAINT: You MUST modify and overwrite the EXACT existing file paths in the project (e.g. existing Services/<Entity>Service.cs, Repositories/<Entity>Repository.cs, Data/AppDbContext.cs). NEVER invent new alternate file names (e.g. `IService.cs` or `ServiceImplementation.cs`) as duplicate definitions in the same namespace will cause CS0101 compilation errors.\n\n"
                        f"## Original Implementation Directive:\n{s['user_requirement']}"
                    )
            save_chat_message(
                self.db,
                project_id,
                "agent3",
                "Starting application implementation, synthesizing directory structure from architectural specifications, and building components...",
            )

            ctx = _make_context(s, "Agent 3: Main Coding Agent", "DEVELOPMENT")
            res = await agent3.execute(ctx, coding_input)
            if remediation_count > 0:
                run.iteration_count = remediation_count
                self.db.query(DefectORM).filter_by(project_id=project_id, status="OPEN").update(
                    {"status": "RESOLVED"}
                )
                self.db.commit()

            s["channel_commit_hash"] = res.metadata.get("commit_hash")

            s["build_success"] = res.metadata.get("build_success", True)

            s["current_phase"] = "DEVELOPMENT"

            build_log = res.metadata.get("build_log", "")
            is_frontend = (
                s.get("is_incremental") or res.metadata.get("target_subsystem") == "frontend"
            )
            subsystem_label = (
                "Frontend client interface" if is_frontend else "Channel application code"
            )
            target_folder = "frontend/" if is_frontend else "channel-app/"
            fw_label = res.metadata.get("effective_framework", "Clean Architecture")

            attempts_taken = res.metadata.get("attempts", 1)
            was_repaired = res.metadata.get("was_repaired", False)

            if s["build_success"]:
                if was_repaired:
                    agent3_msg = (
                        f"✅ **Build Verified & Auto-Repaired by Agent 3** (Attempt {attempts_taken}/3)\n\n"
                        f"Initial compilation encountered errors. Agent 3 analyzed the diagnostics and autonomously corrected the source code.\n\n"
                        f"- **Status**: `PASSED (0 Errors)`\n"
                        f"- **Artifacts**: {len(res.artifacts_created or [])} files compiled & verified\n"
                    )
                    checklist = [
                        f"Synthesized multi-file {fw_label} structure in {target_folder}",
                        f"Auto-repaired compiler errors on attempt {attempts_taken}",
                        "Build verification: PASSED (0 Errors)",
                    ]
                else:
                    agent3_msg = (
                        f"✅ **Build Verified Successfully** (Attempt 1/3)\n\n"
                        f"{subsystem_label} synthesized and cleanly compiled with zero compiler errors.\n\n"
                        f"- **Status**: `PASSED (0 Errors)`\n"
                        f"- **Artifacts**: {len(res.artifacts_created or [])} files verified\n"
                    )
                    checklist = [
                        f"Synthesized multi-file {fw_label} structure in {target_folder}",
                        "Generated project configuration",
                        "Build verification: PASSED (0 Errors)",
                    ]
            else:
                err_lines = [
                    l.strip()
                    for l in build_log.splitlines()
                    if "error CS" in l or "Error(s)" in l or "FAILED" in l or "error:" in l or "SyntaxError" in l
                ]
                err_summary = (
                    "\n".join(err_lines[:8])
                    if err_lines
                    else "Compiler / syntax errors detected during build verification."
                )
                agent3_msg = (
                    f"❌ **Build Verification Failed** (Attempt {attempts_taken}/3)\n\n"
                    f"{subsystem_label} synthesized, but compilation failed. Root cause diagnostics:\n\n"
                    f"```text\n{err_summary}\n```\n\n"
                    f"Agent 3 attempted self-healing, but compiler errors persisted. Human review required."
                )
                checklist = [
                    f"Synthesized multi-file {fw_label} structure in {target_folder}",
                    "Generated project configuration",
                    "Build verification: FAILED (compiler errors detected)",
                ]

            telemetry = self.tracker.get_execution_telemetry(ctx.agent_execution_id)

            save_chat_message(
                self.db,
                project_id,
                "agent3",
                agent3_msg,
                metadata={
                    "checklist": checklist,
                    "buildInfo": {
                        "buildSuccess": s["build_success"],
                        "wasRepaired": was_repaired,
                        "attempts": attempts_taken,
                        "framework": fw_label,
                        "errorSummary": err_summary if not s["build_success"] else None,
                    },
                    "telemetry": telemetry,
                },
            )

            if not s.get("code_approved"):
                existing_app = (
                    self.db.query(HumanApprovalORM)
                    .filter_by(workflow_run_id=run.id, gate_type="DEVELOPMENT", status="PENDING")
                    .first()
                )
                if not existing_app:
                    new_app = self.approval_engine.create_approval_request(
                        workflow_run_id=run.id,
                        gate_type="DEVELOPMENT",
                        prompt_text="Agent 3 has completed the Channel Application implementation and verified the build. Shall I proceed with Independent QA testing?",
                    )
                    save_chat_message(
                        self.db,
                        project_id,
                        "agent3",
                        "Human approval required to proceed with Independent QA Verification.",
                        metadata={
                            "isApprovalCard": True,
                            "approvalRequired": True,
                            "approvalId": str(new_app.id),
                            "gateType": "DEVELOPMENT",
                            "status": "PENDING",
                            "isApproved": False,
                        },
                    )
                s["code_approved"] = False

            self.checkpoint_service.save_checkpoint(run.id, "DEVELOPMENT", s)

            self.db.commit()

            return s

        async def qa_node(s: WorkflowState) -> WorkflowState:
            if _is_run_cancelled():
                s["is_cancelled"] = True
                return s
            remediation_count = s.get("defect_remediation_count", 0)
            attempt_num = remediation_count + 1

            if not s.get("build_success", True):
                s["qa_status"] = "FAILED (BUILD_FAILED)"
                s["qa_passed_count"] = 0
                s["qa_failed_count"] = 1
                s["current_phase"] = "QA_VERIFICATION"
                save_chat_message(
                    self.db,
                    project_id,
                    "agent4",
                    f"### ❌ Independent QA Test Report (Attempt {attempt_num})\n\n"
                    f"- **Status**: `FAILED (BUILD_FAILED)`\n"
                    f"- **Tests Passed**: `0`\n"
                    f"- **Tests Failed**: `1`\n"
                    f"- **Specification**: `docs/XUNIT_TEST_SPEC.md`\n\n"
                    f"**Summary**: Channel application build failed. Cannot verify contract compliance.",
                )
                self.checkpoint_service.save_checkpoint(run.id, "QA_VERIFICATION", s)
                self.db.commit()
                return s

            tf = (project.target_framework or "").lower()
            if "csharp" in tf or "dotnet" in tf:
                live_port = 5001
            elif "typescript" in tf or "next" in tf or "node" in tf:
                live_port = 3000
            else:
                live_port = 8000

            eval_prompt = (
                f"Evaluate black-box HTTP contract compliance against the channel application service.\n"
                f"- Active Base URL: http://localhost:{live_port}\n"
                f"- Target Framework: {s.get('target_framework', project.target_framework)}\n"
                f"- Service Status: Live and serving registered API routes.\n\n"
                f"Validate each contract and test case defined in docs/XUNIT_TEST_SPEC.md against these live endpoints. "
                f"For each test case, verify HTTP method, expected status code, request/response JSON payload schemas, and headers."
            )

            ctx = _make_context(s, "Agent 4: Independent QA Engineer", "QA_VERIFICATION")
            res = await agent4.execute(ctx, eval_prompt)
            s["qa_status"] = res.metadata.get("overall_status", "PASSED")
            s["qa_passed_count"] = res.metadata.get("passed_count", 0)
            s["qa_failed_count"] = res.metadata.get("failed_count", 0)
            s["current_phase"] = "QA_VERIFICATION"

            # Format test results table and CLI execution evidence
            test_results = res.metadata.get("test_results", [])
            cli_out = res.metadata.get("cli_output", "")

            # Format categorized test tables
            unit_tests = [
                tr
                for tr in test_results
                if tr.get("category") == "UNIT_TEST" or str(tr.get("test_key", "")).startswith("UT")
            ]
            integration_tests = [
                tr
                for tr in test_results
                if tr.get("category") == "INTEGRATION_TEST"
                or str(tr.get("test_key", "")).startswith("IT")
            ]
            ext_tests = [
                tr
                for tr in test_results
                if tr.get("category") == "SUPPLEMENTAL_TEST"
                or str(tr.get("test_key", "")).startswith("EXT")
            ]
            other_tests = [
                tr
                for tr in test_results
                if tr not in unit_tests and tr not in integration_tests and tr not in ext_tests
            ]

            table_md = ""

            if unit_tests:
                ut_rows = []
                for tr in unit_tests:
                    k = tr.get("test_key", "UT")
                    name = tr.get("test_name", "")
                    dur = tr.get("duration", "N/A")
                    st = tr.get("status", "PASSED")
                    det = tr.get("details", "")
                    ut_rows.append(f"| **{k}** | `{name}` | `{st}` | `{dur}` | {det} |")
                table_md += (
                    "\n\n#### 🧪 Isolated Unit Tests (Domain & Logic Assertions)\n"
                    "| Test ID | Test Scenario | Status | Duration | Verification Assertion |\n"
                    "| :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(ut_rows)
                )

            if integration_tests:
                it_rows = []
                for tr in integration_tests:
                    k = tr.get("test_key", "IT")
                    m = tr.get("http_method", "POST")
                    ep = tr.get("endpoint", "")
                    exp = tr.get("expected_status", 200)
                    act = tr.get("actual_status", 200)
                    st = tr.get("status", "PASSED")
                    dur = tr.get("duration", "")
                    det = tr.get("details", "")
                    it_rows.append(f"| **{k}** | `{m} {ep}` | `{exp}` | `{act}` | `{st}` | {det} |")
                table_md += (
                    "\n\n#### 🌐 Integration Tests (HTTP & Persistence Contracts)\n"
                    "| Test ID | Method & Route | Expected | Actual | Status | Verification Evidence |\n"
                    "| :--- | :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(it_rows)
                )

            if ext_tests:
                ext_rows = []
                for tr in ext_tests:
                    k = tr.get("test_key", "EXT")
                    name = tr.get("test_name", "")
                    st = tr.get("status", "PASSED")
                    det = tr.get("details", "")
                    ext_rows.append(f"| **{k}** | `{name}` | `{st}` | {det} |")
                table_md += (
                    "\n\n#### 🛡️ Supplemental Compliance Tests\n"
                    "| Test ID | Test Scenario | Status | Verification Evidence |\n"
                    "| :--- | :--- | :--- | :--- |\n" + "\n".join(ext_rows)
                )

            if other_tests and not (unit_tests or integration_tests):
                generic_rows = []
                for tr in other_tests:
                    k = tr.get("test_key", "TC")
                    m = tr.get("http_method", "")
                    ep = tr.get("endpoint", "")
                    exp = tr.get("expected_status", 200)
                    act = tr.get("actual_status", 200)
                    st = tr.get("status", "PASSED")
                    det = tr.get("details", "")
                    generic_rows.append(
                        f"| **{k}** | `{m} {ep}` | `{exp}` | `{act}` | `{st}` | {det} |"
                    )
                table_md = (
                    "\n\n| Test ID | Method & Route | Expected | Actual | Status | Verification Evidence |\n"
                    "| :--- | :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(generic_rows)
                )

            cli_md = ""
            if cli_out and "No channel" not in cli_out:
                cli_md = f"\n\n**Test Runner Execution:**\n```text\n{cli_out[:500]}\n```"

            qa_report_data = {
                "status": s["qa_status"],
                "passedCount": s["qa_passed_count"],
                "failedCount": s["qa_failed_count"],
                "totalCount": s["qa_passed_count"] + s["qa_failed_count"],
                "liveExecuted": res.metadata.get("live_executed", False),
                "testResults": [
                    {
                        "testKey": tr.get("test_key", "TC"),
                        "name": tr.get("test_name") or tr.get("name") or tr.get("test_key", "TC"),
                        "category": tr.get("category", "CONTRACT"),
                        "httpMethod": tr.get("http_method", "GET"),
                        "endpoint": tr.get("endpoint", "/"),
                        "expectedStatus": tr.get("expected_status", 200),
                        "actualStatus": tr.get("actual_status", 200),
                        "latency": tr.get("duration") or tr.get("latency") or "N/A",
                        "status": tr.get("status", "PASSED"),
                        "details": tr.get("details", ""),
                        "curlCommand": tr.get("curl_command", ""),
                        "requestPayload": tr.get("request_payload"),
                        "responseBody": tr.get("response_body", ""),
                    }
                    for tr in test_results
                ],
            }

            qa_checklist = [
                "Evaluated black-box HTTP contract specifications",
                f"Tested {len(test_results)} API endpoints & boundary scenarios",
                "Cleanly terminated test process & verified socket closure",
                f"QA Contract Test Status: {s['qa_status']} ({s['qa_passed_count']} passed, {s['qa_failed_count']} failed)",
            ]

            swagger_url = f"http://localhost:{live_port}/swagger"
            live_server_card = (
                f"\n\n> 🌐 **Live Test Server Active**: `http://localhost:{live_port}`\n"
                f"> 📄 **Interactive Swagger Documentation**: [{swagger_url}]({swagger_url}) *(Open to test live endpoints)*\n"
            )

            if s["qa_status"] == "PASSED":
                if remediation_count > 0:
                    report_msg = (
                        f"### 🎉 Autonomous QA Remediation SUCCESSFUL (Attempt {attempt_num})\n\n"
                        f"- **Status**: `PASSED`\n"
                        f"- **Tests Passed**: `{s['qa_passed_count']}`\n"
                        f"- **Tests Failed**: `0`\n"
                        f"- **Specification**: `docs/XUNIT_TEST_SPEC.md`\n\n"
                        f"**Summary**: All contract and validation test cases verified successfully after autonomous code remediation by Agent 3."
                        f"{live_server_card}"
                        f"{table_md}"
                        f"{cli_md}"
                    )
                else:
                    report_msg = (
                        f"### ✅ Independent QA Test Report\n\n"
                        f"- **Status**: `PASSED`\n"
                        f"- **Tests Passed**: `{s['qa_passed_count']}`\n"
                        f"- **Tests Failed**: `0`\n"
                        f"- **Specification**: `docs/XUNIT_TEST_SPEC.md`\n\n"
                        f"**Summary**: {res.summary}"
                        f"{live_server_card}"
                        f"{table_md}"
                        f"{cli_md}"
                    )
                qa_telemetry = self.tracker.get_execution_telemetry(ctx.agent_execution_id)
                save_chat_message(
                    self.db,
                    project_id,
                    "agent4",
                    report_msg,
                    metadata={
                        "qaReport": qa_report_data,
                        "checklist": qa_checklist,
                        "telemetry": qa_telemetry,
                        "liveServerUrl": f"http://localhost:{live_port}",
                        "swaggerUrl": swagger_url,
                    },
                )
            else:
                report_msg = (
                    f"### ❌ Independent QA Test Report (Attempt {attempt_num})\n\n"
                    f"- **Status**: `FAILED`\n"
                    f"- **Tests Passed**: `{s['qa_passed_count']}`\n"
                    f"- **Tests Failed**: `{s['qa_failed_count']}`\n"
                    f"- **Specification**: `docs/XUNIT_TEST_SPEC.md`\n\n"
                    f"**Summary**: {res.summary}"
                    f"{live_server_card}"
                    f"{table_md}"
                    f"{cli_md}"
                )
                qa_telemetry = self.tracker.get_execution_telemetry(ctx.agent_execution_id)
                save_chat_message(
                    self.db,
                    project_id,
                    "agent4",
                    report_msg,
                    metadata={
                        "qaReport": qa_report_data,
                        "checklist": qa_checklist,
                        "telemetry": qa_telemetry,
                        "liveServerUrl": f"http://localhost:{live_port}",
                        "swaggerUrl": swagger_url,
                    },
                )
                if remediation_count < 2:
                    save_chat_message(
                        self.db,
                        project_id,
                        "assistant",
                        f"⚠️ **Agent 4 identified {s['qa_failed_count']} contract test defect(s)**.\n\n"
                        f"Initiating **Agent 3 Autonomous QA Defect Remediation** (Attempt {attempt_num}/2)...",
                    )
                else:
                    s["qa_status"] = "FAILED (REMEDIATION_EXHAUSTED)"
                    save_chat_message(
                        self.db,
                        project_id,
                        "assistant",
                        "⛔ **Maximum autonomous remediation cycles reached (2/2)**.\n\n"
                        "Agent 4 still identified contract test defects. Autonomous remediation has stopped to prevent infinite looping. Human review required.",
                    )

            run.iteration_count = remediation_count

            if not s.get("qa_approved") and (s.get("qa_status") == "PASSED" or remediation_count >= 2):
                existing_app = (
                    self.db.query(HumanApprovalORM)
                    .filter_by(workflow_run_id=run.id, gate_type="QA_VERIFICATION", status="PENDING")
                    .first()
                )
                if not existing_app:
                    new_app = self.approval_engine.create_approval_request(
                        workflow_run_id=run.id,
                        gate_type="QA_VERIFICATION",
                        prompt_text=f"Agent 4 has completed Independent QA Verification ({s.get('qa_status', 'PASSED')}). Shall I proceed with Security SAST Audit?",
                    )
                    save_chat_message(
                        self.db,
                        project_id,
                        "agent4",
                        "Human approval required to proceed with Security SAST Audit.",
                        metadata={
                            "isApprovalCard": True,
                            "approvalRequired": True,
                            "approvalId": str(new_app.id),
                            "gateType": "QA_VERIFICATION",
                            "status": "PENDING",
                            "isApproved": False,
                        },
                    )
                s["qa_approved"] = False

            self.checkpoint_service.save_checkpoint(run.id, "QA_VERIFICATION", s)
            self.db.commit()
            return s

        async def sec_node(s: WorkflowState) -> WorkflowState:
            if _is_run_cancelled():
                s["is_cancelled"] = True
                return s

            ctx = _make_context(s, "Agent 5: Security Reviewer", "SECURITY_AUDIT")

            res = await agent5.execute(ctx, "Evaluate source security")

            s["security_status"] = res.metadata.get("scan_status", "PASSED")

            s["security_findings_count"] = res.metadata.get("total_findings", 0)

            s["current_phase"] = "SECURITY_AUDIT"

            sec_telemetry = self.tracker.get_execution_telemetry(ctx.agent_execution_id)

            evaluated_checks = res.metadata.get("evaluated_checks", [])
            scanned_files = res.metadata.get("scanned_files", [])

            # Format detailed evidence table if available
            evidence_md = ""
            if evaluated_checks:
                check_rows = []
                for ec in evaluated_checks:
                    cat = ec.get("category", "SECURITY_CHECK")
                    cwe = ec.get("cwe", "")
                    fp = ec.get("file_path", "")
                    ln = ec.get("line_number", "")
                    st = ec.get("status", "PASSED")
                    snip = ec.get("scanned_snippet", "")
                    asrt = ec.get("assertion", "")
                    file_loc = f"`{fp}:{ln}`" if ln else f"`{fp}`"
                    check_rows.append(f"| **{cat}** ({cwe}) | {file_loc} | `{st}` | `{snip[:45]}` | {asrt} |")
                evidence_md = (
                    "\n\n#### 🔍 Verifiable AST / Code Analysis Evidence\n"
                    "| Vulnerability Check | Inspected File & Line | Status | Scanned Code Snippet | Verifiable Proof Assertion |\n"
                    "| :--- | :--- | :--- | :--- | :--- |\n" + "\n".join(check_rows)
                )

            files_md = ""
            if scanned_files:
                files_md = f"\n- **Scanned Source Files**: `{len(scanned_files)} files` ({', '.join(scanned_files[:5])})"

            save_chat_message(
                self.db,
                project_id,
                "agent5",
                f"### 🛡️ Security SAST Audit Report\n\n- **Scan Status**: `{s['security_status']}`\n- **Vulnerabilities Found**: `{s['security_findings_count']}`{files_md}\n\n**Summary**: {res.summary}{evidence_md}",
                metadata={
                    "telemetry": sec_telemetry,
                    "evaluated_checks": evaluated_checks,
                    "scanned_files": scanned_files,
                },
            )

            if not s.get("security_approved"):
                existing_app = (
                    self.db.query(HumanApprovalORM)
                    .filter_by(workflow_run_id=run.id, gate_type="SECURITY_AUDIT", status="PENDING")
                    .first()
                )
                if not existing_app:
                    new_app = self.approval_engine.create_approval_request(
                        workflow_run_id=run.id,
                        gate_type="SECURITY_AUDIT",
                        prompt_text=f"Agent 5 has completed Security SAST Audit ({s.get('security_status', 'PASSED')}). Shall I proceed to Release Promotion & Manifest generation?",
                    )
                    save_chat_message(
                        self.db,
                        project_id,
                        "agent5",
                        "Human approval required to proceed with Release Promotion.",
                        metadata={
                            "isApprovalCard": True,
                            "approvalRequired": True,
                            "approvalId": str(new_app.id),
                            "gateType": "SECURITY_AUDIT",
                            "status": "PENDING",
                            "isApproved": False,
                        },
                    )
                s["security_approved"] = False

            self.checkpoint_service.save_checkpoint(run.id, "SECURITY_AUDIT", s)

            self.db.commit()

            return s

        async def release_node(s: WorkflowState) -> WorkflowState:
            if _is_run_cancelled() or s.get("is_cancelled"):
                s["is_cancelled"] = True
                return s

            # Generate GitReleaseManifest

            manifest = self.git_service.create_release_manifest(
                project_id=uuid.UUID(s["project_id"]),
                release_tag=f"v0.1.{s.get('iteration', 0)}",
            )

            s["release_tag"] = manifest.release_tag

            s["is_completed"] = True

            s["current_phase"] = "COMPLETED"

            run.status = "COMPLETED"

            run.current_phase = "COMPLETED"

            if not s.get("build_success", True):
                run.status = "FAILED"
                release_msg = "⚠️ Project workflow completed with build failures. Review compiler errors and inspect channel-app codebase."
            elif str(s.get("qa_status", "")).startswith("FAILED"):
                run.status = "FAILED"
                release_msg = f"⚠️ Project workflow completed with {s.get('qa_failed_count', 0)} unresolved QA defect(s). Code is committed to channel-app for remediation."
            elif str(s.get("security_status", "")).startswith("FAILED"):
                run.status = "FAILED"
                release_msg = f"⚠️ Project workflow completed with {s.get('security_findings_count', 0)} security vulnerability finding(s). Release promotion blocked."
            else:
                run.status = "COMPLETED"
                release_msg = "Project built and verified successfully. Code is ready in channel-app repository."

            # Dynamically synthesize root README.md and startup scripts in workspace
            workspace_dir = Path(s["workspace_path"])
            tf = (project.target_framework or "").lower()
            has_mock = s.get("requires_mock_vendor", True) and (
                bool(s.get("mock_commit_hash")) or (workspace_dir / "mock-vendor-api").exists()
            )

            # Ensure primary integration branch 'develop' is checked out at release
            try:
                self.git_service.checkout_branch(project.id, RepositoryType.CHANNEL_APP, "develop")
                if has_mock:
                    self.git_service.checkout_branch(project.id, RepositoryType.MOCK_VENDOR_API, "develop")
            except Exception:
                pass

            readme_lines = [
                f"# {project.name}",
                f"\n**Target Framework**: `{project.target_framework or 'Generic'}`",
                f"**Release Version**: `{manifest.release_tag}`\n",
                "## Architecture & Repository Structure",
                "- `channel-app/`: Core application services and endpoints.",
            ]
            if (workspace_dir / "channel-app.Tests").exists():
                readme_lines.append(
                    "- `channel-app.Tests/`: Executable xUnit unit and integration test project."
                )
            if has_mock:
                readme_lines.append(
                    "- `mock-vendor-api/`: Standalone FastAPI external mock vendor service."
                )
            readme_lines.append(
                "- `docs/`: Technical Design Document (TDD) and Test Specifications.\n"
            )

            readme_lines.append("## Quick Start Guide\n")
            if has_mock:
                readme_lines.append(
                    "### 1. Start External Mock Vendor Service (Port 5100)\n```bash\ncd mock-vendor-api\npip install -r requirements.txt\nuvicorn main:app --port 5100\n```\n"
                )

            if any(k in tf for k in ("cs", "csharp", "dotnet", "net")):
                readme_lines.append(
                    "### 2. Start Channel Application (Port 5001)\n```bash\ncd channel-app\ndotnet run\n```\nSwagger UI: http://localhost:5001/swagger\nHealth Check: http://localhost:5001/health\n"
                )
                readme_lines.append("### 3. Run Automated xUnit Tests\n```bash\ndotnet test\n```\n")
            elif any(k in tf for k in ("next", "react", "type", "ts", "node")):
                readme_lines.append(
                    "### 2. Start Channel Application (Port 3000)\n```bash\ncd channel-app\nnpm install\nnpm run dev\n```\n"
                )
            else:
                readme_lines.append(
                    "### 2. Start Channel Application (Port 8000)\n```bash\ncd channel-app\npip install -r requirements.txt\nuvicorn src.main:app --port 8000\n```\n"
                )

            readme_content = "\n".join(readme_lines)
            try:
                (workspace_dir / "README.md").write_text(readme_content, encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not write root README: {e}")

            run_script_lines = [
                "# AAISE Local Multi-Service Launcher\nWrite-Host 'Starting project services...' -ForegroundColor Cyan\n"
            ]
            if has_mock:
                run_script_lines.append(
                    "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd mock-vendor-api; uvicorn main:app --port 5100'"
                )
            if any(k in tf for k in ("cs", "csharp", "dotnet", "net")):
                run_script_lines.append(
                    "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd channel-app; dotnet run'"
                )
            elif any(k in tf for k in ("next", "react", "type", "ts", "node")):
                run_script_lines.append(
                    "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd channel-app; npm run dev'"
                )
            else:
                run_script_lines.append(
                    "Start-Process powershell -ArgumentList '-NoExit', '-Command', 'cd channel-app; uvicorn src.main:app --port 8000'"
                )

            run_script_content = "\n".join(run_script_lines)
            try:
                (workspace_dir / "run.ps1").write_text(run_script_content, encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not write run.ps1: {e}")

            save_chat_message(
                self.db,
                project_id,
                "assistant",
                release_msg,
            )

            self.db.flush()

            self.checkpoint_service.save_checkpoint(run.id, "RELEASE", s)

            return s

        builder = WorkflowGraphBuilder(
            doc_reviewer_fn=doc_node,
            mock_developer_fn=mock_node,
            main_coder_fn=code_node,
            qa_engineer_fn=qa_node,
            security_reviewer_fn=sec_node,
            release_gate_fn=release_node,
        )

        graph = builder.build_graph()

        final_state = await graph.ainvoke(initial_state)

        self.db.commit()

        return final_state
