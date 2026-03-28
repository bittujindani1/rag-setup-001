import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  Layers3,
  Loader2,
  RefreshCcw,
  ShieldAlert,
  Waypoints,
} from 'lucide-react';
import * as api from '../lib/api';
import {
  ExecutionState,
  ModernizationGraphLink,
  ModernizationProgramDetail,
  ModernizationProgramSummary,
  ParagraphTranslationRecord,
} from '../types';

const fallbackExecutionState: ExecutionState = {
  executionId: 'demo-acctproc-001',
  status: 'SUCCEEDED',
  startedAt: '2026-03-28T12:30:00Z',
  updatedAt: '2026-03-28T12:35:00Z',
};

const fallbackPrograms: ModernizationProgramSummary[] = [
  {
    file_id: 'ACCTPROC',
    status: 'ready',
    execution_state: fallbackExecutionState,
    wave_plan: [
      { wave: 1, programs: ['ACCTPROC'] },
      { wave: 2, programs: ['CUSTOMER'] },
    ],
    risk_flags: ['INTER_PROGRAM_CALL', 'COPYBOOK_DEPENDENCY'],
    paragraph_status: { '0000-MAIN': 'translated', '2000-PROCESS': 'flagged', '2100-CLASSIFY': 'translated' },
  },
];

const fallbackDetail: ModernizationProgramDetail = {
  program_id: 'ACCTPROC',
  status: 'ready',
  execution_state: fallbackExecutionState,
  artifacts: {
    dashboard: {
      risk_flags: ['INTER_PROGRAM_CALL', 'COPYBOOK_DEPENDENCY'],
    },
    wave_plan: {
      wave_plan: [
        { wave: 1, programs: ['ACCTPROC'] },
        { wave: 2, programs: ['CUSTOMER'] },
      ],
    },
  },
  paragraph_translation: {
    paragraph_status: { '0000-MAIN': 'translated', '2000-PROCESS': 'flagged', '2100-CLASSIFY': 'translated' },
    paragraphs: [
      {
        paragraph_id: '0000-MAIN',
        status: 'translated',
        cobol: 'PERFORM 1000-INITIALIZE | PERFORM 2000-PROCESS | PERFORM 3000-FINALIZE',
        translated_code: 'def main() -> None:\n    initialize()\n    process()\n    finalize()',
        notes: 'Control flow translated cleanly.',
        confidence: 0.92,
      },
      {
        paragraph_id: '2000-PROCESS',
        status: 'flagged',
        cobol: "READ ACCT-FILE | PERFORM 2100-CLASSIFY | CALL 'CUSTOMER'",
        translated_code: 'def process() -> None:\n    record = read_account()\n    classify(record)\n    customer_main()',
        notes: 'Cross-program call needs orchestration review.',
        confidence: 0.74,
      },
      {
        paragraph_id: '2100-CLASSIFY',
        status: 'translated',
        cobol: "EVALUATE TRUE | WHEN CHECKING | DISPLAY 'OVERDRAFT'",
        translated_code: "def classify(record):\n    if record.type == 'C' and record.balance < 0:\n        alert_overdraft(record)",
        notes: 'Business-rule extraction aligned with the dependency graph.',
        confidence: 0.88,
      },
    ],
  },
};

const fallbackGraph: { graph: { cross_program_links: ModernizationGraphLink[] } } = {
  graph: {
    cross_program_links: [
      { source: 'ACCTPROC:2000-PROCESS', target: 'CUSTOMER', relation: 'call', file: 'ACCTPROC.cbl' },
      { source: 'ACCTPROC', target: 'COMMON', relation: 'copy', file: 'ACCTPROC.cbl' },
    ],
  },
};

const flagSeverity: Record<string, 'HIGH' | 'MEDIUM' | 'LOW'> = {
  INTER_PROGRAM_CALL: 'HIGH',
  COPYBOOK_DEPENDENCY: 'MEDIUM',
};

