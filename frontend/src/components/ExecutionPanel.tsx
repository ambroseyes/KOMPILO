import { useState } from "react";
import { api, type ExecuteResponse } from "../lib/api";
import { useExecutionStream } from "../hooks/useExecutionStream";
import { useT } from "../lib/i18n";

/**
 * Advanced: run the task through /v1/execute (authenticated) and stream the result
 * live. Requires an access token (the public compile screen is unauthenticated).
 */
export function ExecutionPanel({ task }: { task: string }) {
  const t = useT();
  const [token, setToken] = useState("");
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [exec, setExec] = useState<ExecuteResponse | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const stream = useExecutionStream(executionId, token.trim() || null);

  async function run() {
    setStarting(true);
    setStartError(null);
    setExec(null);
    setExecutionId(null);
    try {
      const res = await api.execute({ task: task.trim() }, token.trim());
      setExec(res);
      if (res.execution_id) setExecutionId(res.execution_id);
    } catch (e) {
      setStartError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  const canRun = Boolean(task.trim()) && Boolean(token.trim()) && !starting;

  return (
    <div className="mt-3 space-y-3 text-sm">
      <p className="text-muted">{t("exec.intro")}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="access_token"
          aria-label={t("exec.token.aria")}
          className="flex-1 rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
        />
        <button
          type="button"
          onClick={run}
          disabled={!canRun}
          className="rounded-lg bg-accent px-4 py-2 font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {starting ? t("exec.starting") : t("exec.run")}
        </button>
      </div>

      {startError && (
        <p role="alert" className="text-danger">
          {startError}
        </p>
      )}

      {exec?.status === "needs_clarification" && (
        <p className="text-warn">{t("exec.needsClarification")}</p>
      )}

      {executionId && (
        <div className="rounded-xl border border-line bg-raised p-3">
          <div className="mb-2 flex items-center gap-2 text-xs text-muted">
            <span
              className={
                "h-2 w-2 rounded-full " +
                (stream.status === "streaming"
                  ? "animate-pulse bg-accent"
                  : stream.status === "done"
                    ? "bg-ok"
                    : stream.status === "error"
                      ? "bg-danger"
                      : "bg-subtle")
              }
            />
            {t("exec.stream")} {stream.status}
            {stream.steps.length > 0 && <> · {t("exec.steps", { n: stream.steps.length })}</>}
          </div>
          <pre
            aria-live="polite"
            className="max-h-72 overflow-auto whitespace-pre-wrap font-mono text-sm text-ink"
          >
            {stream.text || "…"}
          </pre>
          {stream.error && <p className="mt-2 text-danger">{stream.error}</p>}
        </div>
      )}

      {exec?.metadata && (
        <p className="text-xs text-muted">
          {t("result.cost")} <span className="text-ok">{t("exec.cost.real")}</span> ~$
          {exec.metadata.actual_cost.cost_usd.toFixed(6)} ·{" "}
          {exec.metadata.cached ? t("exec.cached") : t("exec.executed")} ·{" "}
          {exec.metadata.provider_is_real ? t("exec.model.real") : t("exec.model.stub")}
          {exec.verification && (
            <>
              {" "}
              · {t("exec.verification")}{" "}
              {exec.verification.valid ? t("exec.conform") : exec.verification.summary}
            </>
          )}
        </p>
      )}

      {exec && exec.trace.length > 0 && (
        <div className="flex flex-wrap gap-1 text-[11px]">
          {exec.trace.map((s, i) => (
            <span
              key={`${s.stage}-${i}`}
              className={
                "rounded border px-1.5 py-0.5 " +
                (s.status === "ok"
                  ? "border-ok/30 bg-ok/10 text-ok"
                  : "border-warn/30 bg-warn/10 text-warn")
              }
            >
              {s.stage}
            </span>
          ))}
        </div>
      )}

      {exec?.evaluation && (
        <div className="rounded-xl border border-line bg-raised p-3 text-xs">
          <p className="text-muted">
            {t("exec.eval")}{" "}
            <span className="text-subtle">{t("exec.eval.measured", { method: exec.evaluation.method })}</span>{" "}
            : {t("exec.eval.score")}{" "}
            <span className="font-semibold text-ink">{exec.evaluation.score.toFixed(2)}</span> ·{" "}
            {exec.evaluation.passed ? t("exec.conform") : t("exec.eval.notConform")}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {exec.evaluation.criteria.map((c) => (
              <span
                key={c.name}
                className={
                  "rounded px-1.5 py-0.5 " +
                  (c.passed ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger")
                }
                title={c.detail}
              >
                {c.name} {c.score.toFixed(1)}
              </span>
            ))}
          </div>
        </div>
      )}

      {exec?.improvements && exec.improvements.improvements.length > 0 && (
        <div className="rounded-xl border border-line bg-raised p-3 text-xs">
          <p className="font-semibold text-muted">{t("exec.improvements")}</p>
          <ul className="mt-1 space-y-1">
            {exec.improvements.improvements.map((im, i) => (
              <li key={`${im.target}-${i}`} className="text-muted">
                <span className="text-accent-ink">{im.target}</span> — {im.suggestion}{" "}
                <span className="text-subtle">({im.derived_from})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
