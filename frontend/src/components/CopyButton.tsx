import { useState } from "react";
import { useT } from "../lib/i18n";

export function CopyButton({ text, label }: { text: string; label?: string }) {
  const t = useT();
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable (e.g. insecure context) — fail silently */
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      aria-live="polite"
      className="rounded-lg border border-line bg-raised px-3 py-1.5 text-xs font-medium text-ink transition hover:border-accent hover:text-accent-ink"
    >
      {copied ? t("copy.done") : (label ?? t("copy.default"))}
    </button>
  );
}
