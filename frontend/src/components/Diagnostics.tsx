import type { DiagnosticDimension } from "../lib/api";

const DIM_LABEL: Record<string, string> = {
  clarity: "Clarté",
  specificity: "Précision",
  confidence: "Confiance",
  risk: "Risque",
  complexity: "Complexité",
  strategy_fit: "Stratégie",
};

type Tone = "good" | "warn" | "bad" | "neutral";

function tone(dimension: string, level: string): Tone {
  const l = level.toLowerCase();
  if (dimension === "risk") return l === "low" ? "good" : l === "medium" ? "warn" : "bad";
  if (dimension === "clarity") return l === "proceed" ? "good" : "warn";
  if (dimension === "confidence" || dimension === "specificity") {
    return l === "high" ? "good" : l === "medium" ? "warn" : "bad";
  }
  return "neutral";
}

const TONE_CLASS: Record<Tone, string> = {
  good: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  warn: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  bad: "bg-red-500/15 text-red-300 border-red-500/30",
  neutral: "bg-kompilo-blue/15 text-kompilo-blue-300 border-kompilo-blue/30",
};

export function Diagnostics({ items }: { items: DiagnosticDimension[] }) {
  return (
    <ul className="space-y-2">
      {items.map((d) => (
        <li
          key={d.dimension}
          className="flex flex-col gap-1 rounded-xl border border-kompilo-border bg-kompilo-navy p-3 sm:flex-row sm:items-center sm:gap-3"
        >
          <span className="w-28 shrink-0 text-sm font-semibold text-slate-200">
            {DIM_LABEL[d.dimension] ?? d.dimension}
          </span>
          <span
            className={
              "inline-block w-fit rounded-md border px-2 py-0.5 text-xs font-medium uppercase tracking-wide " +
              TONE_CLASS[tone(d.dimension, d.level)]
            }
          >
            {d.level}
          </span>
          <span className="text-sm text-slate-400">{d.detail}</span>
        </li>
      ))}
    </ul>
  );
}