function statusTone(status: string): string {
  if (status === 'translated' || status === 'ready') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if (status === 'flagged') return 'text-amber-200 bg-amber-500/10 border-amber-500/30';
  return 'text-rose-200 bg-rose-500/10 border-rose-500/30';
}

function executionTone(status: ExecutionState['status']): string {
  if (status === 'RUNNING') return 'text-sky-200 bg-sky-500/10 border-sky-500/30';
  if (status === 'SUCCEEDED') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if (status === 'FAILED') return 'text-rose-200 bg-rose-500/10 border-rose-500/30';
  return 'text-slate-300 bg-slate-500/10 border-slate-500/30';
}

function severityTone(severity: 'HIGH' | 'MEDIUM' | 'LOW'): string {
  if (severity === 'HIGH') return 'text-rose-200 bg-rose-500/10 border-rose-500/30';
  if (severity === 'MEDIUM') return 'text-amber-200 bg-amber-500/10 border-amber-500/30';
  return 'text-emerald-200 bg-emerald-500/10 border-emerald-500/30';
}

function confidenceTone(confidence: number | undefined): string {
  if ((confidence ?? 0) > 0.85) return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if ((confidence ?? 0) >= 0.6) return 'text-amber-200 bg-amber-500/10 border-amber-500/30';
  return 'text-rose-200 bg-rose-500/10 border-rose-500/30';
}

function formatTimestamp(value?: string | number): string {
  if (!value) return 'Unavailable';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unavailable';
  return date.toLocaleString();
}

function toExecutionState(value: any, fallback?: ExecutionState): ExecutionState {
  const status = String(value?.status ?? fallback?.status ?? 'UNKNOWN').toUpperCase() as ExecutionState['status'];
  return {
    executionId: String(value?.executionId ?? value?.execution_id ?? fallback?.executionId ?? ''),
    status: ['RUNNING', 'SUCCEEDED', 'FAILED', 'UNKNOWN'].includes(status) ? status : 'UNKNOWN',
    startedAt: value?.startedAt ?? value?.started_at ?? fallback?.startedAt,
    updatedAt: value?.updatedAt ?? value?.updated_at ?? fallback?.updatedAt,
    rawStatus: value?.rawStatus ?? value?.raw_status ?? fallback?.rawStatus,
  };
}

