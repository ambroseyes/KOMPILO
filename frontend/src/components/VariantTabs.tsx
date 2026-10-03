import { useState } from "react";
import type { CompileMode, PromptRenders } from "../lib/api";
import { useT } from "../lib/i18n";
import { CopyButton } from "./CopyButton";

const ORDER: CompileMode[] = ["compact", "professional", "expert"];
const LABEL: Record<CompileMode, string> = {
  compact: "Compact",
  professional: "Pro",
  expert: "Expert",
};

export function VariantTabs({ renders, initial }: { renders: PromptRenders; initial: CompileMode }) {
  const t = useT();
  const [active, setActive] = useState<CompileMode>(initial);
  const text = renders[active];

  return (
    <div>
      <div className="flex items-center gap-2">
        <div role="tablist" aria-label={t("variants.aria")} className="flex gap-1">
          {ORDER.map((m) => {
            const selected = active === m;
            return (
              <button
                key={m}
                role="tab"
                id={`tab-${m}`}
                aria-selected={selected}
                aria-controls={`panel-${m}`}
                onClick={() => setActive(m)}
                className={
                  "rounded-lg px-3 py-1.5 text-xs font-medium transition " +
                  (selected
                    ? "bg-accent text-white"
                    : "border border-line bg-raised text-muted hover:text-ink")
                }
              >
                {LABEL[m]}
              </button>
            );
          })}
        </div>
        <div className="ml-auto">
          <CopyButton text={text} />
        </div>
      </div>

      <pre
        role="tabpanel"
        id={`panel-${active}`}
        aria-labelledby={`tab-${active}`}
        tabIndex={0}
        className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-raised p-4 font-mono text-sm leading-relaxed text-ink"
      >
        {text}
      </pre>
    </div>
  );
}
