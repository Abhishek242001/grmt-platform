"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch, setTokens, clearTokens, ApiError } from "./api";

type Role = "researcher" | "reviewer" | "organizer" | "platform_admin";

interface AuthState {
  isAuthenticated: boolean;
  role: Role | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, role: "researcher" | "organizer", name: string) => Promise<void>;
  logout: () => void;
  error: string | null;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

// Decode the role claim out of the JWT payload without a signature check —
// this is UI convenience only (which nav shell to render, master doc §6.1),
// never a substitute for the backend's own auth enforcement on every
// endpoint. Never trust this value for an access-control decision anywhere
// except "which sidebar links to show."
function decodeRoleFromToken(token: string): Role | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role ?? null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = typeof window !== "undefined" ? window.localStorage.getItem("grmt_access_token") : null;
    if (token) setRole(decodeRoleFromToken(token));
    setLoading(false);
  }, []);

  async function login(email: string, password: string) {
    setError(null);
    try {
      const resp = await apiFetch<{ access_token: string; refresh_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setTokens(resp.access_token, resp.refresh_token);
      setRole(decodeRoleFromToken(resp.access_token));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Login failed");
      throw e;
    }
  }

  async function signup(email: string, password: string, signupRole: "researcher" | "organizer", name: string) {
    setError(null);
    try {
      await apiFetch("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, role: signupRole, name }),
      });
      await login(email, password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Signup failed");
      throw e;
    }
  }

  function logout() {
    clearTokens();
    setRole(null);
  }

  return (
    <AuthContext.Provider value={{ isAuthenticated: role !== null, role, loading, login, signup, logout, error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
