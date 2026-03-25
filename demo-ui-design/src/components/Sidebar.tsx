import {
  MessageSquare,
  BarChart3,
  Users,
  Plus,
  Settings,
  LogOut,
  Moon,
  Sun,
  History,
} from 'lucide-react';
import { cn } from '../lib/utils';
import { Workspace, ChatThread } from '../types';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import WorkspaceSelector from './chat/WorkspaceSelector';
import ThreadHistoryList from './chat/ThreadHistoryList';
import BrandLogo from './BrandLogo';
import { motion } from 'motion/react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  activeWorkspace: Workspace;
  setActiveWorkspace: (ws: Workspace) => void;
  workspaces: Workspace[];
  threads: ChatThread[];
  activeThreadId: string | null;
  setActiveThreadId: (id: string) => void;
  onNewChat: () => void;
  onDeleteThread: (id: string) => void;
  onCreateWorkspace?: (name: string) => void;
  onDeleteWorkspace?: (id: string) => void;
}

export default function Sidebar({
  activeTab,
  setActiveTab,
  activeWorkspace,
  setActiveWorkspace,
  workspaces,
  threads,
  activeThreadId,
  setActiveThreadId,
  onNewChat,
  onDeleteThread,
  onCreateWorkspace,
  onDeleteWorkspace,
}: SidebarProps) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const navItems = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'analytics', label: 'Analytics', icon: BarChart3 },
    { id: 'agents', label: 'Agents', icon: Users },
  ];

  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col h-screen overflow-hidden relative z-30">
      {/* Brand */}
      <div className="p-6 border-b border-border space-y-3">
        <BrandLogo className="w-fit" />
        <div className="flex items-center gap-2 pl-0.5">
          <div className="w-1.5 h-1.5 rounded-full bg-success" />
          <span className="text-[11px] text-muted font-medium uppercase tracking-[0.16em]">Enterprise Workspace</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="px-4 space-y-1.5 mb-6">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={cn(
              "w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm font-medium transition-colors group relative overflow-hidden border",
              activeTab === item.id
                ? "text-white bg-accent border-accent"
                : "text-muted border-transparent hover:bg-surface-secondary hover:text-foreground hover:border-border"
            )}
          >
            <div className="flex items-center gap-3 relative z-10">
              <item.icon className={cn("w-4 h-4 transition-all", activeTab === item.id ? "text-white" : "text-muted")} />
              <span>{item.label}</span>
            </div>
            {activeTab === item.id && (
              <motion.div
                layoutId="active-nav"
                className="absolute inset-0 bg-accent z-0"
                transition={{ type: "spring", bounce: 0.16, duration: 0.5 }}
              />
            )}
          </button>
        ))}
      </nav>

      {/* Chat panel */}
      {activeTab === 'chat' ? (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="px-4 mb-4">
            <button
              onClick={onNewChat}
              className="w-full bg-surface-secondary hover:bg-surface border border-border rounded-xl py-3 px-3 flex items-center justify-center gap-2.5 transition-colors group"
            >
              <div className="w-5 h-5 bg-accent/12 rounded-lg flex items-center justify-center group-hover:bg-accent group-hover:text-white transition-colors">
                <Plus className="w-3 h-3" />
              </div>
              <span className="text-sm font-medium text-foreground">New Chat</span>
            </button>
          </div>

          <WorkspaceSelector
            activeWorkspace={activeWorkspace}
            setActiveWorkspace={setActiveWorkspace}
            workspaces={workspaces}
            onCreateWorkspace={onCreateWorkspace}
            onDeleteWorkspace={onDeleteWorkspace}
          />

          <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
            <ThreadHistoryList
              threads={threads}
              activeThreadId={activeThreadId}
              setActiveThreadId={setActiveThreadId}
              onDelete={onDeleteThread}
            />
          </div>
        </div>
      ) : (
        <div className="mt-2 flex-1 overflow-y-auto px-3 custom-scrollbar">
          <div className="flex items-center justify-between px-2 mb-3">
            <label className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em]">
              {activeTab === 'analytics' ? 'Datasets' : 'Recent Runs'}
            </label>
            <History className="w-3 h-3 text-muted" />
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="p-3 border-t border-border space-y-3 bg-surface-secondary">
        <div className="flex items-center justify-between px-1">
          <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-background text-muted transition-colors flex items-center gap-2 group">
            {theme === 'dark' ? <Sun className="w-3.5 h-3.5 group-hover:rotate-90 transition-transform" /> : <Moon className="w-3.5 h-3.5 group-hover:-rotate-12 transition-transform" />}
            <span className="text-[11px] font-medium">{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          </button>
          <button className="p-2 rounded-lg hover:bg-background text-muted transition-all hover:rotate-45">
            <Settings className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="bg-background border border-border rounded-xl p-3 flex items-center gap-3 group hover:border-accent/30 transition-colors">
          <div className="relative">
            <div className="w-8 h-8 rounded-lg bg-accent/12 border border-accent/20 flex items-center justify-center text-xs font-semibold text-accent uppercase">
              {user?.username?.charAt(0) || 'U'}
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 bg-success border-2 border-background rounded-full" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-foreground truncate tracking-tight">{user?.username}</p>
            <span className="text-[11px] text-accent font-medium bg-accent/12 px-2 py-0.5 rounded-md capitalize">{user?.role}</span>
          </div>
          <button onClick={logout} className="p-2 rounded-lg hover:bg-error/10 text-muted hover:text-error transition-colors active:scale-90" title="Log off">
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </aside>
  );
}
