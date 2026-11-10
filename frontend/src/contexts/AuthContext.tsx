import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, clearCsrfToken, setCsrfToken } from "../services/api";

export interface MyCloudUser {
  id: string;
  email: string;
  display_name: string;
  role: string;
  is_admin: boolean;
}

interface AuthState {
  user: MyCloudUser | null;
  loading: boolean;
  enrollmentOpen: boolean;
  login: (email: string, password: string) => Promise<MyCloudUser>;
  enroll: (email: string, displayName: string, password: string) => Promise<MyCloudUser>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<MyCloudUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [enrollmentOpen, setEnrollmentOpen] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const me = await api<MyCloudUser>("/v1/auth/me", { signal: undefined });
      setUser(me);
    } catch {
      setUser(null);
      try {
        const status = await api<{ enrollment_open: boolean; reason: string }>(
          "/v1/auth/provider/init/status",
        );
        setEnrollmentOpen(status.enrollment_open);
      } catch {
        setEnrollmentOpen(false);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const payload = await api<{ user: MyCloudUser; csrf_token: string }>("/v1/auth/login", {
      method: "POST",
      json: { email, password },
    });
    setUser(payload.user);
    // Remember the CSRF token for this browser; revoked by logout/revocation.
    setCsrfToken(payload.csrf_token, true);
    return payload.user;
  }, []);

  const enroll = useCallback(async (email: string, displayName: string, password: string) => {
    const payload = await api<{ user: MyCloudUser; csrf_token: string }>(
      "/v1/auth/provider/init",
      { method: "POST", json: { email, display_name: displayName, password } },
    );
    setUser(payload.user);
    setCsrfToken(payload.csrf_token, true);
    setEnrollmentOpen(false);
    return payload.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/v1/auth/logout", { method: "POST" });
    } finally {
      setUser(null);
      clearCsrfToken();
    }
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, loading, enrollmentOpen, login, enroll, logout, refresh }),
    [user, loading, enrollmentOpen, login, enroll, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return context;
}
