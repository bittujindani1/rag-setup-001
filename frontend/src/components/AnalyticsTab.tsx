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

  async function handleUpload() {
    if (!uploadFile || !datasetDraft.trim()) return
    try {
      setBusy(true)
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
      setUploadFile(null)
      pushToast(`Analytics dataset ${response.dataset_id} uploaded with ${response.row_count} rows.`, 'success')
      await loadDatasets(response.dataset_id)
      await hydrateDashboard(response.dataset_id)
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Analytics upload failed.', 'error')
    } finally {
      setBusy(false)
    }
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
          <button type="button" onClick={() => void handleUpload()} disabled={busy || !uploadFile || !datasetDraft.trim()}>
            {busy ? 'Working...' : 'Upload dataset'}
          </button>
        </div>
      </header>

      <div className="analytics-layout">
        <aside className="analytics-sidebar">
          <div className="side-card analytics-side-card">
            <div className="panel-head tight">
              <h3>Datasets</h3>
            </div>
            <div className="analytics-dataset-list">
              {datasets.length === 0 ? <p className="analytics-empty">Upload a structured dataset to start analytics.</p> : null}
              {datasets.map((dataset) => (
                <button
                  key={dataset.dataset_id}
                  type="button"
                  className={`analytics-dataset-item ${selectedDataset === dataset.dataset_id ? 'active' : ''}`}
                  onClick={() => setSelectedDataset(dataset.dataset_id)}
                >
                  <strong>{dataset.dataset_id}</strong>
                  <span>{dataset.source_name ?? 'Structured dataset'}</span>
                  <small>{formatRelativeTime(dataset.updated_at)}</small>
                </button>
              ))}
            </div>
          </div>
        </aside>

        <div className="analytics-main">
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
            {metrics.slice(0, 3).map((metric) => {
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
                <div className="analytics-result-topline">
                  <span className="analytics-source-pill">{analyticsAnswer.source}</span>
                  <span className="analytics-source-pill subtle">{analyticsAnswer.route}</span>
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
              </div>
            ) : null}
          </section>
        </div>
      </div>
    </section>
  )
}
