"use client";

import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch } from "@/lib/api";

export type Role = "SALESPERSON" | "ACCOUNTING" | "MANAGEMENT";

interface AuthUser {
  username: string;
  role: Role;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  isWorker: boolean;
  isAccounting: boolean;
  isManagement: boolean;
  login: (username: string, password: string) => Promise<{ ok: true } | { ok: false; error: string }>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/api/auth/me/");
      const data = await res.json();
      setUser(data.authenticated ? { username: data.username, role: data.role } : null);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      const res = await apiFetch("/api/auth/login/", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        return { ok: false as const, error: data.error ?? "No se pudo iniciar sesión." };
      }
      setUser({ username: data.username, role: data.role });
      return { ok: true as const };
    },
    [],
  );

  const logout = useCallback(async () => {
    await apiFetch("/api/auth/logout/", { method: "POST" });
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isWorker: user !== null,
        isAccounting: user?.role === "ACCOUNTING",
        isManagement: user?.role === "MANAGEMENT",
        login,
        logout,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
