export function OpsSection({
  handleRunQueueNow,
  queueStats,
  opsMetrics,
  queueJobs,
  webhookSimulator,
  setWebhookSimulator,
  handleSimulateTwilioWebhook,
  auditLogs,
  twilioStatuses,
}) {
  return (
    <section className="panel">
      <h3>Ops Console</h3>
      <div className="actions">
        <button type="button" onClick={handleRunQueueNow}>
          Run Queue Now
        </button>
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
                    <td>
                      {job.attempts}/{job.max_attempts}
                    </td>
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
              onChange={(e) =>
                setWebhookSimulator((prev) => ({
                  ...prev,
                  MessageSid: e.target.value,
                }))
              }
              placeholder="SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
            />
          </label>
          <label>
            Message Status
            <select
              value={webhookSimulator.MessageStatus}
              onChange={(e) =>
                setWebhookSimulator((prev) => ({
                  ...prev,
                  MessageStatus: e.target.value,
                }))
              }
            >
              {twilioStatuses.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
          <label>
            To
            <input
              type="text"
              value={webhookSimulator.To}
              onChange={(e) =>
                setWebhookSimulator((prev) => ({ ...prev, To: e.target.value }))
              }
              placeholder="+14155552671"
            />
          </label>
          <label>
            From
            <input
              type="text"
              value={webhookSimulator.From}
              onChange={(e) =>
                setWebhookSimulator((prev) => ({
                  ...prev,
                  From: e.target.value,
                }))
              }
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
                  <td>
                    {log.entity_type} #{log.entity_id || "-"}
                  </td>
                  <td>{log.user_id || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
