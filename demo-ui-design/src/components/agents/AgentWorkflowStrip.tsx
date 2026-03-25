import { 
  Terminal, 
  BarChart3, 
  Search, 
  Cpu, 
  CheckCircle2, 
  Loader2,
  ChevronRight
} from 'lucide-react';
import { AgentStep } from '../../types';
import { cn } from '../../lib/utils';

interface AgentWorkflowStripProps {
  steps: AgentStep[];
}

const AGENT_ICONS = {
  planner: Terminal,
  analyst: BarChart3,
  researcher: Search,
  executor: Cpu,
  synthesizer: CheckCircle2,
};

export default function AgentWorkflowStrip({ steps }: AgentWorkflowStripProps) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-2 custom-scrollbar no-scrollbar">
      {steps.map((step, idx) => {
        const Icon = AGENT_ICONS[step.agent] || Cpu;
        const isLast = idx === steps.length - 1;
        
        return (
          <div key={step.id} className="flex items-center gap-2 shrink-0">
            <div className={cn(
              "flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-all",
              step.status === 'completed' 
                ? "bg-accent/5 border-accent/20 text-accent" 
                : step.status === 'running'
                ? "bg-background border-accent shadow-sm text-accent"
                : "bg-surface-secondary/40 border-border text-muted-foreground/40"
            )}>
              <div className={cn(
                "w-6 h-6 rounded-lg flex items-center justify-center",
                step.status === 'completed' ? "bg-accent/10" : "bg-muted/50"
              )}>
                {step.status === 'running' ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Icon className="w-3.5 h-3.5" />
                )}
              </div>
              <div className="flex flex-col">
                <span className="text-[10px] font-bold uppercase tracking-wider leading-none">
                  {step.agent}
                </span>
                <span className="text-[8px] font-medium opacity-60 mt-0.5 truncate max-w-[100px]">
                  {step.summary}
                </span>
              </div>
            </div>
            
            {!isLast && (
              <ChevronRight className="w-4 h-4 text-muted-foreground/20" />
            )}
          </div>
        );
      })}
    </div>
  );
}
