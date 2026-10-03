import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

/**
 * In-memory auth token (access_token). Deliberately NOT persisted to any browser
 * storage — it lives only for the tab's session, consistent with Kompilo's
 * "aucun stockage navigateur" rule. A refresh clears it and the user signs in again.
 */
interface AuthState {
  token: string | null;
  setToken: (token: string | null) => void;
  clear: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const value = useMemo<AuthState>(
    () => ({ token, setToken, clear: () => setToken(null) }),
    [token],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
