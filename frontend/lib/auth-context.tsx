'use client';

// Tokens are stored in localStorage for this build. This is a deliberate,
// documented tradeoff (XSS surface vs. simplicity) — see the planning log,
// §3 Known Issues. Revisit with httpOnly cookies before any real deployment.

import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
  useCallback,
} from 'react';
import { useRouter } from 'next/navigation';
import * as api from './api';
import type { User } from './api';

const ACCESS_TOKEN_KEY = 'grmt_access_token';
const REFRESH_TOKEN_KEY = 'grmt_refresh_token';

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  signup: (input: {
    email: string;
    password: string;
    full_name: string;
    role: 'researcher' | 'organizer' | 'reviewer';
  }) => Promise<void>;
  login: (input: { email: string; password: string }) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function storeTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
}

function clearTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  // On mount: try to hydrate the session from a stored access token, and if
  // that's expired, fall back to the refresh token once before giving up.
  useEffect(() => {
    async function hydrate() {
      const access = localStorage.getItem(ACCESS_TOKEN_KEY);
      const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);

      if (!access) {
        setIsLoading(false);
        return;
      }

      try {
        const me = await api.getMe(access);
        setUser(me);
      } catch {
        if (refresh) {
          try {
            const tokens = await api.refreshToken(refresh);
            storeTokens(tokens.access_token, tokens.refresh_token);
            setUser(tokens.user);
          } catch {
            clearTokens();
          }
        } else {
          clearTokens();
        }
      } finally {
        setIsLoading(false);
      }
    }
    hydrate();
  }, []);

  const signup = useCallback<AuthContextValue['signup']>(async (input) => {
    const tokens = await api.signup(input);
    storeTokens(tokens.access_token, tokens.refresh_token);
    setUser(tokens.user);
  }, []);

  const login = useCallback<AuthContextValue['login']>(async (input) => {
    const tokens = await api.login(input);
    storeTokens(tokens.access_token, tokens.refresh_token);
    setUser(tokens.user);
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setUser(null);
    router.push('/login');
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, signup, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
