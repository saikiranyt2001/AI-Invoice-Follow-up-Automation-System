import { Line } from "react-chartjs-2";

import { EmptyState } from "./ui";

export function ReportsSection({ reportsOverview, emailAnalytics }) {
  return (
    <section className="panel integration-inner">
      <h3>Recovery & Collection Analytics</h3>

      <section className="panel integration-inner">
        <h3>Email Delivery Feedback Dashboard</h3>
        <section className="cards-grid">
          <article className="card success">
            <p>Open Rate</p>
            <h2>{emailAnalytics ? `${emailAnalytics.open_rate}%` : "-"}</h2>
            <small>Opened emails as a share of sent reminders.</small>
          </article>
          <article className="card info">
            <p>Click Rate</p>
            <h2>{emailAnalytics ? `${emailAnalytics.click_rate}%` : "-"}</h2>
            <small>Clicked reminders as a share of sent reminders.</small>
          </article>
          <article className="card warning">
            <p>Bounce Rate</p>
            <h2>{emailAnalytics ? `${emailAnalytics.bounce_rate}%` : "-"}</h2>
            <small>Bounced deliveries reported by provider webhooks.</small>
          </article>
          <article className="card danger">
            <p>Spam Rate</p>
            <h2>{emailAnalytics ? `${emailAnalytics.spam_rate}%` : "-"}</h2>
            <small>Spam complaints reported by provider webhooks.</small>
          </article>
        </section>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Total</th>
                <th>Sent</th>
                <th>Delivered</th>
                <th>Opened</th>
                <th>Clicked</th>
                <th>Bounced</th>
                <th>Spam</th>
                <th>Failed</th>
              </tr>
            </thead>
            <tbody>
              {!emailAnalytics && (
                <tr>
                  <td colSpan={8}>No email analytics yet</td>
                </tr>
              )}
              {emailAnalytics && (
                <tr>
                  <td>{emailAnalytics.total_messages}</td>
                  <td>{emailAnalytics.sent_messages}</td>
                  <td>{emailAnalytics.delivered_messages}</td>
                  <td>{emailAnalytics.opened_messages}</td>
                  <td>{emailAnalytics.clicked_messages}</td>
                  <td>{emailAnalytics.bounced_messages}</td>
                  <td>{emailAnalytics.spam_reported_messages}</td>
                  <td>{emailAnalytics.failed_messages}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid-two">
        <article className="panel integration-inner">
          <h3>Monthly Recovery Trend</h3>
          {reportsOverview?.monthly_recovery?.length > 0 ? (
            <div className="chart-container">
              <Line
                data={{
                  labels: reportsOverview.monthly_recovery.map((r) => r.month),
                  datasets: [
                    {
                      label: "Invoiced",
                      data: reportsOverview.monthly_recovery.map(
                        (r) => r.invoiced_amount,
                      ),
                      borderColor: "rgba(35, 92, 170, 1)",
                      backgroundColor: "rgba(35, 92, 170, 0.15)",
                      tension: 0.3,
                    },
                    {
                      label: "Recovered",
                      data: reportsOverview.monthly_recovery.map(
                        (r) => r.paid_amount,
                      ),
                      borderColor: "rgba(28, 138, 79, 1)",
                      backgroundColor: "rgba(28, 138, 79, 0.2)",
                      tension: 0.3,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: true,
                  plugins: { legend: { position: "bottom" } },
                }}
              />
            </div>
          ) : (
            <EmptyState
              tone="insights"
              title="No recovery trend yet"
              description="Recovery analytics appear after invoice and payment activity."
            />
          )}
        </article>

        <article className="panel integration-inner">
          <h3>Monthly Cashflow Trend</h3>
          {reportsOverview?.monthly_cashflow?.length > 0 ? (
            <div className="chart-container">
              <Line
                data={{
                  labels: reportsOverview.monthly_cashflow.map((r) => r.month),
                  datasets: [
                    {
                      label: "Cash In",
                      data: reportsOverview.monthly_cashflow.map(
                        (r) => r.cash_in,
                      ),
                      borderColor: "rgba(28, 138, 79, 1)",
                      backgroundColor: "rgba(28, 138, 79, 0.2)",
                      tension: 0.3,
                    },
                    {
                      label: "Outstanding",
                      data: reportsOverview.monthly_cashflow.map(
                        (r) => r.cash_outstanding,
                      ),
                      borderColor: "rgba(193, 106, 47, 1)",
                      backgroundColor: "rgba(193, 106, 47, 0.2)",
                      tension: 0.3,
                    },
                    {
                      label: "Net Cashflow",
                      data: reportsOverview.monthly_cashflow.map(
                        (r) => r.net_cashflow,
                      ),
                      borderColor: "rgba(35, 92, 170, 1)",
                      backgroundColor: "rgba(35, 92, 170, 0.15)",
                      tension: 0.3,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: true,
                  plugins: { legend: { position: "bottom" } },
                }}
              />
            </div>
          ) : (
            <EmptyState
              tone="insights"
              title="No cashflow trend yet"
              description="Cashflow trend appears after invoice and payment activity."
            />
          )}
        </article>
      </div>

      <div className="grid-two">
        <article className="panel integration-inner">
          <h3>Top Late Payers</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Email</th>
                  <th>Overdue</th>
                  <th>Total</th>
                  <th>Rate</th>
                </tr>
              </thead>
              <tbody>
                {(!reportsOverview ||
                  !reportsOverview.top_late_payers?.length) && (
                  <tr>
                    <td colSpan={5}>No repeat late payer data yet</td>
                  </tr>
                )}
                {reportsOverview?.top_late_payers?.map((row) => (
                  <tr key={`${row.customer_email}-${row.customer_name}`}>
                    <td>{row.customer_name}</td>
                    <td>{row.customer_email}</td>
                    <td>{row.overdue_invoices}</td>
                    <td>{row.total_invoices}</td>
                    <td>{row.overdue_rate}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="panel integration-inner">
          <h3>Monthly Cashflow Table</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Cash In</th>
                  <th>Outstanding</th>
                  <th>Net</th>
                </tr>
              </thead>
              <tbody>
                {(!reportsOverview ||
                  !reportsOverview.monthly_cashflow?.length) && (
                  <tr>
                    <td colSpan={4}>No cashflow rows yet</td>
                  </tr>
                )}
                {reportsOverview?.monthly_cashflow?.map((row) => (
                  <tr key={row.month}>
                    <td>{row.month}</td>
                    <td>${Number(row.cash_in || 0).toFixed(2)}</td>
                    <td>${Number(row.cash_outstanding || 0).toFixed(2)}</td>
                    <td>${Number(row.net_cashflow || 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  );
}
