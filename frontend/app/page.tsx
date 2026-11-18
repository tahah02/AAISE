"use client";



import React, { useState, useEffect, useRef } from "react";

import {

  Boxes,

  FolderGit2,

  Users,

  Play,

  FileCode2,

  GitBranch,

  Settings as SettingsIcon,

  Search,

  Bell,

  Plus,

  CheckCircle2,

  Code2,

  ShieldCheck,

  FlaskConical,

  Paperclip,

  AtSign,

  Send,

  Check,

  Wrench,

  ChevronDown,

  RotateCcw,

  AlertTriangle,

  Loader2,

  Sparkles,

  Bot,

  X,

  FileText,
  Download,
  Square,
  ExternalLink,
  XCircle,
  Terminal,
  AlertCircle,
  Copy,
  Zap,
  Clock,
  Activity,
} from "lucide-react";

import {

  fetchProjects,

  fetchProjectArtifacts,

  fetchProjectBranches,

  fetchProjectDiff,

  fetchProjectFileContent,

  fetchProjectMessages,

  getProjectDownloadUrl,

  createProject,

  fetchProjectAgents,

  updateProjectAgents,

  startWorkflow,

  resolveApproval,

  subscribeToWorkflowStream,
  cancelWorkflow,
  runProject,
  stopProject,
  fetchProjectStatus,
  ProjectItem,
  ArtifactItem,
  fetchAnalyticsOverview,
  fetchAnalyticsQAReports,
  AnalyticsOverview,
  AnalyticsQARunItem,
} from "@/lib/api";

import { AgentConfigModal } from "@/components/AgentConfigModal";
import { AnalyticsDashboardModal } from "@/components/AnalyticsDashboardModal";



interface ChatMessage {

  id: string;

  sender: "user" | "assistant" | "agent1" | "agent2" | "agent3" | "agent4" | "agent5";

  senderName: string;

  timestamp: string;

  text?: string;

  checklist?: string[];

  specsReady?: boolean;

  approvalRequired?: boolean;

  isApprovalCard?: boolean;

  approvalId?: string;

  gateType?: string;

  isApproved?: boolean;

  status?: string;

  workingTasks?: string[];
  buildInfo?: {
    buildSuccess: boolean;
    wasRepaired?: boolean;
    attempts?: number;
    framework?: string;
    errorSummary?: string | null;
  };
  qaReport?: {
    status: string;
    passedCount: number;
    failedCount: number;
    totalCount: number;
    liveExecuted?: boolean;
    testResults: Array<{
      testKey: string;
      name: string;
      category?: string;
      httpMethod: string;
      endpoint: string;
      expectedStatus: number;
      actualStatus: number;
      latency: string;
      status: string;
      details: string;
      curlCommand?: string;
      requestPayload?: any;
      responseBody?: string;
    }>;
  };
  telemetry?: {
    totalTokens: number;
    promptTokens?: number;
    completionTokens?: number;
    latencyMs?: number;
    latencySec: number;
    estimatedCostUsd?: number;
    costLabel: string;
    provider?: string;
    model: string;
    isFreeTier?: boolean;
    displayBadge?: string;
  };
}



