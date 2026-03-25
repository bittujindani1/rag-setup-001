import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User } from '../types';
import * as api from '../lib/api';

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    const saved = api.getAuth();
    if (saved) {
      setUser({
        id: '1',
        username: saved.username,
        email: `${saved.username}@htcinc.com`,
        role: saved.role as 'admin' | 'user',
      });
    }
  }, []);

  const login = async (username: string, password: string) => {
    const result = await api.login(username, password);
    setUser({
      id: '1',
      username: result.username,
      email: `${result.username}@htcinc.com`,
      role: result.role as 'admin' | 'user',
    });
  };

  const logout = () => {
    setUser(null);
    api.clearAuth();
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
