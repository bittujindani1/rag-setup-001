import { 
  Search, 
  History, 
  Trash2, 
  ChevronRight, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  Sparkles,
  Layout
} from 'lucide-react';
import { AgentRun } from '../../types';
import { cn } from '../../lib/utils';
import { useState } from 'react';

interface PastRunsSidebarProps {
  runs: AgentRun[];
  activeRunId?: string;
  onSelectRun: (run: AgentRun) => void;
  onDeleteRun: (id: string) => void;
}

export default function PastRunsSidebar({ 
  runs, 
  activeRunId, 
  onSelectRun, 
  onDeleteRun 
}: PastRunsSidebarProps) {
  const [search, setSearch] = useState('');

  const filteredRuns = runs.filter(run => 
    run.goal.toLowerCase().includes(search.toLowerCase()) ||
    run.id.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <aside className="w-80 bg-surface-secondary/30 border-r border-border flex flex-col h-full overflow-hidden relative z-20">
      <div className="p-6 border-b border-border bg-background/40 backdrop-blur-md">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center border border-accent/20">
              <History className="w-4 h-4 text-accent" />
            </div>
            <h2 className="text-[11px] font-bold text-foreground uppercase tracking-widest">Run History</h2>
          </div>
          <div className="flex items-center gap-2 px-2 py-1 bg-background/50 border border-border rounded-md text-[9px] font-bold text-muted-foreground uppercase tracking-widest">
            {runs.length} Runs
          </div>
        </div>

        <div className="relative group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/40 group-focus-within:text-accent transition-colors" />
          <input 
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search past runs..."
            className="w-full bg-background/50 border border-border rounded-xl py-2.5 pl-10 pr-4 text-[11px] text-foreground placeholder:text-muted-foreground/20 focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent/40 transition-all"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-2">
        {filteredRuns.length === 0 ? (
          <div className="py-20 text-center space-y-4">
            <div className="w-12 h-12 rounded-2xl bg-muted/50 flex items-center justify-center mx-auto border border-border/50">
              <Layout className="w-6 h-6 text-muted-foreground/10" />
            </div>
            <div className="space-y-1">
              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">No History</p>
              <p className="text-[9px] text-muted-foreground/40 uppercase tracking-widest">Execute a run to see it here</p>
            </div>
          </div>
        ) : (
          filteredRuns.map((run) => (
            <div 
              key={run.id}
              className={cn(
                "group relative rounded-2xl border transition-all cursor-pointer overflow-hidden",
                activeRunId === run.id 
                  ? "bg-background border-accent/40 shadow-lg shadow-accent/5" 
                  : "bg-background/40 border-border hover:bg-background hover:border-border/80"
              )}
              onClick={() => onSelectRun(run)}
            >
              <div className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      run.status === 'completed' ? "bg-emerald-500" : "bg-amber-500"
                    )} />
                    <span className="text-[10px] font-bold text-foreground uppercase tracking-widest">{run.id}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[9px] text-muted-foreground/40 font-medium uppercase tracking-widest">
                    <Clock className="w-3 h-3" />
                    {new Date(run.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' })}
                  </div>
                </div>
                
                <p className="text-[11px] text-muted-foreground font-medium line-clamp-2 leading-relaxed group-hover:text-foreground transition-colors">
                  {run.goal}
                </p>
                
                <div className="flex items-center justify-between pt-1">
                  <div className="flex items-center gap-2">
                    <div className="flex -space-x-1.5">
                      {[1, 2, 3].map(i => (
                        <div key={i} className="w-5 h-5 rounded-md bg-accent/10 border border-background flex items-center justify-center text-[8px] font-bold text-accent">
                          {i}
                        </div>
                      ))}
                    </div>
                    <span className="text-[9px] text-muted-foreground/40 font-bold uppercase tracking-widest">
                      {run.steps.length} Steps
                    </span>
                  </div>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      onDeleteRun(run.id);
                    }}
                    className="p-1.5 rounded-lg hover:bg-error/10 text-muted-foreground/20 hover:text-error transition-all opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              
              {activeRunId === run.id && (
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-accent" />
              )}
            </div>
          ))
        )}
      </div>

      <div className="p-4 border-t border-border bg-background/40 backdrop-blur-md">
        <div className="bg-accent/5 border border-accent/10 rounded-xl p-3 flex items-center gap-3 group/tip">
          <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center border border-accent/20 group-hover/tip:bg-accent group-hover/tip:text-white transition-all">
            <Sparkles className="w-4 h-4 text-accent" />
          </div>
          <div className="flex-1">
            <p className="text-[9px] font-bold text-foreground uppercase tracking-widest">Pro Tip</p>
            <p className="text-[8px] text-muted-foreground/60 uppercase tracking-widest mt-0.5">Select a run to reopen the full report</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
