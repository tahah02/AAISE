const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8081";

export interface ProjectItem {
  id: string;
  name: string;
  description?: string;
  target_framework: string;
  status: string;
  current_branch?: string;
  workspace_path?: string;
}

export interface ArtifactItem {
  id: string;
  file_name?: string;
  file_path: string;
  file_type: string;
  content?: string;
  created_at?: string;
}

export interface WorkflowStartRequest {
  project_id?: string;
  project_name?: string;
  user_requirement: string;
}

export interface WorkflowStartResponse {
  workflow_run_id?: string;
  project_id?: string;
  status: string;
  message: string;
  is_greeting?: boolean;
  assistant_reply?: string;
}

export interface ResolveApprovalRequest {
  approval_id?: string;
  project_id?: string;
  approved: boolean;
  comments?: string;
}

export interface ResolveApprovalResponse {
  approval_id: string;
  status: string;
  reviewer_comments?: string;
}

export interface BackendChatMessage {
  id: string;
  sender: "user" | "assistant" | "agent1" | "agent3";
  sender_name: string;
  text: string;
  timestamp: string;
  approval_required?: boolean;
  approval_id?: string;
  specs_ready?: boolean;
  agent3_tasks?: { label: string; status: "pending" | "in_progress" | "done" | "failed" }[];
  agent3_logs?: string[];
}

export async function fetchProjects(): Promise<ProjectItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function fetchProjectArtifacts(projectId: string): Promise<ArtifactItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/workflow/${projectId}/artifacts`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export async function fetchProjectBranches(projectId: string): Promise<{ branches: string[]; current_branch: string | null }> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/branches`);
    if (!res.ok) return { branches: [], current_branch: null };
    return res.json();
  } catch {
    return { branches: [], current_branch: null };
  }
}

export async function fetchProjectDiff(projectId: string): Promise<string> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/diff`);
    if (!res.ok) return "";
    const data = await res.json();
    return data.diff || "";
  } catch {
    return "";
  }
}

export async function fetchProjectFileContent(projectId: string, filePath: string): Promise<string> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/file?path=${encodeURIComponent(filePath)}`);
    if (!res.ok) return "";
    const data = await res.json();
    return data.content || "";
  } catch {
    return "";
  }
}

export async function fetchProjectMessages(projectId: string): Promise<{ run_id: string | null; run_status?: string | null; messages: any[] }> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/messages`);
    if (!res.ok) return { run_id: null, run_status: null, messages: [] };
    return res.json();
  } catch {
    return { run_id: null, run_status: null, messages: [] };
  }
}

export function getProjectDownloadUrl(projectId: string): string {
  return `${API_BASE}/api/v1/projects/${projectId}/download`;
}

export interface AgentConfigItem {
  agent_type: string;
  agent_name: string;
  is_mandatory: boolean;
  is_enabled: boolean;
  provider: string;
  model_name: string;
}

export interface ProjectAgentsResponse {
  project_id: string;
  agents: AgentConfigItem[];
  toggles: {
    agent1: boolean;
    agent2: boolean;
    agent3: boolean;
    agent4: boolean;
    agent5: boolean;
  };
}

export async function createProject(
  name: string,
  description?: string,
  target_framework?: string,
  custom_workspace_path?: string,
  agent_toggles?: { agent1?: boolean; agent2?: boolean; agent3?: boolean; agent4?: boolean; agent5?: boolean }
): Promise<ProjectItem> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        description,
        target_framework: target_framework || "PYTHON_FASTAPI",
        custom_workspace_path: custom_workspace_path || undefined,
        agent_toggles: agent_toggles || undefined,
      }),
    });
  } catch (netErr: any) {
    throw new Error(
      `Cannot connect to AAISE backend at ${API_BASE}. Please ensure FastAPI is running (python run_backend.py).`
    );
  }

  if (!res.ok) {
    let msg = "Failed to create project";
    try {
      const errJson = await res.json();
      if (errJson && errJson.detail) msg = errJson.detail;
    } catch {
      const txt = await res.text().catch(() => "");
      if (txt) msg = txt;
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function fetchProjectAgents(projectId: string): Promise<ProjectAgentsResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/agents`);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function updateProjectAgents(
  projectId: string,
  toggles: { agent1?: boolean; agent2?: boolean; agent3?: boolean; agent4?: boolean; agent5?: boolean }
): Promise<ProjectAgentsResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/agents`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent1_enabled: toggles.agent1,
        agent2_enabled: toggles.agent2,
        agent3_enabled: toggles.agent3,
        agent4_enabled: toggles.agent4,
        agent5_enabled: toggles.agent5,
        toggles,
      }),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function startWorkflow(
  req: WorkflowStartRequest,
  files?: File[]
): Promise<WorkflowStartResponse> {
  try {
    if (files && files.length > 0) {
      const formData = new FormData();
      if (req.project_id) formData.append("project_id", req.project_id);
      if (req.project_name) formData.append("project_name", req.project_name);
      formData.append("user_requirement", req.user_requirement);
      files.forEach((file) => formData.append("files", file));

      const res = await fetch(`${API_BASE}/api/v1/workflow/start-multipart`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Failed to send message: ${res.status} ${errorText}`);
      }
      return res.json();
    }

    const res = await fetch(`${API_BASE}/api/v1/workflow/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Failed to send message: ${res.status} ${errorText}`);
    }
    return res.json();
  } catch (err: any) {
    if (err.message && err.message.includes("Failed to send message")) {
      throw err;
    }
    throw new Error(`Cannot connect to AAISE backend at ${API_BASE}. Please ensure FastAPI is running (python run_backend.py).`);
  }
}

