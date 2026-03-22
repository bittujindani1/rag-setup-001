import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type AnalyticsDataset = {
  dataset_id: string
  source_name?: string
  table_name?: string
  updated_at?: number
  schema_columns?: string[]
}

type AnalyticsSummaryResponse = {
  dataset_id: string
  summary: Record<string, unknown>
  metrics: AnalyticsMetric[]
  source?: string
}

type AnalyticsMetric = {
  metric_id: string
  title: string
  description: string
  type: string
  chart_type: string
  sql: string
}

type AnalyticsQueryResponse = {
  dataset_id: string
  route: string
  reason: string
  sql: string
  result: {
    columns: string[]
    rows: Array<Record<string, string | number | null>>
    source: string
  }
  chart_type: string
  answer: string
  grounded_explanation?: string | null
  grounded_rows?: Array<Record<string, string | number | null>>
  source: string
}

type AnalyticsTabProps = {
  apiBaseUrl: string
  pushToast: (message: string, tone: 'info' | 'success' | 'error') => void
}

const CHART_COLORS = ['#0f766e', '#0ea5e9', '#f59e0b', '#8b5cf6', '#ef4444', '#14b8a6']
const CHART_OPTIONS = ['number', 'bar', 'pie', 'line', 'table'] as const
type ChartOption = (typeof CHART_OPTIONS)[number]

