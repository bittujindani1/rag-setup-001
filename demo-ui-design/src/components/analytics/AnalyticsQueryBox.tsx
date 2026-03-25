import { Search, Loader2, History, Sparkles, Send, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { AnalyticsQueryResult } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';

interface AnalyticsQueryBoxProps {
  onQuery: (query: string) => void;
  isLoading: boolean;
  recentQueries: AnalyticsQueryResult[];
  onRerunQuery: (query: string) => void;
  onDeleteHistory: (id: string) => void;
}

const SUGGESTIONS = [
  'Show ticket count by category',
  'Top 5 priorities',
  'Compare assignment groups',
  'Show monthly trend',
  'What are the top recurring issues?'
];

export default function AnalyticsQueryBox({
  onQuery,
  isLoading,
  recentQueries,
  onRerunQuery,
  onDeleteHistory
}: AnalyticsQueryBoxProps) {
  const [query, setQuery] = useState('');
  const [showHistory, setShowHistory] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onQuery(query);
      setQuery('');
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-surface-secondary/30 border border-border rounded-lg p-4 shadow-sm relative overflow-hidden group">
        <div className="relative z-10">
          <form onSubmit={handleSubmit} className="flex items-center gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/30 group-focus-within:text-accent transition-colors" />
              <input 
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask a question about your data..."
                className="w-full bg-background border border-border rounded-md py-2.5 pl-10 pr-4 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent/50 transition-all placeholder:text-muted-foreground/30"
                disabled={isLoading}
              />
            </div>
            
            <div className="flex items-center gap-2">
              <button 
                type="button"
                onClick={() => setShowHistory(!showHistory)}
                className={cn(
                  "p-2.5 rounded-md transition-all border border-border",
                  showHistory ? "text-accent bg-accent/5 border-accent/20" : "text-muted-foreground/60 hover:text-foreground hover:bg-white/5"
                )}
              >
                <History className="w-4 h-4" />
              </button>
              <button 
                type="submit"
                disabled={!query.trim() || isLoading}
                className="px-6 py-2.5 bg-accent hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed text-white text-[11px] font-bold rounded-md transition-all flex items-center gap-2 uppercase tracking-wider border border-accent/20"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                Analyze
              </button>
            </div>
          </form>

          {/* Suggestions - More compact */}
          <div className="mt-4 flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => onQuery(s)}
                disabled={isLoading}
                className="px-3 py-1 bg-white/5 border border-border/50 rounded-md text-[10px] font-medium text-muted-foreground/60 hover:bg-accent/10 hover:text-accent hover:border-accent/20 transition-all tracking-tight"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Recent History Dropdown */}
        <AnimatePresence>
          {showHistory && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="mt-4 pt-4 border-t border-border/10 space-y-3">
                <div className="flex items-center justify-between px-1">
                  <h4 className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">Recent Queries</h4>
                </div>
                
                <div className="space-y-1 max-h-48 overflow-y-auto custom-scrollbar pr-1">
                  {recentQueries.length === 0 ? (
                    <div className="py-8 text-center">
                      <p className="text-[10px] text-muted-foreground/40 font-medium">No recent queries</p>
                    </div>
                  ) : (
                    recentQueries.map((q) => (
                      <div 
                        key={q.id}
                        className="group flex items-center justify-between gap-3 px-3 py-2 hover:bg-white/5 rounded-md transition-all cursor-pointer border border-transparent hover:border-border/50"
                        onClick={() => onRerunQuery(q.query)}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <History className="w-3.5 h-3.5 text-muted-foreground/30 group-hover:text-accent shrink-0" />
                          <span className="text-xs font-medium text-foreground truncate tracking-tight">{q.query}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <span className="text-[10px] text-muted-foreground/40 tabular-nums">
                            {new Date(q.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                          <button 
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteHistory(q.id);
                            }}
                            className="p-1.5 text-muted-foreground/30 hover:text-error opacity-0 group-hover:opacity-100 transition-all hover:bg-error/10 rounded"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
