import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

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
          <App />
        </React.StrictMode>,
      );
    });
} else {
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}