async function apiFetch<T>(apiBaseUrl: string, path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${apiBaseUrl}${path}`, { ...init, headers })
  if (!response.ok) {
    throw new Error((await response.text()) || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

function formatRelativeTime(value?: number): string {
  if (!value) return 'Unknown'
  return new Date(value * 1000).toLocaleString()
}

function formatMetricLabel(value: string): string {
  return value.replace(/^top_/, 'Top ').replace(/_/g, ' ')
}

function formatMetricValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'No data'
  if (typeof value === 'number') return value.toLocaleString()
  const numeric = Number(value)
  if (!Number.isNaN(numeric) && String(value).trim() !== '') {
    return numeric.toLocaleString()
  }
  return String(value)
}

function formatSummaryCardValue(value: unknown): { primary: string; secondary?: string } {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    const label = record.label ?? record.value ?? record.name
    const count = record.count ?? record.total ?? record.rows
    if (label !== undefined) {
      return {
        primary: formatMetricValue(
          typeof label === 'string' || typeof label === 'number' || label === null ? label : String(label),
        ),
        secondary:
          count !== undefined
            ? `${formatMetricValue(typeof count === 'string' || typeof count === 'number' || count === null ? count : String(count))} records`
            : undefined,
      }
    }
  }
  return { primary: formatMetricValue(value as string | number | null | undefined) }
}

function inferChartType(chartType: string, rows: Array<Record<string, string | number | null>>): ChartOption {
  if (!rows.length) return 'table'
  if (chartType === 'number' || (rows.length === 1 && Object.keys(rows[0] ?? {}).length === 1)) return 'number'
  if (chartType === 'line') return 'line'
  if (chartType === 'pie') return 'pie'
  if (chartType === 'table') return 'table'
  return rows.length <= 6 ? 'pie' : 'bar'
}

function availableChartOptions(rows: Array<Record<string, string | number | null>>, baseType: string): ChartOption[] {
  const inferred = inferChartType(baseType, rows)
  if (inferred === 'number') return ['number']
  if (inferred === 'line') return ['line', 'bar', 'table']
  return rows.length <= 6 ? ['pie', 'bar', 'table'] : ['bar', 'table']
}

function suggestedQuestions(datasetId: string): string[] {
  if (datasetId.includes('snow')) {
    return [
      'Which assignment groups handled the most tickets?',
      'Show ticket counts by category.',
      'Which priorities appear most often and explain what is driving them?',
    ]
  }
  if (datasetId.includes('cost')) {
    return [
      'Show monthly cost by service_name.',
      'Which owner_team spends the most?',
      'Which services cost the most and explain the likely optimization focus?',
    ]
  }
  if (datasetId.includes('claims')) {
    return [
      'Show open_claims by region.',
      'How is avg_cycle_days trending over time?',
      'Which region has the highest backlog and explain what stands out?',
    ]
  }
  return [
    'How many rows are in this dataset?',
    'Show the top categories in table format.',
    'Explain what is driving the top segment.',
  ]
}

function AnalyticsChart({
  chartType,
  rows,
}: {
  chartType: ChartOption
  rows: Array<Record<string, string | number | null>>
}) {
  const normalizedRows = useMemo(
    () =>
      rows.map((row) => {
        const entries = Object.entries(row)
        const label = String(entries[0]?.[1] ?? '')
        const rawValue = entries[1]?.[1]
        return {
          label,
          value: typeof rawValue === 'number' ? rawValue : Number(rawValue ?? 0),
        }
      }),
    [rows],
  )

  if (!rows.length) {
    return <p className="analytics-empty">No chartable rows returned.</p>
  }

  if (chartType === 'number') {
    const firstRow = rows[0] ?? {}
    const firstKey = Object.keys(firstRow)[0] ?? 'value'
    return (
      <div className="analytics-number-card">
        <strong>{formatMetricValue(firstRow[firstKey] as string | number | null | undefined)}</strong>
        <span>{formatMetricLabel(firstKey)}</span>
      </div>
    )
  }

  if (chartType === 'table') {
    const columns = Object.keys(rows[0] ?? {})
    return (
      <div className="analytics-table-wrap compact">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${index}-${columns.join('-')}`}>
                {columns.map((column) => (
                  <td key={column}>{formatMetricValue(row[column] as string | number | null | undefined)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  if (chartType === 'line') {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={normalizedRows}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="label" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#0f766e" strokeWidth={3} />
        </LineChart>
      </ResponsiveContainer>
    )
  }

  if (chartType === 'pie') {
    return (
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={normalizedRows} dataKey="value" nameKey="label" outerRadius={90} innerRadius={42}>
            {normalizedRows.map((entry, index) => (
              <Cell key={`${entry.label}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={normalizedRows}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="label" />
        <YAxis />
        <Tooltip />
        <Bar dataKey="value" radius={[10, 10, 0, 0]} fill="#0f766e" />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function AnalyticsTab({ apiBaseUrl, pushToast }: AnalyticsTabProps) {
  const [datasets, setDatasets] = useState<AnalyticsDataset[]>([])
  const [selectedDataset, setSelectedDataset] = useState<string>('')
  const [datasetFilter, setDatasetFilter] = useState('')
  const [openDatasetMenu, setOpenDatasetMenu] = useState<string | null>(null)
  const [datasetDraft, setDatasetDraft] = useState('analytics_demo')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [summary, setSummary] = useState<Record<string, unknown>>({})
  const [metrics, setMetrics] = useState<AnalyticsMetric[]>([])
  const [metricResults, setMetricResults] = useState<Record<string, AnalyticsQueryResponse>>({})
  const [analyticsQuestion, setAnalyticsQuestion] = useState('')
  const [analyticsAnswer, setAnalyticsAnswer] = useState<AnalyticsQueryResponse | null>(null)
  const [metricChartOverrides, setMetricChartOverrides] = useState<Record<string, ChartOption>>({})
  const [answerChartOverride, setAnswerChartOverride] = useState<ChartOption | null>(null)
  const [busy, setBusy] = useState(false)
  const [showUploadWarning, setShowUploadWarning] = useState(false)
  const [uploadStatusMessage, setUploadStatusMessage] = useState('')
  const [uploadStage, setUploadStage] = useState<'idle' | 'uploading' | 'processing' | 'complete'>('idle')
  const selectedDatasetMeta = useMemo(
    () => datasets.find((dataset) => dataset.dataset_id === selectedDataset) ?? null,
    [datasets, selectedDataset],
  )
  const filteredDatasets = useMemo(() => {
    const term = datasetFilter.trim().toLowerCase()
    if (!term) return datasets
    return datasets.filter((dataset) =>
      [dataset.dataset_id, dataset.source_name ?? '', ...(dataset.schema_columns ?? [])]
        .join(' ')
        .toLowerCase()
        .includes(term),
    )
  }, [datasetFilter, datasets])

  async function loadDatasets(selectDataset?: string) {
    const response = await apiFetch<{ datasets: AnalyticsDataset[] }>(apiBaseUrl, '/SFRAG/analytics/datasets')
    setDatasets(response.datasets)
    const next = selectDataset ?? selectedDataset ?? response.datasets[0]?.dataset_id ?? ''
    if (next) {
      setSelectedDataset(next)
    }
    return response.datasets
  }

  async function loadDatasetSummary(datasetId: string) {
    const response = await apiFetch<AnalyticsSummaryResponse>(apiBaseUrl, `/SFRAG/analytics/summary/${datasetId}`)
    setSummary(response.summary ?? {})
    setMetrics(response.metrics ?? [])
    return response
  }

  async function runMetric(datasetId: string, metric: AnalyticsMetric) {
    const response = await apiFetch<AnalyticsQueryResponse>(apiBaseUrl, '/SFRAG/analytics/query', {
      method: 'POST',
      body: JSON.stringify({
        dataset_id: datasetId,
        question: metric.title,
      }),
    })
    setMetricResults((current) => ({ ...current, [metric.metric_id]: response }))
    return response
  }

  async function hydrateDashboard(datasetId: string) {
    const response = await loadDatasetSummary(datasetId)
    const defaultMetrics = response.metrics.filter((metric) => metric.type !== 'summary').slice(0, 3)
    for (const metric of defaultMetrics) {
      await runMetric(datasetId, metric)
    }
  }

  useEffect(() => {
    void loadDatasets()
  }, [])

  useEffect(() => {
    if (selectedDataset) {
      void hydrateDashboard(selectedDataset)
    }
  }, [selectedDataset])

  async function performUpload() {
    if (!uploadFile || !datasetDraft.trim()) return
    try {
      setBusy(true)
      setUploadStage('uploading')
      setUploadStatusMessage(`Uploading ${uploadFile.name} into ${datasetDraft.trim()}...`)
      const form = new FormData()
      form.append('dataset_id', datasetDraft.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, '_'))
      form.append('file', uploadFile)
      const response = await apiFetch<{
        dataset_id: string
        row_count: number
      }>(apiBaseUrl, '/SFRAG/analytics/upload', {
        method: 'POST',
        body: form,
      })
      setUploadStage('processing')
      setUploadStatusMessage(`Processing ${response.row_count} rows for ${response.dataset_id}...`)
      setUploadFile(null)
      pushToast(`Analytics dataset ${response.dataset_id} uploaded with ${response.row_count} rows.`, 'success')
      await loadDatasets(response.dataset_id)
      await hydrateDashboard(response.dataset_id)
      setAnalyticsQuestion('')
      setAnalyticsAnswer(null)
      setUploadStage('complete')
      setUploadStatusMessage(`Analytics dataset ${response.dataset_id} is ready with ${response.row_count} rows.`)
    } catch (error) {
      setUploadStage('idle')
      setUploadStatusMessage('')
      pushToast(error instanceof Error ? error.message : 'Analytics upload failed.', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function handleDeleteDataset(datasetId: string) {
    const confirmed = window.confirm(`Delete analytics dataset "${datasetId}"? This removes its uploaded files, metrics, and Athena table.`)
    if (!confirmed) return
    try {
      setBusy(true)
      setOpenDatasetMenu(null)
      const response = await apiFetch<{
        status: string
        dataset_id: string
        deleted_objects: number
      }>(apiBaseUrl, `/SFRAG/analytics/datasets/${datasetId}`, {
        method: 'DELETE',
      })
      const remaining = await loadDatasets()
      const nextDataset = remaining.find((dataset) => dataset.dataset_id !== datasetId)?.dataset_id ?? ''
      if (selectedDataset === datasetId) {
        setSelectedDataset(nextDataset)
        if (!nextDataset) {
          setSummary({})
          setMetrics([])
          setMetricResults({})
          setAnalyticsAnswer(null)
        }
      }
      pushToast(`Deleted ${response.dataset_id} and removed ${response.deleted_objects} analytics objects.`, 'success')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Dataset deletion failed.', 'error')
    } finally {
      setBusy(false)
    }
  }

  function exportRowsAsCsv() {
    if (!analyticsAnswer?.result.columns?.length) return
    const columns = analyticsAnswer.result.columns
    const escape = (value: string | number | null | undefined) => {
      const text = value === null || value === undefined ? '' : String(value)
      if (text.includes(',') || text.includes('"') || text.includes('\n')) {
        return `"${text.replace(/"/g, '""')}"`
      }
      return text
    }
    const lines = [
      columns.join(','),
      ...analyticsAnswer.result.rows.map((row) => columns.map((column) => escape(row[column] as string | number | null | undefined)).join(',')),
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const slug = (analyticsQuestion.trim() || 'analytics_result').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')
    link.href = url
    link.download = `${selectedDataset || 'dataset'}_${slug || 'result'}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    pushToast('Query result exported as CSV.', 'success')
  }

  function handleUploadIntent() {
    if (!uploadFile || !datasetDraft.trim()) return
    setShowUploadWarning(true)
  }

  async function handleAnalyticsQuery() {
    if (!selectedDataset || !analyticsQuestion.trim()) return
    try {
      setBusy(true)
      const response = await apiFetch<AnalyticsQueryResponse>(apiBaseUrl, '/SFRAG/analytics/query', {
        method: 'POST',
        body: JSON.stringify({
          dataset_id: selectedDataset,
          question: analyticsQuestion,
        }),
      })
      setAnalyticsAnswer(response)
      setAnswerChartOverride(null)
      pushToast('Analytics query executed.', 'success')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Analytics query failed.', 'error')
    } finally {
      setBusy(false)
    }
  }

  const summaryCards = useMemo(() => Object.entries(summary), [summary])

  return (
    <>
      <section className="analytics-shell">
      <header className="analytics-header">
        <div>
          <p className="eyebrow">Structured Analytics</p>
          <h2>Analytics Workbench</h2>
          <p className="helper-text">Upload CSV, JSON, or XLSX datasets into a separate analytics lane backed by S3, Glue, and Athena.</p>
        </div>
        <div className="analytics-upload">
          <input value={datasetDraft} onChange={(event) => setDatasetDraft(event.target.value)} placeholder="dataset_id" />
          <input type="file" accept=".csv,.json,.xlsx" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
          <button type="button" onClick={() => handleUploadIntent()} disabled={busy || !uploadFile || !datasetDraft.trim()}>
            {busy ? 'Working...' : 'Upload dataset'}
          </button>
        </div>
      </header>

      {uploadStatusMessage ? (
        <section className={`analytics-upload-status ${uploadStage}`}>
          <div className="analytics-upload-status-copy">
            <strong>
              {uploadStage === 'uploading'
                ? 'Uploading dataset'
                : uploadStage === 'processing'
                  ? 'Preparing analytics'
                  : uploadStage === 'complete'
                    ? 'Dataset ready'
                    : 'Upload status'}
            </strong>
            <p>{uploadStatusMessage}</p>
          </div>
          <div className="analytics-progress-track" aria-hidden="true">
            <div className={`analytics-progress-bar ${uploadStage}`} />
          </div>
        </section>
      ) : null}

      <div className="analytics-layout">
        <aside className="analytics-sidebar">
          <div className="side-card analytics-side-card">
            <div className="panel-head tight">
              <h3>Datasets</h3>
            </div>
            <div className="analytics-dataset-tools">
              <input
                value={datasetFilter}
                onChange={(event) => setDatasetFilter(event.target.value)}
                placeholder="Search datasets"
                aria-label="Search analytics datasets"
              />
            </div>
            <div className="analytics-dataset-list">
              {datasets.length === 0 ? <p className="analytics-empty">Upload a structured dataset to start analytics.</p> : null}
              {datasets.length > 0 && filteredDatasets.length === 0 ? <p className="analytics-empty">No datasets match this search.</p> : null}
              {filteredDatasets.map((dataset) => (
                <div
                  key={dataset.dataset_id}
                  className={`analytics-dataset-item ${selectedDataset === dataset.dataset_id ? 'active' : ''}`}
                >
                  <div className="analytics-dataset-row">
                    <button
                      type="button"
                      className="analytics-dataset-select"
                      onClick={() => {
                        setSelectedDataset(dataset.dataset_id)
                        setOpenDatasetMenu(null)
                      }}
                    >
                      <strong>{dataset.dataset_id}</strong>
                      <span>{dataset.source_name ?? 'Structured dataset'}</span>
                      <small>{formatRelativeTime(dataset.updated_at)}</small>
                    </button>
                    <div className="analytics-dataset-menu-wrap">
                      <button
                        type="button"
                        className="menu-button analytics-menu-button"
                        aria-label={`Open actions for ${dataset.dataset_id}`}
                        onClick={() => setOpenDatasetMenu((current) => (current === dataset.dataset_id ? null : dataset.dataset_id))}
                      >
                        &#8942;
                      </button>
                      {openDatasetMenu === dataset.dataset_id ? (
                        <div className="thread-menu analytics-dataset-menu">
                          <button
                            type="button"
                            className="thread-menu-item delete"
                            onClick={() => void handleDeleteDataset(dataset.dataset_id)}
                          >
                            Delete dataset
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            {selectedDatasetMeta ? (
              <div className="analytics-dataset-meta">
                <h4>Selected dataset</h4>
                <p>{selectedDatasetMeta.source_name ?? 'Structured upload'}</p>
                <small>{selectedDatasetMeta.schema_columns?.length ?? 0} columns available for analytics.</small>
              </div>
            ) : null}
          </div>
        </aside>

        <div className="analytics-main">
          <section className="analytics-hero-strip">
            <div>
              <h3>Analytics overview</h3>
              <p className="helper-text">
                Use KPI cards for the quick read, then switch charts or ask a natural-language question for deeper analysis.
              </p>
            </div>
            <div className="analytics-query-suggestions">
              {suggestedQuestions(selectedDataset).map((question) => (
                <button
                  key={question}
                  type="button"
                  className="chip"
                  onClick={() => setAnalyticsQuestion(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          </section>

          <div className="analytics-card-grid">
            {summaryCards.map(([key, value]) => {
              const display = formatSummaryCardValue(value)
              return (
                <article key={key} className="analytics-kpi-card">
                  <span>{formatMetricLabel(key)}</span>
                  <strong>{display.primary}</strong>
                  {display.secondary ? <small>{display.secondary}</small> : null}
                </article>
              )
            })}
          </div>

          <div className="analytics-visual-grid">
            {metrics.slice(0, 4).map((metric) => {
              const result = metricResults[metric.metric_id]
              const metricChartOptions = result ? availableChartOptions(result.result.rows, result.chart_type) : []
              const chartChoice = result
                ? (metricChartOverrides[metric.metric_id] ?? inferChartType(result.chart_type, result.result.rows))
                : null
              return (
                <section key={metric.metric_id} className="analytics-visual-card">
                  <div className="panel-head tight">
                    <div>
                      <h3>{metric.title}</h3>
                      <p className="helper-text">{metric.description}</p>
                    </div>
                    <div className="analytics-card-actions">
                      {result ? (
                        <div className="chart-toggle">
                          {metricChartOptions.map((option) => (
                            <button
                              key={`${metric.metric_id}-${option}`}
                              type="button"
                              className={chartChoice === option ? 'active' : ''}
                              onClick={() =>
                                setMetricChartOverrides((current) => ({
                                  ...current,
                                  [metric.metric_id]: option,
                                }))
                              }
                            >
                              {option}
                            </button>
                          ))}
                        </div>
                      ) : null}
                      <button type="button" className="ghost-button" onClick={() => selectedDataset && void runMetric(selectedDataset, metric)}>
                        Refresh
                      </button>
                    </div>
                  </div>
                  {result ? (
                    <AnalyticsChart chartType={chartChoice ?? 'table'} rows={result.result.rows} />
                  ) : (
                    <p className="analytics-empty">Run this metric to load the chart.</p>
                  )}
                </section>
              )
            })}
          </div>

          <section className="analytics-query-card">
            <div className="panel-head tight">
              <div>
                <h3>Analytics Chat</h3>
                <p className="helper-text">Ask for counts, trends, comparisons, or table views. Responses come from executed analytics queries.</p>
              </div>
            </div>
            <div className="analytics-query-box">
              <textarea
                value={analyticsQuestion}
                onChange={(event) => setAnalyticsQuestion(event.target.value)}
                placeholder="How many high-priority network tickets? Show in table format."
              />
              <button type="button" onClick={() => void handleAnalyticsQuery()} disabled={busy || !selectedDataset || !analyticsQuestion.trim()}>
                {busy ? 'Running...' : 'Run analytics'}
              </button>
            </div>

            {analyticsAnswer ? (
              <div className="analytics-result-card">
                <p className="analytics-answer">{analyticsAnswer.answer}</p>
                {analyticsAnswer.grounded_explanation ? (
                  <div className="analytics-insight-card">
                    <span>Grounded explanation</span>
                    <p>{analyticsAnswer.grounded_explanation}</p>
                  </div>
                ) : null}
                <div className="analytics-result-topline">
                  <div className="analytics-result-badges">
                    <span className="analytics-source-pill">{analyticsAnswer.source}</span>
                    <span className="analytics-source-pill subtle">{analyticsAnswer.route}</span>
                  </div>
                  <div className="analytics-result-actions">
                    <button type="button" className="ghost-button" onClick={() => exportRowsAsCsv()}>
                      Export CSV
                    </button>
                    <div className="chart-toggle">
                      {availableChartOptions(analyticsAnswer.result.rows, analyticsAnswer.chart_type).map((option) => (
                        <button
                          key={`answer-${option}`}
                          type="button"
                          className={(answerChartOverride ?? inferChartType(analyticsAnswer.chart_type, analyticsAnswer.result.rows)) === option ? 'active' : ''}
                          onClick={() => setAnswerChartOverride(option)}
                        >
                          {option}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="analytics-chart-frame">
                  <AnalyticsChart
                    chartType={answerChartOverride ?? inferChartType(analyticsAnswer.chart_type, analyticsAnswer.result.rows)}
                    rows={analyticsAnswer.result.rows}
                  />
                </div>
                <div className="analytics-sql">
                  <span>Executed SQL</span>
                  <pre>{analyticsAnswer.sql}</pre>
                </div>
                <div className="analytics-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        {analyticsAnswer.result.columns.map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {analyticsAnswer.result.rows.map((row, index) => (
                        <tr key={`${index}-${analyticsAnswer.sql}`}>
                          {analyticsAnswer.result.columns.map((column) => (
                            <td key={column}>{String(row[column] ?? '')}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {analyticsAnswer.grounded_rows && analyticsAnswer.grounded_rows.length > 0 ? (
                  <div className="analytics-grounded-list">
                    <span>Supporting rows</span>
                    <div className="analytics-table-wrap compact">
                      <table>
                        <thead>
                          <tr>
                            {Object.keys(analyticsAnswer.grounded_rows[0]).map((column) => (
                              <th key={column}>{column}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {analyticsAnswer.grounded_rows.map((row, index) => (
                            <tr key={`grounded-${index}`}>
                              {Object.keys(analyticsAnswer.grounded_rows?.[0] ?? {}).map((column) => (
                                <td key={column}>{formatMetricValue(row[column] as string | number | null | undefined)}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      </div>
      </section>

      {showUploadWarning ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="analytics-upload-warning-title">
            <p className="eyebrow">Upload Warning</p>
            <h2 id="analytics-upload-warning-title">Use only non-sensitive structured data</h2>
            <p className="modal-copy">
              This analytics lane is for safe demo datasets only. Do not upload critical, regulated, confidential, or PII data.
            </p>
            <ul className="policy-list modal-policy-list">
              <li>Supported file types: CSV, JSON, XLSX.</li>
              <li>Best fit: operational datasets, cost tables, KPI exports, ticket histories, and spreadsheet-based summaries.</li>
              <li>Avoid sensitive employee, customer, health, payment, or production secrets in uploads.</li>
              <li>Large datasets may take a little longer because the system profiles schema, writes analytics storage, and prepares KPI cards.</li>
              <li>Upload status will stay visible on the page until the dataset is ready.</li>
            </ul>
            <div className="modal-actions">
              <button
                className="ghost-button"
                onClick={() => {
                  setShowUploadWarning(false)
                  pushToast('Analytics upload cancelled.', 'info')
                }}
              >
                Cancel
              </button>
              <button
                className="primary-button"
                onClick={() => {
                  setShowUploadWarning(false)
                  void performUpload()
                }}
              >
                I Understand, Continue
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}
