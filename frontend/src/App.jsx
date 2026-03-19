import { useEffect, useMemo, useRef, useState } from "react";
import { Line, Bar } from "react-chartjs-2";
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend } from "chart.js";
import { api, getAuthToken, getRefreshToken, setAuthToken, setRefreshToken } from "./api";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, Title, Tooltip, Legend);

const TONES = ["friendly", "professional", "strict"];
const DELIVERY_PROVIDERS = ["smtp", "twilio_sms", "twilio_whatsapp"];
const TWILIO_STATUSES = ["queued", "accepted", "sending", "sent", "delivered", "read", "undelivered", "failed", "canceled"];

const initialInvoiceForm = {
  customer_name: "",
  customer_email: "",
  customer_phone: "",
  amount: "",
  due_date: "",
};

const initialAuthForm = {
  username: "",
  email: "",
  password: "",
  otp_code: "",
};

const initialTeamForm = {
  username: "",
  email: "",
  password: "",
  role: "team",
};

const TEAM_ROLES = ["team", "accountant", "manager", "admin"];
const TEAM_FILTER_MODES = ["all", "owners", "members", "you"];
const TEAM_SORT_KEYS = ["username", "role", "access"];
const TEAM_VIEW_PRESETS = [
  { key: "all-default", label: "All Members", filter: "all", sortKey: "username", sortDir: "asc", search: "" },
  { key: "review-owners", label: "Review Owners", filter: "owners", sortKey: "access", sortDir: "asc", search: "" },
  { key: "my-access", label: "My Access", filter: "you", sortKey: "access", sortDir: "asc", search: "" },
  { key: "member-audit", label: "Member Audit", filter: "members", sortKey: "role", sortDir: "asc", search: "" },
];
const ROLE_LABELS = {
  admin: "Admin Control Mode",
  manager: "Manager Oversight Mode",
  accountant: "Accounting Focus Mode",
  team: "Team Execution Mode",
};

const AUDIENCE_MODES = [
  { key: "cfo", label: "CFO" },
  { key: "ops", label: "Operations" },
  { key: "smb", label: "SMB Owner" },
];

const AUDIENCE_COPY = {
  cfo: {
    heroTitle: "Receivables Governance Console",
    heroSubtitle:
      "Protect cash flow with controlled reminder execution, measurable recovery signals, and audit-friendly approval gates.",
    checklistTitle: "Finance Control Checklist",
    checklist: [
      "Load receivables using direct entry or CSV import.",
      "Generate drafts and ensure approval controls are active.",
      "Track delivery outcomes and overdue exposure against policy.",
    ],
    empty: {
      invoices: "Start by adding receivables to establish baseline exposure and collection forecasting.",
      approvals: "Drafts requiring governance review will be listed here before release.",
      insights: "Risk intelligence appears as payment behavior history becomes statistically meaningful.",
      customers: "Customer behavior and risk trends will appear once invoice history is available.",
      history: "Delivery records and failure reasons appear after first approved dispatch.",
      integrations: "Connect ERP/accounting sources to automate receivable ingestion.",
      team: "Provision accountable operators to enforce separation of duties.",
    },
  },
  ops: {
    heroTitle: "Collections Intelligence Workspace",
    heroSubtitle:
      "Monitor overdue exposure, orchestrate reminder operations, and keep approval-driven communication controlled from one command surface.",
    checklistTitle: "Operator Launch Checklist",
    checklist: [
      "Ingest your first invoice batch using form entry or CSV import.",
      "Generate a reminder draft and route it through the approval queue.",
      "Approve and dispatch, then monitor outcomes in Email History.",
    ],
    empty: {
      invoices: "Create an invoice or upload CSV to initialize automated follow-up workflows.",
      approvals: "New reminder drafts will appear here for policy-compliant review and release.",
      insights: "Risk intelligence will appear once the platform collects enough payment behavior data.",
      customers: "Customer behavior trends are shown as soon as invoices and payments are tracked.",
      history: "Approve and send a reminder to begin tracking delivery outcomes and retries.",
      integrations: "Configure connectors to streamline invoice ingestion from external finance systems.",
      team: "Add manager or accountant users to distribute approvals and collection operations.",
    },
  },
  smb: {
    heroTitle: "Cash Collection Command Hub",
    heroSubtitle:
      "Get paid faster with smart reminders, simple approvals, and a clear view of what needs attention right now.",
    checklistTitle: "Getting Started Checklist",
    checklist: [
      "Add your invoices manually or upload them in one CSV.",
      "Generate reminder drafts for late customers in one click.",
      "Approve and send reminders, then track results instantly.",
    ],
    empty: {
      invoices: "Add your first invoice to start sending smart payment reminders.",
      approvals: "When you create reminder drafts, they will appear here for quick approval.",
      insights: "As you send more reminders, we will highlight risky late-paying customers.",
      customers: "Customer payment history and risk trend lines will appear after your first invoices.",
      history: "Your sent and failed reminders will be listed here after first send.",
      integrations: "Connect tools like accounting systems to import invoices automatically.",
      team: "Invite teammates to share reminder and approval work.",
    },
  },
};

function StatusBadge({ label, variant }) {
  return <span className={`badge ${variant}`}>{label}</span>;
}

function TrendMiniBars({ points }) {
  if (!points?.length) {
    return <span className="trend-empty">No trend yet</span>;
  }

  return (
    <div className="trend-mini" title={points.map((p) => `${p.month}: ${p.risk_score}`).join(" | ")}>
      {points.map((point) => (
        <span key={`${point.month}-${point.risk_score}`} style={{ height: `${Math.max(8, point.risk_score)}%` }} />
      ))}
    </div>
  );
}