export async function resolveApproval(req: ResolveApprovalRequest): Promise<ResolveApprovalResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1/workflow/approval/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  } catch (netErr: any) {
    throw new Error(
      `Cannot connect to AAISE backend at ${API_BASE}. Please ensure FastAPI is running (python run_backend.py).`
    );
  }
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to resolve approval: ${res.status} ${errorText}`);
  }
  return res.json();
}

export async function cancelWorkflow(runIdOrProjectId: { runId?: string; projectId?: string }): Promise<any> {
  const url = runIdOrProjectId.runId
    ? `${API_BASE}/api/v1/workflow/${runIdOrProjectId.runId}/cancel`
    : `${API_BASE}/api/v1/workflow/cancel?project_id=${runIdOrProjectId.projectId}`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      return { status: "ERROR" };
    }
    return res.json();
  } catch {
    return { status: "CANCELLED" };
  }
}

export function subscribeToWorkflowStream(
  runId: string,
  onEvent: (event: Record<string, unknown>) => void,
  onError?: (err: Event) => void
): EventSource {
  const url = `${API_BASE}/api/v1/workflow/${runId}/stream`;
  const es = new EventSource(url);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onEvent(data);
    } catch (e) {
      console.error("Failed to parse SSE payload", e, event.data);
    }
  };

  es.onerror = (err) => {
    if (onError) onError(err);
  };

  return es;
}

export interface ProcessStatusResponse {
  project_id?: string;
  subsystem?: string;
  status: "RUNNING" | "STOPPED" | "ALREADY_RUNNING";
  pid?: number;
  port?: number;
  url?: string;
  started_at?: string;
  message?: string;
  info?: {
    project_id: string;
    subsystem: string;
    pid: number;
    port: number;
    url: string;
    status: string;
    started_at: string;
    log_count: number;
  };
  channel_app?: ProcessStatusResponse;
  frontend?: ProcessStatusResponse;
}

export async function runProject(
  projectId: string,
  subsystem: string = "channel-app"
): Promise<ProcessStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subsystem }),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to start project: ${errorText}`);
  }
  return res.json();
}

export async function stopProject(
  projectId: string,
  subsystem?: string
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subsystem }),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to stop project: ${errorText}`);
  }
  return res.json();
}

export async function fetchProjectStatus(
  projectId: string,
  subsystem: string = "all"
): Promise<ProcessStatusResponse> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/projects/${projectId}/status?subsystem=${subsystem}`);
    if (!res.ok) return { status: "STOPPED" };
    return res.json();
  } catch {
    return { status: "STOPPED" };
  }
}

