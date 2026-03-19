import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import {
  api,
  getAuthToken,
  getRefreshToken,
  setAuthToken,
  setRefreshToken,
} from "./api";
import { DashboardSnapshotPanels } from "./components/DashboardSnapshotPanels";
import { IntegrationsSection } from "./components/IntegrationsSection";
import { OpsSection } from "./components/OpsSection";
import { ReportsSection } from "./components/ReportsSection";
import { RolePermissionsPanel } from "./components/RolePermissionsPanel";
import { TeamSection } from "./components/TeamSection";
import { EmptyState, StatusBadge, Toast, TrendMiniBars } from "./components/ui";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
);

const TONES = ["friendly", "professional", "strict"];
const DELIVERY_PROVIDERS = ["smtp", "twilio_sms", "twilio_whatsapp"];
const TWILIO_STATUSES = [
  "queued",
  "accepted",
  "sending",
  "sent",
  "delivered",
  "read",
  "undelivered",
  "failed",
  "canceled",
];

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
  role: "viewer",
};

const TEAM_ROLES = ["viewer", "accountant", "admin"];
const RBAC_ROLES = ["admin", "accountant", "viewer"];
const TEAM_FILTER_MODES = ["all", "owners", "members", "you"];
const TEAM_SORT_KEYS = ["username", "role", "access"];
const TEAM_VIEW_PRESETS = [
  {
    key: "all-default",
    label: "All Members",
    filter: "all",
    sortKey: "username",
    sortDir: "asc",
    search: "",
  },
  {
    key: "review-owners",
    label: "Review Owners",
    filter: "owners",
    sortKey: "access",
    sortDir: "asc",
    search: "",
  },
  {
    key: "my-access",
    label: "My Access",
    filter: "you",
    sortKey: "access",
    sortDir: "asc",
    search: "",
  },
  {
    key: "member-audit",
    label: "Member Audit",
    filter: "members",
    sortKey: "role",
    sortDir: "asc",
    search: "",
  },
];
const ROLE_LABELS = {
  admin: "Admin Control Mode",
  accountant: "Accounting Focus Mode",
  viewer: "Viewer Read-Only Mode",
};

function normalizeRole(role) {
  const raw = String(role || "").toLowerCase();
  if (raw === "team") {
    return "viewer";
  }
  if (raw === "manager") {
    return "accountant";
  }
  if (["admin", "accountant", "viewer"].includes(raw)) {
    return raw;
  }
  return "viewer";
}

