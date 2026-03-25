import { MessageSquare, MoreVertical, Trash2, Check, X } from 'lucide-react';
import { useState } from 'react';
import { ChatThread } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';

interface ThreadHistoryListProps {
  threads: ChatThread[];
  activeThreadId: string | null;
  setActiveThreadId: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function ThreadHistoryList({ 
  threads, 
  activeThreadId, 
  setActiveThreadId, 
  onDelete 
}: ThreadHistoryListProps) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  return (
    <div className="mt-4 flex-1 overflow-y-auto px-3 custom-scrollbar">
      <div className="flex items-center justify-between px-2 mb-3">
        <label className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em]">
          Recent Threads
        </label>
        <span className="text-[11px] text-muted font-medium bg-background px-2 py-0.5 rounded-full border border-border">{threads.length}</span>
      </div>
      
      <div className="space-y-1">
        <AnimatePresence mode="popLayout">
          {threads.length === 0 ? (
            <div className="px-3 py-10 text-center">
              <div className="w-10 h-10 bg-background border border-border rounded-2xl flex items-center justify-center mx-auto mb-3">
                <MessageSquare className="w-5 h-5 text-muted" />
              </div>
              <p className="text-[11px] text-muted font-medium">No history found</p>
            </div>
          ) : (
            threads.map((thread) => (
              <motion.div
                layout
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                key={thread.id}
                className="group relative"
              >
                <button
                  onClick={() => setActiveThreadId(thread.id)}
                  className={cn(
                    "w-full flex flex-col gap-1.5 px-3 py-3 rounded-xl text-left transition-colors relative overflow-hidden border",
                    activeThreadId === thread.id 
                      ? "bg-accent/12 text-accent border-accent/25" 
                      : "text-muted border-transparent hover:bg-background hover:text-foreground hover:border-border"
                  )}
                >
                  <div className="flex items-center justify-between gap-2.5">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <MessageSquare className={cn("w-3 h-3 shrink-0 transition-colors", activeThreadId === thread.id ? "text-accent" : "text-muted")} />
                      <span className="text-sm font-medium truncate tracking-tight">{thread.title}</span>
                    </div>
                    {activeThreadId === thread.id && (
                      <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                    )}
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] text-muted font-medium">
                      {new Date(thread.updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    {thread.lastMessage && (
                      <span className="text-[11px] text-muted truncate flex-1 text-right">
                        {thread.lastMessage}
                      </span>
                    )}
                  </div>
                </button>

                {/* Actions */}
                <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-x-2 group-hover:translate-x-0 flex items-center gap-1">
                  {confirmDelete === thread.id ? (
                    <div className="flex items-center gap-1 bg-surface border border-border rounded-lg p-1 shadow-lg">
                      <button 
                        onClick={() => {
                          onDelete(thread.id);
                          setConfirmDelete(null);
                        }}
                        className="p-1.5 hover:text-success transition-all hover:bg-success/10 rounded-md"
                      >
                        <Check className="w-3 h-3" />
                      </button>
                      <button 
                        onClick={() => setConfirmDelete(null)}
                        className="p-1.5 hover:text-foreground transition-all hover:bg-background rounded-md"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <button 
                      onClick={() => setConfirmDelete(thread.id)}
                      className="p-2 hover:text-error text-muted transition-all hover:bg-error/10 rounded-lg"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