export default function WorkspacePage() {

  const [projects, setProjects] = useState<ProjectItem[]>([]);

  const [selectedProject, setSelectedProject] = useState<ProjectItem | null>(null);

  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);

  const [codeDiff, setCodeDiff] = useState<string>("");

  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const [activeTab, setActiveTab] = useState<"artifacts" | "diff" | "tests" | "security" | "telemetry">("artifacts");
  const [showAnalyticsModal, setShowAnalyticsModal] = useState(false);
  const [liveQaRuns, setLiveQaRuns] = useState<AnalyticsQARunItem[]>([]);
  const [quickTelemetry, setQuickTelemetry] = useState<AnalyticsOverview | null>(null);

  const [viewingFile, setViewingFile] = useState<{ path: string; content: string } | null>(null);

  const [isLoadingFile, setIsLoadingFile] = useState(false);



  const handleOpenArtifact = async (filePath: string) => {

    if (!selectedProject?.id) return;

    setIsLoadingFile(true);

    try {

      const c = await fetchProjectFileContent(selectedProject.id, filePath);

      setViewingFile({ path: filePath, content: c || "File is empty." });

    } catch {

      setViewingFile({ path: filePath, content: "Could not load file content." });

    } finally {

      setIsLoadingFile(false);

    }

  };

  const [inputMessage, setInputMessage] = useState("");

  const [specApproved, setSpecApproved] = useState<boolean | null>(null);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isWorkflowRunning, setIsWorkflowRunning] = useState(false);

  const [currentRunId, setCurrentRunId] = useState<string | null>(null);

  const [activeApprovalId, setActiveApprovalId] = useState<string | null>(null);

  const [streamStatus, setStreamStatus] = useState<string>("idle");

  const [feedbackInput, setFeedbackInput] = useState("");

  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

  const [showConfigModal, setShowConfigModal] = useState(false);

  const [selectedAgent, setSelectedAgent] = useState<{ id: string; name: string; color: string }>({

    id: "auto",

    name: "Auto (All Agents)",

    color: "text-cyan-400",

  });

  const [showAgentMenu, setShowAgentMenu] = useState(false);

  const [showProjectMenu, setShowProjectMenu] = useState(false);

  const [showBranchMenu, setShowBranchMenu] = useState(false);

  const [availableBranches, setAvailableBranches] = useState<string[]>([]);

  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);

  const [activeNavView, setActiveNavView] = useState<"projects" | "agents" | "runs" | "artifacts" | "git" | "analytics">("projects");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const chatInputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);



  // Dynamic project agents toggle states (All 5 agents independently toggleable)
  const [agentToggles, setAgentToggles] = useState({
    agent1: true,
    agent2: true,
    agent3: true,
    agent4: true,
    agent5: true,
  });

  const handleToggleAgent = async (agentKey: "agent1" | "agent2" | "agent3" | "agent4" | "agent5") => {
    const updated = { ...agentToggles, [agentKey]: !agentToggles[agentKey] };
    setAgentToggles(updated);
    if (selectedProject?.id) {
      await updateProjectAgents(selectedProject.id, updated);
    }
  };

  const handleSaveModalToggles = async (newToggles: { agent1: boolean; agent2: boolean; agent3: boolean; agent4: boolean; agent5: boolean }) => {
    setAgentToggles(newToggles);
    if (selectedProject?.id) {
      await updateProjectAgents(selectedProject.id, newToggles);
    }
  };

  // Live Project Runner State
  const [isRunning, setIsRunning] = useState(false);
  const [isStartingRun, setIsStartingRun] = useState(false);
  const [runningUrl, setRunningUrl] = useState<string | null>(null);
  const [runningPort, setRunningPort] = useState<number | null>(null);

  const pollStatus = async (projectId: string) => {
    try {
      const res = await fetchProjectStatus(projectId, "channel-app");
      if (res.status === "RUNNING" || res.status === "ALREADY_RUNNING") {
        setIsRunning(true);
        setRunningUrl(res.url || (res.port ? `http://localhost:${res.port}` : null));
        setRunningPort(res.port || null);
      } else {
        setIsRunning(false);
        setRunningUrl(null);
        setRunningPort(null);
      }
    } catch {
      setIsRunning(false);
    }
  };

  useEffect(() => {
    if (!selectedProject?.id) return;
    pollStatus(selectedProject.id);
    const interval = setInterval(() => {
      pollStatus(selectedProject.id);
    }, 4000);
    return () => clearInterval(interval);
  }, [selectedProject?.id]);

  useEffect(() => {
    fetchAnalyticsOverview(selectedProject?.id).then((ov) => {
      if (ov) setQuickTelemetry(ov);
    });
    fetchAnalyticsQAReports(selectedProject?.id).then((qa) => {
      if (qa?.test_runs) setLiveQaRuns(qa.test_runs);
    });
  }, [selectedProject?.id, activeTab]);

  const handleRunProject = async () => {
    if (!selectedProject?.id || isStartingRun) return;
    setIsStartingRun(true);
    try {
      const res = await runProject(selectedProject.id, "channel-app");
      if (res.status === "RUNNING" || res.status === "ALREADY_RUNNING") {
        setIsRunning(true);
        const info = res.info;
        const port = info?.port || res.port;
        const url = info?.url || res.url;
        setRunningPort(port || null);
        setRunningUrl(url || (port ? `http://localhost:${port}` : null));
      }
    } catch (e: any) {
      alert(`Could not start project: ${e.message || e}`);
    } finally {
      setIsStartingRun(false);
    }
  };

  const handleStopProject = async () => {
    if (!selectedProject?.id) return;
    try {
      await stopProject(selectedProject.id);
      setIsRunning(false);
      setRunningUrl(null);
      setRunningPort(null);
    } catch (e: any) {
      alert(`Could not stop project: ${e.message || e}`);
    }
  };



  // Keep selectedAgent active only if enabled; otherwise compute safe active agent

  const isAgentDisabled =

    (selectedAgent.id === "agent2" && !agentToggles.agent2) ||

    (selectedAgent.id === "agent4" && !agentToggles.agent4) ||

    (selectedAgent.id === "agent5" && !agentToggles.agent5);



  const currentActiveAgent = isAgentDisabled

    ? { id: "auto", name: "Auto (All Agents)", color: "text-cyan-400" }

    : selectedAgent;



  // Load existing projects from DB on mount and restore last selected project
  useEffect(() => {
    fetchProjects().then((data) => {
      setProjects(data);
      if (data.length > 0) {
        const savedId = typeof window !== "undefined" ? localStorage.getItem("aaise_selected_project_id") : null;
        const matched = savedId ? data.find((p) => p.id === savedId) : null;
        setSelectedProject(matched || data[0]);
      }
    });
  }, []);

  // Persist selected project to localStorage
  useEffect(() => {
    if (selectedProject?.id && typeof window !== "undefined") {
      localStorage.setItem("aaise_selected_project_id", selectedProject.id);
    }
  }, [selectedProject?.id]);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages.length, selectedProject?.id]);



  // Fetch real artifacts, diff & persistent chat messages whenever selected project changes
  useEffect(() => {
    if (!selectedProject?.id) return;

    let isMounted = true;

    // Reset local project state immediately to prevent stale project leakage
    setMessages([]);
    setArtifacts([]);
    setCodeDiff("");
    setCurrentRunId(null);
    setActiveApprovalId(null);
    setStreamStatus("ready");

    fetchProjectArtifacts(selectedProject.id).then((arts) => {
      if (isMounted) setArtifacts(arts);
    });

    fetchProjectDiff(selectedProject.id).then((diff) => {
      if (isMounted) setCodeDiff(diff);
    });

    fetchProjectBranches(selectedProject.id).then((bData) => {
      if (isMounted) {
        if (bData && bData.branches && bData.branches.length > 0) {
          setAvailableBranches(bData.branches);
          if (bData.current_branch) {
            setSelectedProject((prev) => prev ? { ...prev, current_branch: bData.current_branch || undefined } : prev);
          }
        } else {
          setAvailableBranches([]);
          setSelectedProject((prev) => prev ? { ...prev, current_branch: undefined } : prev);
        }
      }
    });

    fetchProjectAgents(selectedProject.id).then((res) => {
      if (isMounted && res && res.toggles) {
        setAgentToggles(res.toggles);
      }
    });

    fetchProjectMessages(selectedProject.id).then((data) => {
      if (isMounted) {
        if (data && data.messages && data.messages.length > 0) {
          setMessages(data.messages);
        } else {
          setMessages([]);
        }
        if (data && data.run_id) {
          setCurrentRunId(data.run_id);
        } else {
          setCurrentRunId(null);
        }
        if (data && data.run_status === "RUNNING") {
          setIsWorkflowRunning(true);
          setStreamStatus("running");
        } else {
          setIsWorkflowRunning(false);
        }
      }
    });

    return () => {
      isMounted = false;
    };
  }, [selectedProject?.id]);

  // Auto-sync real-time status, messages & artifacts from backend
  useEffect(() => {
    if (!selectedProject?.id) return;

    const interval = setInterval(() => {
      fetchProjectMessages(selectedProject.id).then((data) => {
        if (data) {
          if (data.run_id) {
            setCurrentRunId(data.run_id);
          }
          if (data.run_status === "RUNNING") {
            setIsWorkflowRunning(true);
            setStreamStatus((prev) => (prev === "idle" || prev === "ready" ? "running" : prev));
          } else if (data.run_status === "COMPLETED" || data.run_status === "FAILED" || data.run_status === "CANCELLED") {
            setIsWorkflowRunning(false);
            setStreamStatus((prev) => (prev === "running" || prev === "streaming" ? "ready" : prev));
          }

          if (data.messages && data.messages.length > 0) {
            setMessages((prev) => {
              if (prev.length > data.messages.length) {
                const last = prev[prev.length - 1];
                if (last.sender === "user" || isSubmitting) {
                  return prev;
                }
              }
              if (JSON.stringify(data.messages) !== JSON.stringify(prev)) {
                return data.messages;
              }
              return prev;
            });
          } else if (!isSubmitting) {
            setMessages((prev) => (prev.length > 0 && prev.every(m => m.sender !== "user") ? [] : prev));
          }
        }
      });
      fetchProjectArtifacts(selectedProject.id).then((arts) => setArtifacts(arts));
      fetchProjectDiff(selectedProject.id).then((d) => setCodeDiff(d));
    }, 2500);

    return () => clearInterval(interval);

  }, [selectedProject?.id, isSubmitting]);



  // SSE Stream Listener

  useEffect(() => {

    if (!currentRunId) return;



    const es = subscribeToWorkflowStream(

      currentRunId,

      (eventData) => {

        if (eventData.event === "approval_requested") {

          setActiveApprovalId(eventData.approval_id as string);

          setMessages((prev) => {
            const hasApproval = prev.some(
              (m) => m.approvalRequired || m.isApprovalCard || (eventData.approval_id && m.approvalId === eventData.approval_id)
            );
            if (hasApproval) {
              return prev.map((m) =>
                m.approvalRequired || m.isApprovalCard
                  ? { ...m, approvalId: (eventData.approval_id as string) || m.approvalId, status: "PENDING", isApproved: false }
                  : m
              );
            }
            return [
              ...prev,
              {
                id: `approval-${eventData.approval_id || Date.now()}`,
                sender: "agent1",
                senderName: "Agent 1: Documentation Reviewer",
                timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                approvalRequired: true,
                isApprovalCard: true,
                approvalId: eventData.approval_id as string,
                status: "PENDING",
                isApproved: false,
              },
            ];
          });

          // Refresh real artifacts

          if (selectedProject?.id) {

            fetchProjectArtifacts(selectedProject.id).then((arts) => setArtifacts(arts));

          }

        } else if (eventData.event === "stream_end") {

          setStreamStatus("ready");

          es.close();

          if (selectedProject?.id) {

            fetchProjectArtifacts(selectedProject.id).then((arts) => setArtifacts(arts));

          }

        } else {

          setStreamStatus("streaming");

        }

      },

      (err) => {

        console.warn("SSE stream info:", err);

      }

    );



    return () => {

      es.close();

    };

  }, [currentRunId, selectedProject]);



  // Handle User Message / Workflow Trigger

  const handleSendMessage = async (e?: React.FormEvent) => {

    if (e) e.preventDefault();

    if ((!inputMessage.trim() && attachedFiles.length === 0) || isSubmitting) return;



    const userText = inputMessage.trim();

    const filesToSend = [...attachedFiles];

    setInputMessage("");
    if (chatInputRef.current) {
      chatInputRef.current.style.height = "auto";
    }

    setAttachedFiles([]);

    setIsSubmitting(true);



    const userMsg: ChatMessage = {

      id: `user-${Date.now()}`,

      sender: "user",

      senderName: "You",

      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),

      text: userText || (filesToSend.length > 0 ? `Uploaded document: ${filesToSend.map(f => f.name).join(", ")}` : ""),

    };

    setMessages((prev) => [...prev, userMsg]);



    try {

      const resp = await startWorkflow(

        {

          project_id: selectedProject?.id,

          project_name: selectedProject ? undefined : (filesToSend[0]?.name.replace(/\.[^/.]+$/, "") || userText.slice(0, 24)),

          user_requirement: userText || "Please implement the attached software requirements document.",

        },

        filesToSend

      );



      // If response is a greeting / conversational reply / Q&A answer:
      if (resp.is_greeting && resp.assistant_reply) {
        setIsSubmitting(false);
        const activeProjId = selectedProject?.id || (resp.project_id ? String(resp.project_id) : null);
        if (activeProjId) {
          try {
            const data = await fetchProjectMessages(activeProjId);
            if (data && data.messages && data.messages.length > 0) {
              setMessages(data.messages);
              return;
            }
          } catch {
            // fallback to local append
          }
        }
        setMessages((prev) => [
          ...prev,
          {
            id: `assistant-${Date.now()}`,
            sender: "assistant",
            senderName: "AAISE Assistant",
            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            text: resp.assistant_reply,
          },
        ]);
        return;
      }



      // If genuine requirement was submitted:

      if (resp.workflow_run_id) {

        setCurrentRunId(resp.workflow_run_id);

      }



      // Refresh project list if a new one was auto-created

      const updatedProjects = await fetchProjects();

      setProjects(updatedProjects);

      if (!selectedProject && updatedProjects.length > 0) {

        setSelectedProject(updatedProjects[0]);

      }



      if (currentActiveAgent.id === "agent4" || userText.toLowerCase().includes("agent4") || userText.toLowerCase().includes("qa")) {

        setMessages((prev) => [

          ...prev,

          {

            id: `agent4-${Date.now()}`,

            sender: "agent4",

            senderName: "Agent 4: Independent QA",

            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),

            text: "Running Agent 4 (Independent Black-Box QA) and Agent 5 (Security SAST Audit) against the application...",

          },

        ]);

      } else if (currentActiveAgent.id === "agent5" || userText.toLowerCase().includes("agent5") || userText.toLowerCase().includes("security")) {

        setMessages((prev) => [

          ...prev,

          {

            id: `agent5-${Date.now()}`,

            sender: "agent5",

            senderName: "Agent 5: Security Reviewer",

            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),

            text: "Running Agent 5 (Security SAST Audit) against the application...",

          },

        ]);

      } else {

        setMessages((prev) => [

          ...prev,

          {

            id: `agent1-${Date.now()}`,

            sender: "agent1",

            senderName: "Agent 1 (Requirements & Design)",

            timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),

            text: "Analyzing software requirements and architecture boundaries. Generating Technical Design Document (TDD) and Test Specifications...",

          },

        ]);

      }

    } catch (err) {

      console.error("Workflow error:", err);

    } finally {

      setIsSubmitting(false);

    }

  };

  // Handle Workflow Cancellation (Stop Button)
  const handleCancelWorkflow = async () => {
    try {
      if (currentRunId) {
        await cancelWorkflow({ runId: currentRunId });
      } else if (selectedProject?.id) {
        await cancelWorkflow({ projectId: selectedProject.id });
      }
      setIsSubmitting(false);
      setIsWorkflowRunning(false);
      setStreamStatus("idle");
      if (selectedProject?.id) {
        const data = await fetchProjectMessages(selectedProject.id);
        if (data && data.messages) {
          setMessages(data.messages);
        }
      }
    } catch (err: any) {
      console.error("Failed to cancel workflow:", err);
      setIsSubmitting(false);
      setIsWorkflowRunning(false);
    }
  };

  // Handle Human Approval Gate (Approve)

  const handleApprove = async (overrideApprovalId?: string) => {

    setSpecApproved(true);
    setIsSubmitting(true);
    setIsWorkflowRunning(true);
    setStreamStatus("running");

    const targetApprovalId = overrideApprovalId || activeApprovalId;

    if (targetApprovalId) {

      try {

        await resolveApproval({

          approval_id: targetApprovalId,

          approved: true,

        });

      } catch (err: any) {
        console.warn("Approve failed:", err?.message || err);
      }

    }



    setMessages((prev) => [
      ...prev.map((msg) =>
        (msg.approvalRequired || msg.isApprovalCard) && (!targetApprovalId || msg.approvalId === targetApprovalId)
          ? { ...msg, status: "APPROVED", isApproved: true }
          : msg
      ),
      {
        id: `sys-approve-${Date.now()}`,
        sender: "assistant",
        senderName: "AAISE Orchestrator",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        text: "Approval granted. Resuming workflow execution...",
      },
    ]);

  };



  // Handle Human Approval Gate (Request Changes)

  const handleRequestChanges = async () => {

    setSpecApproved(false);
    setIsSubmitting(true);
    setIsWorkflowRunning(true);
    setStreamStatus("running");

    const feedback = feedbackInput.trim() || "Please revise specifications according to requested changes.";

    const targetApprovalId = activeApprovalId;

    // Immediately show revision message in chat
    setMessages((prev) => [
      ...prev.map((m) => (m.approvalRequired || m.isApprovalCard) && (!targetApprovalId || m.approvalId === targetApprovalId)
        ? { ...m, status: "REJECTED", isApproved: false }
        : m
      ),
      {
        id: `user-rev-${Date.now()}`,
        sender: "user",
        senderName: "You",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        text: `Requested Changes to Specifications:\n${feedback}`,
      },
      {
        id: `agent1-rev-${Date.now() + 1}`,
        sender: "agent1",
        senderName: "Agent 1: Documentation Reviewer",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        text: "Analyzing requested changes. Revising Technical Design Document (TDD) and Test Specifications...",
      },
    ]);

    setShowFeedbackModal(false);

    setFeedbackInput("");

    if (targetApprovalId) {

      try {

        await resolveApproval({

          approval_id: targetApprovalId,

          approved: false,

          comments: feedback,

        });

      } catch (err: any) {
        console.warn("Request changes failed:", err?.message || err);
      }

    }

  };



  return (

    <div className="flex h-screen w-screen bg-[#07090e] text-slate-200 overflow-hidden text-[13px]">

      {/* 1. LEFT-MOST ICON NAVIGATION BAR */}

      <aside className="w-14 shrink-0 flex flex-col items-center py-3 border-r border-slate-800/80 bg-[#0a0d14] justify-between z-20">

        <div className="flex flex-col items-center gap-5 w-full">

          <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-cyan-600 to-blue-500 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20 cursor-pointer">

            <Boxes className="h-5 w-5" />

          </div>



          <nav className="flex flex-col items-center gap-2 w-full px-2">

            {/* 1. Home / Projects View */}

            <button

              onClick={() => setActiveNavView("projects")}

              title="Workspace & Projects"

              className={`h-10 w-10 rounded-lg flex items-center justify-center transition ${

                activeNavView === "projects"

                  ? "bg-blue-600/20 text-cyan-400 border border-cyan-500/30"

                  : "text-slate-400 hover:text-white hover:bg-slate-800/60"

              }`}

            >

              <FolderGit2 className="h-4 w-4" />

            </button>



            {/* 2. Agents / Topology Team View */}

            <button

              onClick={() => {

                setActiveNavView("agents");

                setShowConfigModal(true);

              }}

              title="Multi-Agent Topology"

              className={`h-10 w-10 rounded-lg flex items-center justify-center transition ${

                activeNavView === "agents"

                  ? "bg-blue-600/20 text-cyan-400 border border-cyan-500/30"

                  : "text-slate-400 hover:text-white hover:bg-slate-800/60"

              }`}

            >

              <Users className="h-4 w-4" />

            </button>



            {/* 3. Workflows / Runs */}

            <button

              onClick={() => {

                setActiveNavView("runs");

                if (currentRunId) {

                  alert(`Active Workflow Run: ${currentRunId}\nStatus: ${streamStatus}`);

                } else {

                  alert("No active workflow run. Type your software requirements in the chat to start one.");

                }

              }}

              title="Workflow Executions"

              className={`h-10 w-10 rounded-lg flex items-center justify-center transition ${

                activeNavView === "runs"

                  ? "bg-blue-600/20 text-cyan-400 border border-cyan-500/30"

                  : "text-slate-400 hover:text-white hover:bg-slate-800/60"

              }`}

            >

              <Play className="h-4 w-4" />

            </button>



            {/* 4. Artifacts / Documents */}

            <button

              onClick={() => {

                setActiveNavView("artifacts");

                setActiveTab("artifacts");

              }}

              title="Project Artifacts & Technical Specs"

              className={`h-10 w-10 rounded-lg flex items-center justify-center transition ${

                activeNavView === "artifacts" || activeTab === "artifacts"

                  ? "bg-blue-600/20 text-cyan-400 border border-cyan-500/30"

                  : "text-slate-400 hover:text-white hover:bg-slate-800/60"

              }`}

            >

              <FileCode2 className="h-4 w-4" />

            </button>



            {/* 5. Git Branches / Commits */}

            <button

              onClick={() => {

                setActiveNavView("git");

                setActiveTab("diff");

              }}

              title="Git Branches & Code Diff"

              className={`h-10 w-10 rounded-lg flex items-center justify-center transition ${

                activeNavView === "git" || activeTab === "diff"

                  ? "bg-blue-600/20 text-cyan-400 border border-cyan-500/30"

                  : "text-slate-400 hover:text-white hover:bg-slate-800/60"

              }`}

            >

              <GitBranch className="h-4 w-4" />

            </button>

            {/* 6. Observability & Telemetry Portal */}
            <button
              onClick={() => {
                setActiveNavView("analytics");
                setShowAnalyticsModal(true);
              }}
              title="Observability & Telemetry Portal (SQLite Live)"
              className={`h-10 w-10 rounded-lg flex items-center justify-center transition ${
                showAnalyticsModal
                  ? "bg-amber-600/20 text-amber-400 border border-amber-500/30"
                  : "text-slate-400 hover:text-white hover:bg-slate-800/60"
              }`}
            >
              <Activity className="h-4 w-4 text-amber-400" />
            </button>

          </nav>

        </div>



        <div className="flex flex-col items-center gap-3">

          <button

            onClick={() => setShowConfigModal(true)}

            className="h-10 w-10 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-slate-800/60 transition"

          >

            <SettingsIcon className="h-4 w-4" />

          </button>

          <div className="h-7 w-7 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center text-xs font-semibold text-slate-300">

            TH

          </div>

        </div>

      </aside>



      {/* MAIN CONTAINER */}

      <div className="flex-1 flex flex-col min-w-0 h-full">

        {/* TOP HEADER BAR */}

        <header className="h-14 shrink-0 border-b border-slate-800/80 bg-[#0a0d14] flex items-center justify-between px-4">

          <div className="flex items-center gap-4">

            <div>

              <div className="flex items-center gap-2">

                <span className="font-semibold text-slate-100 text-[14px] tracking-tight">AAISE Platform</span>

                <span className="text-[11px] text-slate-500 font-normal hidden sm:inline">Autonomous AI Software Engineer</span>

              </div>

            </div>



            <div className="h-4 w-[1px] bg-slate-800 mx-1" />



            {/* Project Selector Badge & Dropdown */}

            <div className="relative">

              <button

                type="button"

                onClick={() => {

                  setShowProjectMenu((p) => !p);

                  setShowBranchMenu(false);

                }}

                className="flex items-center gap-2 px-2.5 py-1 rounded-md bg-[#131926] border border-slate-700/80 hover:border-slate-600 text-slate-200 transition text-[12px]"

              >

                <FolderGit2 className="h-3.5 w-3.5 text-cyan-400" />

                <span>Project / <span className="font-medium text-white">{selectedProject ? selectedProject.name : "No Project Selected"}</span></span>

                <ChevronDown className="h-3 w-3 text-slate-400 ml-0.5" />

              </button>



              {showProjectMenu && (

                <div className="absolute top-full left-0 mt-1.5 w-60 bg-[#0e121d] border border-slate-700 rounded-xl shadow-2xl p-1.5 z-50 animate-in fade-in duration-150">

                  <div className="px-2 py-1 text-[10px] uppercase font-semibold text-slate-500 border-b border-slate-800 mb-1">

                    Select Project

                  </div>

                  {projects.length === 0 ? (

                    <div className="p-2 text-center text-slate-500 text-[11px]">No projects yet</div>

                  ) : (

                    projects.map((p) => (

                      <button

                        key={p.id}

                        type="button"

                        onClick={() => {

                          setSelectedProject(p);

                          setShowProjectMenu(false);

                          setMessages([]);

                        }}

                        className={`w-full flex items-center justify-between p-2 rounded-lg text-left text-[12px] transition ${

                          selectedProject?.id === p.id

                            ? "bg-blue-600/20 text-cyan-400 border border-cyan-500/30"

                            : "hover:bg-slate-800/60 text-slate-300"

                        }`}

                      >

                        <span className="font-medium truncate">{p.name}</span>

                        {selectedProject?.id === p.id && <Check className="h-3 w-3 text-cyan-400" />}

                      </button>

                    ))

                  )}

                  <button

                    type="button"

                    onClick={async () => {

                      const name = prompt("Enter project name:", "New Project");
                      if (name) {
                        try {
                        const p = await createProject(name, undefined, undefined, undefined, agentToggles);
                        setProjects((prev) => [p, ...prev]);
                        setSelectedProject(p);
                        setMessages([]);
                        setArtifacts([]);
                        setCodeDiff("");
                        setCurrentRunId(null);
                        setActiveApprovalId(null);
                        setShowProjectMenu(false);
                        setMessages([]);
                        setArtifacts([]);
                        setCodeDiff("");
                        setCurrentRunId(null);
                        setActiveApprovalId(null);
                        } catch (err: any) {
                          console.error("Create project failed:", err);
                          alert("Could not connect to backend API: " + (err?.message || "Server unreachable. Please check backend."));
                        }
                      }

                    }}

                    className="w-full mt-1 flex items-center gap-1.5 p-1.5 rounded-lg text-[11.5px] text-cyan-400 hover:bg-cyan-950/40 border border-dashed border-cyan-500/30"

                  >

                    <Plus className="h-3.5 w-3.5" />

                    <span>Create New Project</span>

                  </button>

                </div>

              )}

            </div>





          </div>



          {/* Dynamic Agent Toggles in Header */}

          <div className="flex items-center gap-3">

            <div className="flex items-center gap-1.5 flex-wrap">

              <button
                onClick={() => handleToggleAgent("agent1")}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border transition ${
                  agentToggles.agent1
                    ? "bg-emerald-950/60 border-emerald-500/40 text-emerald-300"
                    : "bg-slate-900 border-slate-700 text-slate-500 line-through"
                }`}
                title="Agent 1: Documentation Reviewer"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${agentToggles.agent1 ? "bg-emerald-400" : "bg-slate-600"}`} />
                Agent 1 {agentToggles.agent1 ? "ON" : "OFF"}
              </button>

              <button
                onClick={() => handleToggleAgent("agent2")}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border transition ${
                  agentToggles.agent2
                    ? "bg-cyan-950/60 border-cyan-500/40 text-cyan-300"
                    : "bg-slate-900 border-slate-700 text-slate-500 line-through"
                }`}
                title="Agent 2: Mock Vendor API Developer"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${agentToggles.agent2 ? "bg-cyan-400" : "bg-slate-600"}`} />
                Agent 2 {agentToggles.agent2 ? "ON" : "OFF"}
              </button>

              <button
                onClick={() => handleToggleAgent("agent3")}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border transition ${
                  agentToggles.agent3
                    ? "bg-blue-950/60 border-blue-500/40 text-blue-300"
                    : "bg-slate-900 border-slate-700 text-slate-500 line-through"
                }`}
                title="Agent 3: Main Coding Agent"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${agentToggles.agent3 ? "bg-blue-400" : "bg-slate-600"}`} />
                Agent 3 {agentToggles.agent3 ? "ON" : "OFF"}
              </button>

              <button
                onClick={() => handleToggleAgent("agent4")}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border transition ${
                  agentToggles.agent4
                    ? "bg-purple-950/60 border-purple-500/40 text-purple-300"
                    : "bg-slate-900 border-slate-700 text-slate-500 line-through"
                }`}
                title="Agent 4: Independent QA Engineer"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${agentToggles.agent4 ? "bg-purple-400" : "bg-slate-600"}`} />
                Agent 4 {agentToggles.agent4 ? "ON" : "OFF"}
              </button>

              <button
                onClick={() => handleToggleAgent("agent5")}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border transition ${
                  agentToggles.agent5
                    ? "bg-amber-950/60 border-amber-500/40 text-amber-300"
                    : "bg-slate-900 border-slate-700 text-slate-500 line-through"
                }`}
                title="Agent 5: Security Reviewer"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${agentToggles.agent5 ? "bg-amber-400" : "bg-slate-600"}`} />
                Agent 5 {agentToggles.agent5 ? "ON" : "OFF"}
              </button>



              <button
                onClick={() => setShowConfigModal(true)}
                className="flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-[#141b2a] border border-cyan-500/30 text-cyan-300 hover:bg-cyan-950/50 text-[11px] font-medium transition"
              >
                <SettingsIcon className="h-3 w-3" />
                Configure
              </button>

              <button
                onClick={() => setShowAnalyticsModal(true)}
                className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-lg bg-[#141b2a] border border-amber-500/40 text-amber-300 hover:bg-amber-950/40 text-[11px] font-medium transition shadow-sm"
                title="AAISE Observability & Telemetry Portal (Live SQLite)"
              >
                <Activity className="h-3 w-3 text-amber-400" />
                <span>Telemetry & QA</span>
                {quickTelemetry && (
                  <span className="font-mono text-[10px] text-slate-300 bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/20">
                    {quickTelemetry.tokens.total.toLocaleString()} toks
                  </span>
                )}
              </button>

              {/* Live Project Runner Controls */}
              {selectedProject && (
                <div className="flex items-center gap-1.5 ml-1">
                  {isRunning ? (
                    <div className="flex items-center gap-1.5 bg-emerald-950/70 border border-emerald-500/40 px-2 py-0.5 rounded-lg shadow-sm shadow-emerald-950">
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                      </span>
                      <span className="text-[11px] font-medium text-emerald-300">
                        :{runningPort || "Active"}
                      </span>
                      {runningUrl && (
                        <a
                          href={runningUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-emerald-400 hover:text-emerald-200 transition p-0.5 hover:bg-emerald-900/40 rounded"
                          title={`Open Live Preview: ${runningUrl}`}
                        >
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      <button
                        type="button"
                        onClick={handleStopProject}
                        className="ml-0.5 text-rose-400 hover:text-rose-200 transition p-0.5 hover:bg-rose-950/60 rounded"
                        title="Stop Project Service"
                      >
                        <Square className="h-3 w-3 fill-rose-400" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={handleRunProject}
                      disabled={isStartingRun}
                      className="flex items-center gap-1 px-2.5 py-0.5 rounded-lg bg-emerald-950/70 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-900/60 hover:border-emerald-400/60 text-[11px] font-medium transition shadow-sm shadow-emerald-950 disabled:opacity-50"
                      title="Run / Start Project Service"
                    >
                      {isStartingRun ? (
                        <Loader2 className="h-3 w-3 animate-spin text-emerald-300" />
                      ) : (
                        <Play className="h-3 w-3 fill-emerald-300" />
                      )}
                      <span>{isStartingRun ? "Starting..." : "Run Project"}</span>
                    </button>
                  )}
                </div>
              )}

            </div>



            <div className="h-4 w-[1px] bg-slate-800 mx-1" />



            <div className="relative flex items-center">

              <Search className="h-3.5 w-3.5 text-slate-500 absolute left-2.5 pointer-events-none" />

              <input

                type="text"

                placeholder="Search..."

                className="bg-[#101522] border border-slate-800 rounded-lg pl-8 pr-3 py-1 text-[12px] text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/50 w-36 transition"

              />

            </div>



            <button className="relative p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition">

              <Bell className="h-4 w-4" />

              <span className="absolute top-1 right-1 h-2 w-2 rounded-full bg-rose-500 ring-2 ring-[#0a0d14]" />

            </button>



            <div className="h-7 w-7 rounded-full bg-gradient-to-tr from-cyan-600 to-indigo-600 text-white font-semibold text-[11px] flex items-center justify-center border border-cyan-400/30">

              TH

            </div>

          </div>

        </header>



        {/* 3-COLUMN WORKSPACE BODY */}

        <div className="flex-1 flex min-h-0 divide-x divide-slate-800/70">

          {/* COLUMN 1: LEFT SIDEBAR */}

          <div className="w-64 shrink-0 flex flex-col bg-[#0b0e17] overflow-y-auto">

            <div className="p-3 border-b border-slate-800/60">

              <div className="flex items-center justify-between mb-2">

                <span className="font-semibold text-slate-300 text-[12px]">Projects</span>

                <button

                  onClick={async () => {

                    const name = prompt("Enter project name:", "My AI Project");
                    if (name) {
                      try {
                        const p = await createProject(name, undefined, undefined, undefined, agentToggles);
                        setProjects((prev) => [p, ...prev]);
                        setSelectedProject(p);
                        setMessages([]);
                        setArtifacts([]);
                        setCodeDiff("");
                        setCurrentRunId(null);
                        setActiveApprovalId(null);
                      } catch (err: any) {
                        console.error("Create project failed:", err);
                        alert("Could not connect to backend API: " + (err?.message || "Server unreachable. Please check backend."));
                      }
                    }

                  }}

                  className="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-blue-600/20 text-cyan-400 border border-cyan-500/30 hover:bg-blue-600/30 transition"

                >

                  <Plus className="h-3 w-3" />

                  New Project

                </button>

              </div>



              {projects.length === 0 ? (

                <div className="p-4 text-center text-slate-500 text-[11px] border border-dashed border-slate-800 rounded-lg">

                  No projects yet.<br />Start by describing your requirements below.

                </div>

              ) : (

                <div className="space-y-1">

                  {projects.map((p) => (

                    <div

                      key={p.id}

                      onClick={() => setSelectedProject(p)}

                      className={`p-2 rounded-lg cursor-pointer transition ${

                        selectedProject?.id === p.id

                          ? "bg-blue-950/40 border border-blue-500/40"

                          : "hover:bg-slate-800/40 border border-transparent"

                      }`}

                    >

                      <div className="flex items-center gap-2">

                        <div className="h-6 w-6 rounded bg-blue-500/20 border border-blue-500/40 flex items-center justify-center text-blue-400 shrink-0">

                          <FolderGit2 className="h-3.5 w-3.5" />

                        </div>

                        <div className="min-w-0">

                          <div className="font-medium text-white text-[12px] truncate">{p.name}</div>

                          <div className="text-[10px] text-slate-400 truncate">{p.target_framework}</div>

                        </div>

                      </div>

                    </div>

                  ))}

                </div>

              )}

            </div>



            {/* AI Agents Status */}

            <div className="p-3 border-b border-slate-800/60">

              <div className="flex items-center justify-between mb-2">

                <span className="font-semibold text-slate-300 text-[12px]">AI Agents</span>

                <button

                  onClick={() => setShowConfigModal(true)}

                  className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-cyan-400 transition"

                >

                  <Wrench className="h-3 w-3" />

                  Configure

                </button>

              </div>



              <div className="space-y-1.5 text-[11.5px]">

                <div className="flex items-center justify-between p-1.5 rounded-md hover:bg-slate-800/30">

                  <div className="flex items-center gap-2">

                    <div className="h-6 w-6 rounded bg-emerald-950/80 border border-emerald-500 flex items-center justify-center text-emerald-400">

                      <FileCode2 className="h-3.5 w-3.5" />

                    </div>

                    <div>

                      <div className="font-medium text-white text-[11px]">Agent 1 <span className="text-slate-400 font-normal">Doc Reviewer</span></div>

                      <div className="text-[10px] text-emerald-400">Mandatory (Active)</div>

                    </div>

                  </div>

                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />

                </div>



                <div className="flex items-center justify-between p-1.5 rounded-md hover:bg-slate-800/30">

                  <div className="flex items-center gap-2">

                    <div className="h-6 w-6 rounded bg-cyan-950/80 border border-cyan-500 flex items-center justify-center text-cyan-400">

                      <Boxes className="h-3.5 w-3.5" />

                    </div>

                    <div>

                      <div className="font-medium text-white text-[11px]">Agent 2 <span className="text-slate-400 font-normal">Mock Dev</span></div>

                      <div className="text-[10px] text-cyan-400">{agentToggles.agent2 ? "Enabled" : "Disabled (Standalone)"}</div>

                    </div>

                  </div>

                  <span className={`text-[10px] ${agentToggles.agent2 ? "text-cyan-400" : "text-slate-500"}`}>{agentToggles.agent2 ? "ON" : "OFF"}</span>

                </div>



                <div className="flex items-center justify-between p-1.5 rounded-md hover:bg-slate-800/30">

                  <div className="flex items-center gap-2">

                    <div className="h-6 w-6 rounded bg-blue-600/20 border border-blue-500 flex items-center justify-center text-blue-400">

                      <Code2 className="h-3.5 w-3.5" />

                    </div>

                    <div>

                      <div className="font-medium text-white text-[11px]">Agent 3 <span className="text-slate-400 font-normal">Main Coder</span></div>

                      <div className="text-[10px] text-blue-400">Mandatory (Active)</div>

                    </div>

                  </div>

                  <CheckCircle2 className="h-3.5 w-3.5 text-blue-400" />

                </div>



                <div className="flex items-center justify-between p-1.5 rounded-md hover:bg-slate-800/30">

                  <div className="flex items-center gap-2">

                    <div className="h-6 w-6 rounded bg-purple-950/60 border border-purple-600/40 flex items-center justify-center text-purple-400">

                      <FlaskConical className="h-3.5 w-3.5" />

                    </div>

                    <div>

                      <div className="font-medium text-slate-300 text-[11px]">Agent 4 <span className="text-slate-400 font-normal">QA Testing</span></div>

                      <div className="text-[10px] text-purple-400">{agentToggles.agent4 ? "Enabled" : "Skipped"}</div>

                    </div>

                  </div>

                  <span className={`text-[10px] ${agentToggles.agent4 ? "text-purple-400" : "text-slate-500"}`}>{agentToggles.agent4 ? "ON" : "OFF"}</span>

                </div>



                <div className="flex items-center justify-between p-1.5 rounded-md hover:bg-slate-800/30">

                  <div className="flex items-center gap-2">

                    <div className="h-6 w-6 rounded bg-amber-950/60 border border-amber-600/40 flex items-center justify-center text-amber-400">

                      <ShieldCheck className="h-3.5 w-3.5" />

                    </div>

                    <div>

                      <div className="font-medium text-slate-300 text-[11px]">Agent 5 <span className="text-slate-400 font-normal">Security SAST</span></div>

                      <div className="text-[10px] text-amber-400">{agentToggles.agent5 ? "Enabled" : "Not Scanned"}</div>

                    </div>

                  </div>

                  <span className={`text-[10px] ${agentToggles.agent5 ? "text-amber-400" : "text-slate-500"}`}>{agentToggles.agent5 ? "ON" : "OFF"}</span>

                </div>

              </div>

            </div>

          </div>



          {/* COLUMN 2: CENTER CHAT */}

          <div className="flex-1 flex flex-col min-w-0 bg-[#090b12]">

            <div className="h-10 shrink-0 border-b border-slate-800/60 px-4 flex items-center justify-between">

              <div className="flex items-center gap-2">

                <span className="font-semibold text-slate-200 text-[13px]">Chat & Agent Activity</span>

                <span className="text-[11px] text-slate-500 hidden md:inline">Ask, plan, approve and build with autonomous AI agents</span>

                {streamStatus !== "idle" && (

                  <span className="ml-2 flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] bg-cyan-950/70 border border-cyan-500/30 text-cyan-400">

                    <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />

                    {streamStatus}

                  </span>

                )}

                {(isSubmitting || isWorkflowRunning || streamStatus === "streaming" || streamStatus === "running") && (
                  <button
                    onClick={handleCancelWorkflow}
                    className="ml-2 flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-[10.5px] bg-rose-500/20 border border-rose-500/50 text-rose-300 hover:bg-rose-500/30 transition font-medium cursor-pointer shadow-sm shadow-rose-950/40"
                    title="Cancel active execution"
                  >
                    <Square className="h-2.5 w-2.5 fill-rose-300" />
                    <span>Stop</span>
                  </button>
                )}

              </div>

              <button

                onClick={() => setMessages([])}

                className="text-[11px] text-slate-400 hover:text-white px-2 py-0.5 rounded hover:bg-slate-800/40"

              >

                Clear

              </button>

            </div>



            {/* Messages Scroll Area */}

            <div className="flex-1 overflow-y-auto p-4 space-y-4">

              {messages.length === 0 ? (

                <div className="h-full flex flex-col items-center justify-center text-center p-8 max-w-lg mx-auto">

                  <div className="h-12 w-12 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 mb-4 shadow-lg shadow-cyan-500/10">

                    <Sparkles className="h-6 w-6" />

                  </div>

                  <h3 className="text-white font-semibold text-[16px] mb-1.5">Fresh Workspace Ready</h3>

                  <p className="text-slate-400 text-[12.5px] leading-relaxed mb-6">

                    Say &quot;Hi&quot; to converse, or describe any software project to build from scratch.

                  </p>

                  <div className="grid grid-cols-2 gap-2.5 w-full text-left">

                    <button

                      onClick={() => setInputMessage("Build a Student Management CRUD API with FastAPI and SQLite.")}

                      className="p-3 rounded-xl bg-[#0f1422] border border-slate-800 hover:border-cyan-500/40 text-[11.5px] text-slate-300 transition"

                    >

                      💡 <span className="font-medium text-white">Student Management API</span>

                      <p className="text-[10px] text-slate-500 mt-1">FastAPI CRUD with SQLite persistence</p>

                    </button>

                    <button

                      onClick={() => setInputMessage("Build JWT Authentication service with login, logout and refresh token.")}

                      className="p-3 rounded-xl bg-[#0f1422] border border-slate-800 hover:border-cyan-500/40 text-[11.5px] text-slate-300 transition"

                    >

                      💡 <span className="font-medium text-white">JWT Auth Service</span>

                      <p className="text-[10px] text-slate-500 mt-1">Role-based access control & refresh tokens</p>

                    </button>

                  </div>

                </div>

              ) : (

                messages.map((m) => (

                  <div key={m.id} className="flex items-start gap-3">

                    {m.sender === "user" ? (

                      <div className="h-7 w-7 rounded-full bg-slate-700 border border-slate-600 flex items-center justify-center text-xs font-semibold text-white shrink-0 mt-0.5">

                        TH

                      </div>

                    ) : m.sender === "assistant" ? (

                      <div className="h-7 w-7 rounded-full bg-cyan-950 border border-cyan-500 flex items-center justify-center text-cyan-400 shrink-0 mt-0.5">

                        <Bot className="h-3.5 w-3.5" />

                      </div>

                    ) : m.sender === "agent1" ? (

                      <div className="h-7 w-7 rounded-full bg-emerald-950 border border-emerald-500 flex items-center justify-center text-emerald-400 shrink-0 mt-0.5">

                        <FileCode2 className="h-3.5 w-3.5" />

                      </div>

                    ) : m.sender === "agent4" ? (

                      <div className="h-7 w-7 rounded-full bg-purple-950 border border-purple-500 flex items-center justify-center text-purple-400 shrink-0 mt-0.5">

                        <FlaskConical className="h-3.5 w-3.5" />

                      </div>

                    ) : m.sender === "agent5" ? (

                      <div className="h-7 w-7 rounded-full bg-amber-950 border border-amber-500 flex items-center justify-center text-amber-400 shrink-0 mt-0.5">

                        <ShieldCheck className="h-3.5 w-3.5" />

                      </div>

                    ) : (

                      <div className="h-7 w-7 rounded-full bg-blue-950 border border-blue-500 flex items-center justify-center text-blue-400 shrink-0 mt-0.5">

                        <Code2 className="h-3.5 w-3.5" />

                      </div>

                    )}



                    <div className="flex-1 space-y-3 max-w-2xl">

                      {!(m.approvalRequired || m.isApprovalCard) && (
                        <div className="bg-[#121624] border border-slate-800 rounded-xl p-3.5 shadow-sm">

                        <div className="flex items-center justify-between mb-1.5">

                          <span className={`font-semibold text-[12px] ${m.sender === "user" ? "text-white" : m.sender === "assistant" ? "text-cyan-400" : m.sender === "agent1" ? "text-emerald-400" : m.sender === "agent4" ? "text-purple-400" : m.sender === "agent5" ? "text-amber-400" : "text-blue-400"}`}>

                            {m.senderName}

                          </span>

                          <span className="text-[10px] text-slate-500">{m.timestamp}</span>

                        </div>

                        {m.text && (
                          m.text.length > 1200 ? (
                            <div className="space-y-2">
                              <div className="flex items-center justify-between text-[11px] text-cyan-300 font-medium bg-cyan-950/60 px-3 py-1.5 rounded-lg border border-cyan-500/30">
                                <span className="flex items-center gap-1.5">
                                  <span>📎</span>
                                  <span>Complete Ingested Requirements &amp; Specifications ({m.text.length.toLocaleString()} characters)</span>
                                </span>
                                <span className="text-[10px] text-slate-400">Full Text Available</span>
                              </div>
                              <div className="max-h-96 overflow-y-auto pr-2 scrollbar-thin scrollbar-thumb-slate-700 bg-black/40 p-3 rounded-lg border border-slate-800 text-slate-200 text-[12px] font-mono leading-relaxed whitespace-pre-wrap break-words select-text">
                                {m.text}
                              </div>
                            </div>
                          ) : (
                            <p className="text-slate-200 leading-relaxed text-[13px] whitespace-pre-wrap break-words">{m.text}</p>
                          )
                        )}



                        {m.checklist && (
                          <div className="mt-3 space-y-1.5 text-[11.5px] text-slate-300">
                            {m.checklist.map((item, idx) => {
                              const itemLower = item.toLowerCase();
                              const isFailure = itemLower.includes("failed") || itemLower.includes("error");
                              const isWarning = itemLower.includes("warning") || itemLower.includes("repaired") || itemLower.includes("remed");
                              return (
                                <div
                                  key={idx}
                                  className={`flex items-start gap-2 ${
                                    isFailure
                                      ? "text-rose-400 font-medium"
                                      : isWarning
                                      ? "text-amber-300 font-medium"
                                      : "text-emerald-400"
                                  }`}
                                >
                                  {isFailure ? (
                                    <XCircle className="h-3.5 w-3.5 shrink-0 text-rose-500 mt-0.5" />
                                  ) : isWarning ? (
                                    <AlertCircle className="h-3.5 w-3.5 shrink-0 text-amber-400 mt-0.5" />
                                  ) : (
                                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-400 mt-0.5" />
                                  )}
                                  <span>{item}</span>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {m.buildInfo && (
                          <div className={`mt-3 rounded-xl border p-3.5 text-[12px] shadow-md transition-all ${
                            m.buildInfo.buildSuccess
                              ? m.buildInfo.wasRepaired
                                ? "bg-[#181408] border-amber-500/40 text-amber-200 shadow-amber-950/20"
                                : "bg-[#081710] border-emerald-500/40 text-emerald-200 shadow-emerald-950/20"
                              : "bg-[#1c0a0a] border-rose-500/60 text-rose-200 shadow-rose-950/30"
                          }`}>
                            <div className="flex items-center justify-between font-mono text-[11px] mb-2 border-b pb-1.5 border-slate-700/50">
                              <span className="font-semibold flex items-center gap-1.5 text-slate-300">
                                <Terminal className="h-3.5 w-3.5 text-cyan-400" />
                                Build Diagnostics &bull; {m.buildInfo.framework || "Compiler"}
                              </span>
                              <span className={`px-2 py-0.5 rounded font-bold text-[10px] tracking-wide uppercase ${
                                m.buildInfo.buildSuccess
                                  ? m.buildInfo.wasRepaired
                                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                    : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30 animate-pulse"
                              }`}>
                                {m.buildInfo.buildSuccess
                                  ? m.buildInfo.wasRepaired ? `Auto-Repaired (Attempt ${m.buildInfo.attempts || 2})` : "Build Verified (0 Errors)"
                                  : `Build Failed (Attempt ${m.buildInfo.attempts || 1})`}
                              </span>
                            </div>
                            {m.buildInfo.errorSummary ? (
                              <div className="bg-black/60 rounded-lg p-2.5 text-rose-300 font-mono text-[11px] whitespace-pre-wrap overflow-x-auto max-h-48 scrollbar-thin scrollbar-thumb-rose-900 border border-rose-900/40 select-text leading-relaxed">
                                {m.buildInfo.errorSummary}
                              </div>
                            ) : (
                              <div className="text-[11.5px] text-emerald-300/80 font-mono flex items-center gap-1.5">
                                <Check className="h-3 w-3 text-emerald-400" />
                                Compilation succeeded with exit code 0. Zero compiler errors detected.
                              </div>
                            )}
                          </div>
                        )}

                        {m.qaReport && (
                          <div className={`mt-3 rounded-xl border p-4 text-[12px] shadow-lg transition-all ${
                            m.qaReport.status === "PASSED"
                              ? "bg-[#081710] border-emerald-500/40 text-emerald-100 shadow-emerald-950/20"
                              : "bg-[#180a0a] border-rose-500/50 text-rose-100 shadow-rose-950/30"
                          }`}>
                            <div className="flex items-center justify-between mb-3 border-b pb-2 border-slate-700/50 font-mono text-[11px]">
                              <div className="flex items-center gap-2">
                                <FlaskConical className={`h-4 w-4 ${m.qaReport.status === "PASSED" ? "text-emerald-400" : "text-rose-400"}`} />
                                <span className="font-semibold text-slate-200">
                                  {m.qaReport.liveExecuted ? "Live HTTP Contract Test Report" : "Contract Specification Test Report"}
                                </span>
                              </div>
                              <div className="flex items-center gap-1.5 text-[10px]">
                                <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-bold">
                                  {m.qaReport.passedCount} Passed
                                </span>
                                {m.qaReport.failedCount > 0 && (
                                  <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-bold animate-pulse">
                                    {m.qaReport.failedCount} Failed
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Test Results Table */}
                            <div className="overflow-x-auto rounded-lg border border-slate-800 bg-black/40">
                              <table className="w-full text-left font-mono text-[11px]">
                                <thead>
                                  <tr className="border-b border-slate-800 bg-slate-900/60 text-slate-400 text-[10px] uppercase tracking-wider">
                                    <th className="py-2 px-2.5">Status</th>
                                    <th className="py-2 px-2">Method</th>
                                    <th className="py-2 px-2.5">Route</th>
                                    <th className="py-2 px-2">Expected</th>
                                    <th className="py-2 px-2">Actual</th>
                                    <th className="py-2 px-2">Latency</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-800/60">
                                  {m.qaReport.testResults.map((tr, idx) => {
                                    const isPass = tr.status === "PASSED";
                                    const methodColor =
                                      tr.httpMethod === "POST" ? "bg-blue-500/20 text-blue-300 border-blue-500/30" :
                                      tr.httpMethod === "GET" ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" :
                                      tr.httpMethod === "DELETE" ? "bg-rose-500/20 text-rose-300 border-rose-500/30" :
                                      "bg-amber-500/20 text-amber-300 border-amber-500/30";
                                    return (
                                      <React.Fragment key={idx}>
                                        <tr className="hover:bg-slate-800/30 transition-colors">
                                          <td className="py-2 px-2.5">
                                            {isPass ? (
                                              <span className="flex items-center gap-1 text-emerald-400 font-bold text-[10.5px]">
                                                <CheckCircle2 className="h-3.5 w-3.5" />
                                                PASS
                                              </span>
                                            ) : (
                                              <span className="flex items-center gap-1 text-rose-400 font-bold text-[10.5px]">
                                                <XCircle className="h-3.5 w-3.5" />
                                                FAIL
                                              </span>
                                            )}
                                          </td>
                                          <td className="py-2 px-2">
                                            <span className={`px-1.5 py-0.5 rounded text-[9.5px] font-bold border ${methodColor}`}>
                                              {tr.httpMethod}
                                            </span>
                                          </td>
                                          <td className="py-2 px-2.5 font-mono text-slate-200">
                                            {tr.endpoint}
                                          </td>
                                          <td className="py-2 px-2 text-slate-400">
                                            {tr.expectedStatus}
                                          </td>
                                          <td className={`py-2 px-2 font-bold ${isPass ? "text-emerald-400" : "text-rose-400"}`}>
                                            {tr.actualStatus}
                                          </td>
                                          <td className="py-2 px-2 text-slate-400 text-[10px]">
                                            {tr.latency}
                                          </td>
                                        </tr>
                                        {tr.curlCommand && (
                                          <tr className="bg-black/60">
                                            <td colSpan={6} className="py-1.5 px-3 border-t border-slate-900">
                                              <div className="flex items-center justify-between text-[10px] text-slate-400 mb-0.5">
                                                <span>Reproduction curl:</span>
                                                <button
                                                  onClick={() => navigator.clipboard.writeText(tr.curlCommand || "")}
                                                  className="hover:text-cyan-300 text-slate-400 flex items-center gap-1 transition-colors"
                                                  title="Copy curl command"
                                                >
                                                  <Copy className="h-2.5 w-2.5" /> Copy
                                                </button>
                                              </div>
                                              <code className="text-cyan-300/90 text-[10.5px] select-all break-all font-mono">
                                                {tr.curlCommand}
                                              </code>
                                            </td>
                                          </tr>
                                        )}
                                      </React.Fragment>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}



                        {m.workingTasks && (

                          <div className="mt-3 space-y-1.5 text-[11.5px] text-slate-300">

                            {m.workingTasks.map((t, idx) => (

                              <div key={idx} className="flex items-center gap-2 text-cyan-300">

                                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />

                                <span>{t}</span>

                              </div>

                            ))}

                          </div>

                        )}

                        {m.telemetry && (
                          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center gap-2 font-mono text-[11px]">
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/25 font-semibold">
                              <Zap className="h-3.5 w-3.5 text-amber-400 fill-amber-400/20" />
                              <span>{m.telemetry.totalTokens.toLocaleString()} tokens</span>
                            </span>
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md bg-slate-800/80 text-slate-300 border border-slate-700/50">
                              <Clock className="h-3 w-3 text-cyan-400" />
                              <span>{m.telemetry.latencySec}s</span>
                            </span>
                            <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md border font-semibold ${
                              m.telemetry.isFreeTier
                                ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/25"
                                : "bg-blue-500/10 text-blue-300 border-blue-500/25"
                            }`}>
                              <span>{m.telemetry.costLabel}</span>
                            </span>
                            <span className="text-[10px] text-slate-500 truncate max-w-[170px]" title={`${m.telemetry.provider || ''}: ${m.telemetry.model}`}>
                              {m.telemetry.model}
                            </span>
                          </div>
                        )}

                      </div>
                      )}



                      {(m.approvalRequired || m.isApprovalCard) && (

                        <div className="bg-[#181308] border-2 border-amber-600/60 rounded-xl p-4 shadow-lg shadow-amber-950/20">

                          <div className="flex items-center gap-2.5 mb-1.5">

                            <div className="h-6 w-6 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400 font-semibold text-xs">

                              !

                            </div>

                            <span className="font-semibold text-amber-300 text-[13px]">Human Approval Required</span>

                            <span className="text-[10px] text-amber-500/80 ml-auto">{m.timestamp}</span>

                          </div>



                          <p className="text-amber-100/90 text-[12.5px] mb-3 ml-8 whitespace-pre-wrap">
                            {m.text || "Human approval required to proceed to the next phase. Shall I proceed?"}
                          </p>

                          {m.status === "REJECTED" ? (
                            <div className="flex items-center gap-2 text-amber-400 text-[12px] font-medium ml-8">
                              <RotateCcw className="h-4 w-4" /> Revisions requested. Resuming agent to revise...
                            </div>
                          ) : m.isApproved || m.status === "APPROVED" ? (
                            <div className="flex items-center gap-2 text-emerald-400 text-[12px] font-medium ml-8">
                              <Check className="h-4 w-4" /> Approved! Proceeding to next phase...
                            </div>
                          ) : (

                            <div className="flex items-center gap-3 ml-8">

                              <button

                                onClick={() => handleApprove(m.approvalId)}

                                className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-[12px] flex items-center gap-1.5 shadow-md shadow-emerald-700/30 transition"

                              >

                                <Check className="h-3.5 w-3.5" /> Approve & Continue

                              </button>



                              <button

                                onClick={() => {

                                  if (m.approvalId) setActiveApprovalId(m.approvalId);

                                  setShowFeedbackModal(true);

                                }}

                                className="px-3.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 font-medium text-[12px] flex items-center gap-1.5 transition"

                              >

                                <RotateCcw className="h-3.5 w-3.5 text-amber-400" /> Request Changes

                              </button>

                            </div>

                          )}



                          {showFeedbackModal && (

                            <div className="mt-3 ml-8 p-3 rounded-lg bg-[#0e121e] border border-amber-600/40 space-y-2">

                              <span className="text-[11px] font-semibold text-amber-300">Specify required changes for Agent 1:</span>

                              <input

                                type="text"

                                value={feedbackInput}

                                onChange={(e) => setFeedbackInput(e.target.value)}

                                placeholder="e.g., Add Redis caching to token validation and rate limiting..."

                                className="w-full bg-[#080b12] border border-slate-700 rounded px-2.5 py-1.5 text-[12px] text-slate-200 focus:outline-none focus:border-amber-500"

                              />

                              <div className="flex items-center gap-2 justify-end">

                                <button

                                  onClick={() => setShowFeedbackModal(false)}

                                  className="px-2.5 py-1 text-[11px] text-slate-400 hover:text-slate-200"

                                >

                                  Cancel

                                </button>

                                <button

                                  onClick={handleRequestChanges}

                                  className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded text-[11px] font-medium"

                                >

                                  Submit Revisions

                                </button>

                              </div>

                            </div>

                          )}

                        </div>

                      )}

                    </div>

                  </div>

                ))

              )}
              <div ref={messagesEndRef} />

            </div>



            {/* Bottom Chat Input Box */}

            <div className="p-3 border-t border-slate-800/80 bg-[#0a0d14]">

              {/* Attached Files Preview Chips */}

              {attachedFiles.length > 0 && (

                <div className="flex flex-wrap items-center gap-2 mb-2">

                  {attachedFiles.map((f, i) => (

                    <div

                      key={i}

                      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#141b2b] border border-cyan-500/40 text-[11.5px] text-cyan-300 shadow-sm"

                    >

                      <FileText className="h-3.5 w-3.5" />

                      <span className="font-medium truncate max-w-[200px]">{f.name}</span>

                      <span className="text-[10px] text-slate-500">({(f.size / 1024).toFixed(1)} KB)</span>

                      <button

                        type="button"

                        onClick={() => setAttachedFiles((prev) => prev.filter((_, idx) => idx !== i))}

                        className="ml-1 text-slate-400 hover:text-white"

                      >

                        <X className="h-3 w-3" />

                      </button>

                    </div>

                  ))}

                </div>

              )}



              {/* Hidden File Input for PDF / DOCX / MD / TXT */}

              <input

                ref={fileInputRef}

                type="file"

                multiple

                accept=".pdf,.doc,.docx,.md,.txt,.json,.csv"

                className="hidden"

                onChange={(e) => {

                  if (e.target.files) {

                    const newFiles = Array.from(e.target.files);

                    setAttachedFiles((prev) => [...prev, ...newFiles]);

                  }

                }}

              />



              <form

                onSubmit={handleSendMessage}

                className="border border-slate-800 focus-within:border-cyan-500/60 rounded-xl bg-[#101420] p-2 transition"

              >

                <textarea
                  ref={chatInputRef}
                  value={inputMessage}
                  onChange={(e) => {
                    setInputMessage(e.target.value);
                    e.target.style.height = "auto";
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 180)}px`;
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  rows={1}
                  placeholder={
                    attachedFiles.length > 0
                      ? "Add notes or prompt for the attached document..."
                      : "Describe your software project, or say 'Hi'..."
                  }
                  disabled={isSubmitting || isWorkflowRunning}
                  className="w-full bg-transparent text-[13px] text-slate-200 placeholder:text-slate-600 focus:outline-none px-2 py-1 disabled:opacity-50 resize-none min-h-[32px] max-h-44 overflow-y-auto leading-relaxed"
                />



                <div className="flex items-center justify-between pt-2 border-t border-slate-800/50 mt-1">

                  <div className="flex items-center gap-2 relative">

                    {/* Paperclip Button */}

                    <button

                      type="button"

                      onClick={() => fileInputRef.current?.click()}

                      title="Attach requirements document (Word, PDF, Markdown, Text)"

                      className="text-slate-500 hover:text-cyan-400 p-1.5 rounded-lg hover:bg-slate-800/70 transition"

                    >

                      <Paperclip className="h-4 w-4" />

                    </button>



                    {/* @ Mention Button */}

                    <button

                      type="button"

                      onClick={() => {

                        setInputMessage((prev) => (prev ? `${prev} @` : "@"));

                        chatInputRef.current?.focus();

                      }}

                      title="Mention an Agent"

                      className="text-slate-500 hover:text-cyan-400 p-1.5 rounded-lg hover:bg-slate-800/70 transition"

                    >

                      <AtSign className="h-4 w-4" />

                    </button>



                    {/* Agent Selector Dropdown Pill */}

                    <div className="relative">

                      <button

                        type="button"

                        onClick={() => setShowAgentMenu((prev) => !prev)}

                        className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700/80 text-[11px] text-slate-200 border border-slate-700 transition"

                      >

                        <Code2 className={`h-3.5 w-3.5 ${currentActiveAgent.color}`} />

                        <span>{currentActiveAgent.name}</span>

                        <ChevronDown className="h-3 w-3 text-slate-400 ml-0.5" />

                      </button>



                      {/* Dropdown Menu */}

                      {showAgentMenu && (

                        <div className="absolute bottom-full left-0 mb-2 w-64 bg-[#0e121d] border border-slate-700 rounded-xl shadow-2xl p-1.5 z-50 space-y-0.5 animate-in fade-in duration-150">

                          <div className="px-2 py-1 text-[10px] uppercase font-semibold tracking-wider text-slate-500">

                            Direct message to Agent

                          </div>

                          {[

                            { id: "auto", name: "Auto (All Agents)", role: "Standard multi-agent topology", color: "text-cyan-400", enabled: true },

                            { id: "agent1", name: "Agent 1: Doc Reviewer", role: "Requirements & Specifications", color: "text-emerald-400", enabled: true },

                            { id: "agent2", name: "Agent 2: Mock Vendor", role: "Mock third-party APIs", color: "text-cyan-400", enabled: agentToggles.agent2 },

                            { id: "agent3", name: "Agent 3: Main Coder", role: "Channel code implementation", color: "text-blue-400", enabled: true },

                            { id: "agent4", name: "Agent 4: QA Engineer", role: "Contract & black-box testing", color: "text-purple-400", enabled: agentToggles.agent4 },

                            { id: "agent5", name: "Agent 5: Security Reviewer", role: "SAST & vulnerability audit", color: "text-amber-400", enabled: agentToggles.agent5 },

                          ]

                            .filter((ag) => ag.enabled)

                            .map((ag) => (

                              <button

                                key={ag.id}

                                type="button"

                                onClick={() => {

                                  setSelectedAgent({ id: ag.id, name: ag.name, color: ag.color });

                                  setShowAgentMenu(false);

                                }}

                                className={`w-full flex items-start gap-2 p-2 rounded-lg text-left transition ${

                                  currentActiveAgent.id === ag.id

                                    ? "bg-blue-600/20 text-white border border-blue-500/30"

                                    : "hover:bg-slate-800/60 text-slate-300"

                                }`}

                              >

                                <Code2 className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${ag.color}`} />

                                <div>

                                  <div className="text-[11.5px] font-medium leading-none mb-1">{ag.name}</div>

                                  <div className="text-[10px] text-slate-500">{ag.role}</div>

                                </div>

                              </button>

                            ))}

                        </div>

                      )}

                    </div>

                  </div>



                  {(isSubmitting || isWorkflowRunning || streamStatus === "streaming" || streamStatus === "running") && (
                    <button
                      type="button"
                      onClick={handleCancelWorkflow}
                      title="Stop / Cancel running workflow execution"
                      className="h-7 px-3 rounded-lg bg-rose-600 hover:bg-rose-500 text-white flex items-center gap-1.5 transition text-[11px] font-medium shadow-md shadow-rose-950/40 border border-rose-500/50 cursor-pointer shrink-0"
                    >
                      <Square className="h-3 w-3 fill-white" />
                      <span>Stop</span>
                    </button>
                  )}

                  <button

                    type="submit"

                    disabled={isSubmitting || isWorkflowRunning || (!inputMessage.trim() && attachedFiles.length === 0)}

                    className="h-7 w-7 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white flex items-center justify-center transition shadow-md shadow-blue-600/30"

                  >

                    {isSubmitting || isWorkflowRunning ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}

                  </button>

                </div>

              </form>



              <div className="flex items-center justify-between text-[10px] text-slate-600 px-1 pt-1.5">

                <span>Enter to submit &nbsp;|&nbsp; Conversational greetings & full specs both supported</span>

                <span>AAISE v1.0 Enterprise</span>

              </div>

            </div>

          </div>



          {/* COLUMN 3: RIGHT PANEL */}

          <div className="w-96 shrink-0 flex flex-col bg-[#0a0d15] overflow-hidden">

            <div className="h-10 shrink-0 border-b border-slate-800/80 flex items-center justify-between px-2 text-[12px]">

              <div className="flex items-center gap-1">

                <button

                  onClick={() => setActiveTab("artifacts")}

                  className={`px-3 py-1.5 rounded-md font-medium transition ${

                    activeTab === "artifacts"

                      ? "bg-[#141b2b] text-cyan-400 border border-cyan-500/30"

                      : "text-slate-400 hover:text-slate-200"

                  }`}

                >

                  Artifacts ({artifacts.length})

                </button>

                <button

                  onClick={() => {

                    setActiveTab("diff");

                    if (selectedProject?.id) {

                      fetchProjectDiff(selectedProject.id).then((d) => setCodeDiff(d));

                    }

                  }}

                  className={`px-3 py-1.5 rounded-md font-medium transition ${

                    activeTab === "diff"

                      ? "bg-[#141b2b] text-cyan-400 border border-cyan-500/30"

                      : "text-slate-400 hover:text-slate-200"

                  }`}

                >

                  Code Diff

                </button>

                <button

                  onClick={() => setActiveTab("tests")}

                  className={`px-3 py-1.5 rounded-md font-medium transition ${

                    activeTab === "tests"

                      ? "bg-[#141b2b] text-cyan-400 border border-cyan-500/30"

                      : "text-slate-400 hover:text-slate-200"

                  }`}

                >

                  Test Results

                </button>

                <button

                  onClick={() => setActiveTab("security")}

                  className={`px-3 py-1.5 rounded-md font-medium transition ${

                    activeTab === "security"

                      ? "bg-[#141b2b] text-cyan-400 border border-cyan-500/30"

                      : "text-slate-400 hover:text-slate-200"

                  }`}

                >

                  Security

                </button>

                <button

                  onClick={() => setActiveTab("telemetry")}

                  className={`px-3 py-1.5 rounded-md font-medium transition ${

                    activeTab === "telemetry"

                      ? "bg-[#141b2b] text-amber-400 border border-amber-500/30"

                      : "text-slate-400 hover:text-slate-200"

                  }`}

                >

                  Telemetry

                </button>

              </div>



              {selectedProject && (

                <a

                  href={getProjectDownloadUrl(selectedProject.id)}

                  download

                  title="Download Project ZIP"

                  className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-400 hover:bg-slate-800/60 transition"

                >

                  <Download className="h-4 w-4" />

                </a>

              )}

            </div>



            {/* Panel Content */}

            <div className="flex-1 overflow-y-auto p-3 space-y-3">

              {activeTab === "diff" ? (

                codeDiff ? (

                  <pre className="font-mono text-[11px] text-slate-300 p-2.5 rounded-lg bg-[#0c101b] border border-slate-800 overflow-x-auto whitespace-pre-wrap leading-relaxed">

                    {codeDiff}

                  </pre>

                ) : (

                  <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500 text-[11.5px]">

                    <GitBranch className="h-8 w-8 text-slate-600 mb-2" />
                    No code diff available yet.<br />
                    {availableBranches.length > 0
                      ? "When changes are committed against the base branch, diffs will appear here."
                      : "No Git repository is initialized for this project."}

                  </div>

                )

              ) : activeTab === "artifacts" ? (

                viewingFile ? (

                  <div className="flex flex-col h-full space-y-2 text-[11.5px]">

                    <div className="flex items-center justify-between pb-2 border-b border-slate-800">

                      <button

                        onClick={() => setViewingFile(null)}

                        className="flex items-center gap-1.5 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-cyan-400 font-medium transition"

                      >

                        <span>← Back to List</span>

                      </button>

                      <span className="font-mono text-slate-300 truncate max-w-[200px]" title={viewingFile.path}>

                        {viewingFile.path}

                      </span>

                      <button

                        onClick={() => navigator.clipboard.writeText(viewingFile.content)}

                        className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition"

                      >

                        Copy

                      </button>

                    </div>

                    <div className="flex-1 overflow-auto bg-[#0a0d14] p-3 rounded-lg border border-slate-800">

                      <pre className="font-mono text-[11px] text-slate-300 whitespace-pre-wrap select-text leading-relaxed">

                        {viewingFile.content}

                      </pre>

                    </div>

                  </div>

                ) : artifacts.length === 0 ? (

                  <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500 text-[11.5px]">

                    <FileCode2 className="h-8 w-8 text-slate-600 mb-2" />

                    No project artifacts generated yet.<br />Artifacts will appear here when Agent 1 generates specifications or Agent 3 creates code.

                  </div>

                ) : (

                  <div className="space-y-2 text-[11.5px]">

                    <div className="text-[10px] text-slate-400 px-1 pb-1">

                      Click any specification or code file to inspect its content:

                    </div>

                    {artifacts.map((art) => (

                      <button

                        key={art.id}

                        type="button"

                        onClick={() => handleOpenArtifact(art.file_path)}

                        className="w-full text-left flex items-center justify-between p-2.5 rounded-lg bg-[#101422] hover:bg-[#161c30] border border-cyan-500/30 hover:border-cyan-400 transition cursor-pointer group"

                      >

                        <div className="flex items-center gap-2 overflow-hidden">

                          {art.file_path.includes("TEST") ? (

                            <FlaskConical className="h-4 w-4 text-purple-400 shrink-0" />

                          ) : (

                            <FileCode2 className="h-4 w-4 text-cyan-400 shrink-0" />

                          )}

                          <span className="font-mono text-slate-200 group-hover:text-cyan-300 truncate font-medium">

                            {art.file_path}

                          </span>

                        </div>

                        <span className="text-[10px] text-emerald-400 font-medium shrink-0 ml-2 group-hover:underline">

                          View ↗

                        </span>

                      </button>

                    ))}

                  </div>

                )

              ) : activeTab === "tests" ? (

                (() => {

                  const qaMsgs = messages.filter((m) => m.sender === "agent4" || (m.text && m.text.includes("Independent QA Test Report")));

                  if (qaMsgs.length === 0) {
                    if (liveQaRuns.length > 0) {
                      const latestRun = liveQaRuns[0];
                      const isFailed = latestRun.status === "FAILED";
                      return (
                        <div className="space-y-3">
                          <div className="p-3 rounded-xl bg-[#101422] border border-purple-500/40 space-y-2">
                            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                              <span className="font-semibold text-purple-400 flex items-center gap-1.5 text-xs">
                                <FlaskConical className="h-4 w-4" /> Agent 4 QA Contract Run (SQLite)
                              </span>
                              <span className={`text-[10px] border px-2 py-0.5 rounded-full font-bold ${
                                isFailed ? "text-rose-400 bg-rose-950/60 border-rose-500/30" : "text-emerald-400 bg-emerald-950/60 border-emerald-500/30"
                              }`}>
                                {latestRun.status}
                              </span>
                            </div>
                            <div className="text-[11px] text-slate-400 flex items-center justify-between">
                              <span>Type: <strong className="text-slate-200">{latestRun.execution_type}</strong></span>
                              <span>{latestRun.passed_count} Passed / {latestRun.failed_count} Failed</span>
                            </div>
                            <div className="space-y-1.5 pt-1 max-h-60 overflow-y-auto">
                              {latestRun.results.map((res) => (
                                <div key={res.id} className="p-2 rounded bg-slate-900 border border-slate-800 text-[11px] font-mono flex items-center justify-between">
                                  <div className="flex items-center gap-1.5 truncate max-w-[200px]">
                                    <span className="text-cyan-400 font-bold">{res.test_key}</span>
                                    <span className="text-slate-400">[{res.http_method}]</span>
                                    <span className="text-slate-300 truncate">{res.endpoint}</span>
                                  </div>
                                  <div className="flex items-center gap-2 shrink-0">
                                    <span className={res.status === "PASSED" ? "text-emerald-400" : "text-rose-400 font-bold"}>
                                      {res.actual_status_code}
                                    </span>
                                    <span className={`text-[9px] px-1 rounded ${res.status === "PASSED" ? "bg-emerald-950 text-emerald-400" : "bg-rose-950 text-rose-400"}`}>
                                      {res.status}
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                            <button
                              type="button"
                              onClick={() => setShowAnalyticsModal(true)}
                              className="w-full mt-2 py-1.5 px-3 rounded bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/30 text-purple-300 text-[11px] font-semibold flex items-center justify-center gap-1.5 transition"
                            >
                              <Activity className="h-3 w-3" />
                              View All Historical QA Reports in Portal ↗
                            </button>
                          </div>
                        </div>
                      );
                    }

                    return (

                      <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500 text-[11.5px]">

                        <FlaskConical className="h-8 w-8 text-slate-600 mb-2" />

                        No QA test results recorded yet.<br />When Agent 4 runs black-box contract testing, results will appear here.

                      </div>

                    );

                  }

                  const latestQa = qaMsgs[qaMsgs.length - 1];
                  const qaText = latestQa.text || "";
                  const isFailed = qaText.includes("FAILED") || qaText.includes("❌");
                  const isSkipped = qaText.includes("SKIPPED");

                  const badgeClass = isSkipped
                    ? "text-slate-400 bg-slate-900 border-slate-700"
                    : isFailed
                    ? "text-rose-400 bg-rose-950/60 border-rose-500/30"
                    : "text-emerald-400 bg-emerald-950/60 border-emerald-500/30";
                  const badgeText = isSkipped ? "SKIPPED" : isFailed ? "FAILED" : "PASSED";
                  const borderClass = isFailed ? "border-rose-500/40" : "border-purple-500/40";

                  // Parse test rows if present in markdown table format
                  const lines = qaText.split("\n");
                  const tableRows = lines
                    .filter((l) => l.trim().startsWith("| **"))
                    .map((l) => {
                      const cols = l.split("|").map((c) => c.trim()).filter(Boolean);
                      return {
                        id: cols[0]?.replace(/\*\*/g, "") || "",
                        route: cols[1]?.replace(/`/g, "") || "",
                        expected: cols[2]?.replace(/`/g, "") || "",
                        actual: cols[3]?.replace(/`/g, "") || "",
                        status: cols[4]?.replace(/`/g, "") || "",
                        details: cols[5] || "",
                      };
                    });

                  const summaryLines = lines
                    .filter((l) => !l.trim().startsWith("|") && !l.trim().startsWith("```") && !l.includes("Test Runner Execution"))
                    .join("\n")
                    .trim();

                  const cliLogs = qaText.includes("```text")
                    ? qaText.split("```text")[1]?.split("```")[0]?.trim()
                    : "";

                  return (
                    <div className={`p-3 rounded-xl bg-[#101422] border ${borderClass} space-y-3 text-[12px]`}>
                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                        <span className="font-semibold text-purple-400 flex items-center gap-1.5">
                          <FlaskConical className="h-4 w-4" /> Agent 4: Independent QA Test Audit
                        </span>
                        <span className={`text-[10px] border px-2 py-0.5 rounded-full ${badgeClass}`}>{badgeText}</span>
                      </div>

                      {summaryLines && (
                        <div className="text-slate-300 text-[11.5px] leading-relaxed whitespace-pre-wrap">
                          {summaryLines}
                        </div>
                      )}

                      {tableRows.length > 0 && (
                        <div className="border border-slate-800 rounded-lg overflow-hidden">
                          <div className="text-[10.5px] font-semibold text-slate-400 bg-slate-900/80 px-2.5 py-1.5 border-b border-slate-800">
                            Evaluated Black-Box Test Cases ({tableRows.length} Tests)
                          </div>
                          <div className="max-h-64 overflow-y-auto divide-y divide-slate-800/60 text-[11px]">
                            {tableRows.map((r, i) => (
                              <div key={i} className="p-2 hover:bg-slate-850/40 flex flex-col gap-1 transition">
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono font-bold text-cyan-400">{r.id}</span>
                                    <span className="font-mono text-slate-300">{r.route}</span>
                                  </div>
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                                      r.status === "PASSED"
                                        ? "bg-emerald-950 text-emerald-400 border border-emerald-500/30"
                                        : "bg-rose-950 text-rose-400 border border-rose-500/30"
                                    }`}
                                  >
                                    {r.status} (HTTP {r.actual})
                                  </span>
                                </div>
                                {r.details && (
                                  <div className="text-slate-400 text-[10.5px] pl-1">
                                    {r.details}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {cliLogs && (
                        <div className="space-y-1">
                          <div className="text-[10px] text-slate-400 font-mono">Console Test Output:</div>
                          <pre className="bg-[#080b12] p-2 rounded-lg font-mono text-[10.5px] text-emerald-400 border border-slate-800 overflow-x-auto whitespace-pre-wrap leading-tight max-h-40">
                            {cliLogs}
                          </pre>
                        </div>
                      )}

                      {tableRows.length === 0 && !cliLogs && (
                        <pre className="font-sans text-slate-200 whitespace-pre-wrap leading-relaxed text-[12px]">
                          {latestQa.text}
                        </pre>
                      )}
                    </div>
                  );

                })()

              ) : activeTab === "security" ? (

                (() => {

                  const secMsgs = messages.filter((m) => m.sender === "agent5" || (m.text && m.text.includes("Security SAST Audit Report")));

                  if (secMsgs.length === 0) {

                    return (

                      <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-500 text-[11.5px]">

                        <ShieldCheck className="h-8 w-8 text-slate-600 mb-2" />

                        No security scans recorded yet.<br />When Agent 5 runs SAST security auditing, results will appear here.

                      </div>

                    );

                  }

                  const latestSec = secMsgs[secMsgs.length - 1];
                  const secText = latestSec.text || "";
                  const hasVulns = secText.includes("CRITICAL") || secText.includes("HIGH") || secText.includes("VULNERABILITY");
                  const isSecSkipped = secText.includes("SKIPPED") || secText.includes("Not Scanned");

                  const secBadgeClass = isSecSkipped
                    ? "text-slate-400 bg-slate-900 border-slate-700"
                    : hasVulns
                    ? "text-rose-400 bg-rose-950/60 border-rose-500/30"
                    : "text-emerald-400 bg-emerald-950/60 border-emerald-500/30";
                  const secBadgeText = isSecSkipped ? "SKIPPED" : hasVulns ? "VULNERABILITIES DETECTED" : "VERIFIED CLEAN";
                  const secBorderClass = hasVulns ? "border-rose-500/40" : "border-amber-500/40";

                  return (

                    <div className={`p-3 rounded-xl bg-[#101422] border ${secBorderClass} space-y-2 text-[12px]`}>

                      <div className="flex items-center justify-between border-b border-slate-800 pb-2">

                        <span className="font-semibold text-amber-400 flex items-center gap-1.5">

                          <ShieldCheck className="h-4 w-4" /> Agent 5: Security SAST Report

                        </span>

                        <span className={`text-[10px] border px-2 py-0.5 rounded-full ${secBadgeClass}`}>{secBadgeText}</span>

                      </div>

                      <pre className="font-sans text-slate-200 whitespace-pre-wrap leading-relaxed text-[12px]">

                        {latestSec.text}

                      </pre>

                    </div>

                  );

                })()

              ) : activeTab === "telemetry" ? (
                (() => {
                  return (
                    <div className="space-y-4">
                      <div className="p-4 rounded-xl bg-[#101422] border border-amber-500/30 space-y-3">
                        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                          <span className="font-semibold text-amber-400 flex items-center gap-1.5 text-xs">
                            <Zap className="h-4 w-4" /> Live LLM & System Telemetry
                          </span>
                          <span className="text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/30 px-2 py-0.5 rounded-full font-mono">
                            SQLite ./data/aaise.db
                          </span>
                        </div>

                        {quickTelemetry ? (
                          <div className="space-y-3 font-sans text-xs">
                            <div className="grid grid-cols-2 gap-2 font-mono">
                              <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800">
                                <div className="text-[10px] text-slate-400 uppercase font-sans">Total Tokens</div>
                                <div className="text-base font-bold text-amber-300 mt-0.5">
                                  {quickTelemetry.tokens.total.toLocaleString()}
                                </div>
                                <div className="text-[9.5px] text-slate-500 mt-0.5">
                                  P: {quickTelemetry.tokens.prompt.toLocaleString()} | C: {quickTelemetry.tokens.completion.toLocaleString()}
                                </div>
                              </div>
                              <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800">
                                <div className="text-[10px] text-slate-400 uppercase font-sans">Estimated Cost</div>
                                <div className="text-base font-bold text-emerald-400 mt-0.5">
                                  ${quickTelemetry.tokens.cost_usd.toFixed(4)}
                                </div>
                                <div className="text-[9.5px] text-slate-500 mt-0.5">
                                  {quickTelemetry.tokens.invocations} calls logged
                                </div>
                              </div>
                              <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800">
                                <div className="text-[10px] text-slate-400 uppercase font-sans">Avg Latency</div>
                                <div className="text-base font-bold text-cyan-300 mt-0.5">
                                  {quickTelemetry.tokens.avg_latency_sec}s
                                </div>
                                <div className="text-[9.5px] text-slate-500 mt-0.5">
                                  {quickTelemetry.tokens.avg_latency_ms} ms avg
                                </div>
                              </div>
                              <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800">
                                <div className="text-[10px] text-slate-400 uppercase font-sans">QA Pass Rate</div>
                                <div className="text-base font-bold text-purple-300 mt-0.5">
                                  {quickTelemetry.qa.pass_rate_pct}%
                                </div>
                                <div className="text-[9.5px] text-slate-500 mt-0.5">
                                  {quickTelemetry.qa.passed_tests}/{quickTelemetry.qa.total_tests} tests
                                </div>
                              </div>
                            </div>

                            <button
                              type="button"
                              onClick={() => setShowAnalyticsModal(true)}
                              className="w-full mt-2 py-2 px-3 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/40 text-amber-300 text-xs font-semibold flex items-center justify-center gap-2 transition cursor-pointer"
                            >
                              <Activity className="h-3.5 w-3.5" />
                              Open Full Analytics & Telemetry Portal ↗
                            </button>
                          </div>
                        ) : (
                          <div className="text-slate-500 text-xs py-4 text-center">
                            Loading telemetry from SQLite...
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })()
              ) : null}

            </div>

          </div>

        </div>

      </div>



      <AgentConfigModal

        isOpen={showConfigModal}

        onClose={() => setShowConfigModal(false)}

        agentToggles={agentToggles}

        onSave={(newToggles) => handleSaveModalToggles(newToggles)}

      />

      <AnalyticsDashboardModal
        isOpen={showAnalyticsModal}
        onClose={() => setShowAnalyticsModal(false)}
        projects={projects}
        selectedProjectId={selectedProject?.id || null}
      />

    </div>

  );

}

