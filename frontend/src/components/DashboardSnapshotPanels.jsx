export function DashboardSnapshotPanels({
  displayStats,
  kpiVisuals,
  followUpSummary,
}) {
  return (
    <section className="grid-two">
      <article className="panel">
        <h3>Invoice Health Snapshot</h3>
        <div className="stats-grid compact">
          <div className="stat-card neutral">
            <p>Total</p>
            <h2>{displayStats.total_invoices}</h2>
            <small>{kpiVisuals.paidPct}% paid coverage</small>
          </div>
          <div className="stat-card success">
            <p>Paid</p>
            <h2>{displayStats.paid_invoices}</h2>
            <small>{kpiVisuals.paidPct}% of invoices</small>
          </div>
          <div className="stat-card warning">
            <p>Pending</p>
            <h2>{displayStats.pending_invoices}</h2>
            <small>{kpiVisuals.pendingPct}% awaiting payment</small>
          </div>
          <div className="stat-card danger">
            <p>Overdue</p>
            <h2>{displayStats.overdue_invoices}</h2>
            <small>{kpiVisuals.overduePct}% at risk</small>
          </div>
        </div>
      </article>

      <article className="panel">
        <h3>Follow-up Pipeline</h3>
        <div className="stats-grid compact">
          <div className="stat-card info">
            <p>Drafts</p>
            <h2>{followUpSummary.draftCount}</h2>
            <small>Awaiting approval</small>
          </div>
          <div className="stat-card neutral">
            <p>Sent</p>
            <h2>{followUpSummary.sentCount}</h2>
            <small>{kpiVisuals.followUpPct}% follow-up coverage</small>
          </div>
          <div className="stat-card success">
            <p>Opened</p>
            <h2>{followUpSummary.openedCount}</h2>
            <small>Customer engagement signal</small>
          </div>
          <div className="stat-card danger">
            <p>Failed</p>
            <h2>{followUpSummary.failedCount}</h2>
            <small>Needs retry or correction</small>
          </div>
        </div>
      </article>
    </section>
  );
}
