import { useState } from "react";
import { api, type ExecuteResponse } from "../lib/api";
import { useExecutionStream } from "../hooks/useExecutionStream";

/**
 * Advanced: run the task through /v1/execute (authenticated) and stream the result
 * live. Requires an access token (the public compile screen is unauthenticated).
 */
export function ExecutionPanel({ task }: { task: string }) {
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
      <p className="text-slate-400">
        Fonctionnalité avancée : exécute la tâche et diffuse le résultat en direct.
        Nécessite un jeton d'accès (via <code>POST /v1/auth/login</code>).
      </p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="access_token"
          aria-label="Jeton d'accès"
          className="flex-1 rounded-lg border border-kompilo-border bg-kompilo-raised px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <button
          type="button"
          onClick={run}
          disabled={!canRun}
          className="rounded-lg bg-kompilo-blue px-4 py-2 font-semibold text-white transition hover:bg-kompilo-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {starting ? "Démarrage…" : "Exécuter en streaming"}
        </button>
      </div>

      {startError && (
        <p role="alert" className="text-red-300">
          {startError}
        </p>
      )}

      {exec?.status === "needs_clarification" && (
        <p className="text-amber-300">Clarification nécessaire — précise la tâche puis réessaie.</p>
      )}

      {executionId && (
        <div className="rounded-xl border border-kompilo-border bg-kompilo-navy p-3">
          <div className="mb-2 flex items-center gap-2 text-xs text-slate-400">
            <span
              className={
                "h-2 w-2 rounded-full " +
                (stream.status === "streaming"
                  ? "animate-pulse bg-kompilo-blue"
                  : stream.status === "done"
                    ? "bg-emerald-400"
                    : stream.status === "error"
                      ? "bg-red-400"
                      : "bg-slate-500")
              }
            />
            flux : {stream.status}
            {stream.steps.length > 0 && <> · {stream.steps.length} étape(s)</>}
          </div>
          <pre
            aria-live="polite"
            className="max-h-72 overflow-auto whitespace-pre-wrap font-mono text-sm text-slate-200"
          >
            {stream.text || "…"}
          </pre>
          {stream.error && <p className="mt-2 text-red-300">{stream.error}</p>}
        </div>
      )}

      {exec?.metadata && (
        <p className="text-xs text-slate-400">
          Coût <span className="text-emerald-300">réel</span> ~$
          {exec.metadata.actual_cost.cost_usd.toFixed(6)} ·{" "}
          {exec.metadata.cached ? "servi par le cache" : "exécuté"} ·{" "}
          {exec.metadata.provider_is_real ? "modèle réel" : "STUB offline"}
          {exec.verification && <> · vérification : {exec.verification.valid ? "conforme ✓" : exec.verification.summary}</>}
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
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border-amber-500/30 bg-amber-500/10 text-amber-300")
              }
            >
              {s.stage}
            </span>
          ))}
        </div>
      )}

      {exec?.evaluation && (
        <div className="rounded-xl border border-kompilo-border bg-kompilo-navy p-3 text-xs">
          <p className="text-slate-300">
            Évaluation <span className="text-slate-500">(mesurée, {exec.evaluation.method})</span> :{" "}
            score <span className="font-semibold text-slate-100">{exec.evaluation.score.toFixed(2)}</span>{" "}
            · {exec.evaluation.passed ? "conforme ✓" : "non conforme"}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            {exec.evaluation.criteria.map((c) => (
              <span
                key={c.name}
                className={
                  "rounded px-1.5 py-0.5 " +
                  (c.passed ? "bg-emerald-500/10 text-emerald-300" : "bg-red-500/10 text-red-300")
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
        <div className="rounded-xl border border-kompilo-border bg-kompilo-navy p-3 text-xs">
          <p className="font-semibold text-slate-300">Améliorations suggérées</p>
          <ul className="mt-1 space-y-1">
            {exec.improvements.improvements.map((im, i) => (
              <li key={`${im.target}-${i}`} className="text-slate-400">
                <span className="text-kompilo-blue-300">{im.target}</span> — {im.suggestion}{" "}
                <span className="text-slate-600">({im.derived_from})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
