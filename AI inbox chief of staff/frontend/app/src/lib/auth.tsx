"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";

import { api, type CurrentUser } from "@/lib/api";

interface AuthState {
  token: string | null;
  currentUser: CurrentUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (token: string) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const initialState: AuthState = {
  token: null,
  currentUser: null,
  isAuthenticated: false,
  isLoading: true,
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(initialState);

  const fetchCurrentUser = useCallback(async () => {
    try {
      const user = await api.auth.me();
      setState((prev) => ({
        ...prev,
        currentUser: user,
        isLoading: false,
      }));
    } catch {
      // Token invalid / 401 — drop it and reset state
      localStorage.removeItem("session_token");
      setState({
        token: null,
        currentUser: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  }, []);

  useEffect(() => {
    const stored =
      typeof window !== "undefined"
        ? localStorage.getItem("session_token")
        : null;
    if (!stored) {
      setState({ ...initialState, isLoading: false });
      return;
    }
    setState({
      token: stored,
      currentUser: null,
      isAuthenticated: true,
      isLoading: true,
    });
    fetchCurrentUser();
  }, [fetchCurrentUser]);

  const login = useCallback(
    (token: string) => {
      localStorage.setItem("session_token", token);
      setState({
        token,
        currentUser: null,
        isAuthenticated: true,
        isLoading: true,
      });
      fetchCurrentUser();
    },
    [fetchCurrentUser],
  );

  const logout = useCallback(() => {
    localStorage.removeItem("session_token");
    setState({ ...initialState, isLoading: false });
  }, []);

  const value = useMemo(
    () => ({ ...state, login, logout, refreshUser: fetchCurrentUser }),
    [state, login, logout, fetchCurrentUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
