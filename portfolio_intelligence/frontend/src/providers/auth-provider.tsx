"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  useRef,
  ReactNode,
} from "react";
import { api } from "@/lib/api";
import { User } from "@/lib/types";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const checkAuth = async () => {
      console.log("🟢 AUTH PROVIDER: checkAuth starting");
      const token = localStorage.getItem("token");
      console.log("🟢 AUTH PROVIDER: Token from localStorage:", token ? "EXISTS" : "NULL");

      if (!token) {
        console.log("🟢 AUTH PROVIDER: No token, setting isLoading=false");
        setIsLoading(false);
        return;
      }

      console.log("🟢 AUTH PROVIDER: Calling /api/v1/auth/me...");
      try {
        const data = await api.getMe();
        console.log("🟢 AUTH PROVIDER: ✅ Auth successful, user:", data.email);
        setUser(data);
      } catch (error) {
        console.error("🟢 AUTH PROVIDER: ❌ Auth check failed:", error);
        localStorage.removeItem("token");
      } finally {
        console.log("🟢 AUTH PROVIDER: Setting isLoading=false");
        setIsLoading(false);
      }
    };

    checkAuth();
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setUser(null);
    window.location.href = "/login";
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