function EmptyState({ title, description, tone = "default" }) {
  return (
    <div className={`empty-cell empty-${tone}`}>
      <div className="empty-illustration" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}

function Toast({ message, type = "success", onClose }) {
  return (
    <div 
      className={`toast toast-${type}`} 
      role="status" 
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="toast-icon">{type === "success" ? "✓" : type === "error" ? "✕" : "ℹ"}</span>
      <span className="toast-message">{message}</span>
      <button 
        className="toast-close" 
        onClick={onClose}
        aria-label="Close notification"
      >
        ×
      </button>
    </div>
  );
}

function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authMode, setAuthMode] = useState("login");
  const [authForm, setAuthForm] = useState(initialAuthForm);
  const [authLoading, setAuthLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [overdue, setOverdue] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [emailHistory, setEmailHistory] = useState([]);
  const [latePayerInsights, setLatePayerInsights] = useState([]);
  const [customerHistory, setCustomerHistory] = useState([]);
  const [reportsOverview, setReportsOverview] = useState(null);
  const [companies, setCompanies] = useState([]);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [switchingCompany, setSwitchingCompany] = useState(false);
  const [teamUsers, setTeamUsers] = useState([]);
  const [teamSearchTerm, setTeamSearchTerm] = useState("");
  const [teamFilterMode, setTeamFilterMode] = useState("all");
  const [teamSortKey, setTeamSortKey] = useState("username");
  const [teamSortDir, setTeamSortDir] = useState("asc");
  const [integrationConnectors, setIntegrationConnectors] = useState([]);
  const [integrationSources, setIntegrationSources] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [queueJobs, setQueueJobs] = useState([]);
  const [queueStats, setQueueStats] = useState({ queued: 0, processing: 0, succeeded: 0, failed: 0 });
  const [opsMetrics, setOpsMetrics] = useState(null);
  const [invoiceForm, setInvoiceForm] = useState(initialInvoiceForm);
  const [teamForm, setTeamForm] = useState(initialTeamForm);
  const [integrationSource, setIntegrationSource] = useState("fake_api");
  const [integrationCount, setIntegrationCount] = useState(5);
  const [selectedTone, setSelectedTone] = useState("professional");
  const [useSmartTone, setUseSmartTone] = useState(true);
  const [deliveryProvider, setDeliveryProvider] = useState("smtp");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [editingEmail, setEditingEmail] = useState(null);
  const [webhookSimulator, setWebhookSimulator] = useState({
    MessageSid: "",
    MessageStatus: "read",
    To: "+14155552671",
    From: "whatsapp:+14155238886",
  });
  const [audienceMode, setAudienceMode] = useState("ops");
  const [displayStats, setDisplayStats] = useState({
    total_invoices: 0,
    paid_invoices: 0,
    pending_invoices: 0,
    overdue_invoices: 0,
  });
  const [toasts, setToasts] = useState([]);
  const [loadingStates, setLoadingStates] = useState({
    dashboard: false,
    reports: false,
    auth: false,
    email: false,
    queue: false,
    team: false,
  });
  const teamSearchInputRef = useRef(null);

  const addToast = (message, type = "success", duration = 3000) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  };

  const setLoadingState = (key, value) => {
    setLoadingStates((prev) => ({ ...prev, [key]: value }));
  };

  const teamPrefsStorageKey = useMemo(
    () => (currentUser?.id ? `team_view_prefs:${currentUser.id}` : ""),
    [currentUser?.id],
  );

  const overdueIds = useMemo(() => new Set(overdue.map((item) => item.id)), [overdue]);
  const roleKey = (currentUser?.role || "team").toLowerCase();
  const roleLabel = ROLE_LABELS[roleKey] || "Operations Mode";
  const audience = AUDIENCE_COPY[audienceMode] || AUDIENCE_COPY.ops;
  const activeCompany = useMemo(
    () => companies.find((company) => company.id === currentUser?.active_company_id) || null,
    [companies, currentUser?.active_company_id],
  );

  const teamVisibleUsers = useMemo(() => {
    const query = teamSearchTerm.trim().toLowerCase();

    const getSortValue = (user, key) => {
      if (key === "role") {
        return String(user.role || "").toLowerCase();
      }
      if (key === "access") {
        if (activeCompany?.owner_user_id === user.id) {
          return 0;
        }
        if (currentUser?.id === user.id) {
          return 1;
        }
        return 2;
      }
      return String(user.username || "").toLowerCase();
    };

    const roleFiltered = teamUsers.filter((user) => {
      const isOwner = activeCompany?.owner_user_id === user.id;
      const isYou = currentUser?.id === user.id;
      if (teamFilterMode === "owners") {
        return isOwner;
      }
      if (teamFilterMode === "members") {
        return !isOwner;
      }
      if (teamFilterMode === "you") {
        return isYou;
      }
      return true;
    });

    const filtered = query
      ? roleFiltered.filter((user) => {
          const username = String(user.username || "").toLowerCase();
          const email = String(user.email || "").toLowerCase();
          const role = String(user.role || "").toLowerCase();
          return username.includes(query) || email.includes(query) || role.includes(query);
        })
      : roleFiltered;

    return [...filtered].sort((a, b) => {
      const aValue = getSortValue(a, teamSortKey);
      const bValue = getSortValue(b, teamSortKey);

      if (aValue < bValue) {
        return teamSortDir === "asc" ? -1 : 1;
      }
      if (aValue > bValue) {
        return teamSortDir === "asc" ? 1 : -1;
      }
      return a.id - b.id;
    });
  }, [teamUsers, teamSearchTerm, teamFilterMode, teamSortKey, teamSortDir, activeCompany?.owner_user_id, currentUser?.id]);

  const kpiVisuals = useMemo(() => {
    const total = invoices.length || stats?.total_invoices || 0;
    const paidCount = invoices.filter((invoice) => invoice.status === "paid").length;
    const pendingCount = Math.max(0, total - paidCount);
    const overdueCount = overdue.length || stats?.overdue_invoices || 0;
    const followedUpCount = emailHistory.filter((email) =>
      ["approved", "sent", "delivered", "opened", "failed"].includes(email.status),
    ).length;

    const paidPct = total > 0 ? Math.round((paidCount / total) * 100) : 0;
    const pendingPct = total > 0 ? Math.round((pendingCount / total) * 100) : 0;
    const overduePct = total > 0 ? Math.round((overdueCount / total) * 100) : 0;
    const followUpPct = total > 0 ? Math.round((followedUpCount / total) * 100) : 0;

    return {
      paidPct,
      pendingPct,
      overduePct,
      followUpPct,
    };
  }, [emailHistory, invoices, overdue, stats]);

  const followUpSummary = useMemo(() => {
    const draftCount = pendingApprovals.length;
    const sentCount = emailHistory.filter((email) => ["sent", "delivered", "opened"].includes(email.status)).length;
    const openedCount = emailHistory.filter((email) => email.status === "opened").length;
    const failedCount = emailHistory.filter((email) => email.status === "failed").length;

    return {
      draftCount,
      sentCount,
      openedCount,
      failedCount,
    };
  }, [emailHistory, pendingApprovals]);

  useEffect(() => {
    async function bootstrapAuth() {
      const token = getAuthToken();
      if (!token) {
        setAuthLoading(false);
        return;
      }

      try {
        const me = await api.me();
        setCurrentUser(me);
      } catch {
        setAuthToken("");
        setRefreshToken("");
        setCurrentUser(null);
      } finally {
        setAuthLoading(false);
      }
    }

    bootstrapAuth();
  }, []);

  async function loadData() {
    setLoading(true);
    setMessage("");
    try {
      const [
        companiesData,
        statsData,
        invoiceData,
        overdueData,
        pendingData,
        allEmails,
        insightsData,
        customerHistoryData,
        reportsData,
        connectorData,
        sourceData,
      ] = await Promise.all([
        api.getCompanies(),
        api.getStats(),
        api.getInvoices(),
        api.getOverdue(),
        api.getPendingApprovals(),
        api.getEmails(),
        api.getLatePayerInsights(),
        api.getCustomerHistory(),
        api.getReportsOverview(),
        api.getIntegrationConnectors(),
        api.getIntegrationSources(),
      ]);

      setCompanies(companiesData);
      setStats(statsData);
      setInvoices(invoiceData);
      setOverdue(overdueData);
      setPendingApprovals(pendingData);
      setEmailHistory(allEmails);
      setLatePayerInsights(insightsData);
      setCustomerHistory(customerHistoryData);
      setReportsOverview(reportsData);
      setIntegrationConnectors(connectorData);
      setIntegrationSources(sourceData.sources || []);

      if (currentUser?.role === "admin") {
        try {
          const [users, logs, jobs, qstats, metrics] = await Promise.all([
            api.getTeamUsers(),
            api.getAuditLogs(80),
            api.getQueueJobs(80),
            api.getQueueStats(),
            api.getOpsMetrics(),
          ]);
          setTeamUsers(users);
          setAuditLogs(logs);
          setQueueJobs(jobs);
          setQueueStats(qstats);
          setOpsMetrics(metrics);
        } catch {
          setTeamUsers([]);
          setAuditLogs([]);
          setQueueJobs([]);
          setQueueStats({ queued: 0, processing: 0, succeeded: 0, failed: 0 });
          setOpsMetrics(null);
        }
      } else {
        setTeamUsers([]);
        setAuditLogs([]);
        setQueueJobs([]);
        setQueueStats({ queued: 0, processing: 0, succeeded: 0, failed: 0 });
        setOpsMetrics(null);
      }
    } catch (error) {
      setMessage(error.message || "Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!currentUser) {
      return;
    }

    loadData();

    // Bonus: real-time-like dashboard refresh every 15s.
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [currentUser]);

  useEffect(() => {
    if (!teamPrefsStorageKey) {
      return;
    }

    try {
      const raw = localStorage.getItem(teamPrefsStorageKey);
      if (!raw) {
        return;
      }

      const parsed = JSON.parse(raw);
      if (TEAM_FILTER_MODES.includes(parsed.teamFilterMode)) {
        setTeamFilterMode(parsed.teamFilterMode);
      }
      if (TEAM_SORT_KEYS.includes(parsed.teamSortKey)) {
        setTeamSortKey(parsed.teamSortKey);
      }
      if (parsed.teamSortDir === "asc" || parsed.teamSortDir === "desc") {
        setTeamSortDir(parsed.teamSortDir);
      }
      if (typeof parsed.teamSearchTerm === "string") {
        setTeamSearchTerm(parsed.teamSearchTerm);
      }
    } catch {
      // Ignore malformed persisted state and continue with defaults.
    }
  }, [teamPrefsStorageKey]);

  useEffect(() => {
    if (!teamPrefsStorageKey) {
      return;
    }

    try {
      localStorage.setItem(
        teamPrefsStorageKey,
        JSON.stringify({
          teamFilterMode,
          teamSortKey,
          teamSortDir,
          teamSearchTerm,
        }),
      );
    } catch {
      // Ignore storage write failures.
    }
  }, [teamPrefsStorageKey, teamFilterMode, teamSortKey, teamSortDir, teamSearchTerm]);

  useEffect(() => {
    if (activeTab !== "team" || currentUser?.role !== "admin") {
      return;
    }

    const onKeyDown = (event) => {
      if (event.defaultPrevented) {
        return;
      }

      const target = event.target;
      const tagName = target?.tagName?.toLowerCase();
      const isTypingTarget =
        tagName === "input"
        || tagName === "textarea"
        || tagName === "select"
        || target?.isContentEditable;

      if (event.key === "/" && !isTypingTarget) {
        event.preventDefault();
        teamSearchInputRef.current?.focus();
        teamSearchInputRef.current?.select();
        return;
      }

      if (isTypingTarget) {
        return;
      }

      if (event.key === "r" || event.key === "R") {
        event.preventDefault();
        resetTeamView();
        return;
      }

      if (["1", "2", "3", "4"].includes(event.key)) {
        const preset = TEAM_VIEW_PRESETS[Number(event.key) - 1];
        if (!preset) {
          return;
        }
        event.preventDefault();
        applyTeamPreset(preset);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeTab, currentUser?.role, teamPrefsStorageKey, teamFilterMode, teamSortKey, teamSortDir, teamSearchTerm]);

  useEffect(() => {
    if (!stats) {
      setDisplayStats({
        total_invoices: 0,
        paid_invoices: 0,
        pending_invoices: 0,
        overdue_invoices: 0,
      });
      return;
    }

    const totalInvoices = invoices.length || stats.total_invoices || 0;
    const paidInvoices = invoices.filter((invoice) => invoice.status === "paid").length;
    const pendingInvoices = Math.max(0, totalInvoices - paidInvoices);

    const target = {
      total_invoices: totalInvoices,
      paid_invoices: paidInvoices,
      pending_invoices: pendingInvoices,
      overdue_invoices: overdue.length || stats.overdue_invoices || 0,
    };

    const durationMs = 650;
    const start = performance.now();
    let frameId = 0;

    const animate = (now) => {
      const t = Math.min((now - start) / durationMs, 1);
      const eased = 1 - (1 - t) * (1 - t);

      setDisplayStats({
        total_invoices: Math.round(target.total_invoices * eased),
        paid_invoices: Math.round(target.paid_invoices * eased),
        pending_invoices: Math.round(target.pending_invoices * eased),
        overdue_invoices: Math.round(target.overdue_invoices * eased),
      });

      if (t < 1) {
        frameId = requestAnimationFrame(animate);
      }
    };

    frameId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameId);
  }, [invoices, overdue, stats]);

  async function handleAuthSubmit(event) {
    event.preventDefault();
    setMessage("");
    try {
      const payload =
        authMode === "signup"
          ? {
              username: authForm.username,
              email: authForm.email,
              password: authForm.password,
            }
          : {
              email: authForm.email,
              password: authForm.password,
              otp_code: authForm.otp_code || undefined,
            };

      const response = authMode === "signup" ? await api.signup(payload) : await api.login(payload);
      setAuthToken(response.access_token);
      setRefreshToken(response.refresh_token || "");
      setCurrentUser(response.user);
      setAuthForm(initialAuthForm);
      setMessage(`Welcome, ${response.user.username}.`);
    } catch (error) {
      setMessage(error.message || "Authentication failed");
    }
  }

  async function handleLogout() {
    try {
      const refresh = getRefreshToken();
      if (refresh) {
        await api.logout(refresh);
      }
    } catch {
      // ignore logout call failures
    }
    setAuthToken("");
    setRefreshToken("");
    setCurrentUser(null);
    setStats(null);
    setInvoices([]);
    setOverdue([]);
    setPendingApprovals([]);
    setEmailHistory([]);
    setLatePayerInsights([]);
    setCustomerHistory([]);
    setReportsOverview(null);
    setIntegrationConnectors([]);
    setCompanies([]);
    setAuditLogs([]);
    setQueueJobs([]);
    setQueueStats({ queued: 0, processing: 0, succeeded: 0, failed: 0 });
    setOpsMetrics(null);
    setMessage("Logged out.");
  }

  async function handleRunQueueNow() {
    try {
      const result = await api.runQueueNow(25);
      setMessage(`Queue run: picked ${result.picked}, succeeded ${result.succeeded}, failed ${result.failed}.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to run queue now");
    }
  }

  async function handleSimulateTwilioWebhook(event) {
    event.preventDefault();
    try {
      const payload = {
        MessageStatus: webhookSimulator.MessageStatus,
        To: webhookSimulator.To || undefined,
        From: webhookSimulator.From || undefined,
      };
      if (webhookSimulator.MessageSid.trim()) {
        payload.MessageSid = webhookSimulator.MessageSid.trim();
      }
      await api.simulateTwilioStatus(payload);
      setMessage(`Twilio webhook simulated: ${payload.MessageStatus}`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Twilio webhook simulation failed");
    }
  }

  async function handleCreateInvoice(event) {
    event.preventDefault();
    try {
      await api.createInvoice({
        ...invoiceForm,
        amount: Number(invoiceForm.amount),
      });
      setInvoiceForm(initialInvoiceForm);
      setMessage("Invoice created successfully.");
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to create invoice");
    }
  }

  async function handleInvoiceUpload(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const result = await api.uploadInvoicesFile(file);
      setMessage(`Imported ${result.created_count} invoices from ${file.name}.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Invoice upload failed");
    } finally {
      event.target.value = "";
    }
  }

  async function handleGenerateEmail() {
    if (!selectedInvoiceId) {
      setMessage("Select an invoice first.");
      return;
    }

    try {
      const payload = {
        invoice_id: Number(selectedInvoiceId),
        auto_tone: useSmartTone,
      };
      if (!useSmartTone) {
        payload.tone = selectedTone;
      }

      await api.generateEmail(payload);
      setMessage("Email draft generated and moved to pending approval.");
      loadData();
    } catch (error) {
      setMessage(error.message || "Failed to generate email");
    }
  }

  async function handleApprove(id) {
    try {
      await api.approveEmail(id, deliveryProvider);
      setMessage(`Email approved and queued via ${deliveryProvider}.`);
      setEditingEmail(null);
      loadData();
    } catch (error) {
      setMessage(error.message || "Approve/send failed");
    }
  }

  async function handleReject(id) {
    try {
      await api.rejectEmail(id);
      setMessage("Email rejected.");
      setEditingEmail(null);
      loadData();
    } catch (error) {
      setMessage(error.message || "Reject failed");
    }
  }

  async function handleSendNow(id) {
    try {
      await api.sendEmail(id, deliveryProvider);
      setMessage(`Email queued via ${deliveryProvider}.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Send failed");
    }
  }

  async function handleDownloadInvoicePdf(id) {
    try {
      await api.downloadInvoicePdf(id);
      setMessage(`Invoice #${id} PDF downloaded.`);
    } catch (error) {
      setMessage(error.message || "Invoice PDF download failed");
    }
  }

  async function handleEditSave() {
    if (!editingEmail) {
      return;
    }
    try {
      await api.editEmail(editingEmail.id, {
        subject: editingEmail.subject,
        body: editingEmail.body,
      });
      setMessage("Pending email updated.");
      loadData();
    } catch (error) {
      setMessage(error.message || "Edit failed");
    }
  }

  async function handleImportFromIntegration() {
    try {
      const created = await api.importIntegrationInvoices({
        source: integrationSource,
        count: Number(integrationCount),
      });
      setMessage(`Imported ${created.length} invoices from ${integrationSource}.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Integration import failed");
    }
  }

  async function handleConnectIntegration(provider) {
    try {
      const started = await api.startIntegrationOAuth(provider);
      const isLiveQuickBooks = provider === "quickbooks" && started.auth_url.includes("appcenter.intuit.com");

      if (isLiveQuickBooks) {
        window.open(started.auth_url, "_blank", "noopener,noreferrer");
        const code = window.prompt(
          "QuickBooks authorization opened in a new tab. Paste the 'code' query parameter from the redirect URL:",
          "",
        );
        if (!code) {
          setMessage("QuickBooks connect canceled: no code provided.");
          return;
        }

        const stateInput = window.prompt(
          "Paste the 'state' query parameter from the redirect URL (or keep default):",
          started.state,
        );
        await api.completeIntegrationOAuth(provider, code, stateInput || started.state);
        setMessage("quickbooks connected (live OAuth).");
      } else {
        await api.completeIntegrationOAuth(provider, "demo-code", started.state);
        setMessage(`${provider} connected (OAuth scaffold).`);
      }

      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to connect integration");
    }
  }

  async function handleDisconnectIntegration(provider) {
    try {
      await api.disconnectIntegration(provider);
      setMessage(`${provider} disconnected.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to disconnect integration");
    }
  }

  async function handleSyncIntegration(provider) {
    try {
      const created = await api.syncIntegrationInvoices(provider, Number(integrationCount) || 5);
      setMessage(`Synced ${created.length} invoices from ${provider}.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to sync integration invoices");
    }
  }

  async function handleCreateTeamUser(event) {
    event.preventDefault();
    try {
      await api.createTeamUser({
        username: teamForm.username,
        email: teamForm.email,
        password: teamForm.password,
        role: teamForm.role,
      });
      setTeamForm(initialTeamForm);
      setMessage("Team user created.");
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to create team user");
    }
  }

  async function handleInviteExistingUser(event) {
    event.preventDefault();
    const email = inviteEmail.trim();
    if (!email) {
      setMessage("Email is required to invite a user.");
      return;
    }

    try {
      await api.inviteToActiveCompany(email);
      setInviteEmail("");
      setMessage(`User ${email} invited to ${activeCompany?.name || "active company"}.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to invite user");
    }
  }

  async function handleRemoveMember(userId, username) {
    const confirmed = window.confirm(`Remove ${username} from ${activeCompany?.name || "this company"}?`);
    if (!confirmed) {
      return;
    }

    try {
      await api.removeFromActiveCompany(userId);
      setMessage(`${username} removed from active company.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to remove user");
    }
  }

  function handleTeamSort(columnKey) {
    if (teamSortKey === columnKey) {
      setTeamSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setTeamSortKey(columnKey);
    setTeamSortDir("asc");
  }

  function teamSortMarker(columnKey) {
    if (teamSortKey !== columnKey) {
      return "↕";
    }
    return teamSortDir === "asc" ? "▲" : "▼";
  }

  function applyTeamPreset(preset) {
    setTeamFilterMode(preset.filter);
    setTeamSortKey(preset.sortKey);
    setTeamSortDir(preset.sortDir);
    setTeamSearchTerm(preset.search);
  }

  function resetTeamView() {
    const defaultPreset = TEAM_VIEW_PRESETS[0];
    applyTeamPreset(defaultPreset);

    if (teamPrefsStorageKey) {
      try {
        localStorage.removeItem(teamPrefsStorageKey);
      } catch {
        // Ignore storage cleanup failures.
      }
    }
  }

  async function handleCreateCompany(event) {
    event.preventDefault();
    const trimmedName = newCompanyName.trim();
    if (!trimmedName) {
      setMessage("Company name is required.");
      return;
    }

    try {
      const created = await api.createCompany({ name: trimmedName });
      setCompanies((prev) => [...prev, created]);
      setNewCompanyName("");
      setMessage(`Company \"${created.name}\" created.`);
    } catch (error) {
      setMessage(error.message || "Unable to create company");
    }
  }

  async function handleSwitchCompany(companyIdValue) {
    const companyId = Number(companyIdValue);
    if (!companyId || companyId === currentUser?.active_company_id) {
      return;
    }

    try {
      setSwitchingCompany(true);
      const updatedUser = await api.switchCompany(companyId);
      setCurrentUser(updatedUser);
      setMessage("Active company switched.");
      await loadData();
    } catch (error) {
      setMessage(error.message || "Unable to switch company");
    } finally {
      setSwitchingCompany(false);
    }
  }

  async function handleMarkPaid(invoiceId) {
    try {
      const ref = `MANUAL-${invoiceId}-${Date.now()}`;
      await api.markInvoicePaid(invoiceId, ref);
      setMessage("Invoice marked as paid.");
      loadData();
    } catch (error) {
      setMessage(error.message || "Unable to mark invoice as paid");
    }
  }

  if (authLoading) {
    return (
      <div className="app-shell">
        <section className="panel">
          <h3>Loading</h3>
          <p>Checking session...</p>
        </section>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="app-shell">
        <header className="hero">
          <p className="eyebrow">AI Invoice Follow-up Automation</p>
          <h1>Secure Access</h1>
          <p>Sign in to access your personal dashboard and protected APIs.</p>
        </header>

        {message && <div className="alert">{message}</div>}

        <section className="panel auth-panel">
          <h3>{authMode === "signup" ? "Create Account" : "Login"}</h3>
          <form className="stack-form" onSubmit={handleAuthSubmit}>
            {authMode === "signup" && (
              <input
                placeholder="Username"
                value={authForm.username}
                onChange={(e) => setAuthForm((prev) => ({ ...prev, username: e.target.value }))}
                required
              />
            )}
            <input
              type="email"
              placeholder="Email"
              value={authForm.email}
              onChange={(e) => setAuthForm((prev) => ({ ...prev, email: e.target.value }))}
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={authForm.password}
              onChange={(e) => setAuthForm((prev) => ({ ...prev, password: e.target.value }))}
              required
              minLength={8}
            />
            {authMode === "login" && (
              <input
                type="text"
                placeholder="OTP Code (if MFA enabled)"
                value={authForm.otp_code}
                onChange={(e) => setAuthForm((prev) => ({ ...prev, otp_code: e.target.value }))}
                minLength={6}
                maxLength={8}
              />
            )}
            <button type="submit">{authMode === "signup" ? "Sign Up" : "Login"}</button>
          </form>

          <div className="auth-switch">
            <span>{authMode === "signup" ? "Already have an account?" : "Need an account?"}</span>
            <button
              type="button"
              className="ghost"
              onClick={() => setAuthMode((prev) => (prev === "signup" ? "login" : "signup"))}
            >
              {authMode === "signup" ? "Go to Login" : "Create Account"}
            </button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className={`app-shell role-${roleKey}`}>
      <header className="hero">
        <p className="eyebrow">AI Invoice Follow-up Automation</p>
        <h1>{audience.heroTitle}</h1>
        <p>{audience.heroSubtitle}</p>
        <div className="audience-switch" role="group" aria-label="Audience Profile">
          {AUDIENCE_MODES.map((item) => (
            <button
              key={item.key}
              type="button"
              className={audienceMode === item.key ? "active" : ""}
              onClick={() => setAudienceMode(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <span className="role-chip">{roleLabel}</span>
        <p className="signed-in-user">
          Signed in as {currentUser.username} ({currentUser.role})
        </p>
        <div className="company-toolbar">
          <label>
            Active Company
            <select
              value={currentUser.active_company_id || ""}
              onChange={(e) => handleSwitchCompany(e.target.value)}
              disabled={switchingCompany || companies.length === 0}
            >
              <option value="" disabled>
                Select company
              </option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </label>
          <form onSubmit={handleCreateCompany} className="company-create-form">
            <input
              type="text"
              placeholder="New company name"
              value={newCompanyName}
              onChange={(e) => setNewCompanyName(e.target.value)}
              maxLength={120}
            />
            <button type="submit">Add Company</button>
          </form>
        </div>
        <p className="active-company-label">
          Current scope: {activeCompany?.name || "No company selected"}
        </p>
      </header>

      <nav className="tabs">
        <button
          className={activeTab === "dashboard" ? "active" : ""}
          onClick={() => setActiveTab("dashboard")}
        >
          Dashboard
        </button>
        <button
          className={activeTab === "reports" ? "active" : ""}
          onClick={() => setActiveTab("reports")}
        >
          Reports
        </button>
        <button
          className={activeTab === "customers" ? "active" : ""}
          onClick={() => setActiveTab("customers")}
        >
          Customer History
        </button>
        <button
          className={activeTab === "history" ? "active" : ""}
          onClick={() => setActiveTab("history")}
        >
          Email History
        </button>
        <button
          className={activeTab === "integrations" ? "active" : ""}
          onClick={() => setActiveTab("integrations")}
        >
          Integrations
        </button>
        {currentUser.role === "admin" && (
          <button
            className={activeTab === "ops" ? "active" : ""}
            onClick={() => setActiveTab("ops")}
          >
            Ops
          </button>
        )}
        {currentUser.role === "admin" && (
          <button
            className={activeTab === "team" ? "active" : ""}
            onClick={() => setActiveTab("team")}
          >
            Team
          </button>
        )}
        <button className="ghost" onClick={handleLogout}>
          Logout
        </button>
      </nav>

      {message && <div className="alert">{message}</div>}

      {activeTab === "dashboard" && (
        <>
          <section className="cards-grid">
            <article className="card">
              <p>Total Invoices</p>
              <h2>{stats ? displayStats.total_invoices : "-"}</h2>
              <small>Live invoice count across the active company ledger</small>
            </article>
            <article className="card success">
              <p>Paid vs Pending</p>
              <h2>{stats ? `${displayStats.paid_invoices} / ${displayStats.pending_invoices}` : "-"}</h2>
              <div className="kpi-spark">
                <span style={{ width: `${kpiVisuals.paidPct}%` }} />
              </div>
              <small>{kpiVisuals.paidPct}% paid, {kpiVisuals.pendingPct}% still pending</small>
            </article>
            <article className="card warning">
              <p>Overdue Invoices</p>
              <h2>{stats ? displayStats.overdue_invoices : "-"}</h2>
              <div className="kpi-spark">
                <span style={{ width: `${kpiVisuals.overduePct}%` }} />
              </div>
              <small>{kpiVisuals.overduePct}% of the invoice book is overdue</small>
            </article>
            <article className="card info">
              <p>Follow-up Status</p>
              <h2>{stats ? followUpSummary.sentCount : "-"}</h2>
              <div className="followup-status-grid">
                <span className="followup-chip neutral">Drafts {followUpSummary.draftCount}</span>
                <span className="followup-chip ok">Sent {followUpSummary.sentCount}</span>
                <span className="followup-chip info">Opened {followUpSummary.openedCount}</span>
                <span className="followup-chip danger">Failed {followUpSummary.failedCount}</span>
              </div>
              <div className="kpi-spark">
                <span style={{ width: `${kpiVisuals.followUpPct}%` }} />
              </div>
              <small>{kpiVisuals.followUpPct}% of invoices have entered the follow-up pipeline</small>
            </article>
          </section>

          {(invoices.length === 0 || emailHistory.length === 0) && (
            <section className="panel onboarding-panel">
              <h3>{audience.checklistTitle}</h3>
              <ol>
                {audience.checklist.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            </section>
          )}

          <section className="grid-two">
            <article className="panel">
              <h3>Invoice Health Snapshot</h3>
              <div className="dashboard-snapshot">
                <div className="snapshot-block">
                  <span className="snapshot-label">Paid</span>
                  <strong>{displayStats.paid_invoices}</strong>
                </div>
                <div className="snapshot-block">
                  <span className="snapshot-label">Pending</span>
                  <strong>{displayStats.pending_invoices}</strong>
                </div>
                <div className="snapshot-block">
                  <span className="snapshot-label">Overdue</span>
                  <strong>{displayStats.overdue_invoices}</strong>
                </div>
              </div>
              <p className="snapshot-footnote">
                Pending invoices are still outstanding. Overdue is the subset already past due.
              </p>
            </article>

            <article className="panel">
              <h3>Follow-up Pipeline</h3>
              <div className="dashboard-snapshot">
                <div className="snapshot-block">
                  <span className="snapshot-label">Awaiting Approval</span>
                  <strong>{followUpSummary.draftCount}</strong>
                </div>
                <div className="snapshot-block">
                  <span className="snapshot-label">Sent/Delivered</span>
                  <strong>{followUpSummary.sentCount}</strong>
                </div>
                <div className="snapshot-block">
                  <span className="snapshot-label">Opened</span>
                  <strong>{followUpSummary.openedCount}</strong>
                </div>
                <div className="snapshot-block">
                  <span className="snapshot-label">Failed</span>
                  <strong>{followUpSummary.failedCount}</strong>
                </div>
              </div>
              <p className="snapshot-footnote">
                This tracks whether reminders are drafted, sent, opened, or failing in the current cycle.
              </p>
            </article>
          </section>

          <section className="grid-two">
            <article className="panel">
              <h3>Add Invoice</h3>
              <form onSubmit={handleCreateInvoice} className="stack-form">
                <input
                  placeholder="Customer Name"
                  value={invoiceForm.customer_name}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({ ...prev, customer_name: e.target.value }))
                  }
                  required
                />
                <input
                  type="email"
                  placeholder="Customer Email"
                  value={invoiceForm.customer_email}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({ ...prev, customer_email: e.target.value }))
                  }
                  required
                />
                <input
                  type="text"
                  placeholder="Customer Phone (optional, E.164 for SMS)"
                  value={invoiceForm.customer_phone}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({ ...prev, customer_phone: e.target.value }))
                  }
                />
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Amount"
                  value={invoiceForm.amount}
                  onChange={(e) => setInvoiceForm((prev) => ({ ...prev, amount: e.target.value }))}
                  required
                />
                <input
                  type="date"
                  value={invoiceForm.due_date}
                  onChange={(e) => setInvoiceForm((prev) => ({ ...prev, due_date: e.target.value }))}
                  required
                />
                <button type="submit">Save Invoice</button>
              </form>

              <div className="csv-upload">
                <label htmlFor="invoiceUpload">CSV / Excel Upload</label>
                <input id="invoiceUpload" type="file" accept=".csv,.xlsx,.xls" onChange={handleInvoiceUpload} />
              </div>
            </article>

            <article className="panel">
              <h3>Generate AI Reminder</h3>
              <select value={selectedInvoiceId} onChange={(e) => setSelectedInvoiceId(e.target.value)}>
                <option value="">Select invoice</option>
                {invoices
                  .filter((inv) => inv.status === "pending")
                  .map((invoice) => (
                    <option key={invoice.id} value={invoice.id}>
                      #{invoice.id} - {invoice.customer_name} (${invoice.amount.toFixed(2)})
                    </option>
                  ))}
              </select>

              <div className="tone-picker">
                {TONES.map((tone) => (
                  <button
                    key={tone}
                    className={selectedTone === tone ? "active" : ""}
                    onClick={() => setSelectedTone(tone)}
                    type="button"
                    disabled={useSmartTone}
                  >
                    {tone}
                  </button>
                ))}
              </div>

              <label>
                <input
                  type="checkbox"
                  checked={useSmartTone}
                  onChange={(e) => setUseSmartTone(e.target.checked)}
                />
                Use Smart AI Tone (based on delay, amount, and payment history)
              </label>

              <label>
                Delivery Provider
                <select value={deliveryProvider} onChange={(e) => setDeliveryProvider(e.target.value)}>
                  {DELIVERY_PROVIDERS.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider}
                    </option>
                  ))}
                </select>
              </label>

              <button type="button" onClick={handleGenerateEmail}>
                Generate Email Draft
              </button>
            </article>
          </section>

          <section className="panel">
            <h3>Invoices</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Customer</th>
                    <th>Email</th>
                    <th>Amount</th>
                    <th>Due Date</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.length === 0 && (
                    <tr>
                      <td colSpan={7}>
                        <EmptyState
                          tone="invoices"
                          title="No invoices on record"
                          description={audience.empty.invoices}
                        />
                      </td>
                    </tr>
                  )}
                  {invoices.map((invoice) => (
                    <tr key={invoice.id}>
                      <td>{invoice.id}</td>
                      <td>{invoice.customer_name}</td>
                      <td>{invoice.customer_email}</td>
                      <td>${invoice.amount.toFixed(2)}</td>
                      <td>{invoice.due_date}</td>
                      <td>
                        {invoice.status === "paid" ? (
                          <StatusBadge label="Paid" variant="ok" />
                        ) : overdueIds.has(invoice.id) ? (
                          <StatusBadge label="Overdue" variant="danger" />
                        ) : (
                          <StatusBadge label="Pending" variant="neutral" />
                        )}
                      </td>
                      <td>
                        <div className="actions">
                          {invoice.payment_url && (
                            <button
                              type="button"
                              onClick={() => window.open(invoice.payment_url, "_blank", "noopener,noreferrer")}
                            >
                              Pay Now
                            </button>
                          )}
                          {invoice.status !== "paid" && (
                            <button type="button" className="ghost" onClick={() => handleMarkPaid(invoice.id)}>
                              Mark Paid
                            </button>
                          )}
                          <button type="button" className="ghost" onClick={() => handleDownloadInvoicePdf(invoice.id)}>
                            Download PDF
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h3>Pending Approval Queue</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Email ID</th>
                    <th>Invoice ID</th>
                    <th>Tone</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingApprovals.length === 0 && (
                    <tr>
                      <td colSpan={5}>
                        <EmptyState
                          tone="approvals"
                          title="Approval queue is clear"
                          description={audience.empty.approvals}
                        />
                      </td>
                    </tr>
                  )}
                  {pendingApprovals.map((email) => (
                    <tr key={email.id}>
                      <td>{email.id}</td>
                      <td>{email.invoice_id}</td>
                      <td>{email.tone}</td>
                      <td>
                        <StatusBadge label={email.status} variant="neutral" />
                      </td>
                      <td>
                        <div className="actions">
                          <button type="button" onClick={() => setEditingEmail(email)}>
                            Preview / Edit
                          </button>
                          <button type="button" onClick={() => handleApprove(email.id)}>
                            Approve + Send
                          </button>
                          <button type="button" className="ghost" onClick={() => handleReject(email.id)}>
                            Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <h3>AI Insights: Late Payer Risk</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Email</th>
                    <th>Overdue Rate</th>
                    <th>Risk</th>
                    <th>Insight</th>
                  </tr>
                </thead>
                <tbody>
                  {latePayerInsights.length === 0 && (
                    <tr>
                      <td colSpan={5}>
                        <EmptyState
                          tone="insights"
                          title="No risk patterns detected yet"
                          description={audience.empty.insights}
                        />
                      </td>
                    </tr>
                  )}
                  {latePayerInsights.map((entry) => (
                    <tr key={entry.customer_email}>
                      <td>{entry.customer_name}</td>
                      <td>{entry.customer_email}</td>
                      <td>{entry.overdue_rate}% ({entry.overdue_invoices}/{entry.total_invoices})</td>
                      <td>
                        <StatusBadge
                          label={entry.risk_level}
                          variant={
                            entry.risk_level === "high"
                              ? "danger"
                              : entry.risk_level === "medium"
                                ? "neutral"
                                : "ok"
                          }
                        />
                      </td>
                      <td>{entry.insight}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {activeTab === "customers" && (
        <section className="panel">
          <h3>Customer Payment History & Risk Trend</h3>
          <div className="table-wrap">
            <table className="mobile-responsive">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Email</th>
                  <th>Paid / Total</th>
                  <th>On-time Rate</th>
                  <th>Avg Days Late</th>
                  <th>Outstanding</th>
                  <th>Risk Score</th>
                  <th>Risk Level</th>
                  <th>6-Month Trend</th>
                </tr>
              </thead>
              <tbody>
                {customerHistory.length === 0 && (
                  <tr>
                    <td colSpan={9}>
                      <EmptyState
                        tone="insights"
                        title="No customer behavior history yet"
                        description={audience.empty.customers}
                      />
                    </td>
                  </tr>
                )}
                {customerHistory.map((entry) => (
                  <tr key={entry.customer_email}>
                    <td data-label="Customer">{entry.customer_name}</td>
                    <td data-label="Email">{entry.customer_email}</td>
                    <td data-label="Paid / Total">{entry.paid_invoices}/{entry.total_invoices}</td>
                    <td data-label="On-time Rate">{entry.on_time_payment_rate}%</td>
                    <td data-label="Avg Days Late">{entry.average_days_late}</td>
                    <td data-label="Outstanding">${Number(entry.outstanding_amount || 0).toFixed(2)}</td>
                    <td data-label="Risk Score">{entry.risk_score}</td>
                    <td data-label="Risk Level">
                      <StatusBadge
                        label={entry.risk_level}
                        variant={
                          entry.risk_level === "high"
                            ? "danger"
                            : entry.risk_level === "medium"
                              ? "neutral"
                              : "ok"
                        }
                      />
                    </td>
                    <td data-label="6-Month Trend">
                      <TrendMiniBars points={entry.trend} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "reports" && (
        <section className="panel">
          <h3>Recovery & Collection Analytics</h3>

          <section className="cards-grid">
            <article className="card info">
              <p>Monthly Recovery Rate</p>
              <h2>{reportsOverview ? `${reportsOverview.monthly_recovery_rate}%` : "-"}</h2>
              <small>Paid amount divided by invoiced amount for recent months.</small>
            </article>
            <article className="card warning">
              <p>Average Payment Delay</p>
              <h2>{reportsOverview ? `${reportsOverview.avg_payment_delay_days} days` : "-"}</h2>
              <small>Average days late across paid invoices.</small>
            </article>
            <article className="card success">
              <p>Email Open Rate</p>
              <h2>{reportsOverview ? `${reportsOverview.email_open_rate}%` : "-"}</h2>
              <small>Share of sent reminders that were opened.</small>
            </article>
            <article className="card">
              <p>Email Click Rate</p>
              <h2>{reportsOverview ? `${reportsOverview.email_click_rate}%` : "-"}</h2>
              <small>Share of sent reminders with at least one click.</small>
            </article>
          </section>

          <div className="grid-two">
            <article className="panel integration-inner">
              <h3>Monthly Recovery Trend</h3>
              {reportsOverview?.monthly_recovery?.length > 0 ? (
                <div className="chart-container">
                  <Bar
                    data={{
                      labels: reportsOverview.monthly_recovery.map((r) => r.month),
                      datasets: [
                        {
                          label: "Paid",
                          data: reportsOverview.monthly_recovery.map((r) => r.paid_amount),
                          backgroundColor: "rgba(28, 138, 79, 0.7)",
                          borderColor: "rgba(28, 138, 79, 1)",
                          borderWidth: 2,
                        },
                        {
                          label: "Invoiced",
                          data: reportsOverview.monthly_recovery.map((r) => r.invoiced_amount),
                          backgroundColor: "rgba(193, 106, 47, 0.5)",
                          borderColor: "rgba(193, 106, 47, 1)",
                          borderWidth: 2,
                        },
                      ],
                    }}
                    options={{
                      responsive: true,
                      maintainAspectRatio: true,
                      plugins: { legend: { position: "bottom" } },
                      scales: { y: { beginAtZero: true } },
                    }}
                  />
                </div>
              ) : (
                <EmptyState
                  tone="insights"
                  title="No recovery trend yet"
                  description="Recovery metrics appear after invoice and payment activity."
                />
              )}
              {reportsOverview?.monthly_recovery?.length > 0 && (
                <div className="table-wrap">
                  <table className="mobile-responsive">
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th>Invoiced</th>
                        <th>Paid</th>
                        <th>Recovery Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reportsOverview.monthly_recovery.map((row) => (
                        <tr key={row.month}>
                          <td data-label="Month">{row.month}</td>
                          <td data-label="Invoiced">${Number(row.invoiced_amount || 0).toFixed(2)}</td>
                          <td data-label="Paid">${Number(row.paid_amount || 0).toFixed(2)}</td>
                          <td data-label="Recovery Rate">{row.recovery_rate}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </article>

            <article className="panel integration-inner">
              <h3>Top Late Payers</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Customer</th>
                      <th>Email</th>
                      <th>Overdue</th>
                      <th>Overdue Rate</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(!reportsOverview || !reportsOverview.top_late_payers?.length) && (
                      <tr>
                        <td colSpan={4}>
                          <EmptyState
                            tone="insights"
                            title="No late payer pattern yet"
                            description="Top late payer insights will appear as customer behavior data grows."
                          />
                        </td>
                      </tr>
                    )}
                    {reportsOverview?.top_late_payers?.map((row) => (
                      <tr key={row.customer_email}>
                        <td>{row.customer_name}</td>
                        <td>{row.customer_email}</td>
                        <td>{row.overdue_invoices}/{row.total_invoices}</td>
                        <td>{row.overdue_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </div>
        </section>
      )}

      {activeTab === "history" && (
        <section className="panel">
          <h3>Email History</h3>
          <div className="table-wrap">
            <table className="mobile-responsive">
              <thead>
                <tr>
                  <th>Email ID</th>
                  <th>Invoice ID</th>
                  <th>Status</th>
                  <th>Tone</th>
                  <th>Retries</th>
                  <th>Sent At</th>
                  <th>Delivered At</th>
                  <th>Opened At</th>
                  <th>Clicks</th>
                  <th>Clicked At</th>
                  <th>Tone Rationale</th>
                  <th>Failure</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {emailHistory.length === 0 && (
                  <tr>
                    <td colSpan={13}>
                      <EmptyState
                        tone="history"
                        title="No delivery history yet"
                        description={audience.empty.history}
                      />
                    </td>
                  </tr>
                )}
                {emailHistory.map((email) => (
                  <tr key={email.id}>
                    <td data-label="Email ID">{email.id}</td>
                    <td data-label="Invoice ID">{email.invoice_id}</td>
                    <td data-label="Status">{email.status}</td>
                    <td data-label="Tone">{email.tone}</td>
                    <td data-label="Retries">{email.retry_count ?? 0}</td>
                    <td data-label="Sent At">{email.sent_at ? new Date(email.sent_at).toLocaleString() : "-"}</td>
                    <td data-label="Delivered At">{email.delivered_at ? new Date(email.delivered_at).toLocaleString() : "-"}</td>
                    <td data-label="Opened At">{email.opened_at ? new Date(email.opened_at).toLocaleString() : "-"}</td>
                    <td data-label="Clicks">{email.click_count ?? 0}</td>
                    <td data-label="Clicked At">{email.clicked_at ? new Date(email.clicked_at).toLocaleString() : "-"}</td>
                    <td data-label="Tone Rationale">{email.tone_rationale || "-"}</td>
                    <td data-label="Failure">{email.failure_reason || "-"}</td>
                    <td data-label="Actions">
                      {(email.status === "failed" || email.status === "approved") && (
                        <button type="button" onClick={() => handleSendNow(email.id)}>
                          Send / Retry
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {activeTab === "integrations" && (
        <section className="panel">
          <h3>Integration Imports (Simulated)</h3>
          <article className="panel integration-inner">
            <h3>OAuth Connector Hub (Scaffold)</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Mode</th>
                    <th>Last Synced</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {integrationConnectors.length === 0 && (
                    <tr>
                      <td colSpan={5}>
                        <EmptyState
                          tone="integrations"
                          title="No connector data yet"
                          description="Connector statuses will appear after first load."
                        />
                      </td>
                    </tr>
                  )}
                  {integrationConnectors.map((connector) => (
                    <tr key={connector.provider}>
                      <td>{connector.display_name}</td>
                      <td>
                        <StatusBadge label={connector.connected ? "Connected" : "Disconnected"} variant={connector.connected ? "ok" : "neutral"} />
                      </td>
                      <td>{connector.mode}</td>
                      <td>{connector.last_synced_at ? new Date(connector.last_synced_at).toLocaleString() : "-"}</td>
                      <td>
                        <div className="actions">
                          {connector.connected ? (
                            <>
                              <button type="button" onClick={() => handleSyncIntegration(connector.provider)}>
                                Sync Invoices
                              </button>
                              <button
                                type="button"
                                className="ghost"
                                onClick={() => handleDisconnectIntegration(connector.provider)}
                              >
                                Disconnect
                              </button>
                            </>
                          ) : (
                            <button type="button" onClick={() => handleConnectIntegration(connector.provider)}>
                              Connect
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <div className="grid-two">
            <article className="panel integration-inner">
              <h3>Available Sources</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Mode</th>
                      <th>Ready</th>
                    </tr>
                  </thead>
                  <tbody>
                    {integrationSources.length === 0 && (
                      <tr>
                        <td colSpan={3}>
                          <EmptyState
                            tone="integrations"
                            title="No integration sources available"
                            description={audience.empty.integrations}
                          />
                        </td>
                      </tr>
                    )}
                    {integrationSources.map((src) => (
                      <tr key={src.id}>
                        <td>{src.id}</td>
                        <td>{src.mode}</td>
                        <td>{src.ready ? "Yes" : "No"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>

            <article className="panel integration-inner">
              <h3>Import Invoices</h3>
              <label>
                Source
                <select value={integrationSource} onChange={(e) => setIntegrationSource(e.target.value)}>
                  <option value="fake_api">fake_api</option>
                  <option value="xero">xero</option>
                  <option value="quickbooks">quickbooks</option>
                  <option value="zoho_books">zoho_books</option>
                </select>
              </label>
              <label>
                Count
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={integrationCount}
                  onChange={(e) => setIntegrationCount(e.target.value)}
                />
              </label>
              <button type="button" onClick={handleImportFromIntegration}>
                Import Invoices
              </button>
            </article>
          </div>
        </section>
      )}

      {activeTab === "team" && currentUser.role === "admin" && (
        <section className="panel">
          <h3>Team Management</h3>
          <section className="grid-two">
            <article className="panel team-inner">
              <h3>Create Team User</h3>
              <form className="stack-form" onSubmit={handleCreateTeamUser}>
                <input
                  placeholder="Username"
                  value={teamForm.username}
                  onChange={(e) => setTeamForm((prev) => ({ ...prev, username: e.target.value }))}
                  required
                />
                <input
                  type="email"
                  placeholder="Email"
                  value={teamForm.email}
                  onChange={(e) => setTeamForm((prev) => ({ ...prev, email: e.target.value }))}
                  required
                />
                <input
                  type="password"
                  placeholder="Temporary Password"
                  value={teamForm.password}
                  onChange={(e) => setTeamForm((prev) => ({ ...prev, password: e.target.value }))}
                  required
                  minLength={8}
                />
                <select
                  value={teamForm.role}
                  onChange={(e) => setTeamForm((prev) => ({ ...prev, role: e.target.value }))}
                >
                  {TEAM_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
                <button type="submit">Create User</button>
              </form>

              <div className="team-divider" />

              <h3>Invite Existing User</h3>
              <form className="stack-form" onSubmit={handleInviteExistingUser}>
                <input
                  type="email"
                  placeholder="Existing user email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                />
                <button type="submit" className="ghost">Invite to Active Company</button>
              </form>
            </article>

            <article className="panel team-inner">
              <h3>Users</h3>
              <div className="team-presets-wrap">
                <div className="team-presets-row">
                  {TEAM_VIEW_PRESETS.map((preset) => {
                    const isActive =
                      teamFilterMode === preset.filter
                      && teamSortKey === preset.sortKey
                      && teamSortDir === preset.sortDir
                      && teamSearchTerm === preset.search;
                    return (
                      <button
                        key={preset.key}
                        type="button"
                        className={`preset-chip ${isActive ? "active" : ""}`}
                        onClick={() => applyTeamPreset(preset)}
                      >
                        {preset.label}
                      </button>
                    );
                  })}
                </div>
                <button type="button" className="preset-reset-btn" onClick={resetTeamView}>
                  Reset Team View
                </button>
              </div>
              <p className="team-shortcuts-hint">Shortcuts: / focus search, R reset, 1-4 apply presets</p>
              <div className="team-search-wrap">
                <input
                  ref={teamSearchInputRef}
                  type="text"
                  placeholder="Search by username, email, or role"
                  value={teamSearchTerm}
                  onChange={(e) => setTeamSearchTerm(e.target.value)}
                />
              </div>
              <div className="team-filter-row">
                {[
                  { key: "all", label: "All" },
                  { key: "owners", label: "Owners" },
                  { key: "members", label: "Members" },
                  { key: "you", label: "You" },
                ].map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    className={`filter-chip ${teamFilterMode === item.key ? "active" : ""}`}
                    onClick={() => setTeamFilterMode(item.key)}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
              <div className="member-summary">
                <span className="member-pill">Company Members: {teamUsers.length}</span>
                {activeCompany && <span className="member-pill subtle">Owner ID: {activeCompany.owner_user_id}</span>}
                <span className="member-pill subtle">Visible: {teamVisibleUsers.length}</span>
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>
                        <button type="button" className="sort-header-btn" onClick={() => handleTeamSort("username")}>
                          Username {teamSortMarker("username")}
                        </button>
                      </th>
                      <th>Email</th>
                      <th>
                        <button type="button" className="sort-header-btn" onClick={() => handleTeamSort("role")}>
                          Role {teamSortMarker("role")}
                        </button>
                      </th>
                      <th>
                        <button type="button" className="sort-header-btn" onClick={() => handleTeamSort("access")}>
                          Company Access {teamSortMarker("access")}
                        </button>
                      </th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {teamVisibleUsers.length === 0 && (
                      <tr>
                        <td colSpan={6}>
                          <EmptyState
                            tone="team"
                            title={teamUsers.length === 0 ? "No team members provisioned" : "No search matches"}
                            description={
                              teamUsers.length === 0
                                ? audience.empty.team
                                : "Try a different username, email, or role filter."
                            }
                          />
                        </td>
                      </tr>
                    )}
                    {teamVisibleUsers.map((user) => (
                      <tr key={user.id}>
                        <td>{user.id}</td>
                        <td>{user.username}</td>
                        <td>{user.email}</td>
                        <td>{user.role}</td>
                        <td>
                          <div className="member-tags">
                            {activeCompany?.owner_user_id === user.id ? (
                              <span className="member-tag owner">Owner</span>
                            ) : (
                              <span className="member-tag member">Member</span>
                            )}
                            {user.id === currentUser.id && <span className="member-tag you">You</span>}
                          </div>
                        </td>
                        <td>
                          {user.id !== currentUser.id && activeCompany?.owner_user_id !== user.id && (
                            <button
                              type="button"
                              className="ghost"
                              onClick={() => handleRemoveMember(user.id, user.username)}
                            >
                              Remove
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
        </section>
      )}

      {activeTab === "ops" && currentUser.role === "admin" && (
        <section className="panel">
          <h3>Ops Console</h3>
          <div className="actions">
            <button type="button" onClick={handleRunQueueNow}>Run Queue Now</button>
          </div>
          <div className="grid-two">
            <article className="panel">
              <h3>Queue Status</h3>
              <p>Queued: {queueStats?.queued ?? 0}</p>
              <p>Processing: {queueStats?.processing ?? 0}</p>
              <p>Succeeded: {queueStats?.succeeded ?? 0}</p>
              <p>Failed: {queueStats?.failed ?? 0}</p>
              <p>Failed Emails: {opsMetrics?.failed_emails ?? 0}</p>
              <p>Webhook Events (24h): {opsMetrics?.webhook_events_24h ?? 0}</p>
            </article>
            <article className="panel">
              <h3>Queue Jobs</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Type</th>
                      <th>Status</th>
                      <th>Attempts</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {queueJobs.slice(0, 20).map((job) => (
                      <tr key={job.id}>
                        <td>{job.id}</td>
                        <td>{job.job_type}</td>
                        <td>{job.status}</td>
                        <td>{job.attempts}/{job.max_attempts}</td>
                        <td>{job.last_error || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </div>
          <article className="panel">
            <h3>Twilio Webhook Simulator</h3>
            <form className="stack-form" onSubmit={handleSimulateTwilioWebhook}>
              <label>
                Message SID (optional in dry-run)
                <input
                  type="text"
                  value={webhookSimulator.MessageSid}
                  onChange={(e) => setWebhookSimulator((prev) => ({ ...prev, MessageSid: e.target.value }))}
                  placeholder="SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
                />
              </label>
              <label>
                Message Status
                <select
                  value={webhookSimulator.MessageStatus}
                  onChange={(e) => setWebhookSimulator((prev) => ({ ...prev, MessageStatus: e.target.value }))}
                >
                  {TWILIO_STATUSES.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>
              <label>
                To
                <input
                  type="text"
                  value={webhookSimulator.To}
                  onChange={(e) => setWebhookSimulator((prev) => ({ ...prev, To: e.target.value }))}
                  placeholder="+14155552671"
                />
              </label>
              <label>
                From
                <input
                  type="text"
                  value={webhookSimulator.From}
                  onChange={(e) => setWebhookSimulator((prev) => ({ ...prev, From: e.target.value }))}
                  placeholder="whatsapp:+14155238886"
                />
              </label>
              <button type="submit">Simulate Webhook</button>
            </form>
          </article>
          <article className="panel">
            <h3>Audit Log</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Action</th>
                    <th>Entity</th>
                    <th>User</th>
                  </tr>
                </thead>
                <tbody>
                  {auditLogs.slice(0, 40).map((log) => (
                    <tr key={log.id}>
                      <td>{new Date(log.created_at).toLocaleString()}</td>
                      <td>{log.action}</td>
                      <td>{log.entity_type} #{log.entity_id || "-"}</td>
                      <td>{log.user_id || "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </section>
      )}

      {editingEmail && (
        <div className="modal-backdrop" onClick={() => setEditingEmail(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Email Preview</h3>
            <label>
              Subject
              <input
                value={editingEmail.subject}
                onChange={(e) => setEditingEmail((prev) => ({ ...prev, subject: e.target.value }))}
              />
            </label>
            <label>
              Body
              <textarea
                rows={10}
                value={editingEmail.body}
                onChange={(e) => setEditingEmail((prev) => ({ ...prev, body: e.target.value }))}
              />
            </label>
            <div className="actions right">
              <button type="button" className="ghost" onClick={() => setEditingEmail(null)}>
                Close
              </button>
              <button type="button" onClick={handleEditSave}>
                Save Changes
              </button>
              <button type="button" onClick={() => handleApprove(editingEmail.id)}>
                Approve + Send
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && <div className="loading-pill">Refreshing data...</div>}

      <div className="toast-container" role="region" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            message={toast.message}
            type={toast.type}
            onClose={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
          />
        ))}
      </div>
    </div>
  );
}

export default App;
