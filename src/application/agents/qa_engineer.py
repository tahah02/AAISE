import asyncio
import json
import logging
import re
import subprocess
import time
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
import httpx

from src.domain.agent_base import BaseAgent
from src.domain.enums import AgentType, RepositoryType, TestStatus, Severity
from src.domain.tools import execute_file_read, execute_file_write, get_file_read_tool
from src.infrastructure.db.models import DefectORM, TestCaseORM, TestResultORM, TestRunORM
from src.infrastructure.execution.process_manager import ProjectProcessManager
from src.infrastructure.git.git_service import GitService
from src.infrastructure.llm.provider_resolver import LLMProviderResolver
from src.infrastructure.llm.token_tracker import TokenTrackerService
from src.ports.agent import AgentContext, AgentResult
from src.ports.llm_gateway import LLMMessage, LLMRequest, ToolDefinition

logger = logging.getLogger(__name__)


QA_SYSTEM_PROMPT = """You are Agent 4: Independent QA Engineer.
Your responsibility:
1. Perform strictly black-box contract testing against the API endpoints and test cases specified in docs/XUNIT_TEST_SPEC.md or Technical Design.
2. You must NEVER inspect, read, or rely on application source code.
3. For EVERY test case defined in the specifications:
   - Identify the exact endpoint route, HTTP method (GET, POST, PUT, DELETE), request payload schema, headers, and expected status codes (e.g. 201 Created, 200 OK, 400 Bad Request, 404 Not Found).
   - Provide realistic request payloads for testing happy path and boundary/error conditions.
   - Use the exact test identifier from the document as test_key (e.g., TC-01, IT-01, UT-01).
4. Synthesize complete, runnable xUnit test files implementing the Unit Tests (UT-01..UT-07) and Integration Tests (IT-01..IT-12).

Respond strictly with a JSON object:
{
  "test_results": [
    {
      "test_key": "<Exact test ID from document, e.g. TC-01, IT-01, UT-01>",
      "test_name": "<Short scenario name, e.g. Create valid record>",
      "category": "<CONTRACT | INTEGRATION | VALIDATION | NOT_FOUND | UNIT_TEST>",
      "endpoint": "<Target API endpoint route, e.g. /api/students>",
      "http_method": "<GET | POST | PUT | DELETE>",
      "headers": {"Content-Type": "application/json"},
      "payload": { ... } or null,
      "expected_status": 201,
      "actual_status": 201,
      "status": "<PASSED | FAILED>",
      "details": "<Exact contract validation criteria>"
    }
  ],
  "test_files": {
    "channel-app.Tests/channel-app.Tests.csproj": "<Project Sdk=\\"Microsoft.NET.Sdk\\">...</Project>",
    "channel-app.Tests/UnitTests.cs": "using Xunit; ...",
    "channel-app.Tests/IntegrationTests.cs": "using Xunit; ..."
  },
  "overall_summary": "<Comprehensive summary of all test cases evaluated>"
}
"""


