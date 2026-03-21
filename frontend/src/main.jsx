import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      errorMessage: error?.message || "Unexpected frontend error",
    };
  }

  componentDidCatch(error, info) {
    console.error("App render failure:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="app-shell">
          <section className="panel">
            <h3>Frontend Error</h3>
            <p>The UI hit a runtime error instead of rendering.</p>
            <p>
              <strong>Details:</strong> {this.state.errorMessage}
            </p>
          </section>
        </div>
      );
    }

    return this.props.children;
  }
}

const root = createRoot(document.getElementById("root"));

if (import.meta.env.DEV) {
  import("@axe-core/react")
    .then(({ default: axe }) => {
      axe(React, createRoot, 1000);
    })
    .catch(() => {
      // Ignore optional accessibility runtime initialization failures.
    })
    .finally(() => {
      root.render(
        <React.StrictMode>
          <AppErrorBoundary>
            <App />
          </AppErrorBoundary>
        </React.StrictMode>,
      );
    });
} else {
  root.render(
    <React.StrictMode>
      <AppErrorBoundary>
        <App />
      </AppErrorBoundary>
    </React.StrictMode>,
  );
}
