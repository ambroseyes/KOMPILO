import type { KeyboardEvent } from "react";
import type { CompileMode } from "../lib/api";
import { useT } from "../lib/i18n";

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
  const t = useT();

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
      className="rounded-2xl border border-line bg-surface p-5 shadow-sm sm:p-6"
    >
      <label htmlFor="task" className="block text-lg font-semibold text-ink sm:text-xl">
        {t("form.question")}
      </label>
      <textarea
        id="task"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        rows={5}
        placeholder={t("form.placeholder")}
        className="mt-3 w-full resize-y rounded-xl border border-line bg-raised p-4 text-base text-ink placeholder:text-subtle"
      />

      <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div role="group" aria-label={t("form.mode.aria")} className="flex gap-1">
          {MODES.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => onModeChange(m)}
              className={
                "rounded-lg px-3 py-1.5 text-sm font-medium transition " +
                (mode === m
                  ? "bg-accent text-white"
                  : "border border-line bg-raised text-muted hover:text-ink")
              }
            >
              {MODE_LABEL[m]}
            </button>
          ))}
        </div>

        <button
          type="submit"
          disabled={isPending || !value.trim()}
          className="rounded-xl bg-accent px-6 py-2.5 text-base font-semibold text-white shadow-sm transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? t("form.submitting") : t("form.submit")}
        </button>
      </div>
      <p className="mt-2 text-xs text-subtle">{t("form.hint")}</p>
    </form>
  );
}
