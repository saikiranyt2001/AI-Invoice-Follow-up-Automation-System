import { useEffect, useMemo, useState } from "react";
import { api, getAuthToken, setAuthToken } from "./api";

const TONES = ["friendly", "professional", "strict"];

const initialInvoiceForm = {
  customer_name: "",
  customer_email: "",
  amount: "",
  due_date: "",
};

const initialAuthForm = {
  username: "",
  email: "",
  password: "",
};

const initialTeamForm = {
  username: "",
  email: "",
  password: "",
  role: "team",
};

function StatusBadge({ label, variant }) {
  return <span className={`badge ${variant}`}>{label}</span>;
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
  const [teamUsers, setTeamUsers] = useState([]);
  const [integrationSources, setIntegrationSources] = useState([]);
  const [invoiceForm, setInvoiceForm] = useState(initialInvoiceForm);
  const [teamForm, setTeamForm] = useState(initialTeamForm);
  const [integrationSource, setIntegrationSource] = useState("fake_api");
  const [integrationCount, setIntegrationCount] = useState(5);
  const [selectedTone, setSelectedTone] = useState("professional");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [activeTab, setActiveTab] = useState("dashboard");
  const [editingEmail, setEditingEmail] = useState(null);

  const overdueIds = useMemo(() => new Set(overdue.map((item) => item.id)), [overdue]);

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
      const [statsData, invoiceData, overdueData, pendingData, allEmails, insightsData, sourceData] = await Promise.all([
        api.getStats(),
        api.getInvoices(),
        api.getOverdue(),
        api.getPendingApprovals(),
        api.getEmails(),
        api.getLatePayerInsights(),
        api.getIntegrationSources(),
      ]);

      setStats(statsData);
      setInvoices(invoiceData);
      setOverdue(overdueData);
      setPendingApprovals(pendingData);
      setEmailHistory(allEmails);
      setLatePayerInsights(insightsData);
      setIntegrationSources(sourceData.sources || []);

      if (currentUser?.role === "admin") {
        try {
          const users = await api.getTeamUsers();
          setTeamUsers(users);
        } catch {
          setTeamUsers([]);
        }
      } else {
        setTeamUsers([]);
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
            };

      const response = authMode === "signup" ? await api.signup(payload) : await api.login(payload);
      setAuthToken(response.access_token);
      setCurrentUser(response.user);
      setAuthForm(initialAuthForm);
      setMessage(`Welcome, ${response.user.username}.`);
    } catch (error) {
      setMessage(error.message || "Authentication failed");
    }
  }

  function handleLogout() {
    setAuthToken("");
    setCurrentUser(null);
    setStats(null);
    setInvoices([]);
    setOverdue([]);
    setPendingApprovals([]);
    setEmailHistory([]);
    setLatePayerInsights([]);
    setMessage("Logged out.");
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

  async function handleCsvUpload(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const created = await api.uploadCsv(file);
      setMessage(`Uploaded ${created.length} invoices from CSV.`);
      loadData();
    } catch (error) {
      setMessage(error.message || "CSV upload failed");
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
      await api.generateEmail({
        invoice_id: Number(selectedInvoiceId),
        tone: selectedTone,
      });
      setMessage("Email draft generated and moved to pending approval.");
      loadData();
    } catch (error) {
      setMessage(error.message || "Failed to generate email");
    }
  }

  async function handleApprove(id) {
    try {
      await api.approveEmail(id, "smtp");
      setMessage("Email approved and sent.");
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
    <div className="app-shell">
      <header className="hero">
        <p className="eyebrow">AI Invoice Follow-up Automation</p>
        <h1>Cashflow Command Center</h1>
        <p>
          Detect overdue invoices, generate payment reminders, route through approval, and
          track delivery status in one place.
        </p>
        <p className="signed-in-user">
          Signed in as {currentUser.username} ({currentUser.role})
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
              <h2>{stats?.total_invoices ?? "-"}</h2>
            </article>
            <article className="card warning">
              <p>Overdue Invoices</p>
              <h2>{stats?.overdue_invoices ?? "-"}</h2>
            </article>
            <article className="card success">
              <p>Emails Sent</p>
              <h2>{stats?.emails_sent ?? "-"}</h2>
            </article>
            <article className="card info">
              <p>Pending Approvals</p>
              <h2>{stats?.pending_approvals ?? "-"}</h2>
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
                <label htmlFor="csvUpload">CSV Upload</label>
                <input id="csvUpload" type="file" accept=".csv" onChange={handleCsvUpload} />
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
                  >
                    {tone}
                  </button>
                ))}
              </div>

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
                  </tr>
                </thead>
                <tbody>
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
                      <td colSpan={5}>No pending approvals.</td>
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
                      <td colSpan={5}>No risky patterns yet.</td>
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

      {activeTab === "history" && (
        <section className="panel">
          <h3>Email History</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email ID</th>
                  <th>Invoice ID</th>
                  <th>Status</th>
                  <th>Tone</th>
                  <th>Sent At</th>
                  <th>Failure</th>
                </tr>
              </thead>
              <tbody>
                {emailHistory.map((email) => (
                  <tr key={email.id}>
                    <td>{email.id}</td>
                    <td>{email.invoice_id}</td>
                    <td>{email.status}</td>
                    <td>{email.tone}</td>
                    <td>{email.sent_at ? new Date(email.sent_at).toLocaleString() : "-"}</td>
                    <td>{email.failure_reason || "-"}</td>
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
                  <option value="team">team</option>
                  <option value="admin">admin</option>
                </select>
                <button type="submit">Create User</button>
              </form>
            </article>

            <article className="panel team-inner">
              <h3>Users</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Username</th>
                      <th>Email</th>
                      <th>Role</th>
                    </tr>
                  </thead>
                  <tbody>
                    {teamUsers.map((user) => (
                      <tr key={user.id}>
                        <td>{user.id}</td>
                        <td>{user.username}</td>
                        <td>{user.email}</td>
                        <td>{user.role}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>
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
    </div>
  );
}

export default App;
