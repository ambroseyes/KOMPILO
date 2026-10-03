import { useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useT } from "../lib/i18n";

/**
 * Compact sign-in for the authenticated areas (library). Holds the access token in
 * memory only. Shows a connected banner (with sign-out) once a token is set.
 */
export function SignInBar() {
  const t = useT();
  const { token, setToken, clear } = useAuth();
  const [orgSlug, setOrgSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (token) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-ok/30 bg-ok/10 px-4 py-2 text-sm text-ok">
        <span>{t("signin.connected")}</span>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-ok/40 px-2 py-1 text-xs hover:bg-ok/10"
        >
          {t("signin.signout")}
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
      className="space-y-3 rounded-2xl border border-line bg-surface p-5"
    >
      <p className="text-sm text-muted">{t("signin.intro")}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <input
          value={orgSlug}
          onChange={(e) => setOrgSlug(e.target.value)}
          placeholder={t("signin.org.ph")}
          aria-label={t("signin.org.aria")}
          autoComplete="organization"
          className="rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
        />
        <input
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder={t("signin.email.ph")}
          type="email"
          aria-label={t("signin.email.aria")}
          autoComplete="email"
          className="rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t("signin.password.ph")}
          type="password"
          aria-label={t("signin.password.aria")}
          autoComplete="current-password"
          className="rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={!canSubmit}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {busy ? t("signin.submitting") : t("signin.submit")}
      </button>
    </form>
  );
}
