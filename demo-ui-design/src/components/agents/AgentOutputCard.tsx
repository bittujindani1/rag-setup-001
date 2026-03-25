import { 
  ChevronDown, 
  ChevronUp, 
  Terminal, 
  BarChart3, 
  Search, 
  Cpu, 
  CheckCircle2, 
  Clock,
  ExternalLink
} from 'lucide-react';
import { useState } from 'react';
import { AgentStep } from '../../types';
import { cn } from '../../lib/utils';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'motion/react';

interface AgentOutputCardProps {
  step: AgentStep;
  defaultExpanded?: boolean;
}

const AGENT_ICONS = {
  planner: Terminal,
  analyst: BarChart3,
  researcher: Search,
  executor: Cpu,
  synthesizer: CheckCircle2,
};

const AGENT_COLORS = {
  planner: 'text-purple-500 bg-purple-500/10 border-purple-500/20',
  analyst: 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  researcher: 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  executor: 'text-rose-500 bg-rose-500/10 border-rose-500/20',
  synthesizer: 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
};

export default function AgentOutputCard({ step, defaultExpanded = false }: AgentOutputCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const Icon = AGENT_ICONS[step.agent] || Cpu;
  const colorClasses = AGENT_COLORS[step.agent] || 'text-muted-foreground bg-muted/10 border-border';

  return (
    <div className="bg-surface-secondary/30 border border-border rounded-2xl overflow-hidden transition-all hover:bg-surface-secondary/50">
      <button 
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-5 py-4 flex items-center justify-between group"
      >
        <div className="flex items-center gap-4">
          <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center border transition-all", colorClasses)}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <h3 className="text-[11px] font-bold text-foreground uppercase tracking-widest leading-none">
                {step.agent} Agent
              </h3>
              <div className={cn(
                "w-1.5 h-1.5 rounded-full",
                step.status === 'completed' ? "bg-emerald-500" : "bg-amber-500 animate-pulse"
              )} />
            </div>
            <p className="text-xs text-muted-foreground mt-1 font-medium">
              {step.summary}
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/40 font-medium uppercase tracking-widest">
            <Clock className="w-3 h-3" />
            {new Date(step.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
          <div className="w-8 h-8 rounded-lg bg-background/50 border border-border flex items-center justify-center group-hover:border-accent/40 group-hover:text-accent transition-all">
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        </div>
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
          >
            <div className="px-5 pb-5 pt-2 border-t border-border/50">
              <div className="bg-background/40 rounded-xl p-5 border border-border/50 relative group/content">
                <div className="absolute top-4 right-4 opacity-0 group-hover/content:opacity-100 transition-opacity">
                  <button className="p-1.5 rounded-md hover:bg-accent/10 text-muted-foreground hover:text-accent transition-all">
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                </div>
                
                <div className="prose prose-invert prose-sm max-w-none prose-p:text-muted-foreground prose-headings:text-foreground prose-headings:font-bold prose-headings:tracking-tight prose-strong:text-foreground prose-code:text-accent prose-code:bg-accent/5 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:content-none prose-code:after:content-none">
                  <ReactMarkdown>{step.output || step.details || 'No detailed output available.'}</ReactMarkdown>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
