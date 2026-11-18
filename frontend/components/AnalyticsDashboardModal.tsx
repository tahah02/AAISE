"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Zap,
  Clock,
  Coins,
  CheckCircle2,
  FlaskConical,
  ShieldCheck,
  Activity,
  RotateCcw,
  Search,
  Layers,
  Cpu,
  FileCheck2,
  ChevronDown,
  AlertTriangle,
} from "lucide-react";
import {
  AnalyticsOverview,
  AnalyticsTokensResponse,
  AnalyticsQAReportsResponse,
  AnalyticsSecurityResponse,
  AnalyticsApprovalsResponse,
  ProjectItem,
  fetchAnalyticsOverview,
  fetchAnalyticsTokens,
  fetchAnalyticsQAReports,
  fetchAnalyticsSecurity,
  fetchAnalyticsApprovals,
} from "@/lib/api";

interface AnalyticsDashboardModalProps {
  isOpen: boolean;
  onClose: () => void;
  projects: ProjectItem[];
  selectedProjectId?: string | null;
}

export function AnalyticsDashboardModal({
  isOpen,
  onClose,
  projects,
  selectedProjectId,
}: AnalyticsDashboardModalProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "tokens" | "qa" | "security" | "approvals">("overview");
  const [filterProjectId, setFilterProjectId] = useState<string>(selectedProjectId || "all");
  const [isLoading, setIsLoading] = useState(false);

  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [tokenData, setTokenData] = useState<AnalyticsTokensResponse | null>(null);
  const [qaData, setQaData] = useState<AnalyticsQAReportsResponse | null>(null);
  const [secData, setSecData] = useState<AnalyticsSecurityResponse | null>(null);
  const [appData, setAppData] = useState<AnalyticsApprovalsResponse | null>(null);

  const [invocationSearch, setInvocationSearch] = useState("");
  const [expandedRunId, setExpandedRunId] = useState<string | null>(null);

  useEffect(() => {
    if (selectedProjectId) {
      setFilterProjectId(selectedProjectId);
    }
  }, [selectedProjectId]);

  useEffect(() => {
    let ignore = false;
    if (isOpen) {
      queueMicrotask(() => {
        if (!ignore) setIsLoading(true);
      });
      const idToPass = filterProjectId === "all" ? undefined : filterProjectId;
      Promise.all([
        fetchAnalyticsOverview(idToPass),
        fetchAnalyticsTokens(idToPass),
        fetchAnalyticsQAReports(idToPass),
        fetchAnalyticsSecurity(idToPass),
        fetchAnalyticsApprovals(idToPass),
      ]).then(([ov, tok, qa, sec, app]) => {
        if (!ignore) {
          setOverview(ov);
          setTokenData(tok);
          setQaData(qa);
          setSecData(sec);
          setAppData(app);
          if (qa?.test_runs && qa.test_runs.length > 0) {
            setExpandedRunId(qa.test_runs[0].id);
          }
          setIsLoading(false);
        }
      }).catch((err) => {
        console.error("Failed to load analytics:", err);
        if (!ignore) setIsLoading(false);
      });
    }
    return () => {
      ignore = true;
    };
  }, [isOpen, filterProjectId]);

  const handleManualRefresh = async () => {
    setIsLoading(true);
    const idToPass = filterProjectId === "all" ? undefined : filterProjectId;
    try {
      const [ov, tok, qa, sec, app] = await Promise.all([
        fetchAnalyticsOverview(idToPass),
        fetchAnalyticsTokens(idToPass),
        fetchAnalyticsQAReports(idToPass),
        fetchAnalyticsSecurity(idToPass),
        fetchAnalyticsApprovals(idToPass),
      ]);
      setOverview(ov);
      setTokenData(tok);
      setQaData(qa);
      setSecData(sec);
      setAppData(app);
      if (qa?.test_runs && qa.test_runs.length > 0) {
        setExpandedRunId(qa.test_runs[0].id);
      }
    } catch (err) {
      console.error("Failed to refresh analytics:", err);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) return null;

  const filteredInvocations = (tokenData?.invocations || []).filter((inv) => {
    if (!invocationSearch.trim()) return true;
    const q = invocationSearch.toLowerCase();
    return (
      inv.model_name.toLowerCase().includes(q) ||
      inv.provider.toLowerCase().includes(q) ||
      inv.agent_name.toLowerCase().includes(q) ||
      inv.project_name.toLowerCase().includes(q)
    );
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="relative w-full max-w-6xl max-h-[92vh] flex flex-col bg-[#0b0f19] border border-slate-800 rounded-xl shadow-2xl overflow-hidden font-sans text-slate-200">
        
        {/* Top Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-[#0d1322]">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Activity className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-100 tracking-wide">
                  AAISE Observability & Telemetry Portal
                </h2>
                <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  SQLite Live Data
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Durable telemetry, token economics, QA black-box contracts, and human approvals from <code className="text-slate-300">./data/aaise.db</code>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Project Filter */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400 font-medium hidden sm:inline">Project:</span>
              <select
                value={filterProjectId}
                onChange={(e) => setFilterProjectId(e.target.value)}
                className="bg-[#141b2d] border border-slate-700/80 rounded-md px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-cyan-500 transition cursor-pointer"
              >
                <option value="all">All Projects (Global)</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Refresh */}
            <button
              onClick={() => handleManualRefresh()}
              disabled={isLoading}
              className="p-1.5 rounded-md border border-slate-700 bg-[#141b2d] text-slate-300 hover:text-white hover:border-slate-600 transition disabled:opacity-50"
              title="Refresh Data"
            >
              <RotateCcw className={`h-4 w-4 ${isLoading ? "animate-spin text-cyan-400" : ""}`} />
            </button>

            {/* Close */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-md border border-slate-800 bg-[#141b2d] text-slate-400 hover:text-slate-100 hover:border-slate-700 transition"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 px-6 pt-3 border-b border-slate-800 bg-[#0d1322]/50 text-xs font-medium">
          <button
            onClick={() => setActiveTab("overview")}
            className={`pb-2.5 px-3 border-b-2 transition flex items-center gap-2 ${
              activeTab === "overview"
                ? "border-cyan-400 text-cyan-300 font-semibold"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Activity className="h-4 w-4" />
            Executive Overview
          </button>
          <button
            onClick={() => setActiveTab("tokens")}
            className={`pb-2.5 px-3 border-b-2 transition flex items-center gap-2 ${
              activeTab === "tokens"
                ? "border-amber-400 text-amber-300 font-semibold"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Zap className="h-4 w-4" />
            Tokens & LLM Invocations ({overview?.tokens?.invocations ?? tokenData?.invocations?.length ?? 0})
          </button>
          <button
            onClick={() => setActiveTab("qa")}
            className={`pb-2.5 px-3 border-b-2 transition flex items-center gap-2 ${
              activeTab === "qa"
                ? "border-purple-400 text-purple-300 font-semibold"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <FlaskConical className="h-4 w-4" />
            QA Contract Reports ({overview?.qa?.total_runs ?? qaData?.test_runs?.length ?? 0})
          </button>
          <button
            onClick={() => setActiveTab("security")}
            className={`pb-2.5 px-3 border-b-2 transition flex items-center gap-2 ${
              activeTab === "security"
                ? "border-emerald-400 text-emerald-300 font-semibold"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <ShieldCheck className="h-4 w-4" />
            Security Audit ({overview?.security?.total_scans ?? secData?.scans?.length ?? 0})
          </button>
          <button
            onClick={() => setActiveTab("approvals")}
            className={`pb-2.5 px-3 border-b-2 transition flex items-center gap-2 ${
              activeTab === "approvals"
                ? "border-blue-400 text-blue-300 font-semibold"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <FileCheck2 className="h-4 w-4" />
            Human Approvals Log ({overview?.approvals?.total ?? appData?.approvals?.length ?? 0})
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading && !overview ? (
            <div className="h-64 flex flex-col items-center justify-center gap-3 text-slate-400">
              <RotateCcw className="h-6 w-6 animate-spin text-cyan-400" />
              <p className="text-sm">Fetching live telemetry from SQLite...</p>
            </div>
          ) : !overview ? (
            <div className="h-64 flex flex-col items-center justify-center gap-3 text-slate-400 text-center p-6">
              <AlertTriangle className="h-8 w-8 text-amber-400 mb-1" />
              <h4 className="text-sm font-semibold text-slate-200">Unable to Connect to Platform Backend API</h4>
              <p className="text-xs text-slate-400 max-w-md">
                Could not fetch telemetry from <code className="text-cyan-400 font-mono">http://localhost:8081/api/v1/analytics</code>.
                Please restart the backend server so the newly added analytics routes are active:
                <br />
                <code className="text-amber-300 font-mono mt-1 inline-block bg-slate-900 px-2 py-1 rounded">.venv\Scripts\python.exe run_backend.py</code>
              </p>
              <button
                onClick={() => handleManualRefresh()}
                className="mt-3 px-3 py-1.5 rounded-md bg-cyan-600 hover:bg-cyan-500 text-xs font-semibold text-white transition"
              >
                Retry Connection
              </button>
            </div>
          ) : (
            <>
              {/* TAB 1: EXECUTIVE OVERVIEW */}
              {activeTab === "overview" && overview && (
                <div className="space-y-6">
                  {/* Top KPI Cards */}
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                    <div className="p-4 rounded-lg bg-[#111827]/80 border border-amber-500/20">
                      <div className="flex items-center justify-between text-amber-400 mb-2">
                        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Total Tokens</span>
                        <Zap className="h-4 w-4" />
                      </div>
                      <div className="text-xl font-bold font-mono text-slate-100">
                        {overview.tokens.total.toLocaleString()}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1 flex gap-2 font-mono">
                        <span>P: {overview.tokens.prompt.toLocaleString()}</span>
                        <span>•</span>
                        <span>C: {overview.tokens.completion.toLocaleString()}</span>
                      </div>
                    </div>

                    <div className="p-4 rounded-lg bg-[#111827]/80 border border-emerald-500/20">
                      <div className="flex items-center justify-between text-emerald-400 mb-2">
                        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Est. Cost (USD)</span>
                        <Coins className="h-4 w-4" />
                      </div>
                      <div className="text-xl font-bold font-mono text-emerald-400">
                        ${overview.tokens.cost_usd.toFixed(4)}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        Across {overview.tokens.invocations} calls
                      </div>
                    </div>

                    <div className="p-4 rounded-lg bg-[#111827]/80 border border-cyan-500/20">
                      <div className="flex items-center justify-between text-cyan-400 mb-2">
                        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Avg LLM Latency</span>
                        <Clock className="h-4 w-4" />
                      </div>
                      <div className="text-xl font-bold font-mono text-cyan-300">
                        {overview.tokens.avg_latency_sec}s
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1 font-mono">
                        {overview.tokens.avg_latency_ms} ms avg
                      </div>
                    </div>

                    <div className="p-4 rounded-lg bg-[#111827]/80 border border-purple-500/20">
                      <div className="flex items-center justify-between text-purple-400 mb-2">
                        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">QA Pass Rate</span>
                        <FlaskConical className="h-4 w-4" />
                      </div>
                      <div className="text-xl font-bold font-mono text-purple-300">
                        {overview.qa.pass_rate_pct}%
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        {overview.qa.passed_tests} / {overview.qa.total_tests} tests passed
                      </div>
                    </div>

                    <div className="p-4 rounded-lg bg-[#111827]/80 border border-blue-500/20">
                      <div className="flex items-center justify-between text-blue-400 mb-2">
                        <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">Human Approvals</span>
                        <CheckCircle2 className="h-4 w-4" />
                      </div>
                      <div className="text-xl font-bold font-mono text-blue-300">
                        {overview.approvals.total}
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1 flex gap-2">
                        <span className="text-emerald-400">{overview.approvals.approved} Appr</span>
                        <span>•</span>
                        <span className="text-amber-400">{overview.approvals.pending} Pend</span>
                      </div>
                    </div>
                  </div>

                  {/* Provider & Model Distribution */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Providers */}
                    <div className="p-4 rounded-lg bg-[#111827]/60 border border-slate-800">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                          <Cpu className="h-4 w-4 text-cyan-400" />
                          LLM Providers Telemetry
                        </h3>
                        <span className="text-[11px] text-slate-500 font-mono">
                          {tokenData?.by_provider.length || 0} active
                        </span>
                      </div>
                      <div className="space-y-2.5">
                        {tokenData?.by_provider.map((p) => (
                          <div
                            key={p.provider}
                            className="p-2.5 rounded-md bg-[#161f36]/60 border border-slate-800 flex items-center justify-between"
                          >
                            <div>
                              <div className="text-xs font-bold text-slate-200 capitalize flex items-center gap-2">
                                <span>{p.provider}</span>
                                {p.provider.toLowerCase().includes("ollama") ? (
                                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                                    Local
                                  </span>
                                ) : (
                                  <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                    Cloud
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-slate-400 mt-0.5">
                                {p.calls} invocations • {p.avg_latency_ms}ms avg
                              </div>
                            </div>
                            <div className="text-right font-mono">
                              <div className="text-xs font-semibold text-amber-300">
                                {p.tokens.toLocaleString()} toks
                              </div>
                              <div className="text-[10px] text-emerald-400">
                                ${p.cost_usd.toFixed(4)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Agent Distribution */}
                    <div className="p-4 rounded-lg bg-[#111827]/60 border border-slate-800">
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                          <Layers className="h-4 w-4 text-purple-400" />
                          Agent Consumption Breakdown
                        </h3>
                        <span className="text-[11px] text-slate-500 font-mono">
                          {tokenData?.by_agent.length || 0} agents
                        </span>
                      </div>
                      <div className="space-y-2.5">
                        {tokenData?.by_agent.map((a) => (
                          <div
                            key={a.agent_name}
                            className="p-2.5 rounded-md bg-[#161f36]/60 border border-slate-800 flex items-center justify-between"
                          >
                            <div>
                              <div className="text-xs font-semibold text-slate-200">
                                {a.agent_name}
                              </div>
                              <div className="text-[10px] text-slate-400 mt-0.5">
                                {a.calls} invocations executed
                              </div>
                            </div>
                            <div className="text-right font-mono">
                              <div className="text-xs font-semibold text-amber-300">
                                {a.tokens.toLocaleString()} toks
                              </div>
                              <div className="text-[10px] text-emerald-400">
                                ${a.cost_usd.toFixed(4)}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: TOKENS & INVOCATIONS */}
              {activeTab === "tokens" && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="relative flex-1 max-w-md">
                      <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-500" />
                      <input
                        type="text"
                        value={invocationSearch}
                        onChange={(e) => setInvocationSearch(e.target.value)}
                        placeholder="Filter by model, provider, agent..."
                        className="w-full bg-[#111827] border border-slate-800 rounded-md pl-9 pr-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500/50"
                      />
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      Showing {filteredInvocations.length} invocations
                    </div>
                  </div>

                  {/* Table */}
                  <div className="border border-slate-800 rounded-lg overflow-hidden bg-[#0e1424]">
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs font-sans">
                        <thead className="bg-[#141c30] text-slate-400 uppercase text-[10px] font-semibold border-b border-slate-800 tracking-wider">
                          <tr>
                            <th className="px-4 py-2.5">Agent & Model</th>
                            <th className="px-3 py-2.5">Provider</th>
                            <th className="px-3 py-2.5">Latency</th>
                            <th className="px-3 py-2.5 font-mono text-right">Prompt</th>
                            <th className="px-3 py-2.5 font-mono text-right">Comp</th>
                            <th className="px-3 py-2.5 font-mono text-right">Total Toks</th>
                            <th className="px-3 py-2.5 font-mono text-right">Cost (USD)</th>
                            <th className="px-4 py-2.5 text-right">Timestamp</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                          {filteredInvocations.length === 0 ? (
                            <tr>
                              <td colSpan={8} className="text-center py-8 text-slate-500 font-sans text-xs">
                                No invocations match your filter.
                              </td>
                            </tr>
                          ) : (
                            filteredInvocations.map((inv) => (
                              <tr key={inv.id} className="hover:bg-slate-800/30 transition">
                                <td className="px-4 py-2.5">
                                  <div className="font-sans font-semibold text-slate-200 text-xs">
                                    {inv.agent_name}
                                  </div>
                                  <div className="text-slate-400 text-[10.5px]">
                                    {inv.model_name}
                                  </div>
                                </td>
                                <td className="px-3 py-2.5 font-sans capitalize">
                                  <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700/60 text-[10px]">
                                    {inv.provider}
                                  </span>
                                </td>
                                <td className="px-3 py-2.5 text-cyan-300">
                                  {inv.latency_sec}s
                                </td>
                                <td className="px-3 py-2.5 text-right text-slate-400">
                                  {inv.prompt_tokens.toLocaleString()}
                                </td>
                                <td className="px-3 py-2.5 text-right text-slate-400">
                                  {inv.completion_tokens.toLocaleString()}
                                </td>
                                <td className="px-3 py-2.5 text-right font-bold text-amber-300">
                                  {inv.total_tokens.toLocaleString()}
                                </td>
                                <td className="px-3 py-2.5 text-right font-semibold text-emerald-400">
                                  ${inv.cost_usd.toFixed(5)}
                                </td>
                                <td className="px-4 py-2.5 text-right text-slate-500 text-[10px] font-sans">
                                  {inv.invoked_at ? new Date(inv.invoked_at).toLocaleTimeString() : "N/A"}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: QA CONTRACT REPORTS */}
              {activeTab === "qa" && (
                <div className="space-y-4">
                  {(!qaData?.test_runs || qaData.test_runs.length === 0) ? (
                    <div className="p-8 text-center rounded-lg border border-slate-800 bg-[#0e1424] text-slate-500">
                      <FlaskConical className="h-8 w-8 mx-auto mb-2 text-slate-600" />
                      <p className="text-xs">No QA test runs recorded yet.</p>
                      <p className="text-[11px] text-slate-600 mt-1">
                        When Agent 4 runs black-box HTTP contract tests, full status codes and responses will appear here.
                      </p>
                    </div>
                  ) : (
                    qaData.test_runs.map((run) => (
                      <div
                        key={run.id}
                        className="rounded-lg border border-slate-800 bg-[#0e1424] overflow-hidden"
                      >
                        <div
                          onClick={() => setExpandedRunId(expandedRunId === run.id ? null : run.id)}
                          className="px-4 py-3 bg-[#131b2e] flex items-center justify-between cursor-pointer hover:bg-[#162138] transition"
                        >
                          <div className="flex items-center gap-3">
                            <span
                              className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                                run.status === "PASSED"
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                  : "bg-rose-500/10 text-rose-400 border-rose-500/30"
                              }`}
                            >
                              {run.status}
                            </span>
                            <span className="text-xs font-bold text-slate-200">
                              {run.execution_type}
                            </span>
                            <span className="text-xs text-slate-500">•</span>
                            <span className="text-xs text-slate-400 font-mono">
                              {run.passed_count} Passed / {run.failed_count} Failed
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-slate-400">
                            <span>{run.executed_at ? new Date(run.executed_at).toLocaleString() : ""}</span>
                            <ChevronDown
                              className={`h-4 w-4 transition transform ${
                                expandedRunId === run.id ? "rotate-180" : ""
                              }`}
                            />
                          </div>
                        </div>

                        {expandedRunId === run.id && (
                          <div className="p-4 border-t border-slate-800 space-y-3">
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-xs font-sans">
                                <thead className="bg-[#101728] text-slate-400 uppercase text-[10px] font-semibold border-b border-slate-800">
                                  <tr>
                                    <th className="px-3 py-2">Test Key</th>
                                    <th className="px-3 py-2">Method</th>
                                    <th className="px-3 py-2">Endpoint</th>
                                    <th className="px-3 py-2 font-mono text-center">Expected</th>
                                    <th className="px-3 py-2 font-mono text-center">Actual</th>
                                    <th className="px-3 py-2 text-center">Status</th>
                                    <th className="px-3 py-2">Response Snippet</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800 font-mono text-[11px]">
                                  {run.results.map((res) => (
                                    <tr key={res.id} className="hover:bg-slate-800/30">
                                      <td className="px-3 py-2 font-bold text-cyan-400 font-sans">
                                        {res.test_key}
                                      </td>
                                      <td className="px-3 py-2 font-sans">
                                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-300">
                                          {res.http_method}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 font-mono text-slate-300 text-[11px]">
                                        {res.endpoint}
                                      </td>
                                      <td className="px-3 py-2 text-center text-slate-400 font-mono">
                                        {res.expected_status}
                                      </td>
                                      <td className={`px-3 py-2 text-center font-bold font-mono ${
                                        res.actual_status_code === res.expected_status ? "text-emerald-400" : "text-rose-400"
                                      }`}>
                                        {res.actual_status_code}
                                      </td>
                                      <td className="px-3 py-2 text-center">
                                        <span className={`px-2 py-0.5 rounded text-[9.5px] font-bold uppercase font-sans ${
                                          res.status === "PASSED"
                                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
                                            : "bg-rose-500/10 text-rose-400 border border-rose-500/25"
                                        }`}>
                                          {res.status}
                                        </span>
                                      </td>
                                      <td className="px-3 py-2 text-slate-400 text-[10.5px] max-w-xs truncate" title={res.response_body || ""}>
                                        {res.response_body || "—"}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* TAB 4: SECURITY AUDIT */}
              {activeTab === "security" && (
                <div className="space-y-4">
                  {(!secData?.scans || secData.scans.length === 0) ? (
                    <div className="p-8 text-center rounded-lg border border-slate-800 bg-[#0e1424] text-slate-400">
                      <ShieldCheck className="h-10 w-10 mx-auto mb-2 text-emerald-400" />
                      <h4 className="text-sm font-semibold text-slate-200">
                        Agent 5 Security Reviewer: Ready & Configured
                      </h4>
                      <p className="text-xs text-slate-500 mt-1 max-w-lg mx-auto">
                        Zero vulnerabilities recorded in <code className="text-slate-400">./data/aaise.db</code>. When Agent 5 AST / SAST scans execute against generated code repositories, all security findings, CWE classifications, and remediation steps will be recorded here.
                      </p>
                    </div>
                  ) : (
                    secData.scans.map((scan) => (
                      <div key={scan.id} className="p-4 rounded-lg border border-slate-800 bg-[#0e1424] space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-slate-200">{scan.scanner_type}</span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold">
                              {scan.status}
                            </span>
                          </div>
                          <span className="text-xs text-slate-500">
                            {scan.scanned_at ? new Date(scan.scanned_at).toLocaleString() : ""}
                          </span>
                        </div>
                        {scan.findings.map((f) => (
                          <div key={f.id} className="p-3 rounded bg-[#131b2e] border border-slate-800 space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-bold text-rose-400 uppercase">{f.severity}: {f.vulnerability_type}</span>
                              <span className="text-[11px] font-mono text-slate-400">{f.file_path}:{f.line_number}</span>
                            </div>
                            <p className="text-xs text-slate-300">{f.description}</p>
                            <p className="text-[11px] text-cyan-300">Advice: {f.remediation_advice}</p>
                          </div>
                        ))}
                      </div>
                    ))
                  )}
                </div>
              )}

              {/* TAB 5: HUMAN APPROVALS LOG */}
              {activeTab === "approvals" && (
                <div className="space-y-4">
                  {(!appData?.approvals || appData.approvals.length === 0) ? (
                    <div className="p-8 text-center rounded-lg border border-slate-800 bg-[#0e1424] text-slate-500">
                      <FileCheck2 className="h-8 w-8 mx-auto mb-2 text-slate-600" />
                      <p className="text-xs">No human approval records found in database.</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {appData.approvals.map((app) => (
                        <div
                          key={app.id}
                          className="p-4 rounded-lg border border-slate-800 bg-[#0e1424] space-y-2 hover:border-slate-700 transition"
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span
                                className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider border ${
                                  app.status === "APPROVED"
                                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                    : app.status === "REJECTED"
                                    ? "bg-rose-500/10 text-rose-400 border-rose-500/30"
                                    : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                                }`}
                              >
                                {app.status}
                              </span>
                              <span className="text-xs font-bold text-slate-200">
                                {app.gate_type} GATE
                              </span>
                              <span className="text-xs text-slate-500 font-mono">
                                ({app.project_name})
                              </span>
                            </div>
                            <span className="text-[11px] text-slate-500 font-mono">
                              {app.requested_at ? new Date(app.requested_at).toLocaleString() : ""}
                            </span>
                          </div>

                          <div className="text-xs text-slate-300 bg-[#12192c] p-2.5 rounded border border-slate-800/80">
                            <span className="text-slate-400 font-semibold">Prompt: </span>
                            {app.prompt_text}
                          </div>

                          {app.reviewer_comments && (
                            <div className="text-xs text-amber-300/90 bg-amber-500/5 p-2.5 rounded border border-amber-500/20">
                              <span className="font-semibold text-amber-400">Reviewer Revision Feedback: </span>
                              <div className="whitespace-pre-wrap font-sans mt-1 text-[11.5px] leading-relaxed">
                                {app.reviewer_comments}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-slate-800 bg-[#0d1322] text-xs text-slate-400">
          <div className="flex items-center gap-2 font-mono text-[11px]">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>Live SQLite Database Connection Active (WAL Mode)</span>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition"
          >
            Close Portal
          </button>
        </div>

      </div>
    </div>
  );
}
