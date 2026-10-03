import type { DiagnosticDimension, DiagnosticLevel } from "../lib/api";

type Tone = "good" | "warn" | "bad";

// Uniform mapping now that every axis uses the same low/medium/high scale.
const TONE: Record<DiagnosticLevel, Tone> = { high: "good", medium: "warn", low: "bad" };

const TONE_CLASS: Record<Tone, string> = {
  good: "bg-ok/15 text-ok border-ok/30",
  warn: "bg-warn/15 text-warn border-warn/30",
  bad: "bg-danger/15 text-danger border-danger/30",
};

const LEVEL_LABEL: Record<DiagnosticLevel, string> = {
  high: "élevé",
  medium: "moyen",
  low: "faible",
};

/**
 * Explainable multidimensional diagnostic: one row per axis with its level and, when
 * weak, the reason + the corrective action. Deliberately NO single aggregate score.
 */
export function Diagnostics({ items }: { items: DiagnosticDimension[] }) {
  return (
    <ul className="space-y-2">
      {items.map((d) => (
        <li
          key={d.dimension}
          className="rounded-xl border border-line bg-raised p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="w-40 shrink-0 text-sm font-semibold text-ink">{d.label}</span>
            <span
              className={
                "inline-block w-fit rounded-md border px-2 py-0.5 text-xs font-medium uppercase tracking-wide " +
                TONE_CLASS[TONE[d.level]]
              }
            >
              {LEVEL_LABEL[d.level]}
            </span>
            <span className="text-sm text-muted">{d.detail}</span>
          </div>
          {d.reason && (
            <p className="mt-1 pl-1 text-xs text-subtle">
              <span className="font-semibold text-muted">Pourquoi :</span> {d.reason}
            </p>
          )}
          {d.recommendation && (
            <p className="mt-0.5 pl-1 text-xs text-accent-ink">
              <span className="font-semibold">Action :</span> {d.recommendation}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
