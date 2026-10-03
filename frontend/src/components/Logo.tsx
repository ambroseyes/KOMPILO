/**
 * KOMPILO logo — reconstruit en SVG vectoriel (net à toute taille, jamais déformé).
 *
 * L'emblème « ‹ • › » et le wordmark se colorent via les tokens de thème :
 * - parties "encre" (chevron gauche, point, lettres OMPILO) -> `ink` (bleu nuit sur fond clair, clair sur fond sombre)
 * - accent (chevron droit, lettre K) -> `accent` (bleu vif #1B4DFF)
 *
 * La taille se pilote par la taille de police du conteneur (em), donc l'emblème et
 * le wordmark grandissent ensemble sans jamais être étirés. Ex. <Logo className="text-2xl" />.
 */
export function Logo({
  className = "",
  withWordmark = true,
}: {
  className?: string;
  withWordmark?: boolean;
}) {
  return (
    <span
      role="img"
      aria-label="KOMPILO"
      className={
        "inline-flex items-center gap-[0.38em] font-extrabold leading-none " + className
      }
    >
      <svg
        viewBox="0 0 124 96"
        className="h-[1.1em] w-auto shrink-0"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        {/* chevron gauche « ‹ » — encre */}
        <polyline
          points="54,16 24,48 54,80"
          className="stroke-ink"
          strokeWidth={13}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* chevron droit « › » — bleu vif */}
        <polyline
          points="70,16 100,48 70,80"
          className="stroke-accent"
          strokeWidth={13}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* point central — encre */}
        <circle cx="62" cy="48" r="9" className="fill-ink" />
      </svg>
      {withWordmark && (
        <span className="tracking-tight" aria-hidden="true">
          <span className="text-accent">K</span>
          <span className="text-ink">OMPILO</span>
        </span>
      )}
    </span>
  );
}
