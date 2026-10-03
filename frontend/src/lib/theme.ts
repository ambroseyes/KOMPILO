/**
 * Gestion du thème clair/sombre.
 *
 * Le **clair est le défaut** (fond blanc) : sans préférence enregistrée, on reste
 * en clair, on ne suit PAS `prefers-color-scheme` pour garantir le fond blanc par
 * défaut. Le choix de l'utilisateur est mémorisé dans localStorage et appliqué via
 * l'attribut `data-theme` sur <html> (voir les variables CSS dans index.css).
 */
export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "kompilo-theme";

/** Lit la préférence enregistrée, ou null si aucune / storage indisponible. */
export function getStoredTheme(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_STORAGE_KEY);
    return v === "dark" || v === "light" ? v : null;
  } catch {
    return null;
  }
}

/** Thème actuellement appliqué sur <html> (clair par défaut). */
export function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

/** Applique un thème : attribut <html>, meta theme-color, et mémorisation. */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#0A1628" : "#FFFFFF");
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* storage indisponible (navigation privée, etc.) — le thème s'applique quand même pour la session */
  }
}
