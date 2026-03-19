const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const TOKEN_KEY = "invoice_auth_token";
const REFRESH_TOKEN_KEY = "invoice_refresh_token";

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setAuthToken(token) {
  if (!token) {
    localStorage.removeItem(TOKEN_KEY);
    return;
  }
  localStorage.setItem(TOKEN_KEY, token);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY) || "";
}

export function setRefreshToken(token) {
  if (!token) {
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    return;
  }
  localStorage.setItem(REFRESH_TOKEN_KEY, token);
}

async function request(path, options = {}) {
  let token = getAuthToken();
  let response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

  if (response.status === 401 && path !== "/auth/login" && path !== "/auth/signup" && path !== "/auth/refresh") {
    const refresh = getRefreshToken();
    if (refresh) {
      const refreshResponse = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (refreshResponse.ok) {
        const refreshed = await refreshResponse.json();
        setAuthToken(refreshed.access_token || "");
        setRefreshToken(refreshed.refresh_token || "");
        token = getAuthToken();
        response = await fetch(`${API_BASE}${path}`, {
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(options.headers || {}),
          },
          ...options,
        });
      }
    }
  }

  if (!response.ok) {
    let detail = "Request failed";
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Ignore JSON parse failures and use fallback message.
    }
    throw new Error(detail);
  }

  return response.json();
}

export const api = {
  signup: (payload) => request("/auth/signup", { method: "POST", body: JSON.stringify(payload) }),
  login: (payload) => request("/auth/login", { method: "POST", body: JSON.stringify(payload) }),
  refresh: (refresh_token) => request("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token }) }),
  logout: (refresh_token) => request("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token }) }),
  logoutAll: () => request("/auth/logout-all", { method: "POST", body: JSON.stringify({}) }),
  setupMfa: () => request("/auth/mfa/setup", { method: "POST", body: JSON.stringify({}) }),
  enableMfa: (otp_code) => request("/auth/mfa/enable", { method: "POST", body: JSON.stringify({ otp_code }) }),
  disableMfa: (otp_code) => request("/auth/mfa/disable", { method: "POST", body: JSON.stringify({ otp_code }) }),
  me: () => request("/auth/me"),
  getStats: () => request("/dashboard/stats"),
  getCompanies: () => request("/companies"),
  createCompany: (payload) => request("/companies", { method: "POST", body: JSON.stringify(payload) }),
  switchCompany: (company_id) =>
    request("/companies/switch", { method: "POST", body: JSON.stringify({ company_id }) }),
  inviteToActiveCompany: (email) =>
    request("/companies/active/invite", { method: "POST", body: JSON.stringify({ email }) }),
  removeFromActiveCompany: (user_id) =>
    request("/companies/active/remove-member", { method: "POST", body: JSON.stringify({ user_id }) }),
  getInvoices: () => request("/invoices"),
  getOverdue: () => request("/overdue"),
  createInvoice: (payload) =>
    request("/invoices", { method: "POST", body: JSON.stringify(payload) }),
  downloadInvoicePdf: async (id) => {
    const token = getAuthToken();
    const response = await fetch(`${API_BASE}/invoices/${id}/pdf`, {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!response.ok) {
      let detail = "Invoice PDF download failed";
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        // Ignore JSON parse failures and use fallback message.
      }
      throw new Error(detail);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `invoice_${id}.pdf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.URL.revokeObjectURL(url);
  },
  markInvoicePaid: (id, payment_reference) =>
    request(`/invoices/${id}/mark-paid`, {
      method: "POST",
      body: JSON.stringify({ payment_reference }),
    }),
  uploadInvoicesFile: async (file) => {
    const token = getAuthToken();
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE}/invoices/upload`, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });

    if (!response.ok) {
      let detail = "Invoice upload failed";
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch {
        // Ignore JSON parse failures and use fallback message.
      }
      throw new Error(detail);
    }

    return response.json();
  },
  generateEmail: (payload) =>
    request("/generate-email", { method: "POST", body: JSON.stringify(payload) }),
  getPendingApprovals: () => request("/emails/pending-approvals"),
  editEmail: (id, payload) =>
    request(`/emails/${id}/edit`, { method: "PATCH", body: JSON.stringify(payload) }),
  approveEmail: (id, provider = "smtp") =>
    request(`/emails/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),
  sendEmail: (id, provider = "smtp") =>
    request(`/emails/${id}/send`, {
      method: "POST",
      body: JSON.stringify({ provider }),
    }),
  rejectEmail: (id) => request(`/emails/${id}/reject`, { method: "POST" }),
  getEmails: () => request("/emails"),
  getAuditLogs: (limit = 50) => request(`/audit/logs?limit=${encodeURIComponent(limit)}`),
  getQueueJobs: (limit = 100, status = "") =>
    request(`/jobs/queue?limit=${encodeURIComponent(limit)}${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  getQueueStats: () => request("/jobs/stats"),
  runQueueNow: (limit = 25) => request(`/jobs/run-now?limit=${encodeURIComponent(limit)}`, { method: "POST" }),
  getOpsMetrics: () => request("/ops/metrics"),
  simulateTwilioStatus: (payload) => request("/webhooks/twilio/status", { method: "POST", body: JSON.stringify(payload) }),
  getLatePayerInsights: () => request("/insights/late-payers"),
  getReportsOverview: () => request("/reports/overview"),
  getCustomerHistory: () => request("/customers/history"),
  getTeamUsers: () => request("/team/users"),
  createTeamUser: (payload) => request("/team/users", { method: "POST", body: JSON.stringify(payload) }),
  getIntegrationSources: () => request("/integrations/sources"),
  getIntegrationConnectors: () => request("/integrations/connectors"),
  startIntegrationOAuth: (provider) => request(`/integrations/${provider}/oauth/start`, { method: "POST" }),
  completeIntegrationOAuth: (provider, code, state) =>
    request(`/integrations/${provider}/oauth/callback`, { method: "POST", body: JSON.stringify({ code, state }) }),
  disconnectIntegration: (provider) => request(`/integrations/${provider}/disconnect`, { method: "POST" }),
  syncIntegrationInvoices: (provider, count = 5) =>
    request(`/integrations/${provider}/sync-invoices`, { method: "POST", body: JSON.stringify({ count }) }),
  importIntegrationInvoices: (payload) =>
    request("/integrations/import-invoices", { method: "POST", body: JSON.stringify(payload) }),
};