function displayRole(role) {
  const normalized = normalizeRole(role);
  if (normalized === "admin") {
    return "Admin";
  }
  if (normalized === "accountant") {
    return "Accountant";
  }
  return "Viewer";
}

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
      invoices:
        "Start by adding receivables to establish baseline exposure and collection forecasting.",
      approvals:
        "Drafts requiring governance review will be listed here before release.",
      insights:
        "Risk intelligence appears as payment behavior history becomes statistically meaningful.",
      customers:
        "Customer behavior and risk trends will appear once invoice history is available.",
      history:
        "Delivery records and failure reasons appear after first approved dispatch.",
      integrations:
        "Connect ERP/accounting sources to automate receivable ingestion.",
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
      invoices:
        "Create an invoice or upload CSV to initialize automated follow-up workflows.",
      approvals:
        "New reminder drafts will appear here for policy-compliant review and release.",
      insights:
        "Risk intelligence will appear once the platform collects enough payment behavior data.",
      customers:
        "Customer behavior trends are shown as soon as invoices and payments are tracked.",
      history:
        "Approve and send a reminder to begin tracking delivery outcomes and retries.",
      integrations:
        "Configure connectors to streamline invoice ingestion from external finance systems.",
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
      invoices:
        "Add your first invoice to start sending smart payment reminders.",
      approvals:
        "When you create reminder drafts, they will appear here for quick approval.",
      insights:
        "As you send more reminders, we will highlight risky late-paying customers.",
      customers:
        "Customer payment history and risk trend lines will appear after your first invoices.",
      history:
        "Your sent and failed reminders will be listed here after first send.",
      integrations:
        "Connect tools like accounting systems to import invoices automatically.",
      team: "Invite teammates to share reminder and approval work.",
    },
  },
};

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
  const [emailAnalytics, setEmailAnalytics] = useState(null);
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
  const [queueStats, setQueueStats] = useState({
    queued: 0,
    processing: 0,
    succeeded: 0,
    failed: 0,
  });
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
  const [themeMode, setThemeMode] = useState(() => {
    try {
      const saved = localStorage.getItem("ui-theme");
      return saved === "dark" ? "dark" : "light";
    } catch {
      return "light";
    }
  });
  const [audienceMode, setAudienceMode] = useState("ops");
  const [displayStats, setDisplayStats] = useState({
    total_invoices: 0,
    paid_invoices: 0,
    pending_invoices: 0,
    overdue_invoices: 0,
  });
  const [toasts, setToasts] = useState([]);
  const [permissionsRoleTab, setPermissionsRoleTab] = useState("viewer");
  const teamSearchInputRef = useRef(null);

  const addToast = (message, type = "success", duration = 3000) => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, duration);
  };

  const notify = (nextMessage, type = "info") => {
    setMessage(nextMessage || "");
    if (nextMessage) {
      addToast(nextMessage, type);
    }
  };

  useEffect(() => {
    try {
      localStorage.setItem("ui-theme", themeMode);
    } catch {
      // Ignore local storage failures.
    }
  }, [themeMode]);

  const teamPrefsStorageKey = useMemo(
    () => (currentUser?.id ? `team_view_prefs:${currentUser.id}` : ""),
    [currentUser?.id],
  );

  const overdueIds = useMemo(
    () => new Set(overdue.map((item) => item.id)),
    [overdue],
  );
  const roleKey = normalizeRole(currentUser?.role);
  const isAdmin = roleKey === "admin";
  const canEditOperations = roleKey === "admin" || roleKey === "accountant";
  const roleLabel = ROLE_LABELS[roleKey] || "Operations Mode";
  const permissionsByRole = useMemo(
    () => ({
      admin: {
        "View invoices, reminders, and reports": true,
        "Create or upload invoices": true,
        "Generate and edit reminder drafts": true,
        "Approve, reject, or send reminders": true,
        "Mark invoices as paid": true,
        "Run integrations (connect, sync, import)": true,
        "Manage users and Ops controls": true,
      },
      accountant: {
        "View invoices, reminders, and reports": true,
        "Create or upload invoices": true,
        "Generate and edit reminder drafts": true,
        "Approve, reject, or send reminders": true,
        "Mark invoices as paid": true,
        "Run integrations (connect, sync, import)": true,
        "Manage users and Ops controls": false,
      },
      viewer: {
        "View invoices, reminders, and reports": true,
        "Create or upload invoices": false,
        "Generate and edit reminder drafts": false,
        "Approve, reject, or send reminders": false,
        "Mark invoices as paid": false,
        "Run integrations (connect, sync, import)": false,
        "Manage users and Ops controls": false,
      },
    }),
    [],
  );
  const permissionCapabilities = useMemo(
    () => Object.keys(permissionsByRole.admin),
    [permissionsByRole],
  );
  const audience = AUDIENCE_COPY[audienceMode] || AUDIENCE_COPY.ops;
  const activeCompany = useMemo(
    () =>
      companies.find(
        (company) => company.id === currentUser?.active_company_id,
      ) || null,
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
          return (
            username.includes(query) ||
            email.includes(query) ||
            role.includes(query)
          );
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
  }, [
    teamUsers,
    teamSearchTerm,
    teamFilterMode,
    teamSortKey,
    teamSortDir,
    activeCompany?.owner_user_id,
    currentUser?.id,
  ]);

  const kpiVisuals = useMemo(() => {
    const total = invoices.length || stats?.total_invoices || 0;
    const paidCount = invoices.filter(
      (invoice) => invoice.status === "paid",
    ).length;
    const pendingCount = Math.max(0, total - paidCount);
    const overdueCount = overdue.length || stats?.overdue_invoices || 0;
    const followedUpCount = emailHistory.filter((email) =>
      ["approved", "sent", "delivered", "opened", "failed"].includes(
        email.status,
      ),
    ).length;

    const paidPct = total > 0 ? Math.round((paidCount / total) * 100) : 0;
    const pendingPct = total > 0 ? Math.round((pendingCount / total) * 100) : 0;
    const overduePct = total > 0 ? Math.round((overdueCount / total) * 100) : 0;
    const followUpPct =
      total > 0 ? Math.round((followedUpCount / total) * 100) : 0;

    return {
      paidPct,
      pendingPct,
      overduePct,
      followUpPct,
    };
  }, [emailHistory, invoices, overdue, stats]);

  const followUpSummary = useMemo(() => {
    const draftCount = pendingApprovals.length;
    const sentCount = emailHistory.filter((email) =>
      ["sent", "delivered", "opened"].includes(email.status),
    ).length;
    const openedCount = emailHistory.filter(
      (email) => email.status === "opened",
    ).length;
    const failedCount = emailHistory.filter(
      (email) => email.status === "failed",
    ).length;

    return {
      draftCount,
      sentCount,
      openedCount,
      failedCount,
    };
  }, [emailHistory, pendingApprovals]);

  useEffect(() => {
    setPermissionsRoleTab(roleKey);
  }, [roleKey]);

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

  const loadData = useCallback(async () => {
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
        emailAnalyticsData,
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
        api.getEmailAnalytics(),
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
      setEmailAnalytics(emailAnalyticsData);
      setIntegrationConnectors(connectorData);
      setIntegrationSources(sourceData.sources || []);

      if (isAdmin) {
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
  }, [isAdmin]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }

    loadData();

    // Bonus: real-time-like dashboard refresh every 15s.
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [currentUser, loadData]);

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
  }, [
    teamPrefsStorageKey,
    teamFilterMode,
    teamSortKey,
    teamSortDir,
    teamSearchTerm,
  ]);

  useEffect(() => {
    if (activeTab !== "team" || !isAdmin) {
      return;
    }

    const onKeyDown = (event) => {
      if (event.defaultPrevented) {
        return;
      }

      const target = event.target;
      const tagName = target?.tagName?.toLowerCase();
      const isTypingTarget =
        tagName === "input" ||
        tagName === "textarea" ||
        tagName === "select" ||
        target?.isContentEditable;

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
  }, [
    activeTab,
    applyTeamPreset,
    isAdmin,
    resetTeamView,
    teamFilterMode,
    teamPrefsStorageKey,
    teamSearchTerm,
    teamSortDir,
    teamSortKey,
  ]);

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
    const paidInvoices = invoices.filter(
      (invoice) => invoice.status === "paid",
    ).length;
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

      const response =
        authMode === "signup"
          ? await api.signup(payload)
          : await api.login(payload);
      setAuthToken(response.access_token);
      setRefreshToken(response.refresh_token || "");
      setCurrentUser(response.user);
      setAuthForm(initialAuthForm);
      notify(`Welcome, ${response.user.username}.`, "success");
    } catch (error) {
      notify(error.message || "Authentication failed", "error");
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
    setEmailAnalytics(null);
    setIntegrationConnectors([]);
    setCompanies([]);
    setAuditLogs([]);
    setQueueJobs([]);
    setQueueStats({ queued: 0, processing: 0, succeeded: 0, failed: 0 });
    setOpsMetrics(null);
    notify("Logged out.", "info");
  }

  async function handleRunQueueNow() {
    try {
      const result = await api.runQueueNow(25);
      notify(
        `Queue run: picked ${result.picked}, succeeded ${result.succeeded}, failed ${result.failed}.`,
        "success",
      );
      loadData();
    } catch (error) {
      notify(error.message || "Unable to run queue now", "error");
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
      notify(`Twilio webhook simulated: ${payload.MessageStatus}`, "success");
      loadData();
    } catch (error) {
      notify(error.message || "Twilio webhook simulation failed", "error");
    }
  }

  async function handleCreateInvoice(event) {
    event.preventDefault();
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Ask an admin to grant Accountant role for write actions.",
        "info",
      );
      return;
    }
    try {
      await api.createInvoice({
        ...invoiceForm,
        amount: Number(invoiceForm.amount),
      });
      setInvoiceForm(initialInvoiceForm);
      notify("Invoice created successfully.", "success");
      loadData();
    } catch (error) {
      notify(error.message || "Unable to create invoice", "error");
    }
  }

  async function handleInvoiceUpload(event) {
    if (!canEditOperations) {
      notify("Viewer access is read-only. Invoice upload is disabled.", "info");
      event.target.value = "";
      return;
    }
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const result = await api.uploadInvoicesFile(file);
      notify(
        `Imported ${result.created_count} invoices from ${file.name}.`,
        "success",
      );
      loadData();
    } catch (error) {
      notify(error.message || "Invoice upload failed", "error");
    } finally {
      event.target.value = "";
    }
  }

  async function handleGenerateEmail() {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Reminder generation is disabled.",
        "info",
      );
      return;
    }
    if (!selectedInvoiceId) {
      notify("Select an invoice first.", "info");
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
      notify("Email draft generated and moved to pending approval.", "success");
      loadData();
    } catch (error) {
      notify(error.message || "Failed to generate email", "error");
    }
  }

  async function handleApprove(id) {
    if (!canEditOperations) {
      notify("Viewer access is read-only. Email approval is disabled.", "info");
      return;
    }
    try {
      await api.approveEmail(id, deliveryProvider);
      notify(`Email approved and queued via ${deliveryProvider}.`, "success");
      setEditingEmail(null);
      loadData();
    } catch (error) {
      notify(error.message || "Approve/send failed", "error");
    }
  }

  async function handleReject(id) {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Email rejection is disabled.",
        "info",
      );
      return;
    }
    try {
      await api.rejectEmail(id);
      notify("Email rejected.", "success");
      setEditingEmail(null);
      loadData();
    } catch (error) {
      notify(error.message || "Reject failed", "error");
    }
  }

  async function handleSendNow(id) {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Sending reminders is disabled.",
        "info",
      );
      return;
    }
    try {
      await api.sendEmail(id, deliveryProvider);
      notify(`Email queued via ${deliveryProvider}.`, "success");
      loadData();
    } catch (error) {
      notify(error.message || "Send failed", "error");
    }
  }

  async function handleDownloadInvoicePdf(id) {
    try {
      await api.downloadInvoicePdf(id);
      notify(`Invoice #${id} PDF downloaded.`, "success");
    } catch (error) {
      notify(error.message || "Invoice PDF download failed", "error");
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
      notify("Pending email updated.", "success");
      loadData();
    } catch (error) {
      notify(error.message || "Edit failed", "error");
    }
  }

  async function handleImportFromIntegration() {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Integration import is disabled.",
        "info",
      );
      return;
    }
    try {
      const created = await api.importIntegrationInvoices({
        source: integrationSource,
        count: Number(integrationCount),
      });
      notify(
        `Imported ${created.length} invoices from ${integrationSource}.`,
        "success",
      );
      loadData();
    } catch (error) {
      notify(error.message || "Integration import failed", "error");
    }
  }

  async function handleConnectIntegration(provider) {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Integration changes are disabled.",
        "info",
      );
      return;
    }
    try {
      const started = await api.startIntegrationOAuth(provider);
      const isLiveQuickBooks =
        provider === "quickbooks" &&
        started.auth_url.includes("appcenter.intuit.com");

      if (isLiveQuickBooks) {
        window.open(started.auth_url, "_blank", "noopener,noreferrer");
        const code = window.prompt(
          "QuickBooks authorization opened in a new tab. Paste the 'code' query parameter from the redirect URL:",
          "",
        );
        if (!code) {
          notify("QuickBooks connect canceled: no code provided.", "info");
          return;
        }

        const stateInput = window.prompt(
          "Paste the 'state' query parameter from the redirect URL (or keep default):",
          started.state,
        );
        await api.completeIntegrationOAuth(
          provider,
          code,
          stateInput || started.state,
        );
        notify("quickbooks connected (live OAuth).", "success");
      } else {
        await api.completeIntegrationOAuth(
          provider,
          "demo-code",
          started.state,
        );
        notify(`${provider} connected (OAuth scaffold).`, "success");
      }

      loadData();
    } catch (error) {
      notify(error.message || "Unable to connect integration", "error");
    }
  }

  async function handleDisconnectIntegration(provider) {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Integration changes are disabled.",
        "info",
      );
      return;
    }
    try {
      await api.disconnectIntegration(provider);
      notify(`${provider} disconnected.`, "success");
      loadData();
    } catch (error) {
      notify(error.message || "Unable to disconnect integration", "error");
    }
  }

  async function handleSyncIntegration(provider) {
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Integration sync is disabled.",
        "info",
      );
      return;
    }
    try {
      const created = await api.syncIntegrationInvoices(
        provider,
        Number(integrationCount) || 5,
      );
      notify(`Synced ${created.length} invoices from ${provider}.`, "success");
      loadData();
    } catch (error) {
      notify(error.message || "Unable to sync integration invoices", "error");
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
      notify("Team user created.", "success");
      loadData();
    } catch (error) {
      notify(error.message || "Unable to create team user", "error");
    }
  }

  async function handleInviteExistingUser(event) {
    event.preventDefault();
    const email = inviteEmail.trim();
    if (!email) {
      notify("Email is required to invite a user.", "info");
      return;
    }

    try {
      await api.inviteToActiveCompany(email);
      setInviteEmail("");
      notify(
        `User ${email} invited to ${activeCompany?.name || "active company"}.`,
        "success",
      );
      loadData();
    } catch (error) {
      notify(error.message || "Unable to invite user", "error");
    }
  }

  async function handleRemoveMember(userId, username) {
    const confirmed = window.confirm(
      `Remove ${username} from ${activeCompany?.name || "this company"}?`,
    );
    if (!confirmed) {
      return;
    }

    try {
      await api.removeFromActiveCompany(userId);
      notify(`${username} removed from active company.`, "success");
      loadData();
    } catch (error) {
      notify(error.message || "Unable to remove user", "error");
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

  const applyTeamPreset = useCallback((preset) => {
    setTeamFilterMode(preset.filter);
    setTeamSortKey(preset.sortKey);
    setTeamSortDir(preset.sortDir);
    setTeamSearchTerm(preset.search);
  }, []);

  const resetTeamView = useCallback(() => {
    const defaultPreset = TEAM_VIEW_PRESETS[0];
    applyTeamPreset(defaultPreset);

    if (teamPrefsStorageKey) {
      try {
        localStorage.removeItem(teamPrefsStorageKey);
      } catch {
        // Ignore storage cleanup failures.
      }
    }
  }, [applyTeamPreset, teamPrefsStorageKey]);

  async function handleCreateCompany(event) {
    event.preventDefault();
    if (!canEditOperations) {
      notify(
        "Viewer access is read-only. Company creation is disabled.",
        "info",
      );
      return;
    }
    const trimmedName = newCompanyName.trim();
    if (!trimmedName) {
      notify("Company name is required.", "info");
      return;
    }

    try {
      const created = await api.createCompany({ name: trimmedName });
      setCompanies((prev) => [...prev, created]);
      setNewCompanyName("");
      notify(`Company "${created.name}" created.`, "success");
    } catch (error) {
      notify(error.message || "Unable to create company", "error");
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
      notify("Active company switched.", "success");
      await loadData();
    } catch (error) {
      notify(error.message || "Unable to switch company", "error");
    } finally {
      setSwitchingCompany(false);
    }
  }

  async function handleMarkPaid(invoiceId) {
    if (!canEditOperations) {
      notify("Viewer access is read-only. Mark paid is disabled.", "info");
      return;
    }
    try {
      const ref = `MANUAL-${invoiceId}-${Date.now()}`;
      await api.markInvoicePaid(invoiceId, ref);
      notify("Invoice marked as paid.", "success");
      loadData();
    } catch (error) {
      notify(error.message || "Unable to mark invoice as paid", "error");
    }
  }

  if (authLoading) {
    return (
      <div className={`app-shell theme-${themeMode}`}>
        <section className="panel">
          <h3>Loading</h3>
          <p>Checking session...</p>
        </section>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className={`app-shell theme-${themeMode}`}>
        <header className="hero">
          <p className="eyebrow">AI Invoice Follow-up Automation</p>
          <h1>Secure Access</h1>
          <p>Sign in to access your personal dashboard and protected APIs.</p>
          <button
            type="button"
            className="theme-toggle"
            aria-label="Toggle dark mode"
            aria-pressed={themeMode === "dark"}
            onClick={() =>
              setThemeMode((prev) => (prev === "dark" ? "light" : "dark"))
            }
          >
            Theme: {themeMode === "dark" ? "Dark" : "Light"}
          </button>
        </header>

        {message && <div className="alert">{message}</div>}

        <section className="panel auth-panel">
          <h3>{authMode === "signup" ? "Create Account" : "Login"}</h3>
          <form className="stack-form" onSubmit={handleAuthSubmit}>
            {authMode === "signup" && (
              <input
                placeholder="Username"
                value={authForm.username}
                onChange={(e) =>
                  setAuthForm((prev) => ({ ...prev, username: e.target.value }))
                }
                required
              />
            )}
            <input
              type="email"
              placeholder="Email"
              value={authForm.email}
              onChange={(e) =>
                setAuthForm((prev) => ({ ...prev, email: e.target.value }))
              }
              required
            />
            <input
              type="password"
              placeholder="Password"
              value={authForm.password}
              onChange={(e) =>
                setAuthForm((prev) => ({ ...prev, password: e.target.value }))
              }
              required
              minLength={8}
            />
            {authMode === "login" && (
              <input
                type="text"
                placeholder="OTP Code (if MFA enabled)"
                value={authForm.otp_code}
                onChange={(e) =>
                  setAuthForm((prev) => ({ ...prev, otp_code: e.target.value }))
                }
                minLength={6}
                maxLength={8}
              />
            )}
            <button type="submit">
              {authMode === "signup" ? "Sign Up" : "Login"}
            </button>
          </form>

          <div className="auth-switch">
            <span>
              {authMode === "signup"
                ? "Already have an account?"
                : "Need an account?"}
            </span>
            <button
              type="button"
              className="ghost"
              onClick={() =>
                setAuthMode((prev) => (prev === "signup" ? "login" : "signup"))
              }
            >
              {authMode === "signup" ? "Go to Login" : "Create Account"}
            </button>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className={`app-shell role-${roleKey} theme-${themeMode}`}>
      <header className="hero">
        <p className="eyebrow">AI Invoice Follow-up Automation</p>
        <h1>{audience.heroTitle}</h1>
        <p>{audience.heroSubtitle}</p>
        <button
          type="button"
          className="theme-toggle"
          aria-label="Toggle dark mode"
          aria-pressed={themeMode === "dark"}
          onClick={() =>
            setThemeMode((prev) => (prev === "dark" ? "light" : "dark"))
          }
        >
          Theme: {themeMode === "dark" ? "Dark" : "Light"}
        </button>
        <div
          className="audience-switch"
          role="group"
          aria-label="Audience Profile"
        >
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
          Signed in as {currentUser.username} ({displayRole(currentUser.role)})
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
              disabled={!canEditOperations}
            />
            <button type="submit" disabled={!canEditOperations}>
              Add Company
            </button>
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
        {isAdmin && (
          <button
            className={activeTab === "ops" ? "active" : ""}
            onClick={() => setActiveTab("ops")}
          >
            Ops
          </button>
        )}
        {isAdmin && (
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
              <h2>
                {stats
                  ? `${displayStats.paid_invoices} / ${displayStats.pending_invoices}`
                  : "-"}
              </h2>
              <div className="kpi-spark">
                <span style={{ width: `${kpiVisuals.paidPct}%` }} />
              </div>
              <small>
                {kpiVisuals.paidPct}% paid, {kpiVisuals.pendingPct}% still
                pending
              </small>
            </article>
            <article className="card warning">
              <p>Overdue Invoices</p>
              <h2>{stats ? displayStats.overdue_invoices : "-"}</h2>
              <div className="kpi-spark">
                <span style={{ width: `${kpiVisuals.overduePct}%` }} />
              </div>
              <small>
                {kpiVisuals.overduePct}% of the invoice book is overdue
              </small>
            </article>
            <article className="card info">
              <p>Follow-up Status</p>
              <h2>{stats ? followUpSummary.sentCount : "-"}</h2>
              <div className="followup-status-grid">
                <span className="followup-chip neutral">
                  Drafts {followUpSummary.draftCount}
                </span>
                <span className="followup-chip ok">
                  Sent {followUpSummary.sentCount}
                </span>
                <span className="followup-chip info">
                  Opened {followUpSummary.openedCount}
                </span>
                <span className="followup-chip danger">
                  Failed {followUpSummary.failedCount}
                </span>
              </div>
              <div className="kpi-spark">
                <span style={{ width: `${kpiVisuals.followUpPct}%` }} />
              </div>
              <small>
                {kpiVisuals.followUpPct}% of invoices have entered the follow-up
                pipeline
              </small>
            </article>
          </section>

          <RolePermissionsPanel
            currentUser={currentUser}
            displayRole={displayRole}
            permissionsRoleTab={permissionsRoleTab}
            setPermissionsRoleTab={setPermissionsRoleTab}
            permissionCapabilities={permissionCapabilities}
            permissionsByRole={permissionsByRole}
            rbacRoles={RBAC_ROLES}
          />

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

          <DashboardSnapshotPanels
            displayStats={displayStats}
            kpiVisuals={kpiVisuals}
            followUpSummary={followUpSummary}
          />

          <section className="grid-two">
            <article className="panel">
              <h3>Add Invoice</h3>
              {!canEditOperations && (
                <p className="snapshot-footnote">
                  Viewer role has read-only access. Contact an admin to request
                  Accountant role.
                </p>
              )}
              <form onSubmit={handleCreateInvoice} className="stack-form">
                <input
                  placeholder="Customer Name"
                  value={invoiceForm.customer_name}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({
                      ...prev,
                      customer_name: e.target.value,
                    }))
                  }
                  disabled={!canEditOperations}
                  required
                />
                <input
                  type="email"
                  placeholder="Customer Email"
                  value={invoiceForm.customer_email}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({
                      ...prev,
                      customer_email: e.target.value,
                    }))
                  }
                  disabled={!canEditOperations}
                  required
                />
                <input
                  type="text"
                  placeholder="Customer Phone (optional, E.164 for SMS)"
                  value={invoiceForm.customer_phone}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({
                      ...prev,
                      customer_phone: e.target.value,
                    }))
                  }
                  disabled={!canEditOperations}
                />
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="Amount"
                  value={invoiceForm.amount}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({
                      ...prev,
                      amount: e.target.value,
                    }))
                  }
                  disabled={!canEditOperations}
                  required
                />
                <input
                  type="date"
                  value={invoiceForm.due_date}
                  onChange={(e) =>
                    setInvoiceForm((prev) => ({
                      ...prev,
                      due_date: e.target.value,
                    }))
                  }
                  disabled={!canEditOperations}
                  required
                />
                <button type="submit" disabled={!canEditOperations}>
                  Save Invoice
                </button>
              </form>

              <div className="csv-upload">
                <label htmlFor="invoiceUpload">CSV / Excel Upload</label>
                <input
                  id="invoiceUpload"
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={handleInvoiceUpload}
                  disabled={!canEditOperations}
                />
              </div>
            </article>

            <article className="panel">
              <h3>Generate AI Reminder</h3>
              <select
                value={selectedInvoiceId}
                onChange={(e) => setSelectedInvoiceId(e.target.value)}
              >
                <option value="">Select invoice</option>
                {invoices
                  .filter((inv) => inv.status === "pending")
                  .map((invoice) => (
                    <option key={invoice.id} value={invoice.id}>
                      #{invoice.id} - {invoice.customer_name} ($
                      {invoice.amount.toFixed(2)})
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
                <select
                  value={deliveryProvider}
                  onChange={(e) => setDeliveryProvider(e.target.value)}
                >
                  {DELIVERY_PROVIDERS.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider}
                    </option>
                  ))}
                </select>
              </label>

              <button
                type="button"
                onClick={handleGenerateEmail}
                disabled={!canEditOperations}
              >
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
                              onClick={() =>
                                window.open(
                                  invoice.payment_url,
                                  "_blank",
                                  "noopener,noreferrer",
                                )
                              }
                            >
                              Pay Now
                            </button>
                          )}
                          {invoice.status !== "paid" && (
                            <button
                              type="button"
                              className="ghost"
                              onClick={() => handleMarkPaid(invoice.id)}
                              disabled={!canEditOperations}
                            >
                              Mark Paid
                            </button>
                          )}
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => handleDownloadInvoicePdf(invoice.id)}
                          >
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
                          <button
                            type="button"
                            onClick={() => setEditingEmail(email)}
                          >
                            Preview / Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => handleApprove(email.id)}
                            disabled={!canEditOperations}
                          >
                            Approve + Send
                          </button>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() => handleReject(email.id)}
                            disabled={!canEditOperations}
                          >
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
                      <td>
                        {entry.overdue_rate}% ({entry.overdue_invoices}/
                        {entry.total_invoices})
                      </td>
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
                    <td data-label="Paid / Total">
                      {entry.paid_invoices}/{entry.total_invoices}
                    </td>
                    <td data-label="On-time Rate">
                      {entry.on_time_payment_rate}%
                    </td>
                    <td data-label="Avg Days Late">
                      {entry.average_days_late}
                    </td>
                    <td data-label="Outstanding">
                      ${Number(entry.outstanding_amount || 0).toFixed(2)}
                    </td>
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
              <h2>
                {reportsOverview
                  ? `${reportsOverview.monthly_recovery_rate}%`
                  : "-"}
              </h2>
              <small>
                Paid amount divided by invoiced amount for recent months.
              </small>
            </article>
            <article className="card warning">
              <p>Average Payment Delay</p>
              <h2>
                {reportsOverview
                  ? `${reportsOverview.avg_payment_delay_days} days`
                  : "-"}
              </h2>
              <small>Average days late across paid invoices.</small>
            </article>
            <article className="card success">
              <p>Email Open Rate</p>
              <h2>
                {reportsOverview ? `${reportsOverview.email_open_rate}%` : "-"}
              </h2>
              <small>Share of sent reminders that were opened.</small>
            </article>
            <article className="card">
              <p>Email Click Rate</p>
              <h2>
                {reportsOverview ? `${reportsOverview.email_click_rate}%` : "-"}
              </h2>
              <small>Share of sent reminders with at least one click.</small>
            </article>
          </section>

          <ReportsSection
            reportsOverview={reportsOverview}
            emailAnalytics={emailAnalytics}
          />
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
                    <td data-label="Sent At">
                      {email.sent_at
                        ? new Date(email.sent_at).toLocaleString()
                        : "-"}
                    </td>
                    <td data-label="Delivered At">
                      {email.delivered_at
                        ? new Date(email.delivered_at).toLocaleString()
                        : "-"}
                    </td>
                    <td data-label="Opened At">
                      {email.opened_at
                        ? new Date(email.opened_at).toLocaleString()
                        : "-"}
                    </td>
                    <td data-label="Clicks">{email.click_count ?? 0}</td>
                    <td data-label="Clicked At">
                      {email.clicked_at
                        ? new Date(email.clicked_at).toLocaleString()
                        : "-"}
                    </td>
                    <td data-label="Tone Rationale">
                      {email.tone_rationale || "-"}
                    </td>
                    <td data-label="Failure">{email.failure_reason || "-"}</td>
                    <td data-label="Actions">
                      {(email.status === "failed" ||
                        email.status === "approved") && (
                        <button
                          type="button"
                          onClick={() => handleSendNow(email.id)}
                          disabled={!canEditOperations}
                        >
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
        <IntegrationsSection
          integrationConnectors={integrationConnectors}
          integrationSources={integrationSources}
          handleSyncIntegration={handleSyncIntegration}
          handleDisconnectIntegration={handleDisconnectIntegration}
          handleConnectIntegration={handleConnectIntegration}
          canEditOperations={canEditOperations}
          integrationSource={integrationSource}
          setIntegrationSource={setIntegrationSource}
          integrationCount={integrationCount}
          setIntegrationCount={setIntegrationCount}
          handleImportFromIntegration={handleImportFromIntegration}
          audience={audience}
        />
      )}

      {activeTab === "team" && isAdmin && (
        <TeamSection
          teamForm={teamForm}
          setTeamForm={setTeamForm}
          handleCreateTeamUser={handleCreateTeamUser}
          inviteEmail={inviteEmail}
          setInviteEmail={setInviteEmail}
          handleInviteExistingUser={handleInviteExistingUser}
          teamUsers={teamUsers}
          teamVisibleUsers={teamVisibleUsers}
          teamFilterMode={teamFilterMode}
          setTeamFilterMode={setTeamFilterMode}
          teamSearchTerm={teamSearchTerm}
          setTeamSearchTerm={setTeamSearchTerm}
          teamSearchInputRef={teamSearchInputRef}
          teamSortMarker={teamSortMarker}
          handleTeamSort={handleTeamSort}
          teamSortKey={teamSortKey}
          teamSortDir={teamSortDir}
          TEAM_ROLES={TEAM_ROLES}
          TEAM_VIEW_PRESETS={TEAM_VIEW_PRESETS}
          applyTeamPreset={applyTeamPreset}
          resetTeamView={resetTeamView}
          currentUser={currentUser}
          activeCompany={activeCompany}
          handleRemoveMember={handleRemoveMember}
          audience={audience}
        />
      )}

      {activeTab === "ops" && isAdmin && (
        <OpsSection
          handleRunQueueNow={handleRunQueueNow}
          queueStats={queueStats}
          opsMetrics={opsMetrics}
          queueJobs={queueJobs}
          webhookSimulator={webhookSimulator}
          setWebhookSimulator={setWebhookSimulator}
          handleSimulateTwilioWebhook={handleSimulateTwilioWebhook}
          auditLogs={auditLogs}
          twilioStatuses={TWILIO_STATUSES}
        />
      )}

      {editingEmail && (
        <div className="modal-backdrop" onClick={() => setEditingEmail(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Email Preview</h3>
            <label>
              Subject
              <input
                value={editingEmail.subject}
                onChange={(e) =>
                  setEditingEmail((prev) => ({
                    ...prev,
                    subject: e.target.value,
                  }))
                }
              />
            </label>
            <label>
              Body
              <textarea
                rows={10}
                value={editingEmail.body}
                onChange={(e) =>
                  setEditingEmail((prev) => ({ ...prev, body: e.target.value }))
                }
              />
            </label>
            <div className="actions right">
              <button
                type="button"
                className="ghost"
                onClick={() => setEditingEmail(null)}
              >
                Close
              </button>
              <button type="button" onClick={handleEditSave}>
                Save Changes
              </button>
              <button
                type="button"
                onClick={() => handleApprove(editingEmail.id)}
              >
                Approve + Send
              </button>
            </div>
          </div>
        </div>
      )}

      {loading && <div className="loading-pill">Refreshing data...</div>}

      <div
        className="toast-container"
        role="region"
        aria-live="polite"
        aria-atomic="true"
      >
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            message={toast.message}
            type={toast.type}
            onClose={() =>
              setToasts((prev) => prev.filter((t) => t.id !== toast.id))
            }
          />
        ))}
      </div>
    </div>
  );
}

export default App;
