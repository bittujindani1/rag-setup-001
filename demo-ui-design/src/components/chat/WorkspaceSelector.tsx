import { Database, ChevronDown, Check, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Workspace } from '../../types';
import { cn } from '../../lib/utils';

interface WorkspaceSelectorProps {
  activeWorkspace: Workspace;
  setActiveWorkspace: (ws: Workspace) => void;
  workspaces: Workspace[];
  onCreateWorkspace?: (name: string) => void;
  onDeleteWorkspace?: (id: string) => void;
}

export default function WorkspaceSelector({
  activeWorkspace,
  setActiveWorkspace,
  workspaces,
  onCreateWorkspace,
  onDeleteWorkspace,
}: WorkspaceSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newWsName, setNewWsName] = useState('');

  const handleCreate = () => {
    if (!newWsName.trim()) return;
    onCreateWorkspace?.(newWsName.trim());
    setNewWsName('');
    setIsCreating(false);
    setIsOpen(false);
  };

  return (
    <div className="px-4 mb-3">
      <label className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em] px-2 mb-2 block">
        Workspace
      </label>
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={cn(
            "w-full flex items-center justify-between px-3 py-2.5 bg-surface-secondary border border-border rounded-lg text-sm text-foreground hover:bg-background transition-colors group",
            isOpen && "ring-1 ring-accent/20 border-accent/50"
          )}
        >
          <div className="flex items-center gap-2 min-w-0">
            <div className={cn(
              "w-1 h-1 rounded-full shrink-0",
              activeWorkspace.type === 'personal' ? "bg-accent shadow-[0_0_4px_rgba(59,130,246,0.5)]" : "bg-success shadow-[0_0_4px_rgba(16,185,129,0.5)]"
            )} />
            <span className="truncate font-medium tracking-tight">{activeWorkspace.name}</span>
          </div>
          <ChevronDown className={cn("w-3 h-3 text-muted transition-transform duration-300 group-hover:text-foreground", isOpen && "rotate-180")} />
        </button>

        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-1.5 bg-surface border border-border rounded-lg shadow-lg z-50 overflow-hidden animate-in fade-in slide-in-from-top-1">
            <div className="p-1 space-y-0.5 max-h-48 overflow-y-auto custom-scrollbar">
              {workspaces.map((ws) => (
                <button
                  key={ws.id}
                  onClick={() => { setActiveWorkspace(ws); setIsOpen(false); }}
                  className={cn(
                    "w-full flex items-center justify-between px-2.5 py-2 rounded-md text-sm transition-colors group",
                    activeWorkspace.id === ws.id
                      ? "bg-accent/12 text-accent font-medium"
                      : "text-muted hover:bg-background hover:text-foreground"
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Database className={cn("w-3 h-3", activeWorkspace.id === ws.id ? "text-accent" : "text-muted")} />
                    <span className="truncate tracking-tight">{ws.name}</span>
                  </div>
                  {activeWorkspace.id === ws.id && <Check className="w-3 h-3" />}
                </button>
              ))}
            </div>

            <div className="border-t border-border p-1 bg-background">
              {isCreating ? (
                <div className="p-1.5 space-y-1.5">
                  <input
                    autoFocus
                    value={newWsName}
                    onChange={(e) => setNewWsName(e.target.value)}
                    placeholder="Workspace name..."
                    className="w-full bg-surface-secondary border border-border rounded-md px-2 py-2 text-sm focus:ring-1 focus:ring-accent outline-none placeholder:text-muted font-medium"
                    onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                  />
                  <div className="flex gap-1.5">
                    <button onClick={handleCreate} className="flex-1 bg-accent text-white text-[11px] font-medium py-2 rounded-md hover:bg-accent-hover transition-colors">Add</button>
                    <button onClick={() => setIsCreating(false)} className="flex-1 bg-surface-secondary text-muted text-[11px] font-medium py-2 rounded-md hover:bg-background transition-colors">Cancel</button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setIsCreating(true)}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-md text-sm text-muted hover:bg-background hover:text-foreground transition-colors group"
                >
                  <Plus className="w-3.5 h-3.5 text-muted group-hover:text-accent transition-colors" />
                  <span className="font-medium">New Workspace</span>
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {activeWorkspace.type === 'personal' && onDeleteWorkspace && (
        <div className="mt-2 px-2 flex items-center justify-between">
          <span className="text-[11px] text-muted font-medium">Personal workspace</span>
          <button
            onClick={() => onDeleteWorkspace(activeWorkspace.id)}
            className="text-[11px] text-error/80 hover:text-error transition-colors flex items-center gap-1 font-medium"
          >
            <Trash2 className="w-2.5 h-2.5" />
            Delete
          </button>
        </div>
      )}
    </div>
  );
}
