import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Execution } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useT } from "../lib/i18n";
import { SignInBar } from "./SignInBar";

/**
 * Executions = observability over the async pipeline runs the backend already
 * records (status, timings, cost/latency inside `output`, per-step trace, errors).
 * Read-only surface over `GET /v1/executions` and `/executions/{id}`; tenant-scoped.
 */
export function ExecutionsPage() {
  const t = useT();
  const { token } = useAuth();
  if (!token) {
    return (
      <div className="space-y-4">
        <SignInBar />
        <p className="text-sm text-subtle">{t("execs.signin.hint")}</p>
      </div>
    );
  }
  return <ExecutionsAuthed token={token} />;
}

function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (s === "succeeded" || s === "done" || s === "completed")
    return "border-ok/40 bg-ok/10 text-ok";
  if (s === "failed" || s === "error") return "border-danger/40 bg-danger/10 text-danger";
  return "border-warn/40 bg-warn/10 text-warn"; // pending / running / queued
}

function isInFlight(status: string): boolean {
  const s = status.toLowerCase();
  return s === "pending" || s === "running" || s === "queued";
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={"rounded-md border px-2 py-0.5 text-xs font-medium " + statusTone(status)}>
      {status}
    </span>
  );
}

function ExecutionsAuthed({ token }: { token: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="space-y-4">
      <SignInBar />
      {selected ? (
        <ExecutionDetail token={token} id={selected} onBack={() => setSelected(null)} />
      ) : (
        <ExecutionList token={token} onOpen={setSelected} />
      )}
    </div>
  );
}

function ExecutionList({ token, onOpen }: { token: string; onOpen: (id: string) => void }) {
  const t = useT();
  const q = useQuery({ queryKey: ["executions"], queryFn: () => api.listExecutions(token) });

  if (q.isError)
    return (
      <p role="alert" className="text-sm text-danger">
        {(q.error as Error).message}
      </p>
    );
  if (!q.data) return <p className="text-sm text-muted">{t("execs.loading")}</p>;
  if (q.data.length === 0) return <p className="text-sm text-muted">{t("execs.empty")}</p>;

  return (
    <ul className="space-y-2">
      {q.data.map((e) => (
        <li key={e.id}>
          <button
            type="button"
            onClick={() => onOpen(e.id)}
            className="w-full rounded-xl border border-line bg-surface p-4 text-left transition hover:border-accent/50"
          >
            <div className="flex items-center justify-between gap-3">
              <StatusBadge status={e.status} />
              <code className="truncate text-xs text-subtle">{e.id}</code>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              <span>{new Date(e.created_at).toLocaleString()}</span>
              <span>
                {t("execs.version")}:{" "}
                <code className="text-subtle">{e.prompt_version_id ?? t("execs.raw")}</code>
              </span>
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}

function ExecutionDetail({
  token,
  id,
  onBack,
}: {
  token: string;
  id: string;
  onBack: () => void;
}) {
  const t = useT();
  const q = useQuery({
    queryKey: ["execution", id],
    queryFn: () => api.getExecution(token, id),
    // Poll while the worker is still running so status/output update live.
    refetchInterval: (query) => {
      const data = query.state.data as Execution | undefined;
      return data && isInFlight(data.status) ? 2000 : false;
    },
  });

  return (
    <div className="space-y-4">
      <button type="button" onClick={onBack} className="text-sm text-muted hover:text-ink">
        {t("execs.back")}
      </button>

      {q.isError && (
        <p role="alert" className="text-sm text-danger">
          {(q.error as Error).message}
        </p>
      )}
      {q.data && <ExecutionCard e={q.data} />}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-subtle">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{value}</dd>
    </div>
  );
}

function ExecutionCard({ e }: { e: Execution }) {
  const t = useT();
  const fmt = (v: string | null) => (v ? new Date(v).toLocaleString() : "—");
  return (
    <div className="space-y-4 rounded-2xl border border-line bg-surface p-5 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <StatusBadge status={e.status} />
        {isInFlight(e.status) && (
          <span className="inline-flex items-center gap-2 text-xs text-muted">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" />
            {t("execs.live")}
          </span>
        )}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
        <Field label={t("execs.version")} value={e.prompt_version_id ?? t("execs.raw")} />
        <Field label={t("execs.created")} value={fmt(e.created_at)} />
        <Field label={t("execs.started")} value={fmt(e.started_at)} />
        <Field label={t("execs.finished")} value={fmt(e.finished_at)} />
      </dl>

      {e.error && (
        <div
          role="alert"
          className="rounded-xl border border-danger/40 bg-danger/10 p-3 text-sm text-danger"
        >
          <p className="font-semibold">{t("execs.error")}</p>
          <p className="mt-1 break-words">{e.error}</p>
        </div>
      )}

      {e.output && (
        <details open className="rounded-xl border border-line bg-raised p-3">
          <summary className="cursor-pointer text-sm font-semibold text-muted">
            {t("execs.output")}
          </summary>
          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs text-ink">
            {JSON.stringify(e.output, null, 2)}
          </pre>
        </details>
      )}

      {e.input && (
        <details className="rounded-xl border border-line bg-raised p-3">
          <summary className="cursor-pointer text-sm font-semibold text-muted">
            {t("execs.input")}
          </summary>
          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-muted">
            {JSON.stringify(e.input, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
