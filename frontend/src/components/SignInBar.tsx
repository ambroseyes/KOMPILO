import { useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";

/**
 * Compact sign-in for the authenticated areas (library). Holds the access token in
 * memory only. Shows a connected banner (with sign-out) once a token is set.
 */
export function SignInBar() {
  const { token, setToken, clear } = useAuth();
  const [orgSlug, setOrgSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (token) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-200">
        <span>Connecté — jeton actif (en mémoire uniquement).</span>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-emerald-400/40 px-2 py-1 text-xs hover:bg-emerald-400/10"
        >
          Se déconnecter
        </button>
      </div>
    );
  }

  async function signIn() {
    setBusy(true);
    setError(null);
    try {
      const res = await api.login({
        org_slug: orgSlug.trim(),
        email: email.trim(),
        password,
      });
      setToken(res.access_token);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const canSubmit = orgSlug.trim() && email.trim() && password && !busy;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) void signIn();
      }}
      className="space-y-3 rounded-2xl border border-kompilo-border bg-kompilo-panel p-5"
    >
      <p className="text-sm text-slate-300">
        Connecte-toi pour accéder à ta bibliothèque de prompts (tenant isolé).
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        <input
          value={orgSlug}
          onChange={(e) => setOrgSlug(e.target.value)}
          placeholder="org (slug)"
          aria-label="Organisation (slug)"
          autoComplete="organization"
          className="rounded-lg border border-kompilo-border bg-kompilo-raised px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email"
          type="email"
          aria-label="Email"
          autoComplete="email"
          className="rounded-lg border border-kompilo-border bg-kompilo-raised px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="mot de passe"
          type="password"
          aria-label="Mot de passe"
          autoComplete="current-password"
          className="rounded-lg border border-kompilo-border bg-kompilo-raised px-3 py-2 text-slate-100 placeholder:text-slate-500"
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={!canSubmit}
        className="rounded-lg bg-kompilo-blue px-4 py-2 text-sm font-semibold text-white transition hover:bg-kompilo-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? "Connexion…" : "Se connecter"}
      </button>
    </form>
  );
}
