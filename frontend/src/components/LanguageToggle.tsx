import { LANGS, useI18n } from "../lib/i18n";

/** Sélecteur de langue compact (EN | FR) pour l'en-tête. Anglais par défaut. */
export function LanguageToggle() {
  const { lang, setLang, t } = useI18n();

  return (
    <div
      role="group"
      aria-label={t("lang.aria")}
      className="inline-flex h-9 shrink-0 overflow-hidden rounded-lg border border-line bg-surface text-xs font-semibold"
    >
      {LANGS.map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={lang === l}
          onClick={() => setLang(l)}
          className={
            "px-2.5 transition " +
            (lang === l ? "bg-accent text-white" : "text-muted hover:text-ink")
          }
        >
          {l.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
