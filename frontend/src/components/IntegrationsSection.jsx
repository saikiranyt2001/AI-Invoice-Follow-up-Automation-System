import { EmptyState, StatusBadge } from "./ui";

export function IntegrationsSection({
  integrationConnectors,
  integrationSources,
  handleSyncIntegration,
  handleDisconnectIntegration,
  handleConnectIntegration,
  canEditOperations,
  integrationSource,
  setIntegrationSource,
  integrationCount,
  setIntegrationCount,
  handleImportFromIntegration,
  audience,
}) {
  return (
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
                    <StatusBadge
                      label={connector.connected ? "Connected" : "Disconnected"}
                      variant={connector.connected ? "ok" : "neutral"}
                    />
                  </td>
                  <td>{connector.mode}</td>
                  <td>
                    {connector.last_synced_at
                      ? new Date(connector.last_synced_at).toLocaleString()
                      : "-"}
                  </td>
                  <td>
                    <div className="actions">
                      {connector.connected ? (
                        <>
                          <button
                            type="button"
                            onClick={() =>
                              handleSyncIntegration(connector.provider)
                            }
                            disabled={!canEditOperations}
                          >
                            Sync Invoices
                          </button>
                          <button
                            type="button"
                            className="ghost"
                            onClick={() =>
                              handleDisconnectIntegration(connector.provider)
                            }
                            disabled={!canEditOperations}
                          >
                            Disconnect
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() =>
                            handleConnectIntegration(connector.provider)
                          }
                          disabled={!canEditOperations}
                        >
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
            <select
              value={integrationSource}
              onChange={(e) => setIntegrationSource(e.target.value)}
              disabled={!canEditOperations}
            >
              <option value="fake_api">fake_api</option>
              <option value="xero">xero</option>
              <option value="quickbooks">quickbooks</option>
              <option value="zoho_books">zoho_books</option>
              <option value="tally">tally</option>
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
              disabled={!canEditOperations}
            />
          </label>
          <button
            type="button"
            onClick={handleImportFromIntegration}
            disabled={!canEditOperations}
          >
            Import Invoices
          </button>
        </article>
      </div>
    </section>
  );
}
