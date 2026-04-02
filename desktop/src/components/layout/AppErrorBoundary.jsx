import React from "react";

function formatErrorMessage(error) {
  if (!error) {
    return "Unknown error";
  }
  if (error instanceof Error) {
    return error.stack || error.message || error.name || "Unknown error";
  }
  if (typeof error === "string") {
    return error;
  }
  try {
    return JSON.stringify(error, null, 2);
  } catch (_stringifyError) {
    return String(error);
  }
}

function AppCrashScreen({ error }) {
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
        <p style={{ margin: "0 0 16px", color: "var(--text-muted)" }}>
          The app stopped rendering because an uncaught exception occurred. The error details are shown below so we can fix the underlying issue.
        </p>
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
          {formatErrorMessage(error)}
        </pre>
      </section>
    </main>
  );
}

export class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    this.props?.onError?.(error);
  }

  render() {
    if (this.state.error) {
      return <AppCrashScreen error={this.state.error} />;
    }
    return this.props.children;
  }
}
