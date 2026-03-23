import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type GoalPreset = {
  id: string
  title: string
  goal: string
  icon: string
}

type AgentMessage = {
  type: 'plan' | 'agent_message' | 'synthesis' | 'done'
  run_id?: string
  goal?: string
  steps?: Array<{ agent: string; task: string }>
  agent?: string
  agent_name?: string
  icon?: string
  color?: string
  task?: string
  thought?: string | null
  tool_used?: string | null
  tool_result?: string | null
  output?: string
  timestamp?: number
  total_steps?: number
  created_at?: number
  workspace_id?: string
}

type PastRun = {
  run_id: string
  goal: string
  workspace_id: string
  created_at: number
  status: string
  step_count: number
}

type AgentsTabProps = {
  apiBaseUrl: string
  indexName: string
  workspaceId: string
  pushToast: (message: string, tone: 'info' | 'success' | 'error') => void
}

// ---------------------------------------------------------------------------
// Agent color mapping
// ---------------------------------------------------------------------------

const AGENT_COLORS: Record<string, string> = {
  planner: 'agent-gray',
  analyst: 'agent-teal',
  researcher: 'agent-blue',
  executor: 'agent-amber',
  synthesizer: 'agent-purple',
}

const AGENT_LABELS: Record<string, string> = {
  planner: 'Planner',
  analyst: 'Analyst',
  researcher: 'Researcher',
  executor: 'Executor',
  synthesizer: 'Synthesizer',
}

const TOOL_LABELS: Record<string, string> = {
  athena_sql: 'SQL Query',
  rag_retrieval: 'Knowledge Search',
}

