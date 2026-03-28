import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, GitBranch, Layers3, RefreshCcw, ShieldAlert, Waypoints } from 'lucide-react';
import * as api from '../lib/api';
import { ModernizationGraphLink, ModernizationProgramDetail, ModernizationProgramSummary, ParagraphTranslationRecord } from '../types';

const fallbackPrograms: ModernizationProgramSummary[] = [
  {
    file_id: 'ACCTPROC',
    status: 'ready',
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
      },
      {
        paragraph_id: '2000-PROCESS',
        status: 'flagged',
        cobol: "READ ACCT-FILE | PERFORM 2100-CLASSIFY | CALL 'CUSTOMER'",
        translated_code: 'def process() -> None:\n    record = read_account()\n    classify(record)\n    customer_main()',
        notes: 'Cross-program call needs orchestration review.',
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

function statusTone(status: string): string {
  if (status === 'translated' || status === 'ready') return 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30';
  if (status === 'flagged') return 'text-amber-200 bg-amber-500/10 border-amber-500/30';
  return 'text-rose-200 bg-rose-500/10 border-rose-500/30';
}

export default function ModernizationTab() {
  const [programs, setPrograms] = useState<ModernizationProgramSummary[]>(fallbackPrograms);
  const [selectedProgram, setSelectedProgram] = useState('ACCTPROC');
  const [detail, setDetail] = useState<ModernizationProgramDetail>(fallbackDetail);
  const [graphLinks, setGraphLinks] = useState<ModernizationGraphLink[]>(fallbackGraph.graph.cross_program_links);
  const [loading, setLoading] = useState(true);
  const [actionMessage, setActionMessage] = useState('');

  const modernizationApiBase = api.getModernizationApiBase();
  const actionsEnabled = useMemo(() => {
    try {
      const url = new URL(modernizationApiBase);
      return url.hostname !== 'localhost' && url.hostname !== '127.0.0.1';
    } catch {
      return false;
    }
  }, [modernizationApiBase]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await api.listModernizationPrograms();
        if (!cancelled && data.programs?.length) {
          setPrograms(data.programs);
          setSelectedProgram(data.programs[0].file_id);
        }
      } catch {
        // Keep safe fallback data so the existing V2 UI never breaks.
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadProgram() {
      try {
        const [program, graph] = await Promise.all([
          api.getModernizationProgram(selectedProgram),
          api.getModernizationGraph(selectedProgram),
        ]);
        if (!cancelled) {
          setDetail(program);
          setGraphLinks(graph.graph?.cross_program_links ?? []);
        }
      } catch {
        if (!cancelled) {
          setDetail(fallbackDetail);
          setGraphLinks(fallbackGraph.graph.cross_program_links);
        }
      }
    }
    void loadProgram();
    return () => {
      cancelled = true;
    };
  }, [selectedProgram]);

  const wavePlan = useMemo(
    () => detail.artifacts?.wave_plan?.wave_plan ?? programs.find((item) => item.file_id === selectedProgram)?.wave_plan ?? [],
    [detail, programs, selectedProgram],
  );

  const paragraphs: ParagraphTranslationRecord[] = detail.paragraph_translation?.paragraphs ?? [];
  const riskFlags: string[] = detail.artifacts?.dashboard?.risk_flags ?? programs.find((item) => item.file_id === selectedProgram)?.risk_flags ?? [];

  async function handleApprove() {
    if (!actionsEnabled) {
      setActionMessage('Approve is disabled in the live demo because no public modernization API endpoint is configured yet.');
      return;
    }
    try {
      await api.approveModernization(selectedProgram);
      setActionMessage('Approve request sent successfully.');
    } catch {
      setActionMessage('Approve request failed. Verify the modernization API endpoint is reachable.');
    }
  }

  async function handleRetry() {
    if (!actionsEnabled) {
      setActionMessage('Retry is disabled in the live demo because no public modernization API endpoint is configured yet.');
      return;
    }
    try {
      await api.retryModernization(selectedProgram);
      setActionMessage('Retry request sent successfully.');
    } catch {
      setActionMessage('Retry request failed. Verify the modernization API endpoint is reachable.');
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
                onClick={() => void handleRetry()}
                disabled={!actionsEnabled}
                className={`rounded-2xl border px-4 py-2 text-sm font-medium transition ${
                  actionsEnabled
                    ? 'border-slate-700 bg-slate-900 text-slate-100 hover:border-cyan-400'
                    : 'cursor-not-allowed border-slate-800 bg-slate-900/70 text-slate-500'
                }`}
              >
                Retry
              </button>
              <button
                onClick={() => void handleApprove()}
                disabled={!actionsEnabled}
                className={`rounded-2xl px-4 py-2 text-sm font-semibold transition ${
                  actionsEnabled
                    ? 'bg-cyan-400 text-slate-950 hover:bg-cyan-300'
                    : 'cursor-not-allowed bg-slate-700 text-slate-400'
                }`}
              >
                Approve
              </button>
            </div>
          </div>
          {!actionsEnabled && (
            <div className="mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
              This live V2 view is running in demo mode. Modernization data can still be viewed, but `Approve` and `Retry`
              need a public modernization API endpoint instead of the current local default: <span className="font-semibold">{modernizationApiBase}</span>
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
                    {(program.risk_flags ?? []).slice(0, 2).map((flag) => (
                      <span key={flag} className="rounded-full bg-slate-800 px-2 py-1 text-[10px] uppercase tracking-[0.14em] text-slate-300">
                        {flag.replaceAll('_', ' ')}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
            {loading && <p className="mt-4 text-xs text-slate-500">Loading live modernization data...</p>}
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
              <div className="rounded-3xl border border-slate-800 bg-slate-900 p-5">
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
                          <div className="text-sm font-semibold text-slate-100">{link.source}</div>
                          <div className="mt-1 text-xs text-slate-500">{link.file ?? 'derived from graph output'}</div>
                        </div>
                        <div className="rounded-full bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-cyan-200">
                          {link.relation}
                        </div>
                      </div>
                      <div className="mt-3 text-sm text-slate-300">-&gt; {link.target}</div>
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
                  {wavePlan.map((wave) => (
                    <div key={wave.wave} className="rounded-2xl border border-slate-800 bg-slate-950 p-4">
                      <div className="text-sm font-semibold text-slate-100">Wave {wave.wave}</div>
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
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusTone(paragraph.status)}`}>{paragraph.status}</span>
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
                    riskFlags.map((flag) => (
                      <div key={flag} className="flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-950 p-4">
                        <ShieldAlert className="h-4 w-4 text-amber-300" />
                        <div className="text-sm text-slate-200">{flag.replaceAll('_', ' ')}</div>
                      </div>
                    ))
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