export interface AnalyticsOverview {
  total_projects: number;
  total_runs: number;
  tokens: {
    total: number;
    prompt: number;
    completion: number;
    cost_usd: number;
    invocations: number;
    avg_latency_ms: number;
    avg_latency_sec: number;
  };
  projects_summary?: Array<{
    id: string;
    name: string;
    target_framework: string;
    tokens: number;
    invocations: number;
  }>;
  qa: {
    total_runs: number;
    passed_runs: number;
    failed_runs: number;
    total_tests: number;
    passed_tests: number;
    failed_tests: number;
    pass_rate_pct: number;
  };
  security: {
    total_scans: number;
    passed_scans: number;
    total_findings: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  approvals: {
    total: number;
    pending: number;
    approved: number;
    rejected: number;
  };
}

export interface AnalyticsInvocationItem {
  id: string;
  provider: string;
  model_name: string;
  latency_ms: number;
  latency_sec: number;
  llm_latency_sec?: number;
  task_duration_sec?: number | null;
  task_duration_label?: string | null;
  success: boolean;
  error_message?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  invoked_at: string | null;
  agent_name: string;
  task_type?: string;
  project_id?: string | null;
  project_name: string;
}

export interface AnalyticsTokensResponse {
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    calls: number;
  };
  by_provider: Array<{
    provider: string;
    tokens: number;
    cost_usd: number;
    calls: number;
    avg_latency_ms: number;
  }>;
  by_model: Array<{
    model: string;
    provider: string;
    tokens: number;
    cost_usd: number;
    calls: number;
  }>;
  by_agent: Array<{
    agent_name: string;
    tokens: number;
    cost_usd: number;
    calls: number;
  }>;
  invocations: AnalyticsInvocationItem[];
}

export interface AnalyticsQAResultItem {
  id: string;
  test_key: string;
  category: string;
  endpoint: string;
  http_method: string;
  expected_status: number;
  actual_status_code: number;
  status: string;
  response_body?: string | null;
}

export interface AnalyticsQARunItem {
  id: string;
  project_id: string;
  project_name: string;
  execution_type: string;
  passed_count: number;
  failed_count: number;
  total_count: number;
  status: string;
  executed_at: string | null;
  results: AnalyticsQAResultItem[];
}

export interface AnalyticsQAReportsResponse {
  test_runs: AnalyticsQARunItem[];
}

export interface AnalyticsSecurityFindingItem {
  id: string;
  severity: string;
  vulnerability_type: string;
  target_repo: string;
  file_path: string;
  line_number?: number | null;
  description: string;
  remediation_advice: string;
  status: string;
  discovered_at: string | null;
}

export interface AnalyticsSecurityScanItem {
  id: string;
  project_id: string;
  project_name: string;
  scanner_type: string;
  status: string;
  scanned_at: string | null;
  findings_count: number;
  findings: AnalyticsSecurityFindingItem[];
}

export interface AnalyticsSecurityResponse {
  scans: AnalyticsSecurityScanItem[];
}

export interface AnalyticsApprovalItem {
  id: string;
  workflow_run_id: string;
  project_id?: string | null;
  project_name: string;
  gate_type: string;
  status: string;
  prompt_text: string;
  reviewer_comments?: string | null;
  requested_at: string | null;
  resolved_at?: string | null;
}

export interface AnalyticsApprovalsResponse {
  approvals: AnalyticsApprovalItem[];
}

export async function fetchAnalyticsOverview(projectId?: string): Promise<AnalyticsOverview | null> {
  try {
    const url = projectId
      ? `${API_BASE}/api/v1/analytics/overview?project_id=${projectId}`
      : `${API_BASE}/api/v1/analytics/overview`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function fetchAnalyticsTokens(projectId?: string): Promise<AnalyticsTokensResponse | null> {
  try {
    const url = projectId
      ? `${API_BASE}/api/v1/analytics/tokens?project_id=${projectId}`
      : `${API_BASE}/api/v1/analytics/tokens`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function fetchAnalyticsQAReports(projectId?: string): Promise<AnalyticsQAReportsResponse | null> {
  try {
    const url = projectId
      ? `${API_BASE}/api/v1/analytics/qa-reports?project_id=${projectId}`
      : `${API_BASE}/api/v1/analytics/qa-reports`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function fetchAnalyticsSecurity(projectId?: string): Promise<AnalyticsSecurityResponse | null> {
  try {
    const url = projectId
      ? `${API_BASE}/api/v1/analytics/security?project_id=${projectId}`
      : `${API_BASE}/api/v1/analytics/security`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export async function fetchAnalyticsApprovals(projectId?: string): Promise<AnalyticsApprovalsResponse | null> {
  try {
    const url = projectId
      ? `${API_BASE}/api/v1/analytics/approvals?project_id=${projectId}`
      : `${API_BASE}/api/v1/analytics/approvals`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
