import { useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useT } from "../lib/i18n";

type Mode = "login" | "signup";

/**
 * Sign-in / sign-up for the authenticated areas (library). Holds the access token in
 * memory only. In "signup" mode it creates the organization + owner account via
 * POST /v1/auth/signup and logs in with the returned access token. Shows a connected
 * banner (with sign-out) once a token is set.
 */
export function SignInBar() {
  const t = useT();
  const { token, setToken, clear } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [orgSlug, setOrgSlug] = useState("");
  const [orgName, setOrgName] = useState("");
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

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "signup"
          ? await api.signup({
              org_slug: orgSlug.trim(),
              org_name: orgName.trim(),
              email: email.trim(),
              password,
            })
          : await api.login({
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

  const canSubmit =
    !!orgSlug.trim() &&
    !!email.trim() &&
    !!password &&
    (mode === "login" || !!orgName.trim()) &&
    !busy;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) void submit();
      }}
      className="space-y-3 rounded-2xl border border-line bg-surface p-5"
    >
      <p className="text-sm text-muted">
        {t(mode === "signup" ? "signin.signup.intro" : "signin.intro")}
      </p>
      <div className="grid gap-2 sm:grid-cols-3">
        <input
          value={orgSlug}
          onChange={(e) => setOrgSlug(e.target.value)}
          placeholder={t("signin.org.ph")}
          aria-label={t("signin.org.aria")}
          autoComplete="organization"
          className="rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
        />
        {mode === "signup" && (
          <input
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder={t("signin.orgname.ph")}
            aria-label={t("signin.orgname.aria")}
            autoComplete="organization-title"
            className="rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
          />
        )}
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
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
          className="rounded-lg border border-line bg-raised px-3 py-2 text-ink placeholder:text-subtle"
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="submit"
          disabled={!canSubmit}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy
            ? t(mode === "signup" ? "signin.signup.submitting" : "signin.submitting")
            : t(mode === "signup" ? "signin.signup.submit" : "signin.submit")}
        </button>
        <button
          type="button"
          onClick={() => {
            setMode((m) => (m === "login" ? "signup" : "login"));
            setError(null);
          }}
          className="text-sm text-accent-ink underline-offset-2 hover:underline"
        >
          {t(mode === "login" ? "signin.toggle.toSignup" : "signin.toggle.toLogin")}
        </button>
      </div>
    </form>
  );
}