// ---------------------------------------------------------------------------
// Helper: format epoch seconds
// ---------------------------------------------------------------------------
function fmtTime(epoch?: number): string {
  if (!epoch) return ''
  return new Date(epoch * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

// ---------------------------------------------------------------------------
// AgentsTab
// ---------------------------------------------------------------------------

export function AgentsTab({ apiBaseUrl, workspaceId, pushToast }: AgentsTabProps) {
  const [presets, setPresets] = useState<GoalPreset[]>([])
  const [goal, setGoal] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [ragIndex, setRagIndex] = useState('')
  const [running, setRunning] = useState(false)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [planSteps, setPlanSteps] = useState<Array<{ agent: string; task: string }>>([])
  const [runId, setRunId] = useState<string | null>(null)
  const [synthesis, setSynthesis] = useState<string | null>(null)
  const [pastRuns, setPastRuns] = useState<PastRun[]>([])
  const [expandedThoughts, setExpandedThoughts] = useState<Set<number>>(new Set())
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set())
  const timelineRef = useRef<HTMLDivElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Load presets on mount
  useEffect(() => {
    fetch(`${apiBaseUrl}/SFRAG/agents/presets`, {
      headers: _authHeaders(),
    })
      .then((r) => r.json())
      .then((data: { presets: GoalPreset[] }) => setPresets(data.presets ?? []))
      .catch(() => {})
  }, [apiBaseUrl])

  // Load past runs when workspaceId changes
  useEffect(() => {
    _loadPastRuns()
  }, [workspaceId])

  // Scroll to bottom of timeline as new messages arrive
  useEffect(() => {
    if (timelineRef.current) {
      timelineRef.current.scrollTo({ top: timelineRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages, synthesis])

  function _authHeaders(): Record<string, string> {
    const raw = localStorage.getItem('rag-demo-auth-session')
    if (!raw) return {}
    try {
      const session = JSON.parse(raw) as { authorization?: string }
      return session.authorization ? { Authorization: session.authorization } : {}
    } catch {
      return {}
    }
  }

  async function _loadPastRuns() {
    try {
      const response = await fetch(`${apiBaseUrl}/SFRAG/agents/runs?workspace_id=${encodeURIComponent(workspaceId)}`, {
        headers: _authHeaders(),
      })
      if (response.ok) {
        const data = (await response.json()) as { runs: PastRun[] }
        setPastRuns(data.runs ?? [])
      }
    } catch {
      // silent
    }
  }

  const handleRun = useCallback(async () => {
    const trimmedGoal = goal.trim()
    if (!trimmedGoal || running) return

    // Reset state
    setMessages([])
    setPlanSteps([])
    setSynthesis(null)
    setRunId(null)
    setExpandedThoughts(new Set())
    setExpandedTools(new Set())
    setRunning(true)

    abortRef.current = new AbortController()

    try {
      const response = await fetch(`${apiBaseUrl}/SFRAG/agents/runs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ..._authHeaders(),
        },
        body: JSON.stringify({
          goal: trimmedGoal,
          dataset_id: datasetId.trim() || undefined,
          index_name: ragIndex.trim() || undefined,
          workspace_id: workspaceId,
        }),
        signal: abortRef.current.signal,
      })

      if (!response.ok) {
        const text = await response.text()
        throw new Error(text || `HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Parse SSE lines from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        let currentEvent = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6)) as AgentMessage
              payload.type = currentEvent as AgentMessage['type']
              _handleEvent(payload)
            } catch {
              // malformed JSON line
            }
            currentEvent = ''
          }
        }
      }

      // Refresh past runs after completion
      await _loadPastRuns()
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        pushToast(`Agent run failed: ${(err as Error).message}`, 'error')
      }
    } finally {
      setRunning(false)
    }
  }, [goal, datasetId, ragIndex, workspaceId, running, apiBaseUrl, pushToast])

  function _handleEvent(payload: AgentMessage) {
    switch (payload.type) {
      case 'plan':
        setPlanSteps(payload.steps ?? [])
        setMessages((prev) => [...prev, payload])
        break
      case 'agent_message':
        setMessages((prev) => [...prev, payload])
        break
      case 'synthesis':
        setSynthesis(payload.output ?? null)
        setMessages((prev) => [...prev, payload])
        break
      case 'done':
        setRunId(payload.run_id ?? null)
        break
    }
  }

  function handleStop() {
    abortRef.current?.abort()
    setRunning(false)
  }

  function handleCopyReport() {
    if (!synthesis) return
    navigator.clipboard.writeText(synthesis).then(() => pushToast('Report copied to clipboard.', 'success'))
  }

  async function handleLoadPastRun(run: PastRun) {
    try {
      const response = await fetch(
        `${apiBaseUrl}/SFRAG/agents/runs/${run.run_id}?workspace_id=${encodeURIComponent(run.workspace_id)}`,
        { headers: _authHeaders() },
      )
      if (!response.ok) throw new Error('Not found')
      const data = (await response.json()) as { goal: string; messages: AgentMessage[] }
      setGoal(data.goal ?? '')
      setMessages([])
      setPlanSteps([])
      setSynthesis(null)
      setRunId(run.run_id)
      setExpandedThoughts(new Set())
      setExpandedTools(new Set())

      // Re-emit stored messages
      for (const msg of data.messages ?? []) {
        if (msg.type === 'synthesis') {
          setSynthesis(msg.output ?? null)
        }
        setMessages((prev) => [...prev, msg])
      }
      pushToast('Past run loaded.', 'info')
    } catch {
      pushToast('Failed to load past run.', 'error')
    }
  }

  function toggleThought(index: number) {
    setExpandedThoughts((prev) => {
      const next = new Set(prev)
      next.has(index) ? next.delete(index) : next.add(index)
      return next
    })
  }

  function toggleTool(index: number) {
    setExpandedTools((prev) => {
      const next = new Set(prev)
      next.has(index) ? next.delete(index) : next.add(index)
      return next
    })
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="agents-shell">
      {/* Left panel: goal input + timeline */}
      <div className="agents-main">
        {/* Goal input */}
        <div className="agents-goal-panel">
          <div className="agents-goal-header">
            <h2>Agent Collaboration</h2>
            <p className="helper-text">Give the agents a high-level goal. They will plan, analyze, research, and deliver a structured report.</p>
          </div>

          <div className="agents-goal-input-row">
            <textarea
              className="agents-goal-textarea"
              rows={2}
              placeholder="e.g. Prepare a Q1 incident report with root causes and fixes"
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              disabled={running}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  void handleRun()
                }
              }}
            />
            <div className="agents-run-controls">
              {running ? (
                <button className="ghost-button danger-toggle" onClick={handleStop}>
                  Stop
                </button>
              ) : (
                <button
                  className="primary-button agents-run-btn"
                  onClick={() => void handleRun()}
                  disabled={!goal.trim()}
                >
                  Run
                </button>
              )}
            </div>
          </div>

          {/* Optional dataset/index inputs */}
          <div className="agents-config-row">
            <label className="field agents-config-field">
              <span>Dataset ID (for SQL)</span>
              <input
                placeholder="e.g. incident_ops_agent_demo"
                value={datasetId}
                onChange={(e) => setDatasetId(e.target.value)}
                disabled={running}
              />
            </label>
            <label className="field agents-config-field">
              <span>RAG Index (for search)</span>
              <input
                placeholder="e.g. snow_idx"
                value={ragIndex}
                onChange={(e) => setRagIndex(e.target.value)}
                disabled={running}
              />
            </label>
          </div>

          {/* Preset chips */}
          {presets.length > 0 && (
            <div className="agents-presets">
              <span className="agents-presets-label">Quick goals:</span>
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  className="preset-chip"
                  disabled={running}
                  onClick={() => setGoal(preset.goal)}
                  title={preset.goal}
                >
                  {preset.title}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Agent timeline */}
        <div className="agents-timeline-container" ref={timelineRef}>
          {messages.length === 0 && !running && (
            <div className="agents-empty-state">
              <p>Enter a goal above and click <strong>Run</strong> to watch the agents collaborate.</p>
              <p className="helper-text">The Planner decomposes your goal, the Analyst queries real data, the Researcher searches your documents, and the Executor proposes action items.</p>
            </div>
          )}

          {running && messages.length === 0 && (
            <div className="agents-empty-state">
              <div className="agents-spinner" />
              <p>Planning steps...</p>
            </div>
          )}

          {messages.map((msg, index) => {
            if (msg.type === 'plan') {
              return (
                <div key={index} className={`agent-card agent-card-plan ${AGENT_COLORS['planner']}`}>
                  <div className="agent-card-header">
                    <span className="agent-avatar agent-gray">P</span>
                    <div className="agent-card-meta">
                      <span className="agent-name">Planner</span>
                      <span className="agent-time">{fmtTime(msg.timestamp)}</span>
                    </div>
                  </div>
                  <div className="agent-card-body">
                    <p className="agent-task-label">Created {(msg.steps ?? []).length}-step plan:</p>
                    <ol className="agent-plan-list">
                      {(msg.steps ?? []).map((step, i) => (
                        <li key={i}>
                          <span className={`agent-badge ${AGENT_COLORS[step.agent] ?? 'agent-gray'}`}>
                            {AGENT_LABELS[step.agent] ?? step.agent}
                          </span>
                          {' '}{step.task}
                        </li>
                      ))}
                    </ol>
                  </div>
                </div>
              )
            }

            if (msg.type === 'agent_message') {
              const colorClass = AGENT_COLORS[msg.agent ?? ''] ?? 'agent-gray'
              const initial = (msg.agent_name ?? 'A')[0].toUpperCase()
              return (
                <div key={index} className={`agent-card ${colorClass}`}>
                  <div className="agent-card-header">
                    <span className={`agent-avatar ${colorClass}`}>{initial}</span>
                    <div className="agent-card-meta">
                      <span className="agent-name">{msg.agent_name}</span>
                      {msg.tool_used && (
                        <span className="agent-tool-badge">
                          {msg.tool_used === 'athena_sql' ? '⚡ ' : '🔍 '}
                          {TOOL_LABELS[msg.tool_used] ?? msg.tool_used}
                        </span>
                      )}
                      <span className="agent-time">{fmtTime(msg.timestamp)}</span>
                    </div>
                  </div>
                  <div className="agent-card-body">
                    <p className="agent-task-label">{msg.task}</p>

                    {/* Output */}
                    <div className="agent-output">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.output ?? ''}</ReactMarkdown>
                    </div>

                    {/* Collapsible: thought */}
                    {msg.thought && msg.thought !== msg.output && (
                      <div className="agent-collapse">
                        <button
                          className="ghost-button agent-collapse-toggle"
                          onClick={() => toggleThought(index)}
                        >
                          {expandedThoughts.has(index) ? '▲ Hide reasoning' : '▼ Show reasoning'}
                        </button>
                        {expandedThoughts.has(index) && (
                          <pre className="agent-thought">{msg.thought}</pre>
                        )}
                      </div>
                    )}

                    {/* Collapsible: tool result */}
                    {msg.tool_result && (
                      <div className="agent-collapse">
                        <button
                          className="ghost-button agent-collapse-toggle"
                          onClick={() => toggleTool(index)}
                        >
                          {expandedTools.has(index)
                            ? `▲ Hide ${TOOL_LABELS[msg.tool_used ?? ''] ?? 'data'}`
                            : `▼ Show ${TOOL_LABELS[msg.tool_used ?? ''] ?? 'data'}`}
                        </button>
                        {expandedTools.has(index) && (
                          <pre className="agent-tool-result">{msg.tool_result}</pre>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            }

            if (msg.type === 'synthesis') {
              return (
                <div key={index} className="agent-card agent-purple agent-synthesis">
                  <div className="agent-card-header">
                    <span className="agent-avatar agent-purple">✨</span>
                    <div className="agent-card-meta">
                      <span className="agent-name">Synthesizer — Final Report</span>
                      <span className="agent-time">{fmtTime(msg.timestamp)}</span>
                    </div>
                  </div>
                  <div className="agent-card-body">
                    <div className="agent-output agent-synthesis-output">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.output ?? ''}</ReactMarkdown>
                    </div>
                    <div className="agent-actions">
                      <button className="primary-button" onClick={handleCopyReport}>
                        Copy Report
                      </button>
                    </div>
                  </div>
                </div>
              )
            }

            return null
          })}

          {running && messages.length > 0 && messages[messages.length - 1]?.type !== 'synthesis' && (
            <div className="agent-card agent-loading">
              <div className="agents-spinner" />
              <span>Agent working...</span>
            </div>
          )}
        </div>
      </div>

      {/* Right panel: past runs */}
      <div className="agents-sidebar">
        <div className="panel">
          <div className="panel-head tight">
            <h2>Past Runs</h2>
            <button className="ghost-button" onClick={_loadPastRuns} disabled={running}>
              Refresh
            </button>
          </div>
          {pastRuns.length === 0 ? (
            <p className="helper-text">No past runs yet.</p>
          ) : (
            <ul className="past-runs-list">
              {pastRuns.map((run) => (
                <li
                  key={run.run_id}
                  className={`past-run-item ${runId === run.run_id ? 'active' : ''}`}
                  onClick={() => void handleLoadPastRun(run)}
                  title={run.goal}
                >
                  <div className="past-run-goal">{run.goal.length > 60 ? `${run.goal.slice(0, 60)}...` : run.goal}</div>
                  <div className="past-run-meta">
                    <span>{fmtTime(run.created_at)}</span>
                    <span>{run.step_count} steps</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Plan summary (visible after run starts) */}
        {planSteps.length > 0 && (
          <div className="panel">
            <div className="panel-head tight">
              <h2>Run Plan</h2>
            </div>
            <ol className="plan-summary-list">
              {planSteps.map((step, i) => (
                <li key={i} className={`plan-step ${AGENT_COLORS[step.agent] ?? 'agent-gray'}`}>
                  <span className={`agent-badge ${AGENT_COLORS[step.agent] ?? 'agent-gray'}`}>
                    {AGENT_LABELS[step.agent] ?? step.agent}
                  </span>
                  <span className="plan-step-task">{step.task}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </div>
  )
}
