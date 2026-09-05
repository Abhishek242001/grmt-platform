'use client';

// update51 — this file exists specifically to fix a real reported bug:
// logging in as a researcher in one tab and as admin in another tab (same
// browser) would disconnect one of them. Root cause: both login paths
// wrote to the SAME localStorage keys via the shared AuthContext, so the
// second login silently overwrote the first tab's tokens.
//
// Fix: the admin identity is now completely separate end to end —
// different storage keys, AND sessionStorage instead of localStorage.
// sessionStorage is scoped per-tab (not shared across tabs of the same
// browser the way localStorage is), so logging into /admin in one tab
// can never touch a researcher/organizer/reviewer session open in another
// tab, regardless of whether that other tab is the same browser or not.
// The tradeoff: an admin session doesn't persist if that specific tab is
// closed — acceptable for infrequent, high-trust admin access, and matches
// how short-lived admin panels commonly behave elsewhere.

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

const ADMIN_ACCESS_TOKEN_KEY = 'grmt_admin_access_token';
const ADMIN_REFRESH_TOKEN_KEY = 'grmt_admin_refresh_token';

interface AdminAuthContextValue {
  user: User | null;
  accessToken: string | null;
  isLoading: boolean;
  adminLogin: (input: { username: string; password: string }) => Promise<void>;
  logout: () => void;
}

const AdminAuthContext = createContext<AdminAuthContextValue | undefined>(undefined);

function storeAdminTokens(access: string, refresh: string) {
  sessionStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, access);
  sessionStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, refresh);
}

function clearAdminTokens() {
  sessionStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY);
}

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    async function hydrate() {
      const access = sessionStorage.getItem(ADMIN_ACCESS_TOKEN_KEY);
      const refresh = sessionStorage.getItem(ADMIN_REFRESH_TOKEN_KEY);

      if (!access) {
        setIsLoading(false);
        return;
      }

      try {
        const me = await api.getMe(access);
        setUser(me);
        setAccessToken(access);
      } catch {
        if (refresh) {
          try {
            const tokens = await api.refreshToken(refresh);
            storeAdminTokens(tokens.access_token, tokens.refresh_token);
            setUser(tokens.user);
            setAccessToken(tokens.access_token);
          } catch {
            clearAdminTokens();
          }
        } else {
          clearAdminTokens();
        }
      } finally {
        setIsLoading(false);
      }
    }
    hydrate();
  }, []);

  const adminLogin = useCallback<AdminAuthContextValue['adminLogin']>(async (input) => {
    const tokens = await api.adminLogin(input);
    storeAdminTokens(tokens.access_token, tokens.refresh_token);
    setUser(tokens.user);
    setAccessToken(tokens.access_token);
  }, []);

  const logout = useCallback(() => {
    clearAdminTokens();
    setUser(null);
    setAccessToken(null);
    router.push('/admin');
  }, [router]);

  return (
    <AdminAuthContext.Provider value={{ user, accessToken, isLoading, adminLogin, logout }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth(): AdminAuthContextValue {
  const ctx = useContext(AdminAuthContext);
  if (!ctx) throw new Error('useAdminAuth must be used within an AdminAuthProvider');
  return ctx;
}
