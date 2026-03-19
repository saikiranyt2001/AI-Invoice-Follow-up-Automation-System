export function StatusBadge({ label, variant }) {
  return <span className={`badge ${variant}`}>{label}</span>;
}

export function TrendMiniBars({ points }) {
  if (!points?.length) {
    return <span className="trend-empty">No trend yet</span>;
  }

  return (
    <div
      className="trend-mini"
      title={points.map((p) => `${p.month}: ${p.risk_score}`).join(" | ")}
    >
      {points.map((point) => (
        <span
          key={`${point.month}-${point.risk_score}`}
          style={{ height: `${Math.max(8, point.risk_score)}%` }}
        />
      ))}
    </div>
  );
}

export function EmptyState({ title, description, tone = "default" }) {
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

export function Toast({ message, type = "success", onClose }) {
  return (
    <div
      className={`toast toast-${type}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="toast-icon">
        {type === "success" ? "✓" : type === "error" ? "✕" : "ℹ"}
      </span>
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