export default function ModernizationTab() {
  const [programs, setPrograms] = useState<ModernizationProgramSummary[]>(fallbackPrograms);
  const [selectedProgram, setSelectedProgram] = useState('ACCTPROC');
  const [detail, setDetail] = useState<ModernizationProgramDetail>(fallbackDetail);
  const [graphLinks, setGraphLinks] = useState<ModernizationGraphLink[]>(fallbackGraph.graph.cross_program_links);
  const [executionState, setExecutionState] = useState<ExecutionState>(fallbackExecutionState);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [usingFallback, setUsingFallback] = useState(false);
  const [actionMessage, setActionMessage] = useState('');
  const pollRef = useRef<number | null>(null);

  const wavePlan = useMemo(
    () => detail.artifacts?.wave_plan?.wave_plan ?? programs.find((item) => item.file_id === selectedProgram)?.wave_plan ?? [],
    [detail, programs, selectedProgram],
  );

  const paragraphs: ParagraphTranslationRecord[] = detail.paragraph_translation?.paragraphs ?? [];
  const riskFlags: string[] = detail.artifacts?.dashboard?.risk_flags ?? programs.find((item) => item.file_id === selectedProgram)?.risk_flags ?? [];

  const loadPrograms = useCallback(async () => {
    try {
      const data = await api.listModernizationPrograms();
      if (data.programs?.length) {
        setPrograms(data.programs);
        setSelectedProgram((current) => {
          const exists = data.programs.some((program: ModernizationProgramSummary) => program.file_id === current);
          return exists ? current : data.programs[0].file_id;
        });
        setUsingFallback(false);
      }
    } catch (err) {
      console.error('Modernization programs load failed', err);
      setPrograms(fallbackPrograms);
      setSelectedProgram('ACCTPROC');
      setUsingFallback(true);
      setError('Live modernization data is temporarily unavailable. Showing fallback demo data.');
    }
  }, []);

  const loadProgram = useCallback(
    async (programId: string) => {
      setIsLoading(true);
      setActionMessage('');
      try {
        const [program, graph] = await Promise.all([
          api.getModernizationProgram(programId),
          api.getModernizationGraph(programId),
        ]);
        setDetail(program);
        setGraphLinks(graph.graph?.cross_program_links ?? []);
        setExecutionState(
          toExecutionState(
            program.execution_state ?? programs.find((item) => item.file_id === programId)?.execution_state,
            fallbackExecutionState,
          ),
        );
        setError('');
        setUsingFallback(false);
      } catch (err) {
        console.error('Modernization program load failed', { programId, err });
        setDetail(fallbackDetail);
        setGraphLinks(fallbackGraph.graph.cross_program_links);
        setExecutionState(fallbackExecutionState);
        setUsingFallback(true);
        setError('Live modernization data is temporarily unavailable. Showing fallback demo data.');
      } finally {
        setIsLoading(false);
      }
    },
    [programs],
  );

  const refreshProgram = useCallback(async () => {
    setError('');
    await loadPrograms();
    await loadProgram(selectedProgram);
  }, [loadProgram, loadPrograms, selectedProgram]);

  useEffect(() => {
    void loadPrograms();
  }, [loadPrograms]);

  useEffect(() => {
    void loadProgram(selectedProgram);
  }, [loadProgram, selectedProgram]);

  useEffect(() => {
    console.info('Modernization execution state', executionState);
  }, [executionState]);

  useEffect(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }

    if (!executionState.executionId || executionState.status !== 'RUNNING') {
      return;
    }

    pollRef.current = window.setInterval(async () => {
      try {
        const latest = await api.getExecutionStatus(executionState.executionId);
        setExecutionState((current) => {
          const next = toExecutionState(latest, current);
          if (next.status !== current.status) {
            console.info('Modernization execution status changed', { from: current.status, to: next.status, executionId: next.executionId });
          }
          return next;
        });
      } catch (err) {
        console.error('Modernization execution polling failed', { executionId: executionState.executionId, err });
      }
    }, 5000);

    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [executionState.executionId, executionState.status]);

  async function handleApprove() {
    try {
      const response = await api.approveModernization(selectedProgram);
      setExecutionState((current) =>
        toExecutionState(
          {
            executionId: response.execution_id,
            status: 'SUCCEEDED',
            updatedAt: new Date().toISOString(),
          },
          current,
        ),
      );
      setActionMessage(`Approve request sent successfully for execution ${response.execution_id}.`);
    } catch (err) {
      console.error('Modernization approve failed', { selectedProgram, err });
      setActionMessage('Approve request failed. Verify the modernization API endpoint is reachable.');
      setError('Approve request failed. The backend did not accept the approval action.');
    }
  }

  async function handleRetry() {
    try {
      const response = await api.retryModernization(selectedProgram);
      setExecutionState((current) =>
        toExecutionState(
          {
            executionId: response.execution_id,
            status: 'RUNNING',
            startedAt: current.startedAt ?? new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          },
          current,
        ),
      );
      setActionMessage(`Retry request sent successfully for execution ${response.execution_id}.`);
    } catch (err) {
      console.error('Modernization retry failed', { selectedProgram, err });
      setActionMessage('Retry request failed. Verify the modernization API endpoint is reachable.');
      setError('Retry request failed. The backend did not accept the retry action.');
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-slate-950 text-slate-100">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
        <div className="rounded-3xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-950 to-slate-900 p-6 shadow-2xl">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-300">
                <Waypoints className="h-3.5 w-3.5" />
                Modernization Control Plane
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">WinFrame-style demo visibility on top of the current MVP</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-400">
                Dependency graph, wave planning, paragraph-level translation status, and escalation signals are layered onto the existing parser,
                graph, MCP, and Step Functions flow.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => void refreshProgram()}
                className="rounded-2xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100 transition hover:border-cyan-400"
                title="Refresh modernization data"
              >
                Refresh
              </button>
              <button
                onClick={() => void handleRetry()}
                className="rounded-2xl border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100 transition hover:border-cyan-400"
              >
                Retry
              </button>
              <button
                onClick={() => void handleApprove()}
                className="rounded-2xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
              >
                Approve
              </button>
            </div>
          </div>

          <div className="mt-5 grid gap-4 rounded-2xl border border-slate-800 bg-slate-950/80 p-4 md:grid-cols-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Execution ID</div>
              <div className="mt-2 text-sm font-semibold text-slate-100">{executionState.executionId || 'Unavailable'}</div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Status</div>
              <div className="mt-2">
                <span className={`rounded-full border px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${executionTone(executionState.status)}`}>
                  {executionState.status}
                </span>
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Last Updated</div>
              <div className="mt-2 text-sm text-slate-200">{formatTimestamp(executionState.updatedAt)}</div>
            </div>
          </div>

          {isLoading && (
            <div className="mt-4 flex items-center gap-2 rounded-2xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-200">
              <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
              Loading modernization data...
            </div>
          )}
          {error && (
            <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
              {error}
            </div>
          )}
          {usingFallback && !error && (
            <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-200">
              Fallback demo data is active because the modernization API did not return a live payload.
            </div>
          )}
          {actionMessage && (
            <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-900/80 p-4 text-sm text-slate-200">
              {actionMessage}
            </div>
          )}
        </div>

        <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
          <aside className="rounded-3xl border border-slate-800 bg-slate-900/80 p-4">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">Program Dashboard</div>
            <div className="space-y-3">
              {programs.map((program) => (
                <button
                  key={program.file_id}
                  onClick={() => setSelectedProgram(program.file_id)}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    selectedProgram === program.file_id ? 'border-cyan-400 bg-cyan-400/10' : 'border-slate-800 bg-slate-950 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold">{program.file_id}</div>
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(program.status)}`}>{program.status}</span>
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-400">
                    <Layers3 className="h-3.5 w-3.5" />
                    Wave {program.wave_plan?.[0]?.wave ?? 1}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {(program.risk_flags ?? []).slice(0, 2).map((flag) => {
                      const severity = flagSeverity[flag] ?? 'LOW';
                      return (
                        <span key={flag} className={`rounded-full border px-2 py-1 text-[10px] uppercase tracking-[0.14em] ${severityTone(severity)}`}>
                          [{severity}] {flag.replaceAll('_', ' ')}
                        </span>
                      );
                    })}
                  </div>
                </button>
              ))}
            </div>
          </aside>

          <div className="grid gap-6">
            <section className="grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <GitBranch className="h-4 w-4 text-cyan-300" />
                  Dependency Graph
                </div>
                <div className="mt-4 text-3xl font-semibold">{graphLinks.length}</div>
                <p className="mt-2 text-sm text-slate-400">Cross-file links detected for the selected program.</p>
              </div>
              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5" title="Grouped based on dependency graph">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <Waypoints className="h-4 w-4 text-cyan-300" />
                  Wave Plan
                </div>
                <div className="mt-4 text-3xl font-semibold">{wavePlan.length}</div>
                <p className="mt-2 text-sm text-slate-400">Migration waves generated from in-memory dependency traversal.</p>
              </div>
              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <ShieldAlert className="h-4 w-4 text-cyan-300" />
                  Risk Flags
                </div>
                <div className="mt-4 text-3xl font-semibold">{riskFlags.length}</div>
                <p className="mt-2 text-sm text-slate-400">Flagged constructs surfaced from existing AST and graph artifacts.</p>
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-4 flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <GitBranch className="h-4 w-4 text-cyan-300" />
                  Dependency Graph
                </div>
                <div className="space-y-3">
                  {graphLinks.map((link) => (
                    <div key={`${link.source}-${link.target}-${link.relation}`} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-semibold text-slate-100">
                            {link.source} <span className="text-slate-500">→</span> {link.target}
                          </div>
                          <div className="mt-1 text-xs text-slate-500">{link.file ?? 'derived from graph output'}</div>
                        </div>
                        <div className="rounded-full bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-200">
                          {String(link.relation).toUpperCase()}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-4 flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <Layers3 className="h-4 w-4 text-cyan-300" />
                  Wave Plan
                </div>
                <div className="space-y-4">
                  {wavePlan.map((wave, index) => (
                    <div key={wave.wave} className="rounded-2xl border border-slate-800 bg-slate-950 p-4" title="Grouped based on dependency graph">
                      <div className="text-sm font-semibold text-slate-100">
                        Wave {wave.wave} ({index === 0 ? 'Independent' : `Depends on Wave ${Math.max(1, wave.wave - 1)}`})
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {wave.programs.map((program) => (
                          <span key={program} className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-200">
                            {program}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                  Retry and escalation remain governed by the existing Step Functions pipeline. This tab is only surfacing the state already written by the platform.
                </div>
              </div>
            </section>

            <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-4 flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <RefreshCcw className="h-4 w-4 text-cyan-300" />
                  Paragraph Translation View
                </div>
                <div className="space-y-4">
                  {paragraphs.map((paragraph) => (
                    <div key={paragraph.paragraph_id} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
                      <div className="mb-3 flex items-center justify-between gap-3">
                        <div className="text-sm font-semibold">{paragraph.paragraph_id}</div>
                        <div className="flex items-center gap-2">
                          {typeof paragraph.confidence === 'number' && (
                            <span className={`rounded-full border px-2 py-0.5 text-[11px] ${confidenceTone(paragraph.confidence)}`}>
                              Confidence: {paragraph.confidence.toFixed(2)}
                            </span>
                          )}
                          <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(paragraph.status)}`}>{paragraph.status}</span>
                        </div>
                      </div>
                      <div className="grid gap-4 lg:grid-cols-2">
                        <div>
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">COBOL</div>
                          <pre className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900 p-3 text-xs text-slate-300">{paragraph.cobol}</pre>
                        </div>
                        <div>
                          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">Translated Code</div>
                          <pre className="overflow-x-auto rounded-2xl border border-slate-800 bg-slate-900 p-3 text-xs text-cyan-100">{paragraph.translated_code}</pre>
                        </div>
                      </div>
                      <p className="mt-3 text-sm text-slate-400">{paragraph.notes}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
                <div className="mb-4 flex items-center gap-2 text-xs uppercase tracking-[0.14em] text-slate-400">
                  <AlertTriangle className="h-4 w-4 text-cyan-300" />
                  Flags & Escalation
                </div>
                <div className="space-y-3">
                  {riskFlags.length ? (
                    riskFlags.map((flag) => {
                      const severity = flagSeverity[flag] ?? 'LOW';
                      return (
                        <div key={flag} className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950 p-4">
                          <ShieldAlert className={`h-4 w-4 ${severity === 'HIGH' ? 'text-rose-300' : severity === 'MEDIUM' ? 'text-amber-300' : 'text-emerald-300'}`} />
                          <div className="flex flex-col gap-1">
                            <div className={`w-fit rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] ${severityTone(severity)}`}>
                              [{severity}]
                            </div>
                            <div className="text-sm text-slate-200">{flag.replaceAll('_', ' ')}</div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="flex items-center gap-3 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-200">
                      <CheckCircle2 className="h-4 w-4" />
                      No high-risk flags for the current program.
                    </div>
                  )}
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
