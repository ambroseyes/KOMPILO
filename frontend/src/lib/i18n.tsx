import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * i18n léger (sans librairie) : un contexte + des dictionnaires EN/FR.
 * **Anglais par défaut** ; le choix de l'utilisateur est mémorisé (localStorage)
 * et reflété sur l'attribut `<html lang>`. Extensible à d'autres langues en
 * ajoutant une clé de langue dans chaque entrée de `MESSAGES`.
 */
export type Lang = "en" | "fr";

export const LANGS: Lang[] = ["en", "fr"];
export const DEFAULT_LANG: Lang = "en";
export const LANG_STORAGE_KEY = "kompilo-lang";

type Entry = Record<Lang, string>;

const MESSAGES = {
  // Header / nav / shell
  "app.tagline": {
    en: "AI Execution Intelligence — turn an intent into an execution strategy.",
    fr: "AI Execution Intelligence — transforme une intention en stratégie d'exécution.",
  },
  "nav.compile": { en: "Compile", fr: "Compiler" },
  "nav.library": { en: "Library", fr: "Bibliothèque" },
  "footer.note": {
    en: "KOMPILO · the compilation core is deterministic · displayed costs = estimated",
    fr: "KOMPILO · le cœur de compilation est déterministe · coûts affichés = estimés",
  },
  "lang.aria": { en: "Language", fr: "Langue" },

  // Theme toggle
  "theme.toLight": { en: "Switch to light theme", fr: "Activer le thème clair" },
  "theme.toDark": { en: "Switch to dark theme", fr: "Activer le thème sombre" },
  "theme.light": { en: "Light theme", fr: "Thème clair" },
  "theme.dark": { en: "Dark theme", fr: "Thème sombre" },

  // CompileForm
  "form.question": { en: "What do you want to accomplish?", fr: "Que veux-tu accomplir ?" },
  "form.placeholder": {
    en: "E.g.: Write a courteous customer follow-up email in 150 words…",
    fr: "Ex. : Rédige un email de relance client courtois en 150 mots…",
  },
  "form.mode.aria": { en: "Compilation mode", fr: "Mode de compilation" },
  "form.submit": { en: "Compile", fr: "Compiler" },
  "form.submitting": { en: "Compiling…", fr: "Compilation…" },
  "form.hint": {
    en: "Tip: Ctrl / ⌘ + Enter to compile.",
    fr: "Astuce : Ctrl / ⌘ + Entrée pour compiler.",
  },

  // Compile states (App)
  "compile.pending": { en: "Compiling…", fr: "Compilation en cours…" },
  "compile.error.title": { en: "Compilation failed.", fr: "La compilation a échoué." },
  "compile.live": { en: "Live execution", fr: "Exécution en direct" },
  "common.advanced": { en: "(advanced)", fr: "(avancé)" },

  // ResultView
  "result.understood": { en: "Understood intent", fr: "Intention comprise" },
  "result.domainLabel": { en: "domain:", fr: "domaine :" },
  "result.questions": { en: "Questions to clarify", fr: "Questions à clarifier" },
  "result.questions.hint": {
    en: "Clarify these points then re-run the compilation to get the instruction.",
    fr: "Précise ces points puis relance la compilation pour obtenir l'instruction.",
  },
  "result.compiled": { en: "Compiled instruction", fr: "Instruction compilée" },
  "result.diagnostic": { en: "Diagnostic", fr: "Diagnostic" },
  "result.details": { en: "Details", fr: "Détails" },
  "result.details.rest": {
    en: "— execution plan, costs, sections, metadata",
    fr: "— plan d'exécution, coûts, sections, métadonnées",
  },
  "result.plan": { en: "Execution plan", fr: "Plan d'exécution" },
  "result.strategy": { en: "Strategy:", fr: "Stratégie :" },
  "result.model": { en: "Model:", fr: "Modèle :" },
  "result.fallback": { en: "Fallback:", fr: "Repli :" },
  "result.cost": { en: "Cost", fr: "Coût" },
  "result.estimated": { en: "estimated", fr: "estimé" },
  "result.cost.tokens": {
    en: "({in} in / {out} out tokens)",
    fr: "({in} in / {out} out tokens)",
  },
  "result.ir": { en: "IR sections", fr: "Sections de l'IR" },
  "result.metadata": { en: "Metadata", fr: "Métadonnées" },
  "result.meta.engine": { en: "engine: {v}", fr: "moteur : {v}" },
  "result.meta.deterministic": { en: "deterministic: {v}", fr: "déterministe : {v}" },
  "result.meta.llm": { en: "LLM used: {v}", fr: "LLM utilisé : {v}" },
  "result.meta.costs": { en: "estimated costs: {v}", fr: "coûts estimés : {v}" },
  "result.meta.note": { en: "note: {v}", fr: "note : {v}" },
  "common.yes": { en: "yes", fr: "oui" },
  "common.no": { en: "no", fr: "non" },

  // CopyButton
  "copy.default": { en: "Copy", fr: "Copier" },
  "copy.done": { en: "Copied ✓", fr: "Copié ✓" },
  "copy.json": { en: "Copy JSON", fr: "Copier le JSON" },

  // VariantTabs
  "variants.aria": { en: "Instruction variants", fr: "Variantes de l'instruction" },

  // Diagnostics
  "diag.level.high": { en: "high", fr: "élevé" },
  "diag.level.medium": { en: "medium", fr: "moyen" },
  "diag.level.low": { en: "low", fr: "faible" },
  "diag.why": { en: "Why:", fr: "Pourquoi :" },
  "diag.action": { en: "Action:", fr: "Action :" },

  // ExecutionPanel
  "exec.intro": {
    en: "Advanced feature: runs the task and streams the result live. Requires an access token (via POST /v1/auth/login).",
    fr: "Fonctionnalité avancée : exécute la tâche et diffuse le résultat en direct. Nécessite un jeton d'accès (via POST /v1/auth/login).",
  },
  "exec.token.aria": { en: "Access token", fr: "Jeton d'accès" },
  "exec.run": { en: "Run (streaming)", fr: "Exécuter en streaming" },
  "exec.starting": { en: "Starting…", fr: "Démarrage…" },
  "exec.needsClarification": {
    en: "Clarification needed — refine the task then retry.",
    fr: "Clarification nécessaire — précise la tâche puis réessaie.",
  },
  "exec.stream": { en: "stream:", fr: "flux :" },
  "exec.steps": { en: "{n} step(s)", fr: "{n} étape(s)" },
  "exec.cost.real": { en: "real", fr: "réel" },
  "exec.cached": { en: "served from cache", fr: "servi par le cache" },
  "exec.executed": { en: "executed", fr: "exécuté" },
  "exec.model.real": { en: "real model", fr: "modèle réel" },
  "exec.model.stub": { en: "STUB offline", fr: "STUB offline" },
  "exec.verification": { en: "verification:", fr: "vérification :" },
  "exec.conform": { en: "conforms ✓", fr: "conforme ✓" },
  "exec.eval": { en: "Evaluation", fr: "Évaluation" },
  "exec.eval.measured": { en: "(measured, {method})", fr: "(mesurée, {method})" },
  "exec.eval.score": { en: "score", fr: "score" },
  "exec.eval.notConform": { en: "not conforming", fr: "non conforme" },
  "exec.improvements": { en: "Suggested improvements", fr: "Améliorations suggérées" },

  // SignInBar
  "signin.connected": {
    en: "Connected — token active (in memory only).",
    fr: "Connecté — jeton actif (en mémoire uniquement).",
  },
  "signin.signout": { en: "Sign out", fr: "Se déconnecter" },
  "signin.intro": {
    en: "Sign in to access your prompt library (isolated tenant).",
    fr: "Connecte-toi pour accéder à ta bibliothèque de prompts (tenant isolé).",
  },
  "signin.org.ph": { en: "org (slug)", fr: "org (slug)" },
  "signin.org.aria": { en: "Organization (slug)", fr: "Organisation (slug)" },
  "signin.email.ph": { en: "email", fr: "email" },
  "signin.email.aria": { en: "Email", fr: "Email" },
  "signin.password.ph": { en: "password", fr: "mot de passe" },
  "signin.password.aria": { en: "Password", fr: "Mot de passe" },
  "signin.submit": { en: "Sign in", fr: "Se connecter" },
  "signin.submitting": { en: "Signing in…", fr: "Connexion…" },

  // LibraryPage
  "lib.signin.hint": {
    en: "Tip: use the account created by the demo script (see GUIDE_DEMO).",
    fr: "Astuce : utilise le compte créé par le script de démo (voir le GUIDE_DEMO).",
  },
  "filters.search.ph": { en: "Search (name, slug, description)", fr: "Rechercher (nom, slug, description)" },
  "filters.search.aria": { en: "Search", fr: "Recherche" },
  "filters.tags.ph": { en: "tags (comma-separated)", fr: "tags (séparés par des virgules)" },
  "filters.tags.aria": { en: "Filter by tags", fr: "Filtrer par tags" },
  "filters.project.aria": { en: "Filter by project", fr: "Filtrer par projet" },
  "filters.allProjects": { en: "All projects", fr: "Tous les projets" },
  "list.empty": { en: "No prompt matches.", fr: "Aucun prompt ne correspond." },
  "pager.range": { en: "{a}–{b} of {total}", fr: "{a}–{b} sur {total}" },
  "pager.prev": { en: "Previous", fr: "Précédent" },
  "pager.next": { en: "Next", fr: "Suivant" },
  "newprompt.summary": { en: "+ New prompt", fr: "+ Nouveau prompt" },
  "newprompt.needProject": {
    en: "Create a project first (via the API or the demo script).",
    fr: "Crée d'abord un projet (via l'API ou le script de démo).",
  },
  "newprompt.project.aria": { en: "Project", fr: "Projet" },
  "newprompt.project.choose": { en: "Choose a project…", fr: "Choisir un projet…" },
  "newprompt.slug.ph": { en: "slug (e.g. welcome-email)", fr: "slug (ex. welcome-email)" },
  "newprompt.slug.aria": { en: "Slug", fr: "Slug" },
  "newprompt.name.ph": { en: "name", fr: "nom" },
  "newprompt.name.aria": { en: "Name", fr: "Nom" },
  "newprompt.tags.ph": { en: "tags (commas)", fr: "tags (virgules)" },
  "newprompt.tags.aria": { en: "Tags", fr: "Tags" },
  "newprompt.create": { en: "Create", fr: "Créer" },
  "newprompt.creating": { en: "Creating…", fr: "Création…" },

  // PromptDetail
  "detail.back": { en: "← Back to library", fr: "← Retour à la bibliothèque" },
  "detail.save.title": { en: "Save a compilation", fr: "Sauvegarder une compilation" },
  "detail.save.hint": {
    en: "Kompilo compiles the task server-side and stores the result as a new version (catr, ir, renders, diagnostics).",
    fr: "Kompilo compile la tâche côté serveur et enregistre le résultat comme une nouvelle version (catr, ir, renders, diagnostics).",
  },
  "detail.save.ph": { en: "What do you want to accomplish?", fr: "Que veux-tu accomplir ?" },
  "detail.save.submit": { en: "Compile & save", fr: "Compiler & sauvegarder" },
  "detail.save.saved": {
    en: "Version {n} saved — clarification suggested.",
    fr: "Version {n} enregistrée — clarification suggérée.",
  },
  "detail.versions": { en: "Versions", fr: "Versions" },
  "detail.versions.loading": { en: "Loading…", fr: "Chargement…" },
  "detail.versions.empty": {
    en: "No version — save a compilation above.",
    fr: "Aucune version — sauvegarde une compilation ci-dessus.",
  },
  "detail.version.model": { en: "model: {v}", fr: "modèle : {v}" },
  "detail.compare.title": { en: "Compare two versions", fr: "Comparer deux versions" },
  "detail.compare.from": { en: "from", fr: "de" },
  "detail.compare.to": { en: "to", fr: "à" },
  "detail.compare.submit": { en: "Compare", fr: "Comparer" },
  "detail.compare.comparing": { en: "Comparing…", fr: "Comparaison…" },
  "detail.compare.different": {
    en: "Choose two different versions.",
    fr: "Choisis deux versions différentes.",
  },
  "detail.diff.catr": { en: "CATR fields", fr: "Champs CATR" },
  "detail.diff.diagnostic": { en: "Diagnostic", fr: "Diagnostic" },
  "detail.diff.render": { en: "Render « {mode} » (changed)", fr: "Rendu « {mode} » (modifié)" },
  "detail.diff.none": {
    en: "No structural difference between these two versions.",
    fr: "Aucune différence structurelle entre ces deux versions.",
  },
} satisfies Record<string, Entry>;

export type MsgKey = keyof typeof MESSAGES;

export function getStoredLang(): Lang | null {
  try {
    const v = localStorage.getItem(LANG_STORAGE_KEY);
    return v === "en" || v === "fr" ? v : null;
  } catch {
    return null;
  }
}

function applyLangAttr(lang: Lang): void {
  document.documentElement.setAttribute("lang", lang);
}

type TFn = (key: MsgKey, vars?: Record<string, string | number>) => string;

interface I18n {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: TFn;
}

const I18nContext = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => getStoredLang() ?? DEFAULT_LANG);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    applyLangAttr(l);
    try {
      localStorage.setItem(LANG_STORAGE_KEY, l);
    } catch {
      /* storage indisponible — la langue reste valable pour la session */
    }
  }, []);

  const t = useCallback<TFn>(
    (key, vars) => {
      let s = MESSAGES[key]?.[lang] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
        }
      }
      return s;
    },
    [lang],
  );

  const value = useMemo<I18n>(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within <I18nProvider>");
  return ctx;
}

/** Raccourci quand seul `t` est nécessaire. */
export function useT(): TFn {
  return useI18n().t;
}
