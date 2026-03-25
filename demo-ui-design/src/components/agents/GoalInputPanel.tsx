import { Play, Loader2, Database, Search } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../../lib/utils';
import { toast } from 'sonner';

const DEFAULT_QUICK_GOALS = [
  'Analyze Q1 incident trends',
  'SLA compliance audit',
  'Root cause of service outages',
  'Resource allocation review'
];

interface GoalInputPanelProps {
  onRun: (goal: string, datasetId: string, ragIndex: string) => void;
  isLoading: boolean;
  presets?: Array<{ id: string; title: string; goal: string; icon: string }>;
}

export default function GoalInputPanel({ onRun, isLoading, presets }: GoalInputPanelProps) {
  const [goal, setGoal] = useState('');
  const [datasetId, setDatasetId] = useState('');
  const [ragIndex, setRagIndex] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) {
      toast.error('Please enter a goal for the agents');
      return;
    }
    onRun(goal, datasetId, ragIndex);
  };

  return (
    <div className="bg-surface-secondary/30 border border-border rounded-3xl p-6 shadow-sm relative overflow-hidden group">
      <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-700" />
      
      <form onSubmit={handleSubmit} className="relative z-10 space-y-6">
        <div className="space-y-2">
          <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest ml-1">
            Primary Objective
          </label>
          <textarea
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Describe the high-level goal for the multi-agent workflow..."
            className="w-full bg-background/50 border border-border rounded-2xl p-4 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent/40 transition-all min-h-[100px] resize-none"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest ml-1 flex items-center gap-2">
              <Database className="w-3 h-3" />
              Dataset ID (Optional)
            </label>
            <input
              type="text"
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
              placeholder="e.g. ServiceNow_Q1_2024"
              className="w-full bg-background/50 border border-border rounded-xl px-4 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent/40 transition-all"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest ml-1 flex items-center gap-2">
              <Search className="w-3 h-3" />
              RAG Index (Optional)
            </label>
            <input
              type="text"
              value={ragIndex}
              onChange={(e) => setRagIndex(e.target.value)}
              placeholder="e.g. Identity_Docs_V2"
              className="w-full bg-background/50 border border-border rounded-xl px-4 py-2.5 text-xs text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent/40 transition-all"
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-2">
          <span className="text-[9px] font-bold text-muted-foreground/40 uppercase tracking-widest mr-2">Quick Goals:</span>
          {(presets && presets.length > 0 ? presets.map(p => p.goal) : DEFAULT_QUICK_GOALS).map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setGoal(q)}
              className="px-3 py-1.5 rounded-full bg-background/40 border border-border hover:border-accent/40 hover:bg-accent/5 text-[10px] text-muted-foreground hover:text-accent transition-all"
            >
              {q}
            </button>
          ))}
        </div>

        <div className="pt-4 flex justify-end">
          <button
            type="submit"
            disabled={isLoading || !goal.trim()}
            className={cn(
              "px-8 py-3 rounded-xl text-xs font-bold uppercase tracking-widest transition-all flex items-center gap-3 shadow-lg",
              isLoading || !goal.trim()
                ? "bg-muted text-muted-foreground cursor-not-allowed"
                : "bg-accent text-white hover:bg-accent/90 hover:shadow-accent/20 active:scale-95"
            )}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Orchestrating...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                Execute Workflow
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
