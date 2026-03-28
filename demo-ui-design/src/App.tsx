import { useCallback, useEffect, useMemo, useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import LoginPage from './components/LoginPage';
import Sidebar from './components/Sidebar';
import ChatTab from './components/ChatTab';
import AnalyticsTab from './components/AnalyticsTab';
import AgentsTab from './components/AgentsTab';
import ModernizationTab from './components/ModernizationTab';
import { Toaster } from 'sonner';
import { Workspace, ChatThread } from './types';
import * as api from './lib/api';

const DEFAULT_INDEX = 'statefarm_rag';
const SHARED_WORKSPACE = 'demo-shared';
const SNOW_WORKSPACE = 'snow_idx';
const PERSONAL_WS_KEY = 'rag-v2-personal-ws';
const ACTIVE_WS_KEY = 'rag-v2-active-ws';

function normalizeWorkspace(v: string): string {
  const n = v.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64);
  return n.length >= 3 ? n : DEFAULT_INDEX;
}

function toWorkspace(id: string): Workspace {
  const isShared = id === SHARED_WORKSPACE;
  const isSnow = id === SNOW_WORKSPACE;
  return {
    id,
    name: isShared ? 'Shared Demo' : isSnow ? 'ServiceNow' : id,
    type: isShared ? 'shared' : isSnow ? 'servicenow' : 'personal',
    isReadOnly: isShared || isSnow,
  };
}

function AppContent() {
  const { isAuthenticated } = useAuth();
  const { theme } = useTheme();
  const [activeTab, setActiveTab] = useState('chat');

  // Workspace state
  const savedWs = localStorage.getItem(ACTIVE_WS_KEY) || SHARED_WORKSPACE;
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(savedWs);
  const [personalWsList, setPersonalWsList] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(PERSONAL_WS_KEY) || '[]'); } catch { return []; }
  });

  const workspaces: Workspace[] = useMemo(() => {
    const base = [toWorkspace(SHARED_WORKSPACE), toWorkspace(SNOW_WORKSPACE)];
    const personal = personalWsList.map(toWorkspace);
    return [...personal, ...base];
  }, [personalWsList]);

  const activeWorkspace = useMemo(() => toWorkspace(activeWorkspaceId), [activeWorkspaceId]);

  const setActiveWorkspace = useCallback((ws: Workspace) => {
    setActiveWorkspaceId(ws.id);
    localStorage.setItem(ACTIVE_WS_KEY, ws.id);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    let cancelled = false;

    api.listWorkspaces()
      .then(({ workspaces: persisted = [] }) => {
        if (cancelled) {
          return;
        }

        const normalized = persisted
          .map(normalizeWorkspace)
          .filter((id) => id !== SHARED_WORKSPACE && id !== SNOW_WORKSPACE);

        setPersonalWsList((current) => {
          const next = Array.from(new Set([...normalized, ...current]));
          localStorage.setItem(PERSONAL_WS_KEY, JSON.stringify(next));
          return next;
        });
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [isAuthenticated]);

  // Thread state
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState('');

  const refreshThreads = useCallback(async (wsId = activeWorkspaceId) => {
    try {
      const data = await api.listThreads(wsId);
      const mapped: ChatThread[] = (data.threads || []).map((t: any) => ({
        id: t.id,
        title: t.name || 'Untitled',
        workspaceId: wsId,
        updatedAt: t.createdAt || new Date().toISOString(),
        lastMessage: t.steps?.[t.steps.length - 1]?.output?.slice(0, 60),
      }));
      setThreads(mapped);
      return mapped;
    } catch {
      setThreads([]);
      return [];
    }
  }, [activeWorkspaceId]);

  useEffect(() => {
    if (isAuthenticated) {
      setActiveThreadId(null);
      setSessionId('');
      refreshThreads(activeWorkspaceId);
    }
  }, [isAuthenticated, activeWorkspaceId, refreshThreads]);

  const handleNewChat = useCallback(async () => {
    try {
      const created = await api.createThread(activeWorkspaceId, 'New chat');
      setActiveThreadId(created.thread_id);
      setSessionId(created.session_id);
      await refreshThreads();
    } catch { /* silent */ }
  }, [activeWorkspaceId, refreshThreads]);

  const handleDeleteThread = useCallback(async (id: string) => {
    try {
      await api.deleteThread(id, activeWorkspaceId);
      if (activeThreadId === id) {
        setActiveThreadId(null);
        setSessionId('');
      }
      await refreshThreads();
    } catch { /* silent */ }
  }, [activeWorkspaceId, activeThreadId, refreshThreads]);

  const handleCreateWorkspace = useCallback((name: string) => {
    const id = normalizeWorkspace(name);
    if (!personalWsList.includes(id)) {
      const next = [id, ...personalWsList.filter(ws => ws !== id)];
      setPersonalWsList(next);
      localStorage.setItem(PERSONAL_WS_KEY, JSON.stringify(next));
    }
    setActiveWorkspace(toWorkspace(id));
  }, [personalWsList, setActiveWorkspace]);

  const handleDeleteWorkspace = useCallback(async (id: string) => {
    try {
      await api.deleteWorkspace(id);
    } catch { /* ignore */ }
    const next = personalWsList.filter(w => w !== id);
    setPersonalWsList(next);
    localStorage.setItem(PERSONAL_WS_KEY, JSON.stringify(next));
    if (activeWorkspaceId === id) {
      setActiveWorkspace(toWorkspace(SHARED_WORKSPACE));
    }
  }, [personalWsList, activeWorkspaceId, setActiveWorkspace]);

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden relative">
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/10 blur-[120px] rounded-full animate-pulse" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-600/5 blur-[120px] rounded-full animate-pulse delay-1000" />
      </div>

      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        activeWorkspace={activeWorkspace}
        setActiveWorkspace={setActiveWorkspace}
        workspaces={workspaces}
        threads={threads.filter(t => t.workspaceId === activeWorkspaceId)}
        activeThreadId={activeThreadId}
        setActiveThreadId={(id) => {
          setActiveThreadId(id);
          // Load thread to get session_id
          api.getThread(id, activeWorkspaceId).then((t: any) => {
            setSessionId(t?.metadata?.session_id || '');
          }).catch(() => {});
        }}
        onNewChat={handleNewChat}
        onDeleteThread={handleDeleteThread}
        onCreateWorkspace={handleCreateWorkspace}
        onDeleteWorkspace={handleDeleteWorkspace}
      />

      <main className="flex-1 relative overflow-hidden flex flex-col z-10">
        <div className="flex-1 overflow-hidden">
          {activeTab === 'chat' && (
            <ChatTab
              workspace={activeWorkspace}
              activeThreadId={activeThreadId}
              sessionId={sessionId}
              setSessionId={setSessionId}
              setActiveThreadId={setActiveThreadId}
              refreshThreads={refreshThreads}
            />
          )}
          {activeTab === 'analytics' && <AnalyticsTab />}
          {activeTab === 'agents' && (
            <AgentsTab workspaceId={activeWorkspaceId} indexName={activeWorkspaceId} />
          )}
          {activeTab === 'modernization' && <ModernizationTab />}
        </div>
      </main>

      <Toaster position="top-right" theme={theme} />
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AppContent />
      </AuthProvider>
    </ThemeProvider>
  );
}
