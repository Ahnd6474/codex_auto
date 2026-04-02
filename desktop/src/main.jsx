import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { I18nProvider } from "./i18n";
import { ensureLanguageCatalog, resolveInitialLanguage } from "./locale";
import { AppErrorBoundary } from "./components/layout/AppErrorBoundary";
import "./styles.css";

const initialLanguage = resolveInitialLanguage();

function FatalErrorBridge({ children }) {
  const [fatalError, setFatalError] = useState(null);

  useEffect(() => {
    function handleError(event) {
      const error = event?.error || new Error(event?.message || "Unknown runtime error");
      setFatalError(error);
    }

    function handleRejection(event) {
      setFatalError(event?.reason || new Error("Unhandled promise rejection"));
    }

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);
    return () => {
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);

  if (fatalError) {
    return (
      <main
        style={{
          alignItems: "center",
          background: "var(--bg-base)",
          color: "var(--text)",
          display: "flex",
          fontFamily: 'Segoe UI, sans-serif',
          justifyContent: "center",
          minHeight: "100vh",
          padding: "32px",
        }}
      >
        <section
          style={{
            background: "var(--bg-panel)",
            border: "1px solid var(--state-danger-border)",
            borderRadius: "10px",
            boxShadow: "var(--shadow-elevated)",
            maxWidth: "960px",
            padding: "20px 24px",
            width: "100%",
          }}
        >
          <h1 style={{ margin: "0 0 12px", fontSize: "20px" }}>The desktop UI hit an error</h1>
          <pre
            style={{
              background: "var(--bg-base)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              color: "var(--text)",
              fontSize: "12px",
              lineHeight: 1.5,
              margin: 0,
              overflow: "auto",
              padding: "16px",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {String(fatalError?.stack || fatalError?.message || fatalError || "Unknown runtime error")}
          </pre>
        </section>
      </main>
    );
  }

  return (
    <AppErrorBoundary onError={setFatalError}>
      {children}
    </AppErrorBoundary>
  );
}

function renderApp() {
  ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
      <FatalErrorBridge>
        <I18nProvider initialLanguage={initialLanguage}>
          <App />
        </I18nProvider>
      </FatalErrorBridge>
    </React.StrictMode>,
  );
}

void ensureLanguageCatalog(initialLanguage)
  .catch(() => null)
  .finally(() => {
    renderApp();
  });
