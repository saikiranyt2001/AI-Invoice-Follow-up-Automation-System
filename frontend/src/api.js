const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000";
const TOKEN_KEY = "invoice_auth_token";

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

async function request(path, options = {}) {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });

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
  me: () => request("/auth/me"),
  getStats: () => request("/dashboard/stats"),
  getInvoices: () => request("/invoices"),
  getOverdue: () => request("/overdue"),
  createInvoice: (payload) =>
    request("/invoices", { method: "POST", body: JSON.stringify(payload) }),
  uploadCsv: async (file) => {
    const token = getAuthToken();
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE}/invoices/upload-csv`, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });

    if (!response.ok) {
      let detail = "CSV upload failed";
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
  rejectEmail: (id) => request(`/emails/${id}/reject`, { method: "POST" }),
  getEmails: () => request("/emails"),
  getLatePayerInsights: () => request("/insights/late-payers"),
  getTeamUsers: () => request("/team/users"),
  createTeamUser: (payload) => request("/team/users", { method: "POST", body: JSON.stringify(payload) }),
  getIntegrationSources: () => request("/integrations/sources"),
  importIntegrationInvoices: (payload) =>
    request("/integrations/import-invoices", { method: "POST", body: JSON.stringify(payload) }),
};
