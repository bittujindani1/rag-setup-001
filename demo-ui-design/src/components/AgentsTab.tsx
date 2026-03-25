import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Loader2,
  Sparkles,
  Layout,
  Search,
  Terminal,
  Cpu,
  BarChart3,
} from 'lucide-react';
import { toast } from 'sonner';
import { motion, AnimatePresence } from 'motion/react';
import { AgentRun, AgentStep, AgentMessage, AgentRunSummary } from '../types';
import * as api from '../lib/api';

import GoalInputPanel from './agents/GoalInputPanel';
import AgentWorkflowStrip from './agents/AgentWorkflowStrip';
import AgentOutputCard from './agents/AgentOutputCard';
import FinalReportCard from './agents/FinalReportCard';
import PastRunsSidebar from './agents/PastRunsSidebar';

interface AgentsTabProps {
  workspaceId: string;
  indexName: string;
}

export default function AgentsTab({ workspaceId }: AgentsTabProps) {
  const [pastRuns, setPastRuns] = useState<AgentRun[]>([]);
  const [activeRun, setActiveRun] = useState<AgentRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [currentGoal, setCurrentGoal] = useState('');
  const [presets, setPresets] = useState<Array<{ id: string; title: string; goal: string; icon: string }>>([]);
  const abortRef = useRef<(() => void) | null>(null);

  // Load presets
  useEffect(() => {
    api.getAgentPresets().then(data => setPresets(data.presets || [])).catch(() => {});
  }, []);

  // Load past runs
  const loadPastRuns = useCallback(async () => {
    try {
      const data = await api.listAgentRuns(workspaceId);
      const runs: AgentRun[] = (data.runs || []).map((r: AgentRunSummary) => ({
        id: r.run_id,
        goal: r.goal,
        status: r.status === 'completed' ? 'completed' as const : 'running' as const,
        timestamp: new Date(r.created_at * 1000).toISOString(),
        steps: [],
      }));
      setPastRuns(runs);
    } catch { /* silent */ }
  }, [workspaceId]);

  useEffect(() => { loadPastRuns(); }, [loadPastRuns]);

  const handleRun = async (goal: string, datasetId: string, ragIndex: string) => {
    setIsRunning(true);
    setCurrentGoal(goal);
    setActiveRun(null);

    const steps: AgentStep[] = [];
    let synthesis: string | null = null;
    let runId: string | null = null;

    try {
      const { response, abort } = api.startAgentRunStream(goal, workspaceId, datasetId || undefined, ragIndex || undefined);
      abortRef.current = abort;

      const res = await response;
      if (!res.ok) throw new Error(await res.text() || `HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        let currentEvent = '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6)) as AgentMessage;
              payload.type = currentEvent as AgentMessage['type'];

              if (payload.type === 'plan') {
                const planSteps = payload.steps || [];
                // Create step placeholders
                planSteps.forEach((s, i) => {
                  steps.push({
                    id: `step-${i}`,
                    agent: s.agent as AgentStep['agent'],
                    status: 'pending',
                    summary: s.task,
                    timestamp: new Date().toISOString(),
                  });
                });
              } else if (payload.type === 'agent_message') {
                const agent = payload.agent || 'analyst';
                const existing = steps.find(s => s.agent === agent && s.status !== 'completed');
                if (existing) {
                  existing.status = 'completed';
                  existing.output = payload.output || '';
                  existing.details = payload.thought || payload.task || '';
                  existing.tool_used = payload.tool_used;
                  existing.tool_result = payload.tool_result;
                } else {
                  steps.push({
                    id: `step-${steps.length}`,
                    agent: agent as AgentStep['agent'],
                    status: 'completed',
                    summary: payload.task || payload.output?.slice(0, 80) || '',
                    output: payload.output,
                    details: payload.thought || '',
                    timestamp: new Date().toISOString(),
                    tool_used: payload.tool_used,
                    tool_result: payload.tool_result,
                  });
                }
              } else if (payload.type === 'synthesis') {
                synthesis = payload.output || null;
              } else if (payload.type === 'done') {
                runId = payload.run_id || null;
              }

              // Update active run in real time
              setActiveRun({
                id: runId || 'streaming',
                goal,
                datasetId: datasetId || undefined,
                ragIndex: ragIndex || undefined,
                status: 'running',
                timestamp: new Date().toISOString(),
                steps: [...steps],
                finalReport: synthesis ? {
                  title: goal,
                  overview: synthesis.slice(0, 200),
                  keyFindings: [],
                  recommendations: [],
                  content: synthesis,
                } : undefined,
              });
            } catch { /* malformed JSON */ }
          }
        }
      }

      // Final update
      setActiveRun({
        id: runId || 'completed',
        goal,
        datasetId: datasetId || undefined,
        ragIndex: ragIndex || undefined,
        status: 'completed',
        timestamp: new Date().toISOString(),
        steps: [...steps],
        finalReport: synthesis ? {
          title: goal,
          overview: synthesis.slice(0, 200),
          keyFindings: [],
          recommendations: [],
          content: synthesis,
        } : undefined,
      });

      toast.success('Report generation complete');
      await loadPastRuns();
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        toast.error(`Agent run failed: ${(err as Error).message}`);
      }
    } finally {
      setIsRunning(false);
      abortRef.current = null;
    }
  };

  const handleLoadPastRun = useCallback(async (run: AgentRun) => {
    try {
      const data = await api.getAgentRun(run.id, workspaceId);
      const messages: AgentMessage[] = data.messages || [];
      const steps: AgentStep[] = [];
      let synthesis: string | null = null;

      for (const msg of messages) {
        if (msg.type === 'agent_message') {
          steps.push({
            id: `step-${steps.length}`,
            agent: (msg.agent || 'analyst') as AgentStep['agent'],
            status: 'completed',
            summary: msg.task || msg.output?.slice(0, 80) || '',
            output: msg.output,
            details: msg.thought || '',
            timestamp: msg.timestamp ? new Date(msg.timestamp * 1000).toISOString() : new Date().toISOString(),
            tool_used: msg.tool_used,
            tool_result: msg.tool_result,
          });
        } else if (msg.type === 'synthesis') {
          synthesis = msg.output || null;
        }
      }

      setActiveRun({
        id: run.id,
        goal: data.goal || run.goal,
        status: 'completed',
        timestamp: run.timestamp,
        steps,
        finalReport: synthesis ? {
          title: data.goal || run.goal,
          overview: synthesis.slice(0, 200),
          keyFindings: [],
          recommendations: [],
          content: synthesis,
        } : undefined,
      });
    } catch {
      toast.error('Could not load run details');
    }
  }, [workspaceId]);

  const handleDeleteRun = (_id: string) => {
    setPastRuns(prev => prev.filter(r => r.id !== _id));
    if (activeRun?.id === _id) setActiveRun(null);
  };

  return (
    <div className="flex h-full bg-background overflow-hidden relative">
      <PastRunsSidebar
        runs={pastRuns}
        activeRunId={activeRun?.id}
        onSelectRun={handleLoadPastRun}
        onDeleteRun={handleDeleteRun}
      />
      <main className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(37,99,235,0.03),transparent_50%)] pointer-events-none" />
        <header className="px-8 py-4 border-b border-border bg-background z-30 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-accent/10 rounded-xl flex items-center justify-center border border-accent/20">
              <Cpu className="w-5 h-5 text-accent" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground tracking-tight">Agent Orchestration</h1>
              <p className="text-sm text-muted mt-1">Multi-agent workflow and report synthesis engine.</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-accent/10 text-accent rounded-full text-[11px] font-medium border border-accent/20">
              <Sparkles className="w-3 h-3" />
              5-Agent Pipeline
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="max-w-[1000px] mx-auto px-8 py-8 space-y-8">
            <section className="animate-in fade-in slide-in-from-top-4 duration-500">
              <GoalInputPanel onRun={handleRun} isLoading={isRunning} presets={presets} />
            </section>

            <AnimatePresence mode="wait">
              {isRunning && !activeRun ? (
                <motion.div key="running" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} className="py-24 flex flex-col items-center justify-center text-center space-y-8">
                  <div className="relative">
                    <div className="w-20 h-20 bg-accent/5 rounded-3xl flex items-center justify-center border border-accent/10 shadow-xl">
                      <Loader2 className="w-8 h-8 text-accent animate-spin" />
                    </div>
                  </div>
                  <div className="space-y-3">
                    <h3 className="text-lg font-bold text-foreground tracking-tight">Orchestrating Agents</h3>
                    <p className="text-sm text-muted max-w-md mx-auto leading-relaxed">
                      Running: <span className="text-foreground font-medium italic">"{currentGoal}"</span>
                    </p>
                  </div>
                </motion.div>
              ) : activeRun ? (
                <motion.div key={activeRun.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-12 pb-24">
                  {activeRun.steps.length > 0 && (
                    <section>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-1.5 h-1.5 rounded-full bg-accent" />
                        <h4 className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em]">Workflow Pipeline</h4>
                      </div>
                      <AgentWorkflowStrip steps={activeRun.steps} />
                    </section>
                  )}
                  {activeRun.steps.length > 0 && (
                    <section className="space-y-6">
                      <div className="flex items-center gap-3 mb-6">
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                        <h4 className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em]">Agent Timeline</h4>
                      </div>
                      <div className="space-y-4">
                        {activeRun.steps.map((step, idx) => (
                          <AgentOutputCard key={step.id} step={step} defaultExpanded={idx === activeRun.steps.length - 1} />
                        ))}
                      </div>
                    </section>
                  )}
                  {activeRun.finalReport && (
                    <section className="pt-12 border-t border-border">
                      <div className="flex items-center gap-3 mb-8">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                        <h4 className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em]">Synthesized Report</h4>
                      </div>
                      <FinalReportCard report={activeRun.finalReport} timestamp={activeRun.timestamp} />
                    </section>
                  )}
                </motion.div>
              ) : (
                <motion.div key="empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="py-32 flex flex-col items-center justify-center text-center">
                  <div className="w-20 h-20 bg-surface-secondary border border-border rounded-3xl flex items-center justify-center mb-8">
                    <Layout className="w-8 h-8 text-muted" />
                  </div>
                  <div className="space-y-3">
                    <h3 className="text-lg font-bold text-foreground tracking-tight">Agent Workspace Ready</h3>
                    <p className="text-sm text-muted max-w-sm mx-auto leading-relaxed">Define a goal above to trigger the multi-agent orchestration engine.</p>
                  </div>
                  <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-2xl w-full">
                    {[
                      { title: 'Planner', desc: 'Defines strategy', icon: Terminal },
                      { title: 'Analyst', desc: 'Processes data', icon: BarChart3 },
                      { title: 'Researcher', desc: 'Retrieves docs', icon: Search },
                    ].map((item, i) => (
                      <div key={i} className="bg-surface-secondary border border-border rounded-2xl p-5 flex flex-col items-center group hover:bg-background transition-colors">
                        <div className="w-8 h-8 rounded-lg bg-background flex items-center justify-center mb-3 text-muted group-hover:text-accent group-hover:bg-accent/10 transition-colors">
                          <item.icon className="w-4 h-4" />
                        </div>
                        <p className="text-sm font-semibold text-foreground mb-1">{item.title}</p>
                        <p className="text-[11px] text-muted">{item.desc}</p>
                      </div>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  );
}