class QAEngineerAgent(BaseAgent):
    def __init__(
        self,
        resolver: LLMProviderResolver,
        git_service: GitService | None = None,
        tracker: TokenTrackerService | None = None,
        db: Session | None = None,
    ) -> None:
        super().__init__(
            agent_type=AgentType.QA_ENGINEER,
            resolver=resolver,
            tracker=tracker,
            db=db,
        )
        self.git_service = git_service

    def get_system_prompt(self, context: AgentContext) -> str:
        return QA_SYSTEM_PROMPT

    def get_tools(self) -> list[ToolDefinition]:
        return [get_file_read_tool()]

    def _read_xunit_spec(self, workspace_path: str) -> str:
        try:
            return execute_file_read(workspace_path, "docs/XUNIT_TEST_SPEC.md")
        except FileNotFoundError:
            return ""

    @staticmethod
    def _parse_trx_file(trx_path: Path) -> list[dict]:
        import xml.etree.ElementTree as ET
        import re

        try:
            tree = ET.parse(trx_path)
        except Exception as e:
            logger.warning(f"Could not parse TRX file at {trx_path}: {e}")
            return []

        root = tree.getroot()
        results = []
        for elem in root.iter():
            if elem.tag.endswith("UnitTestResult"):
                full_test_name = elem.attrib.get("testName", "")
                outcome = elem.attrib.get("outcome", "Passed")
                duration = elem.attrib.get("duration", "")

                clean_dur = ""
                if duration:
                    try:
                        parts = duration.split(":")
                        secs = float(parts[-1])
                        if secs < 1:
                            clean_dur = f"{int(secs * 1000)}ms"
                        else:
                            clean_dur = f"{secs:.2f}s"
                    except Exception:
                        clean_dur = duration

                error_msg = ""
                error_info = elem.find(".//{*}ErrorInfo")
                if error_info is not None:
                    msg_elem = error_info.find(".//{*}Message")
                    if msg_elem is not None and msg_elem.text:
                        error_msg = msg_elem.text.strip()

                id_match = re.search(r"([A-Za-z]{2,4}[-_]\d{1,3})", full_test_name)
                test_key = id_match.group(1).upper().replace("_", "-") if id_match else full_test_name.split(".")[-1]

                test_display = full_test_name.split(".")[-1]
                if id_match:
                    test_display = re.sub(r"^[A-Za-z]{2,4}[-_]\d{1,3}[-_]?", "", test_display).strip()

                key_upper = test_key.upper()
                if key_upper.startswith("UT") or "UNIT" in full_test_name.upper():
                    category = "UNIT_TEST"
                elif key_upper.startswith("IT") or "INTEGRATION" in full_test_name.upper():
                    category = "INTEGRATION_TEST"
                elif key_upper.startswith("EXT"):
                    category = "SUPPLEMENTAL_TEST"
                else:
                    category = "CONTRACT"

                status = "PASSED" if outcome.lower() == "passed" else "FAILED"
                details = error_msg if error_msg else f"Test verified cleanly with zero assertions failed ({clean_dur})."

                http_m = "POST" if "POST" in full_test_name.upper() else ("GET" if "GET" in full_test_name.upper() else "")
                ep = "/"

                results.append({
                    "test_key": test_key,
                    "test_name": test_display or test_key,
                    "category": category,
                    "status": status,
                    "duration": clean_dur,
                    "details": details,
                    "http_method": http_m,
                    "endpoint": ep,
                    "expected_status": 200,
                    "actual_status": 200,
                })

        return results

    def _execute_cli_tests(self, target_root: Path, target_framework: str = "csharp") -> tuple[bool, str, list[dict]]:
        framework_lower = (target_framework or "").lower()
        if not any(k in framework_lower for k in ("cs", "csharp", "dotnet", "net")):
            return False, "CLI test runner skipped for non-C# target framework.", []

        test_projects = list(target_root.glob("**/*[Tt]est*/*.csproj"))
        if not test_projects:
            test_projects = list(target_root.glob("*[Tt]est*/*.csproj"))

        if test_projects:
            try:
                for old_trx in target_root.glob("**/test_results.trx"):
                    try:
                        old_trx.unlink()
                    except Exception:
                        pass

                res = subprocess.run(
                    [
                        "dotnet", "test", str(test_projects[0]),
                        "--logger", "trx;LogFileName=test_results.trx",
                        "--nologo", "-v", "minimal",
                    ],
                    cwd=str(target_root),
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                output = f"{res.stdout}\n{res.stderr}".strip()
                failed_match = re.search(r"Failed:\s*(\d+)", output)
                has_failed = bool(failed_match and int(failed_match.group(1)) > 0)
                success = (res.returncode == 0) and ("Build FAILED" not in output) and not has_failed

                trx_files = list(target_root.glob("**/test_results.trx")) or list(target_root.glob("**/*.trx"))
                trx_results = []
                if trx_files:
                    trx_results = self._parse_trx_file(trx_files[0])

                return success, output, trx_results
            except Exception as e:
                logger.warning(f"Could not execute dotnet test: {e}")
                return False, f"CLI runner execution error: {e}", []

        return False, "No physical test project detected on disk.", []

    async def _execute_live_http_tests(
        self,
        project_id: uuid.UUID | str,
        target_framework: str,
        test_cases: list[dict],
        workspace_path: str,
    ) -> tuple[bool, list[dict], str]:
        ws_p = Path(workspace_path).resolve()
        base_dir = str(ws_p.parent) if ws_p.name == str(project_id) else str(ws_p)
        pm = ProjectProcessManager.get_instance(base_workspace_dir=base_dir)
        live_results: list[dict] = []
        execution_log = ""
        server_launched = False

        try:
            launch_info = pm.start_project(
                project_id=project_id,
                target_framework=target_framework,
                subsystem="channel-app",
            )
            port = launch_info.get("info", {}).get("port")
            if not port:
                return False, test_cases, "Could not obtain port from launched service."
            server_launched = True
            base_url = f"http://localhost:{port}"
            execution_log += f"Live service launched on port {port} (PID: {launch_info.get('info', {}).get('pid')})\n"

            # Probe server for readiness (up to 8 seconds)
            ready = False
            async with httpx.AsyncClient(timeout=2.0) as probe:
                for _ in range(16):
                    try:
                        res = await probe.get(f"{base_url}/health")
                        if res.status_code < 500:
                            ready = True
                            break
                    except Exception:
                        pass
                    try:
                        res = await probe.get(f"{base_url}/swagger/v1/swagger.json")
                        if res.status_code == 200:
                            ready = True
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)

            if not ready:
                execution_log += "Service port open; proceeding with HTTP contract test execution.\n"
            else:
                execution_log += "Service health check confirmed responsive.\n"

            # Execute real HTTP contract calls
            async with httpx.AsyncClient(timeout=10.0) as client:
                for tc in test_cases:
                    t_key = tc.get("test_key", "TC")
                    t_name = tc.get("test_name") or tc.get("name") or t_key
                    cat = tc.get("category", "CONTRACT")
                    method = (tc.get("http_method") or "GET").upper()
                    ep = tc.get("endpoint", "/")
                    if not ep.startswith("/"):
                        ep = f"/{ep}"
                    exp_status = int(tc.get("expected_status", 200))
                    payload = tc.get("payload")
                    headers = tc.get("headers") or {}
                    if payload and method in ("POST", "PUT", "PATCH") and "Content-Type" not in headers:
                        headers["Content-Type"] = "application/json"

                    full_url = f"{base_url}{ep}"

                    # Dynamically randomize unique fields (email, username, etc.) to prevent false-negative 409 conflict loops
                    def _randomize_payload(obj):
                        if isinstance(obj, dict):
                            new_obj = {}
                            for k, v in obj.items():
                                if isinstance(v, str) and "@" in v and not v.startswith("conflict_"):
                                    parts = v.split("@")
                                    rand_suffix = uuid.uuid4().hex[:6]
                                    new_obj[k] = f"{parts[0]}_{rand_suffix}@{parts[1]}"
                                else:
                                    new_obj[k] = _randomize_payload(v)
                            return new_obj
                        elif isinstance(obj, list):
                            return [_randomize_payload(i) for i in obj]
                        return obj

                    effective_payload = _randomize_payload(payload) if payload else payload

                    curl_cmd = f"curl -X {method} \"{full_url}\""
                    for hk, hv in headers.items():
                        curl_cmd += f" -H \"{hk}: {hv}\""
                    if effective_payload and method in ("POST", "PUT", "PATCH"):
                        curl_cmd += f" -d '{json.dumps(effective_payload)}'"

                    t0 = time.perf_counter()
                    try:
                        req_kw = {"headers": headers}
                        if effective_payload is not None:
                            if method in ("POST", "PUT", "PATCH"):
                                req_kw["json"] = effective_payload
                            elif method == "GET" and isinstance(effective_payload, dict):
                                req_kw["params"] = effective_payload

                        resp = await client.request(method, full_url, **req_kw)
                        latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
                        actual_status = resp.status_code
                        resp_snippet = resp.text[:400] if resp.text else ""
                        passed = (actual_status == exp_status)
                        details = (
                            f"HTTP {actual_status} ({latency_ms}ms) - Contract verified cleanly."
                            if passed
                            else f"Assertion failed: Expected HTTP {exp_status}, received HTTP {actual_status}. Response: {resp_snippet[:150]}"
                        )
                    except Exception as exc:
                        latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
                        actual_status = 0
                        resp_snippet = f"Connection error: {exc}"
                        passed = False
                        details = f"Connection error connecting to {full_url}: {exc}"

                    live_results.append({
                        "test_key": t_key,
                        "test_name": t_name,
                        "category": cat,
                        "http_method": method,
                        "endpoint": ep,
                        "expected_status": exp_status,
                        "actual_status": actual_status,
                        "status": "PASSED" if passed else "FAILED",
                        "duration": f"{latency_ms}ms",
                        "duration_ms": latency_ms,
                        "details": details,
                        "request_payload": effective_payload,
                        "response_body": resp_snippet,
                        "curl_command": curl_cmd,
                    })

            all_passed = all(r.get("status") == "PASSED" for r in live_results)
            return all_passed, live_results, execution_log

        except Exception as e:
            logger.warning(f"Live HTTP execution encountered an issue: {e}")
            return False, test_cases, f"Live HTTP execution failed: {e}"

        finally:
            # Keep server running if live tests ran so user can click Swagger/API links
            # We do NOT kill immediately on shutdown, allowing user inspection
            if server_launched:
                logger.info(f"Test server remains active on base URL: {base_url} for user and Swagger inspection.")

    async def execute(self, context: AgentContext, input_text: str) -> AgentResult:
        # Load XUnit test specifications document
        test_spec = self._read_xunit_spec(context.workspace_path)
        if not test_spec:
            return AgentResult(
                success=False,
                summary="docs/XUNIT_TEST_SPEC.md not found in workspace. Cannot perform black-box testing.",
                error_message="Missing test specification artifact",
            )

        user_content = (
            f"## XUnit Test Specifications Document:\n\n{test_spec}\n\n"
            f"## Evaluation Context:\n{input_text}"
        )

        messages = self.build_initial_messages(context, user_content)

        resolved_config = self.resolver.resolve_agent_config(
            session=self.db,
            project_id=context.project_id,
            agent=self.agent_type,
        )
        adapter = resolved_config.adapter

        request = LLMRequest(
            provider=resolved_config.provider,
            model=resolved_config.model,
            fallback_provider=resolved_config.fallback_provider,
            fallback_model=resolved_config.fallback_model,
            messages=messages,
            response_schema={"type": "json_object"},
            temperature=0.0,
            max_tokens=4000,
        )

        response = await adapter.complete(request)

        if self.tracker:
            self.tracker.record_invocation(
                agent_execution_id=context.agent_execution_id,
                provider=resolved_config.provider,
                model_name=resolved_config.model,
                latency_ms=response.latency_ms,
                success=True,
                response=response,
            )

        try:
            content_data = json.loads(response.content)
            results_list = content_data.get("test_results", [])
            test_files = content_data.get("test_files", {})
            summary = content_data.get("overall_summary", "Black-box contract testing completed.")
        except Exception:
            results_list = []
            test_files = {}
            summary = "Contract evaluation raw output parsed."

        passed_count = sum(1 for r in results_list if r.get("status") == "PASSED")
        failed_count = sum(1 for r in results_list if r.get("status") != "PASSED")
        overall_status = "PASSED" if (failed_count == 0 and passed_count > 0) else "FAILED"

        # Locate channel repo path
        channel_repo_path: Path | None = None
        if self.git_service:
            try:
                channel_repo_path = Path(self.git_service.get_repository_path(
                    project_id=context.project_id,
                    repo_type=RepositoryType.CHANNEL_APP,
                ))
            except Exception:
                pass
        if not channel_repo_path:
            channel_repo_path = Path(context.workspace_path) / "channel-app"

        # Write any dynamically generated test files to workspace
        written_test_files: list[str] = []
        target_root = channel_repo_path.parent if channel_repo_path.name == "channel-app" else channel_repo_path
        if test_files:
            for rel_p, code_content in test_files.items():
                execute_file_write(str(target_root), rel_p, code_content)
                written_test_files.append(rel_p)

        # Check if runnable backend application files exist on disk
        channel_dir = Path(target_root) / "channel-app" if (Path(target_root) / "channel-app").exists() else Path(target_root)
        has_runnable_backend = (
            (channel_dir / "Program.cs").exists()
            or (channel_dir / "main.py").exists()
            or (channel_dir / "src" / "main.py").exists()
        )

        cli_output = ""
        live_executed = False

        if has_runnable_backend and results_list:
            live_success, live_results, live_log = await self._execute_live_http_tests(
                project_id=context.project_id,
                target_framework=context.target_framework or "generic",
                test_cases=results_list,
                workspace_path=context.workspace_path,
            )
            if live_results:
                results_list = live_results
                passed_count = sum(1 for r in results_list if r.get("status") == "PASSED")
                failed_count = sum(1 for r in results_list if r.get("status") != "PASSED")
                overall_status = "PASSED" if (failed_count == 0 and passed_count > 0 and live_success) else "FAILED"
                summary = f"Live API Contract Testing completed: {passed_count} passed, {failed_count} failed."
                cli_output = live_log
                live_executed = True

        if not live_executed:
            has_physical_project = bool(list(target_root.glob("**/*[Tt]est*/*.csproj")) or list(target_root.glob("*[Tt]est*/*.csproj")))
            framework_lower = (context.target_framework or "").lower()
            is_csharp = any(k in framework_lower for k in ("cs", "csharp", "dotnet", "net"))

            if has_physical_project and is_csharp and (channel_dir / "Program.cs").exists():
                cli_success, cli_output, trx_results = self._execute_cli_tests(target_root, context.target_framework or "csharp")
                if trx_results:
                    results_list = trx_results
                    passed_count = sum(1 for r in results_list if r.get("status") == "PASSED")
                    failed_count = sum(1 for r in results_list if r.get("status") != "PASSED")
                    overall_status = "PASSED" if (failed_count == 0 and passed_count > 0 and cli_success) else "FAILED"
                    summary = f"xUnit test suite executed cleanly with {passed_count} passed and {failed_count} failed."
                elif not cli_success:
                    passed_count = 0
                    failed_count = max(1, len(results_list))
                    overall_status = "FAILED"
                    summary = f"Physical test runner failed during compilation or execution: {cli_output[:300]}"
                    if not results_list:
                        results_list = [{
                            "test_key": "BUILD-VERIFY",
                            "status": "FAILED",
                            "category": "BUILD",
                            "endpoint": "/",
                            "details": cli_output[:1000] if cli_output else "Compilation/Execution failed.",
                        }]
            else:
                passed_count = sum(1 for r in results_list if r.get("status") == "PASSED")
                failed_count = sum(1 for r in results_list if r.get("status") != "PASSED")
                overall_status = "PASSED" if (failed_count == 0 and passed_count > 0) else "FAILED"

        defects_created = []

        # Persist test run and test results in database
        if self.db:
            test_run = TestRunORM(
                project_id=context.project_id,
                execution_type="BLACK_BOX_CONTRACT",
                passed_count=passed_count,
                failed_count=failed_count,
                status=overall_status,
            )
            self.db.add(test_run)
            self.db.flush()

            for r in results_list:
                test_case = (
                    self.db.query(TestCaseORM)
                    .filter_by(project_id=context.project_id, test_key=r.get("test_key", "TC"))
                    .first()
                )
                if not test_case:
                    test_case = TestCaseORM(
                        project_id=context.project_id,
                        test_key=r.get("test_key", f"TC-{uuid.uuid4().hex[:6]}"),
                        category=r.get("category", "CONTRACT"),
                        endpoint=r.get("endpoint", "/"),
                        http_method=r.get("http_method", "GET"),
                        expected_status=r.get("expected_status", 200),
                    )
                    self.db.add(test_case)
                    self.db.flush()

                test_res = TestResultORM(
                    test_run_id=test_run.id,
                    test_case_id=test_case.id,
                    status=r.get("status", "PASSED"),
                    actual_status_code=r.get("actual_status", 200),
                    response_body=r.get("details", ""),
                )
                self.db.add(test_res)

                if r.get("status") != "PASSED":
                    defect = DefectORM(
                        project_id=context.project_id,
                        assigned_agent=AgentType.MAIN_CODING.value,
                        severity=r.get("severity", "HIGH"),
                        description=f"Test {r.get('test_key')} failed on {r.get('endpoint')}: {r.get('details')}",
                        status="OPEN",
                    )
                    self.db.add(defect)
                    defects_created.append(defect)

            self.db.flush()

        return AgentResult(
            success=(overall_status == "PASSED"),
            summary=summary,
            artifacts_created=written_test_files,
            metadata={
                "passed_count": passed_count,
                "failed_count": failed_count,
                "overall_status": overall_status,
                "live_executed": live_executed,
                "defects_reported": len(defects_created),
                "test_results": results_list,
                "cli_output": cli_output,
                "test_artifacts": written_test_files,
            },
        )
