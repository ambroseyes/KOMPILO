import type { KeyboardEvent } from "react";
import type { CompileMode } from "../lib/api";

const MODES: CompileMode[] = ["compact", "professional", "expert"];
const MODE_LABEL: Record<CompileMode, string> = {
  compact: "Compact",
  professional: "Pro",
  expert: "Expert",
};

interface Props {
  value: string;
  onChange: (v: string) => void;
  mode: CompileMode;
  onModeChange: (m: CompileMode) => void;
  onSubmit: () => void;
  isPending: boolean;
}

export function CompileForm({ value, onChange, mode, onModeChange, onSubmit, isPending }: Props) {
  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      if (value.trim()) onSubmit();
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (value.trim()) onSubmit();
      }}
      className="rounded-2xl border border-kompilo-border bg-kompilo-panel p-5 shadow-xl sm:p-6"
    >
      <label htmlFor="task" className="block text-lg font-semibold text-white sm:text-xl">
        Que veux-tu accomplir&nbsp;?
      </label>
      <textarea
        id="task"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={5}
        placeholder="Ex. : Rédige un email de relance client courtois en 150 mots…"
        className="mt-3 w-full resize-y rounded-xl border border-kompilo-border bg-kompilo-raised p-4 text-base text-slate-100 placeholder:text-slate-500"
      />

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="group" aria-label="Mode de compilation" className="flex gap-1">
          {MODES.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => onModeChange(m)}
              className={
                "rounded-lg px-3 py-1.5 text-sm font-medium transition " +
                (mode === m
                  ? "bg-kompilo-blue text-white"
                  : "border border-kompilo-border bg-kompilo-raised text-slate-300 hover:text-white")
              }
            >
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={isPending || !value.trim()}
          className="rounded-xl bg-kompilo-blue px-6 py-2.5 text-base font-semibold text-white shadow-lg transition hover:bg-kompilo-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? "Compilation…" : "Compiler"}
        </button>
      </div>
      <p className="mt-2 text-xs text-slate-500">Astuce : Ctrl / ⌘ + Entrée pour compiler.</p>
    </form>
  );
}
