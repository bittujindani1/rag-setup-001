import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AnalyticsTab } from './components/AnalyticsTab'
import { AgentsTab } from './components/AgentsTab'
import './App.css'

type Message = {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  citations?: Array<{ pdf_url?: string; filename?: string }>
}

type Thread = {
  id: string
  name: string
  createdAt: string
  metadata?: {
    session_id?: string
    workspace_id?: string
  }
  steps?: Array<{
    type: string
    output?: string
    input?: string
    createdAt?: string
  }>
}

type CategorySummary = {
  category: string
  count: number
}

type DocumentRecord = {
  filename: string
  category: string
  content_type: string
  size_bytes: number
  updated_at: number
}

type UploadResultBanner = {
  filename: string
  category: string
  status: 'indexed'
}

type UploadProgressState = {
  phase: 'idle' | 'selected' | 'uploading' | 'indexed' | 'failed'
  filename?: string
  message?: string
}

type RetrievalResponse = {
  mode: 'answer' | 'clarify'
  response: { content: string }
  citation?: Array<{ pdf_url?: string; filename?: string }>
  categories?: CategorySummary[]
  selected_category?: string | null
  image_query?: {
    extracted_text?: string
    intent?: string
    retrieval_query?: string
    filename?: string
  }
}

type DirectIngestResponse = {
  status: string
  index_name?: string
  imagecount?: number
  tablecount?: number
  category?: string
  content_type?: string
  warnings?: string[]
  processing_mode?: string
  page_count?: number
  message?: string
  detail?: string
}

type PresignedUploadResponse = {
  url: string
  fields: Record<string, string>
  bucket: string
  object_key: string
}

type AsyncIngestResponse = {
  job_id: string
  status: string
}

type IngestJobStatusResponse = {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  index_name?: string
  filename?: string
  source_type?: string
  created_at?: number
  updated_at?: number
  error?: string
  result?: DirectIngestResponse
}

type FeedbackResponse = {
  status: string
}

type UploadPolicy = {
  workspace_id: string
  is_exception_workspace: boolean
  exception_workspace_id: string
  supported_types: string[]
  max_upload_mb: number
  workspace_document_limit: number | null
  workspace_document_count: number
  pdf_page_warning_threshold: number | null
  pdf_text_only_threshold: number | null
  pdf_page_hard_limit: number | null
  warnings: string[]
}

type Toast = {
  id: string
  tone: 'info' | 'success' | 'error'
  message: string
}

type AnalyticsDatasetSidebarRecord = {
  dataset_id: string
  source_name?: string
  table_name?: string
  updated_at?: number
  schema_columns?: string[]
}

type AuthSession = {
  username: string
  role: 'admin' | 'user'
  authorization: string
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const DEFAULT_INDEX = import.meta.env.VITE_INDEX_NAME ?? 'statefarm_rag'
const SHARED_WORKSPACE = import.meta.env.VITE_SHARED_INDEX_NAME ?? 'demo-shared'
const SNOW_WORKSPACE = import.meta.env.VITE_SNOW_INDEX_NAME ?? 'snow_idx'
const PERSONAL_WORKSPACE_KEY = 'rag-demo-personal-workspace'
const PERSONAL_WORKSPACES_KEY = 'rag-demo-personal-workspaces'
const ACTIVE_WORKSPACE_KEY = 'rag-demo-active-workspace'
const FEEDBACK_USER_KEY = 'rag-demo-feedback-user'
const THEME_KEY = 'rag-demo-theme'
const AUTH_SESSION_KEY = 'rag-demo-auth-session'
const ANALYTICS_HISTORY_KEY = 'rag-analytics-history'

type ChatStarter = {
  label: string
  prompt: string
  documentFilter?: string | null
}

function normalizeWorkspace(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 64)

  return normalized.length >= 3 ? normalized : DEFAULT_INDEX
}

function generateWorkspaceName(): string {
  const suffix = Math.random().toString(36).slice(2, 8)
  return normalizeWorkspace(`demo-${suffix}`)
}

function summarizeThread(thread: Thread): string {
  const firstUserStep = thread.steps?.find((step) => step.type === 'user_message')
  const rawText = (firstUserStep?.output ?? firstUserStep?.input ?? thread.name ?? 'New chat').trim()
  return rawText.length > 42 ? `${rawText.slice(0, 42)}...` : rawText
}

function nowIso(): string {
  return new Date().toISOString()
}

function createClientId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text()
  if (!text) return `Request failed: ${response.status}`
  try {
    const parsed = JSON.parse(text) as { detail?: string; message?: string; error?: string }
    return parsed.detail || parsed.message || parsed.error || text
  } catch {
    return text
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const rawSession = localStorage.getItem(AUTH_SESSION_KEY)
  if (rawSession && !headers.has('Authorization')) {
    try {
      const session = JSON.parse(rawSession) as AuthSession
      if (session.authorization) {
        headers.set('Authorization', session.authorization)
      }
    } catch {
      localStorage.removeItem(AUTH_SESSION_KEY)
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })
  if (!response.ok) {
    throw new Error(await readErrorMessage(response))
  }
  return response.json() as Promise<T>
}

async function uploadFileToPresignedTarget(target: PresignedUploadResponse, file: File): Promise<void> {
  const formData = new FormData()
  Object.entries(target.fields).forEach(([key, value]) => {
    formData.append(key, value)
  })
  formData.append('file', file)

  const response = await fetch(target.url, {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `S3 upload failed with status ${response.status}`)
  }
}

async function waitForIngestJob(jobId: string): Promise<IngestJobStatusResponse> {
  const maxAttempts = 90
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const job = await apiFetch<IngestJobStatusResponse>(`/SFRAG/ingest-status/${jobId}`)
    if (job.status === 'completed' || job.status === 'failed') {
      return job
    }
    await new Promise((resolve) => window.setTimeout(resolve, attempt < 10 ? 1000 : 2000))
  }
  throw new Error('Indexing timed out before the upload service reported completion.')
}

function mapStepsToMessages(thread?: Thread): Message[] {
  return (
    thread?.steps?.map((step, index) => ({
      role: step.type === 'user_message' ? 'user' : 'assistant',
      content: (step.output ?? step.input ?? '').trim(),
      timestamp: step.createdAt ?? new Date(Date.now() - index * 1000).toISOString(),
    })) ?? []
  )
}

function formatBytes(size: number): string {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function normalizeUploadExtension(filename: string): string {
  const match = filename.toLowerCase().match(/\.[^.]+$/)
  return match?.[0] ?? ''
}

function buildUploadFailureMessage(file: File, uploadPolicy: UploadPolicy | null, error: unknown): string {
  const extension = normalizeUploadExtension(file.name)
  const supportedTypes = uploadPolicy?.supported_types?.map((item) => `.${item.toLowerCase()}`) ?? ['.pdf', '.txt', '.docx', '.xlsx']
  const maxUploadMb = uploadPolicy?.max_upload_mb ?? 5

  if (!supportedTypes.includes(extension)) {
    return `Upload failed: ${extension || 'This file type'} is not supported. Allowed types: ${supportedTypes.join(', ')}.`
  }

  if (file.size > maxUploadMb * 1024 * 1024) {
    return `Upload failed: ${file.name} exceeds the ${maxUploadMb} MB workspace limit. Please use a smaller file.`
  }

  if (
    uploadPolicy?.workspace_document_limit &&
    uploadPolicy.workspace_document_count >= uploadPolicy.workspace_document_limit
  ) {
    return `Upload failed: this workspace already has ${uploadPolicy.workspace_document_limit} indexed documents. Delete an older file or switch to a new workspace.`
  }

  const rawMessage = error instanceof Error ? error.message : 'Upload failed.'
  const normalized = rawMessage.toLowerCase()

  if (!navigator.onLine) {
    return 'Upload failed because your browser appears to be offline. Reconnect to the network and try again.'
  }

  if (normalized.includes('unauthorized') || normalized.includes('401')) {
    return 'Upload failed because your session is no longer authorized. Please sign in again and retry the upload.'
  }

  if (normalized.includes('failed to fetch') || normalized.includes('networkerror')) {
    return 'Upload failed because the app could not reach the upload service. This is usually a network issue, expired session, CORS block, or backend timeout. Please retry, and if it persists, sign in again.'
  }

  if (normalized.includes('unsupported file type') || normalized.includes('unexpected content type')) {
    return rawMessage
  }

  if (normalized.includes('workspace document limit') || normalized.includes('page limit') || normalized.includes('exceeds')) {
    return rawMessage
  }

  return rawMessage
}

function buildGreeting(workspaceType: 'personal' | 'shared' | 'snow'): Message {
  const content =
    workspaceType === 'snow'
      ? 'Hello. You are in the ServiceNow workspace. Ask about recurring incidents, priorities, assignment groups, SLA patterns, or request a quick ticket summary.'
      : workspaceType === 'shared'
        ? 'Hello. You are in the shared demo workspace. Ask for a summary, key themes, policy details, or evidence-backed answers from the indexed documents.'
        : 'Hello. Upload a document or ask a question about your current workspace. If you are not sure where to begin, start with a quick summary of the uploaded documents.'

  return { role: 'assistant', content, timestamp: nowIso() }
}

function normalizeDocumentHint(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, '')
}

function pickPreferredDocument(documents: DocumentRecord[], preferredFilename?: string | null): DocumentRecord | null {
  if (preferredFilename) {
    const matched = documents.find((document) => document.filename === preferredFilename)
    if (matched) return matched
  }
  if (documents.length === 0) return null
  return [...documents].sort((left, right) => (right.updated_at ?? 0) - (left.updated_at ?? 0))[0]
}

function inferDocumentFilter(
  prompt: string,
  documents: DocumentRecord[],
  preferredFilename?: string | null,
): string | null {
  const loweredPrompt = prompt.toLowerCase()
  const normalizedPrompt = normalizeDocumentHint(prompt)
  for (const document of documents) {
    const loweredFilename = document.filename.toLowerCase()
    const normalizedFilename = normalizeDocumentHint(document.filename)
    const normalizedStem = normalizeDocumentHint(document.filename.replace(/\.[^.]+$/, ''))
    if (
      loweredFilename.includes(loweredPrompt)
      || loweredPrompt.includes(loweredFilename)
      || (normalizedFilename && normalizedPrompt.includes(normalizedFilename))
      || (normalizedStem && normalizedPrompt.includes(normalizedStem))
    ) {
      return document.filename
    }
  }

  const preferredDocument = pickPreferredDocument(documents, preferredFilename)
  if (!preferredDocument) return null
  if (documents.length !== 1) return null
  if (
    loweredPrompt.includes('uploaded document')
    || loweredPrompt.includes('uploaded pdf')
    || loweredPrompt.includes('uploaded file')
    || loweredPrompt.includes('uploaded documents')
    || loweredPrompt.includes('this document')
    || loweredPrompt.includes('this pdf')
    || loweredPrompt.includes('policy name')
    || loweredPrompt.includes('summarize')
  ) {
    return preferredDocument.filename
  }
  return null
}

function summarizePrompt(
  workspaceType: 'personal' | 'shared' | 'snow',
  documents: DocumentRecord[],
  preferredFilename?: string | null,
): string {
  if (workspaceType === 'snow') {
    return 'Summarize the ServiceNow ticket dataset with top categories, priorities, assignment groups, and recurring issues.'
  }
  const preferredDocument = pickPreferredDocument(documents, preferredFilename)
  if (preferredDocument) {
    return `Summarize the document "${preferredDocument.filename}" and highlight the top takeaways, risks, and recommended next steps.`
  }
  const names = documents.map((document) => document.filename).filter(Boolean)
  if (names.length === 1) {
    return `Summarize the document "${names[0]}" and highlight the top takeaways, risks, and recommended next steps.`
  }
  if (names.length > 1) {
    return `Summarize these uploaded documents: ${names.join(', ')}. Highlight the top takeaways, risks, and recommended next steps for each document.`
  }
  return 'Summarize the uploaded documents in this workspace and highlight the top takeaways, risks, and recommended next steps.'
}

function buildChatStarters(
  workspaceType: 'personal' | 'shared' | 'snow',
  documents: DocumentRecord[],
  preferredFilename?: string | null,
): ChatStarter[] {
  if (workspaceType === 'snow') {
    return [
      {
        label: 'Dataset summary',
        prompt: 'Summarize the ServiceNow ticket dataset with top categories, priorities, and recurring issues.',
      },
      {
        label: 'Recurring issues',
        prompt: 'What are the top recurring incident patterns in the ServiceNow tickets?',
      },
      {
        label: 'Assignment groups',
        prompt: 'Show the main assignment groups and the types of tickets they handle most often.',
      },
    ]
  }

  const preferredDocument = pickPreferredDocument(documents, preferredFilename)
  if (preferredDocument) {
    const filename = preferredDocument.filename
    return [
      {
        label: 'Summarize document',
        prompt: `Summarize the document "${filename}" and highlight the top takeaways.`,
        documentFilter: filename,
      },
      {
        label: 'Key topics',
        prompt: `What are the key topics covered in the document "${filename}"?`,
        documentFilter: filename,
      },
      {
        label: 'Risks and actions',
        prompt: `List the most important risks, actions, or next steps mentioned in the document "${filename}".`,
        documentFilter: filename,
      },
    ]
  }

  const names = documents.map((document) => document.filename).filter(Boolean)
  if (names.length > 1) {
    const joined = names.join(', ')
    return [
      {
        label: 'Summarize docs',
        prompt: `Summarize these uploaded documents: ${joined}. Highlight the top takeaways from each document.`,
      },
      {
        label: 'Key topics',
        prompt: `What are the key topics covered across these uploaded documents: ${joined}?`,
      },
      {
        label: 'Compare documents',
        prompt: `Compare these uploaded documents: ${joined}. Show the main themes, risks, and recommended actions from each one.`,
      },
    ]
  }

  return workspaceType === 'shared'
    ? [
        { label: 'Shared summary', prompt: 'Summarize the shared demo documents and highlight the top takeaways.' },
        { label: 'Main topics', prompt: 'What are the main topics covered in the shared knowledge base?' },
        { label: 'Where to start', prompt: 'Which sections should I read first for a quick understanding?' },
      ]
    : [
        { label: 'Summarize docs', prompt: 'Summarize the uploaded documents and highlight the top takeaways.' },
        { label: 'Key topics', prompt: 'What are the key topics covered in the uploaded documents?' },
        { label: 'Risks and actions', prompt: 'List the most important risks, actions, or next steps from the uploaded files.' },
      ]
}

function App() {
  const [authSession, setAuthSession] = useState<AuthSession | null>(null)
  const [loginUsername, setLoginUsername] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [appView, setAppView] = useState<'chat' | 'analytics' | 'agents'>('chat')
  const [personalWorkspace, setPersonalWorkspace] = useState(DEFAULT_INDEX)
  const [personalWorkspaceHistory, setPersonalWorkspaceHistory] = useState<string[]>([])
  const [workspaceDraft, setWorkspaceDraft] = useState(DEFAULT_INDEX)
  const [activeWorkspace, setActiveWorkspace] = useState<'personal' | 'shared' | 'snow'>('personal')
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string>('')
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [lastUploadResult, setLastUploadResult] = useState<UploadResultBanner | null>(null)
  const [categories, setCategories] = useState<CategorySummary[]>([])
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadProgress, setUploadProgress] = useState<UploadProgressState>({ phase: 'idle' })
  const [chatImageFile, setChatImageFile] = useState<File | null>(null)
  const [feedbackUserId, setFeedbackUserId] = useState('')
  const [feedbackText, setFeedbackText] = useState('')
  const [uploadPolicy, setUploadPolicy] = useState<UploadPolicy | null>(null)
  const [uploadPolicyNotices, setUploadPolicyNotices] = useState<string[]>([])
  const [showUploadWarning, setShowUploadWarning] = useState(false)
  const [openMenuThreadId, setOpenMenuThreadId] = useState<string | null>(null)
  const [confirmDeleteThreadId, setConfirmDeleteThreadId] = useState<string | null>(null)
  const [openWorkspaceMenuId, setOpenWorkspaceMenuId] = useState<string | null>(null)
  const [confirmDeleteWorkspaceId, setConfirmDeleteWorkspaceId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('Ready')
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [documentsOpen, setDocumentsOpen] = useState(true)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [analyticsDatasets, setAnalyticsDatasets] = useState<AnalyticsDatasetSidebarRecord[]>([])
  const [analyticsSelectedDataset, setAnalyticsSelectedDataset] = useState('')
  const [analyticsSelectedDatasetMeta, setAnalyticsSelectedDatasetMeta] = useState<AnalyticsDatasetSidebarRecord | null>(null)
  const [analyticsDatasetFilter, setAnalyticsDatasetFilter] = useState('')
  const [analyticsOpenDatasetMenuId, setAnalyticsOpenDatasetMenuId] = useState<string | null>(null)
  const [analyticsConfirmDeleteDatasetId, setAnalyticsConfirmDeleteDatasetId] = useState<string | null>(null)
  const chatLogRef = useRef<HTMLDivElement | null>(null)
  const menuContainerRef = useRef<HTMLDivElement | null>(null)

  const indexName = useMemo(() => {
    if (activeWorkspace === 'shared') return SHARED_WORKSPACE
    if (activeWorkspace === 'snow') return SNOW_WORKSPACE
    return personalWorkspace
  }, [activeWorkspace, personalWorkspace])
  const isSharedWorkspace = activeWorkspace === 'shared'
  const isSnowWorkspace = activeWorkspace === 'snow'
  const isReadOnlyWorkspace = isSharedWorkspace || isSnowWorkspace
  const preferredDocument = useMemo(
    () => pickPreferredDocument(documents, lastUploadResult?.filename ?? null),
    [documents, lastUploadResult],
  )
  const chatStarterPrompts = useMemo(
    () => buildChatStarters(activeWorkspace, documents, preferredDocument?.filename ?? null),
    [activeWorkspace, documents, preferredDocument],
  )
  const sortedThreads = useMemo(
    () =>
      [...threads].sort(
        (left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
      ),
    [threads],
  )
  const historicalThreads = useMemo(
    () => sortedThreads.filter((thread) => thread.id !== activeThreadId),
    [activeThreadId, sortedThreads],
  )
  const orderedMessages = useMemo(() => [...messages], [messages])
  const filteredAnalyticsDatasets = useMemo(() => {
    const term = analyticsDatasetFilter.trim().toLowerCase()
    if (!term) return analyticsDatasets
    return analyticsDatasets.filter((dataset) =>
      [dataset.dataset_id, dataset.source_name ?? '', ...(dataset.schema_columns ?? [])]
        .join(' ')
        .toLowerCase()
        .includes(term),
    )
  }, [analyticsDatasetFilter, analyticsDatasets])
  const logoSrc = theme === 'dark' ? '/logo_dark.PNG' : '/logo_light.PNG'
  const isAdmin = authSession?.role === 'admin'

  function pushToast(message: string, tone: Toast['tone']) {
    const id = createClientId()
    setToasts((current) => [...current, { id, tone, message }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 3500)
  }

  function storeWorkspaceHistory(next: string[]) {
    setPersonalWorkspaceHistory(next)
    localStorage.setItem(PERSONAL_WORKSPACES_KEY, JSON.stringify(next))
  }

  const refreshThreads = useCallback(async (workspaceId = indexName) => {
    const data = await apiFetch<{ threads: Thread[] }>(
      `/SFRAG/threads?workspace_id=${encodeURIComponent(workspaceId)}`,
    )
    setThreads(data.threads)
    return data.threads
  }, [indexName])

  const refreshDocuments = useCallback(async (workspaceId = indexName) => {
    const [documentResponse, categoryResponse] = await Promise.all([
      apiFetch<{ documents: DocumentRecord[] }>(`/SFRAG/documents/${workspaceId}`),
      apiFetch<{ categories: CategorySummary[] }>(`/SFRAG/categories/${workspaceId}`),
    ])
    setDocuments(documentResponse.documents)
    setCategories(categoryResponse.categories)
    return documentResponse.documents
  }, [indexName])

  const refreshUploadPolicy = useCallback(async (workspaceId = indexName) => {
    const policy = await apiFetch<UploadPolicy>(`/SFRAG/upload-policy/${workspaceId}`)
    setUploadPolicy(policy)
    return policy
  }, [indexName])

  const resetWorkspaceState = useCallback(() => {
    setThreads([])
    setActiveThreadId(null)
    setSessionId('')
    setMessages([])
    setSelectedCategory(null)
    setPendingQuestion(null)
    setQuestion('')
    setUploadFile(null)
    setUploadProgress({ phase: 'idle' })
    setUploadPolicyNotices([])
    setOpenMenuThreadId(null)
    setConfirmDeleteThreadId(null)
    setOpenWorkspaceMenuId(null)
    setConfirmDeleteWorkspaceId(null)
  }, [])

  async function ensureThread(questionSeed?: string): Promise<{ threadId: string; sessionId: string }> {
    if (activeThreadId && sessionId) {
      return { threadId: activeThreadId, sessionId }
    }
    const created = await apiFetch<{ thread_id: string; session_id: string; name: string }>('/SFRAG/threads', {
      method: 'POST',
      body: JSON.stringify({ name: questionSeed?.slice(0, 80) || 'New chat', workspace_id: indexName }),
    })
    setActiveThreadId(created.thread_id)
    setSessionId(created.session_id)
    await refreshThreads(indexName)
    return { threadId: created.thread_id, sessionId: created.session_id }
  }

  async function createNewThread() {
    try {
      setBusy(true)
      setLoadingMessage('Starting a new chat...')
      setActiveThreadId(null)
      setSessionId('')
      setMessages([])
      setPendingQuestion(null)
      setQuestion('')
      setSelectedCategory(null)
      const created = await apiFetch<{ thread_id: string; session_id: string; name: string }>('/SFRAG/threads', {
        method: 'POST',
        body: JSON.stringify({ name: 'New chat', workspace_id: indexName }),
      })
      setActiveThreadId(created.thread_id)
      setSessionId(created.session_id)
      setMessages([buildGreeting(activeWorkspace)])
      await refreshThreads(indexName)
      pushToast('New chat started.', 'success')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Could not start a new chat.', 'error')
    } finally {
      setBusy(false)
      setLoadingMessage('Ready')
    }
  }

  function commitWorkspaceSelection(nextWorkspace: string) {
    const normalized = normalizeWorkspace(nextWorkspace)
    setPersonalWorkspace(normalized)
    setWorkspaceDraft(normalized)
    storeWorkspaceHistory([normalized, ...personalWorkspaceHistory.filter((item) => item !== normalized)].slice(0, 12))
    setActiveWorkspace('personal')
    pushToast(`Switched to workspace ${normalized}.`, 'success')
  }

  function createWorkspaceFromDraft() {
    commitWorkspaceSelection(workspaceDraft)
  }

  function createFreshWorkspace() {
    commitWorkspaceSelection(generateWorkspaceName())
  }

  const openThread = useCallback(async (threadId: string) => {
    const thread = await apiFetch<Thread>(
      `/SFRAG/threads/${threadId}?workspace_id=${encodeURIComponent(indexName)}`,
    )
    setActiveThreadId(threadId)
    setSessionId(thread.metadata?.session_id ?? '')
    const mapped = mapStepsToMessages(thread)
    setMessages(mapped.length > 0 ? mapped : [buildGreeting(activeWorkspace)])
    setPendingQuestion(null)
    setOpenMenuThreadId(null)
    setConfirmDeleteThreadId(null)
  }, [activeWorkspace, indexName])

  async function handleDeleteThread(threadId: string) {
    try {
      await apiFetch(`/SFRAG/threads/${threadId}?workspace_id=${encodeURIComponent(indexName)}`, { method: 'DELETE' })
    } catch {
      await apiFetch(`/SFRAG/threads/${threadId}`, { method: 'DELETE' })
    }
    setOpenMenuThreadId(null)
    setConfirmDeleteThreadId(null)
    const remainingThreads = threads.filter((thread) => thread.id !== threadId)
    setThreads(remainingThreads)
    if (activeThreadId === threadId) {
      const nextThread = remainingThreads[0]
      setActiveThreadId(nextThread?.id ?? null)
      if (nextThread?.id) {
        await openThread(nextThread.id)
      } else {
        setMessages([buildGreeting(activeWorkspace)])
        setSessionId('')
      }
    }
    window.setTimeout(() => {
      void refreshThreads(indexName)
    }, 2500)
    pushToast('Chat deleted.', 'success')
  }

  async function handleDeleteWorkspace(workspaceId: string) {
    try {
      setBusy(true)
      await apiFetch(`/SFRAG/workspaces/${encodeURIComponent(workspaceId)}`, { method: 'DELETE' })
      const remaining = personalWorkspaceHistory.filter((item) => item !== workspaceId)
      storeWorkspaceHistory(remaining)
      setOpenWorkspaceMenuId(null)
      setConfirmDeleteWorkspaceId(null)

      if (personalWorkspace === workspaceId) {
        const fallback = remaining[0] ?? generateWorkspaceName()
        setPersonalWorkspace(fallback)
        setWorkspaceDraft(fallback)
        if (remaining.length === 0) {
          storeWorkspaceHistory([fallback])
        }
      }
      pushToast(`Workspace ${workspaceId} deleted.`, 'success')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Workspace deletion failed.', 'error')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (chatLogRef.current) {
      chatLogRef.current.scrollTo({ top: chatLogRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [orderedMessages])

  useEffect(() => {
    const rawSession = localStorage.getItem(AUTH_SESSION_KEY)
    if (rawSession) {
      try {
        setAuthSession(JSON.parse(rawSession) as AuthSession)
      } catch {
        localStorage.removeItem(AUTH_SESSION_KEY)
      }
    }
  }, [])

  useEffect(() => {
    const handleAnalyticsSidebarState = (event: Event) => {
      const customEvent = event as CustomEvent<{
        datasets: AnalyticsDatasetSidebarRecord[]
        selectedDataset: string
        selectedDatasetMeta: AnalyticsDatasetSidebarRecord | null
      }>
      setAnalyticsDatasets(customEvent.detail?.datasets ?? [])
      setAnalyticsSelectedDataset(customEvent.detail?.selectedDataset ?? '')
      setAnalyticsSelectedDatasetMeta(customEvent.detail?.selectedDatasetMeta ?? null)
    }

    window.addEventListener('analytics-sidebar-state', handleAnalyticsSidebarState as EventListener)
    return () => {
      window.removeEventListener('analytics-sidebar-state', handleAnalyticsSidebarState as EventListener)
    }
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!menuContainerRef.current?.contains(event.target as Node)) {
        setOpenMenuThreadId(null)
        setOpenWorkspaceMenuId(null)
        setAnalyticsOpenDatasetMenuId(null)
      }
    }
    document.addEventListener('mousedown', onDocumentClick)
    return () => document.removeEventListener('mousedown', onDocumentClick)
  }, [])

  async function handleSend(rawQuestion?: string, forcedCategory?: string | null, documentFilter?: string | null) {
    const finalQuestion = (rawQuestion ?? question).trim()
    if (!finalQuestion && !chatImageFile) return
    const inferredDocumentFilter = documentFilter ?? inferDocumentFilter(finalQuestion, documents, preferredDocument?.filename ?? null)
    const retrievalQuestion =
      !isSnowWorkspace && inferredDocumentFilter && !finalQuestion.toLowerCase().includes(inferredDocumentFilter.toLowerCase())
        ? `For the document "${inferredDocumentFilter}", answer this question: ${finalQuestion}`
        : finalQuestion
    if (!isSnowWorkspace && documents.length === 0) {
      pushToast('Upload and index a document first, then ask your question.', 'info')
      setMessages((current) => {
        if (current.length > 0) return current
        return [buildGreeting(activeWorkspace)]
      })
      return
    }
    try {
      setBusy(true)
      setLoadingMessage(chatImageFile ? `Analyzing image in ${indexName}...` : `Searching ${indexName}...`)
      const seedText = finalQuestion || chatImageFile?.name || 'Image question'
      const { threadId, sessionId: currentSessionId } = await ensureThread(seedText)

      const userBubbleContent = chatImageFile
        ? `${finalQuestion ? `${finalQuestion}\n\n` : ''}[Image attached: ${chatImageFile.name}]`
        : finalQuestion
      setMessages((current) => [...current, { role: 'user', content: userBubbleContent, timestamp: nowIso() }])
      setQuestion('')
      let payload: RetrievalResponse
      if (chatImageFile) {
        const form = new FormData()
        form.append('index_name', indexName)
        form.append('session_id', currentSessionId)
        form.append('thread_id', threadId)
        if (finalQuestion) {
          form.append('prompt', finalQuestion)
        }
        form.append('file', chatImageFile)
        payload = await apiFetch<RetrievalResponse>('/SFRAG/retrieval-image', {
          method: 'POST',
          body: form,
        })
      } else {
        payload = await apiFetch<RetrievalResponse>('/SFRAG/retrieval', {
          method: 'POST',
          body: JSON.stringify({
            user_query: retrievalQuestion,
            index_name: indexName,
            session_id: currentSessionId,
            thread_id: threadId,
            selected_category: forcedCategory ?? selectedCategory,
            document_filter: inferredDocumentFilter ?? undefined,
          }),
        })
      }

      if (payload.mode === 'clarify') {
        setPendingQuestion(payload.image_query?.retrieval_query ?? finalQuestion)
        setMessages((current) => [
          ...current,
          {
            role: 'assistant',
            content: payload.response.content,
            timestamp: nowIso(),
            citations: payload.citation ?? [],
          },
        ])
        setCategories(payload.categories ?? categories)
        pushToast('Multiple categories found. Pick one to continue.', 'info')
      } else {
        setPendingQuestion(null)
        setSelectedCategory(payload.selected_category ?? forcedCategory ?? null)
        setMessages((current) => [
          ...current,
          {
            role: 'assistant',
            content: payload.response.content,
            timestamp: nowIso(),
            citations: payload.citation ?? [],
          },
        ])
        if (payload.image_query?.retrieval_query && chatImageFile) {
          pushToast(`Image routed as: ${payload.image_query.retrieval_query}`, 'info')
        }
        pushToast('Answer ready.', 'success')
      }

      setChatImageFile(null)
      await refreshThreads(indexName)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Request failed.'
      pushToast(message, 'error')
    } finally {
      setBusy(false)
      setLoadingMessage('Ready')
    }
  }

  async function handleStarterPrompt(prompt: string, documentFilter?: string | null) {
    setQuestion(prompt)
    await handleSend(prompt, null, documentFilter)
  }

  async function performUpload() {
    if (!uploadFile || isReadOnlyWorkspace) return
    const pendingFile = uploadFile
    try {
      setBusy(true)
      setUploadProgress({
        phase: 'uploading',
        filename: pendingFile.name,
        message: 'Uploading and indexing document...',
      })
      setLoadingMessage(`Uploading ${pendingFile.name}...`)
      const presignedUpload = await apiFetch<PresignedUploadResponse>('/SFRAG/uploads/presign', {
        method: 'POST',
        body: JSON.stringify({
          index_name: indexName,
          filename: pendingFile.name,
          content_type: pendingFile.type || 'application/octet-stream',
        }),
      })
      setUploadProgress({
        phase: 'uploading',
        filename: pendingFile.name,
        message: 'Uploading file to the document store...',
      })
      await uploadFileToPresignedTarget(presignedUpload, pendingFile)
      setUploadProgress({
        phase: 'uploading',
        filename: pendingFile.name,
        message: 'File uploaded. Indexing document for RAG...',
      })
      setLoadingMessage(`Indexing ${pendingFile.name}...`)
      const queuedJob = await apiFetch<AsyncIngestResponse>('/SFRAG/ingest-async', {
        method: 'POST',
        body: JSON.stringify({
          index_name: indexName,
          s3_key: presignedUpload.object_key,
          content_type: pendingFile.type || 'application/octet-stream',
          filename: pendingFile.name,
        }),
      })
      const completedJob = await waitForIngestJob(queuedJob.job_id)
      if (completedJob.status === 'failed') {
        throw new Error(completedJob.error || 'Upload failed during indexing.')
      }
      const ingestResponse = completedJob.result
      if (!ingestResponse || ingestResponse.status === 'Error') {
        throw new Error(ingestResponse?.detail || ingestResponse?.message || 'Upload failed.')
      }
      setUploadFile(null)
      const refreshedDocuments = await refreshDocuments(indexName)
      await refreshUploadPolicy(indexName)
      setUploadPolicyNotices(ingestResponse.warnings ?? [])
      setLastUploadResult({
        filename: pendingFile.name,
        category: ingestResponse.category ?? 'uncategorized',
        status: 'indexed',
      })
      setUploadProgress({
        phase: 'indexed',
        filename: pendingFile.name,
        message: 'Document uploaded and indexed successfully.',
      })
      if (!refreshedDocuments.some((document) => document.filename === pendingFile.name)) {
        setDocuments((current) => [
          {
            filename: pendingFile.name,
            category: ingestResponse.category ?? 'uncategorized',
            content_type: pendingFile.type || 'application/octet-stream',
            size_bytes: pendingFile.size,
            updated_at: Math.floor(Date.now() / 1000),
          },
          ...current.filter((document) => document.filename !== pendingFile.name),
        ])
        window.setTimeout(() => {
          void refreshDocuments(indexName)
        }, 2500)
      }
      setDocumentsOpen(true)
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          content: `Uploaded and indexed "${pendingFile.name}" successfully under category "${ingestResponse.category ?? 'uncategorized'}". You can now ask questions about this document or use "Summarize docs".`,
          timestamp: nowIso(),
        },
      ])
      pushToast(
        `Indexed ${pendingFile.name} as ${ingestResponse.category ?? 'uncategorized'}.`,
        'success',
      )
      for (const warning of ingestResponse.warnings ?? []) {
        pushToast(warning, 'info')
      }
    } catch (error) {
      const failureMessage = buildUploadFailureMessage(pendingFile, uploadPolicy, error)
      setUploadProgress({
        phase: 'failed',
        filename: pendingFile.name,
        message: failureMessage,
      })
      pushToast(failureMessage, 'error')
    } finally {
      setBusy(false)
      setLoadingMessage('Ready')
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!uploadFile || isReadOnlyWorkspace) return
    setShowUploadWarning(true)
  }

  async function handleFeedbackSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!feedbackUserId.trim() || !feedbackText.trim()) {
      pushToast('Feedback needs both your ID and a short note.', 'error')
      return
    }
    try {
      setBusy(true)
      await apiFetch<FeedbackResponse>('/SFRAG/feedback', {
        method: 'POST',
        body: JSON.stringify({
          user_id: feedbackUserId.trim(),
          workspace_id: indexName,
          feedback: feedbackText.trim(),
        }),
      })
      localStorage.setItem(FEEDBACK_USER_KEY, feedbackUserId.trim())
      setFeedbackText('')
      pushToast('Feedback sent to dhairya.jindani@htcinc.com. Thank you.', 'success')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Feedback submission failed.', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function copyMessage(content: string) {
    try {
      await navigator.clipboard.writeText(content)
      pushToast('Response copied to clipboard.', 'success')
    } catch {
      pushToast('Copy failed on this browser.', 'error')
    }
  }

  useEffect(() => {
    const storedWorkspace = localStorage.getItem(PERSONAL_WORKSPACE_KEY)
    const storedWorkspaceHistory = localStorage.getItem(PERSONAL_WORKSPACES_KEY)
    const normalizedWorkspace = normalizeWorkspace(storedWorkspace || generateWorkspaceName())
    const parsedHistory = storedWorkspaceHistory ? (JSON.parse(storedWorkspaceHistory) as string[]) : []
    const nextHistory = [normalizedWorkspace, ...parsedHistory.filter((item) => item !== normalizedWorkspace)].slice(0, 12)
    const storedMode = localStorage.getItem(ACTIVE_WORKSPACE_KEY)
    const storedUserId = localStorage.getItem(FEEDBACK_USER_KEY)
    const storedTheme = localStorage.getItem(THEME_KEY)
    setPersonalWorkspace(normalizedWorkspace)
    setPersonalWorkspaceHistory(nextHistory)
    setWorkspaceDraft(normalizedWorkspace)
    setActiveWorkspace(storedMode === 'shared' ? 'shared' : storedMode === 'snow' ? 'snow' : 'personal')
    setFeedbackUserId(storedUserId ?? '')
    setTheme(storedTheme === 'dark' ? 'dark' : 'light')
    localStorage.setItem(PERSONAL_WORKSPACES_KEY, JSON.stringify(nextHistory))
  }, [])

  useEffect(() => {
    localStorage.setItem(PERSONAL_WORKSPACE_KEY, personalWorkspace)
    setWorkspaceDraft(personalWorkspace)
  }, [personalWorkspace])

  useEffect(() => {
    localStorage.setItem(ACTIVE_WORKSPACE_KEY, activeWorkspace)
  }, [activeWorkspace])

  useEffect(() => {
    resetWorkspaceState()
    void refreshThreads(indexName).then((loaded) => {
      if (loaded[0]?.id) {
        void openThread(loaded[0].id)
      } else {
        setMessages([buildGreeting(activeWorkspace)])
      }
    })
    void refreshDocuments(indexName)
    void refreshUploadPolicy(indexName)
  }, [indexName, activeWorkspace, openThread, refreshDocuments, refreshThreads, refreshUploadPolicy, resetWorkspaceState])

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      setBusy(true)
      setLoginError('')
      const response = await fetch(`${API_BASE_URL}/SFRAG/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUsername, password: loginPassword }),
      })
      if (!response.ok) {
        throw new Error((await response.text()) || 'Login failed.')
      }
      const payload = (await response.json()) as { username: string; role: 'admin' | 'user' }
      const authorization = `Basic ${btoa(`${loginUsername}:${loginPassword}`)}`
      const session: AuthSession = { username: payload.username, role: payload.role, authorization }
      localStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session))
      setAuthSession(session)
      setLoginPassword('')
      pushToast(`Signed in as ${payload.username}.`, 'success')
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Login failed.')
    } finally {
      setBusy(false)
    }
  }

  function handleLogout() {
    localStorage.removeItem(AUTH_SESSION_KEY)
    setAuthSession(null)
    setLoginUsername('')
    setLoginPassword('')
    setLoginError('')
  }

  async function handleAdminReset() {
    const confirmed = window.confirm('Reset the demo? This deletes all chat history, workspaces, datasets, and indexes except ServiceNow snow.')
    if (!confirmed) return
    try {
      setBusy(true)
      const response = await apiFetch<{ status: string }>(`/SFRAG/admin/reset-demo`, { method: 'POST' })
      localStorage.removeItem(PERSONAL_WORKSPACE_KEY)
      localStorage.removeItem(PERSONAL_WORKSPACES_KEY)
      localStorage.removeItem(ACTIVE_WORKSPACE_KEY)
      localStorage.removeItem(ANALYTICS_HISTORY_KEY)
      setPersonalWorkspace(DEFAULT_INDEX)
      setWorkspaceDraft(DEFAULT_INDEX)
      setPersonalWorkspaceHistory([])
      setAnalyticsDatasets([])
      setAnalyticsSelectedDataset('')
      setAnalyticsSelectedDatasetMeta(null)
      setAnalyticsDatasetFilter('')
      setActiveWorkspace('snow')
      setAppView('chat')
      resetWorkspaceState()
      pushToast(response.status === 'reset_complete' ? 'Demo reset completed.' : 'Demo reset requested.', 'success')
      await refreshThreads(SNOW_WORKSPACE)
      await refreshDocuments(SNOW_WORKSPACE)
      await refreshUploadPolicy(SNOW_WORKSPACE)
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Admin reset failed.', 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!authSession) {
    return (
      <div className="auth-shell">
        <form className="auth-card" onSubmit={handleLogin}>
          <img className="brand-logo auth-logo" src={logoSrc} alt="RAG demo logo" />
          <p className="eyebrow">Secure Access</p>
          <h1>RAG Demo Login</h1>
          <p className="helper-text">Sign in to access the chat, analytics, and agent workflows.</p>
          <label className="field">
            <span>Username</span>
            <input value={loginUsername} onChange={(event) => setLoginUsername(event.target.value)} />
          </label>
          <label className="field">
            <span>Password</span>
            <input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} />
          </label>
          {loginError ? <p className="auth-error">{loginError}</p> : null}
          <button className="primary-button auth-submit" type="submit" disabled={busy || !loginUsername || !loginPassword}>
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="panel brand-panel">
          <div className="brand-row">
            <img className="brand-logo" src={logoSrc} alt="RAG demo logo" />
            <div className="brand-actions">
              {isAdmin ? (
                <button className="ghost-button danger-toggle" onClick={() => void handleAdminReset()}>
                  Reset demo
                </button>
              ) : null}
              <button className="ghost-button theme-toggle" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>
                {theme === 'light' ? 'Dark mode' : 'Light mode'}
              </button>
              <button className="ghost-button theme-toggle" onClick={handleLogout}>
                Logout
              </button>
            </div>
          </div>
          <div className="panel-head">
            <div>
              <p className="eyebrow">MVP Console</p>
              <h1>RAG Demo</h1>
            </div>
            <button className="ghost-button" onClick={() => void createNewThread()}>
              New
            </button>
          </div>
          <div className="app-view-tabs">
            <button className={`workspace-tab ${appView === 'chat' ? 'active' : ''}`} onClick={() => setAppView('chat')}>
              Chat
            </button>
            <button className={`workspace-tab ${appView === 'analytics' ? 'active' : ''}`} onClick={() => setAppView('analytics')}>
              Analytics
            </button>
            <button className={`workspace-tab ${appView === 'agents' ? 'active' : ''}`} onClick={() => setAppView('agents')}>
              Agents
            </button>
          </div>
          {appView === 'analytics' ? <p className="helper-text">Switch to the analytics tab to upload structured datasets and run SQL-backed insights.</p> : null}
          {appView === 'chat' ? (
            <>
          <div className="workspace-switcher">
            <button
              className={`workspace-tab ${activeWorkspace === 'personal' ? 'active' : ''}`}
              onClick={() => setActiveWorkspace('personal')}
            >
              My workspace
            </button>
            <button
              className={`workspace-tab ${isSharedWorkspace ? 'active' : ''}`}
              onClick={() => setActiveWorkspace('shared')}
            >
              Shared demo
            </button>
            <button
              className={`workspace-tab ${isSnowWorkspace ? 'active' : ''}`}
              onClick={() => setActiveWorkspace('snow')}
            >
              ServiceNow
            </button>
          </div>
          <label className="field">
            <span>{isSharedWorkspace ? 'Shared workspace' : isSnowWorkspace ? 'ServiceNow index' : 'Personal workspace'}</span>
            <input
              value={isReadOnlyWorkspace ? indexName : workspaceDraft}
              disabled={isReadOnlyWorkspace}
              onChange={(event) => setWorkspaceDraft(event.target.value)}
              onBlur={() => !isReadOnlyWorkspace && commitWorkspaceSelection(workspaceDraft)}
            />
          </label>
          {!isReadOnlyWorkspace ? (
            <div className="workspace-actions">
              <button className="ghost-button" type="button" onClick={createWorkspaceFromDraft}>
                Use workspace
              </button>
              <button className="ghost-button" type="button" onClick={createFreshWorkspace}>
                New workspace
              </button>
            </div>
          ) : null}
          <p className="helper-text">
            {isSharedWorkspace
              ? 'Read-only workspace with preloaded demo content.'
              : isSnowWorkspace
                ? 'Read-only ServiceNow ticket analysis index.'
                : 'Only your uploads and queries use this workspace.'}
          </p>
          {!isReadOnlyWorkspace ? (
            <div className="workspace-history" ref={menuContainerRef}>
              <div className="panel-head tight">
                <h2>Workspace history</h2>
              </div>
              <div className="thread-list workspace-thread-list">
                {personalWorkspaceHistory.map((workspaceId) => (
                  <div key={workspaceId} className={`thread-item ${workspaceId === personalWorkspace ? 'active' : ''}`}>
                    <button className="thread-link" onClick={() => commitWorkspaceSelection(workspaceId)}>
                      <strong>{workspaceId}</strong>
                      <span>{workspaceId === 'test-big-001' ? 'Limit exception enabled' : 'Reusable personal workspace'}</span>
                    </button>
                    <div className="thread-actions">
                      <button
                        className="menu-button kebab-button"
                        aria-label="Workspace actions"
                        onClick={() => {
                          setOpenWorkspaceMenuId((current) => (current === workspaceId ? null : workspaceId))
                          setConfirmDeleteWorkspaceId(null)
                        }}
                      >
                        <span />
                        <span />
                        <span />
                      </button>
                      {openWorkspaceMenuId === workspaceId ? (
                        <div className="thread-menu">
                          {confirmDeleteWorkspaceId === workspaceId ? (
                            <>
                              <p className="thread-menu-copy">Delete this workspace and its indexed data?</p>
                              <button className="thread-menu-item delete" onClick={() => void handleDeleteWorkspace(workspaceId)}>
                                Confirm delete
                              </button>
                              <button className="thread-menu-item" onClick={() => setConfirmDeleteWorkspaceId(null)}>
                                Cancel
                              </button>
                            </>
                          ) : (
                            <button className="thread-menu-item delete" onClick={() => setConfirmDeleteWorkspaceId(workspaceId)}>
                              Delete workspace
                            </button>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
            </>
          ) : null}
        </div>
        {appView === 'chat' ? (
          <>
            <div className="panel grow">
              <div className="panel-head">
                <h2>Chat History</h2>
              </div>
              <div className="thread-list">
                {historicalThreads.length === 0 ? <p className="history-empty">Past chats will appear here.</p> : null}
                {historicalThreads.map((thread) => (
                  <div key={thread.id} className={`thread-item ${thread.id === activeThreadId ? 'active' : ''}`}>
                    <button className="thread-link" onClick={() => void openThread(thread.id)}>
                      <strong>{summarizeThread(thread)}</strong>
                      <span>{new Date(thread.createdAt).toLocaleString()}</span>
                    </button>
                    <div className="thread-actions">
                      <button
                        className="menu-button kebab-button"
                        aria-label="Thread actions"
                        onClick={() => setOpenMenuThreadId((current) => (current === thread.id ? null : thread.id))}
                      >
                        <span />
                        <span />
                        <span />
                      </button>
                      {openMenuThreadId === thread.id ? (
                        <div className="thread-menu">
                          {confirmDeleteThreadId === thread.id ? (
                            <>
                              <p className="thread-menu-copy">Delete this chat history?</p>
                              <button className="thread-menu-item delete" onClick={() => void handleDeleteThread(thread.id)}>
                                Confirm delete
                              </button>
                              <button className="thread-menu-item" onClick={() => setConfirmDeleteThreadId(null)}>
                                Cancel
                              </button>
                            </>
                          ) : (
                            <button className="thread-menu-item delete" onClick={() => setConfirmDeleteThreadId(thread.id)}>
                              Delete chat
                            </button>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-head">
                <h2>Categories</h2>
              </div>
              <div className="chip-wrap">
                <button className={`chip ${selectedCategory === null ? 'selected' : ''}`} onClick={() => setSelectedCategory(null)}>
                  All
                </button>
                {categories.map((item) => (
                  <button
                    key={item.category}
                    className={`chip ${selectedCategory === item.category ? 'selected' : ''}`}
                    onClick={() => setSelectedCategory(item.category)}
                  >
                    {item.category} <span>{item.count}</span>
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : null}
        {appView === 'analytics' ? (
          <div className="panel grow">
            <div className="panel-head">
              <h2>Datasets</h2>
            </div>
            <div className="analytics-dataset-tools">
              <input
                value={analyticsDatasetFilter}
                onChange={(event) => setAnalyticsDatasetFilter(event.target.value)}
                placeholder="Search datasets"
                aria-label="Search analytics datasets"
              />
            </div>
            <div className="thread-list analytics-sidebar-list">
              {analyticsDatasets.length === 0 ? <p className="history-empty">Upload a structured dataset to start analytics.</p> : null}
              {analyticsDatasets.length > 0 && filteredAnalyticsDatasets.length === 0 ? <p className="history-empty">No datasets match this search.</p> : null}
              {filteredAnalyticsDatasets.map((dataset) => (
                <div key={dataset.dataset_id} className={`thread-item ${dataset.dataset_id === analyticsSelectedDataset ? 'active' : ''}`}>
                  <button
                    className="thread-link"
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent('analytics-sidebar-select', { detail: { datasetId: dataset.dataset_id } }))
                      setAnalyticsOpenDatasetMenuId(null)
                    }}
                  >
                    <strong>{dataset.dataset_id}</strong>
                    <span>{dataset.source_name ?? 'Structured dataset'}</span>
                    <span>{dataset.updated_at ? new Date(dataset.updated_at * 1000).toLocaleString() : 'Unknown'}</span>
                  </button>
                  <div className="thread-actions">
                    <button
                      className="menu-button kebab-button"
                      aria-label="Dataset actions"
                      onClick={() => {
                        setAnalyticsOpenDatasetMenuId((current) => (current === dataset.dataset_id ? null : dataset.dataset_id))
                        setAnalyticsConfirmDeleteDatasetId(null)
                      }}
                    >
                      <span />
                      <span />
                      <span />
                    </button>
                    {analyticsOpenDatasetMenuId === dataset.dataset_id ? (
                      <div className="thread-menu">
                        {analyticsConfirmDeleteDatasetId === dataset.dataset_id ? (
                          <>
                            <p className="thread-menu-copy">Delete this analytics dataset and its uploaded data?</p>
                            <button
                              className="thread-menu-item delete"
                              onClick={() => {
                                window.dispatchEvent(new CustomEvent('analytics-sidebar-delete', { detail: { datasetId: dataset.dataset_id } }))
                                setAnalyticsConfirmDeleteDatasetId(null)
                                setAnalyticsOpenDatasetMenuId(null)
                              }}
                            >
                              Confirm delete
                            </button>
                            <button className="thread-menu-item" onClick={() => setAnalyticsConfirmDeleteDatasetId(null)}>
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button className="thread-menu-item delete" onClick={() => setAnalyticsConfirmDeleteDatasetId(dataset.dataset_id)}>
                            Delete dataset
                          </button>
                        )}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
            {analyticsSelectedDatasetMeta ? (
              <div className="analytics-dataset-meta sidebar-analytics-meta">
                <h4>Selected dataset</h4>
                <p>{analyticsSelectedDatasetMeta.source_name ?? 'Structured upload'}</p>
                <small>{analyticsSelectedDatasetMeta.schema_columns?.length ?? 0} columns available for analytics.</small>
              </div>
            ) : null}
          </div>
        ) : null}
      </aside>

      <main className="workspace">
        {appView === 'agents' ? (
          <>
            <AgentsTab
              apiBaseUrl={API_BASE_URL}
              indexName={indexName}
              workspaceId={indexName}
              pushToast={pushToast}
            />
            <div className="toast-stack" aria-live="polite">
              {toasts.map((toast) => (
                <div key={toast.id} className={`toast ${toast.tone}`}>
                  {toast.message}
                </div>
              ))}
            </div>
          </>
        ) : appView === 'analytics' ? (
          <>
            <AnalyticsTab apiBaseUrl={API_BASE_URL} pushToast={pushToast} />
            <div className="toast-stack" aria-live="polite">
              {toasts.map((toast) => (
                <div key={toast.id} className={`toast ${toast.tone}`}>
                  {toast.message}
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <section className="hero-card">
              <div>
                <p className="eyebrow">Cost-lean local implementation</p>
                <h2>
                  {isSharedWorkspace
                    ? 'Explore shared demo documents safely'
                    : isSnowWorkspace
                      ? 'Analyze ServiceNow ticket history from the dedicated snow_idx index'
                      : 'Upload docs and test your own isolated workspace'}
                </h2>
                <p className="helper-text strong">Active workspace: {indexName}</p>
                <div className="workspace-meta-row">
                  <span className="hero-badge">{isReadOnlyWorkspace ? 'Read-only' : 'Read / Write'}</span>
                  <span className="hero-badge subtle">{loadingMessage}</span>
                  {uploadPolicy?.is_exception_workspace ? <span className="hero-badge exception">Limit exception active</span> : null}
                </div>
                <div className="policy-summary-row">
                  <span className="hero-badge subtle">
                    {(uploadPolicy?.supported_types ?? ['pdf', 'txt', 'docx', 'xlsx']).map((item) => item.toUpperCase()).join(', ')}
                  </span>
                  <span className="hero-badge subtle">
                    {isSnowWorkspace ? 'Preloaded tickets' : `Up to ${uploadPolicy?.max_upload_mb ?? 5} MB`}
                  </span>
                  {uploadPolicy?.workspace_document_limit ? (
                    <span className="hero-badge subtle">
                      {uploadPolicy.workspace_document_count} / {uploadPolicy.workspace_document_limit} docs
                    </span>
                  ) : null}
                </div>
                {uploadPolicyNotices.length > 0 ? (
                  <div className="policy-notice compact">
                    {uploadPolicyNotices.map((notice) => (
                      <p key={notice}>{notice}</p>
                    ))}
                  </div>
                ) : null}
                {lastUploadResult ? (
                  <div className="upload-success-banner">
                    <strong>{lastUploadResult.filename}</strong>
                    <span>Indexed successfully</span>
                    <small>Category: {lastUploadResult.category}</small>
                  </div>
                ) : null}
                {uploadProgress.phase !== 'idle' && uploadProgress.phase !== 'indexed' ? (
                  <div className={`upload-status-banner phase-${uploadProgress.phase}`}>
                    <strong>{uploadProgress.filename}</strong>
                    <span>{uploadProgress.message}</span>
                  </div>
                ) : null}
              </div>
              <form className="upload-form" onSubmit={(event) => void handleUpload(event)}>
                <input
                  type="file"
                  accept=".pdf,.txt,.docx,.xlsx"
                  disabled={isReadOnlyWorkspace || busy || uploadProgress.phase === 'uploading'}
                  onChange={(event) => {
                    const nextFile = event.target.files?.[0] ?? null
                    setUploadFile(nextFile)
                    setLastUploadResult(null)
                    setUploadProgress(
                      nextFile
                        ? {
                            phase: 'selected',
                            filename: nextFile.name,
                            message: 'File selected. Click Upload and confirm to index it for RAG.',
                          }
                        : { phase: 'idle' },
                    )
                  }}
                />
                <div className="upload-actions">
                  <button
                    type="button"
                    className="ghost-button compact-action"
                    disabled={busy || uploadProgress.phase === 'uploading' || (!isSnowWorkspace && documents.length === 0)}
                    onClick={() =>
                      void handleStarterPrompt(
                        summarizePrompt(activeWorkspace, documents, preferredDocument?.filename ?? null),
                        !isSnowWorkspace ? preferredDocument?.filename ?? null : null,
                      )
                    }
                  >
                    {isSnowWorkspace ? 'Summarize data' : 'Summarize docs'}
                  </button>
                  <button
                    type="submit"
                    disabled={busy || uploadProgress.phase === 'uploading' || !uploadFile || isReadOnlyWorkspace}
                  >
                    {uploadProgress.phase === 'uploading'
                      ? 'Uploading...'
                      : busy
                        ? 'Working...'
                        : isReadOnlyWorkspace
                          ? 'Read-only'
                          : 'Upload'}
                  </button>
                </div>
              </form>
            </section>
            <section className="content-grid">
              <div className="chat-card">
                <div className="chat-starters">
                  <span className="chat-starters-label">Frequent queries:</span>
                  {chatStarterPrompts.map((starter) => (
                    <button
                      key={starter.label}
                      type="button"
                      className="chip"
                      onClick={() => void handleStarterPrompt(starter.prompt, starter.documentFilter)}
                      disabled={busy || (!isSnowWorkspace && documents.length === 0)}
                      title={starter.prompt}
                    >
                      {starter.label}
                    </button>
                  ))}
                </div>
                <div className="chat-log" ref={chatLogRef}>
                  {busy && messages.length === 0 ? (
                    <div className="chat-skeleton">
                      <div className="skeleton-line wide" />
                      <div className="skeleton-line" />
                      <div className="skeleton-line short" />
                    </div>
                  ) : null}
                  {messages.length === 0 && !busy ? (
                    <div className="empty-state">
                      {isSharedWorkspace
                        ? 'Ask questions against the shared demo workspace.'
                        : isSnowWorkspace
                          ? 'Ask about recurring incidents, root causes, assignment groups, or ask for ticket summaries in table format.'
                          : 'Start a thread or upload a document to begin.'}
                    </div>
                  ) : (
                    orderedMessages.map((message, index) => (
                      <article key={`${message.role}-${index}`} className={`bubble ${message.role}`}>
                        <div className="bubble-topline">
                          <div className="bubble-identity">
                            <div className={`avatar ${message.role}`}>{message.role === 'user' ? 'U' : 'AI'}</div>
                            <div>
                              <span>{message.role === 'user' ? 'You' : 'Assistant'}</span>
                              <small>{formatTimestamp(message.timestamp)}</small>
                            </div>
                          </div>
                          {message.role === 'assistant' ? (
                            <button className="copy-button" onClick={() => void copyMessage(message.content)}>
                              Copy
                            </button>
                          ) : null}
                        </div>
                        <div className="bubble-body">
                          {message.role === 'assistant' ? (
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                          ) : (
                            <p>{message.content}</p>
                          )}
                          {message.role === 'assistant' && message.citations && message.citations.length > 0 ? (
                            <div className="bubble-sources">
                              <span className="bubble-sources-label">Sources</span>
                              <div className="bubble-source-list">
                                {message.citations.map((citation, citationIndex) => {
                                  const label = citation.filename || citation.pdf_url || `Source ${citationIndex + 1}`
                                  const href = citation.pdf_url && citation.pdf_url !== 'N/A' ? citation.pdf_url : undefined
                                  return href ? (
                                    <a
                                      key={`${label}-${citationIndex}`}
                                      className="bubble-source-pill"
                                      href={href}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      {label}
                                    </a>
                                  ) : (
                                    <span key={`${label}-${citationIndex}`} className="bubble-source-pill">
                                      {label}
                                    </span>
                                  )
                                })}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </article>
                    ))
                  )}
                </div>

                {pendingQuestion ? (
                  <div className="clarify-box">
                    <p>Choose a category for: "{pendingQuestion}"</p>
                    <div className="chip-wrap">
                      {categories.map((item) => (
                        <button key={item.category} className="chip selected" onClick={() => void handleSend(pendingQuestion, item.category)}>
                          {item.category}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}

                <form
                  className="composer"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void handleSend()
                  }}
                >
                  <div className="composer-main">
                    <textarea
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                      placeholder={
                        isSnowWorkspace
                          ? 'Ask about repeat incidents, priorities, root causes, or ask to show ServiceNow tickets in table format...'
                          : 'Ask about coverage, claims, policy details, or similar support tickets...'
                      }
                    />
                    <div className="composer-toolbar">
                      <label className="image-attach-button">
                        <input
                          type="file"
                          accept="image/png,image/jpeg,image/jpg,image/webp"
                          onChange={(event) => setChatImageFile(event.target.files?.[0] ?? null)}
                        />
                        Add image
                      </label>
                      {chatImageFile ? (
                        <div className="attachment-pill">
                          <span>{chatImageFile.name}</span>
                          <button type="button" className="attachment-clear" onClick={() => setChatImageFile(null)}>
                            x
                          </button>
                        </div>
                      ) : (
                        <span className="composer-hint">Attach a screenshot to extract and answer the question from it.</span>
                      )}
                    </div>
                  </div>
                  <button type="submit" disabled={busy || (!question.trim() && !chatImageFile)}>
                    {busy ? 'Thinking...' : chatImageFile ? 'Ask from image' : 'Send'}
                  </button>
                </form>
              </div>

              <div className="side-stack">
                <div className="side-card">
                  <button className="accordion-toggle" onClick={() => setDocumentsOpen((current) => !current)}>
                    <span>Indexed documents</span>
                    <div className="accordion-meta">
                      <span className="accordion-count">{documents.length}</span>
                      <span className={`accordion-chevron ${documentsOpen ? 'open' : ''}`}>^</span>
                    </div>
                  </button>
                  {documentsOpen ? (
                    <div className="document-list">
                      {documents.length === 0 && uploadProgress.phase === 'selected' ? (
                        <article className="document-item pending">
                          <header>
                            <strong>{uploadProgress.filename}</strong>
                            <span className="badge">pending</span>
                          </header>
                          <p>Selected only. Click Upload and confirm to index this document.</p>
                        </article>
                      ) : null}
                      {documents.length === 0 && uploadProgress.phase === 'uploading' ? (
                        <article className="document-item pending">
                          <header>
                            <strong>{uploadProgress.filename}</strong>
                            <span className="badge">indexing</span>
                          </header>
                          <p>Upload accepted. Indexing is in progress.</p>
                        </article>
                      ) : null}
                      {documents.map((document) => (
                        <article key={document.filename} className="document-item">
                          <header>
                            <strong>{document.filename}</strong>
                            <span className="badge">{document.category}</span>
                          </header>
                          <p>{document.content_type || 'unknown type'}</p>
                          <small>{formatBytes(document.size_bytes)}</small>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <p className="accordion-helper">Expand to inspect uploaded files and detected categories.</p>
                  )}
                </div>

                <div className="side-card">
                  <button className="accordion-toggle" onClick={() => setFeedbackOpen((current) => !current)}>
                    <span>Feedback</span>
                    <span className={`accordion-chevron ${feedbackOpen ? 'open' : ''}`}>^</span>
                  </button>
                  {feedbackOpen ? (
                    <div className="feedback-panel-body">
                      <form className="feedback-form" onSubmit={(event) => void handleFeedbackSubmit(event)}>
                        <label className="field">
                          <span>User ID</span>
                          <input value={feedbackUserId} onChange={(event) => setFeedbackUserId(event.target.value)} placeholder="your.id@company.com" />
                        </label>
                        <label className="field">
                          <span>Feedback</span>
                          <textarea
                            value={feedbackText}
                            onChange={(event) => setFeedbackText(event.target.value)}
                            placeholder="What worked well, what felt confusing, and what should improve?"
                          />
                        </label>
                        <button type="submit" disabled={busy || !feedbackUserId.trim() || !feedbackText.trim()}>
                          Submit feedback
                        </button>
                      </form>
                    </div>
                  ) : (
                    <p className="accordion-helper">Open to share quick feedback after your demo test.</p>
                  )}
                </div>
              </div>
            </section>
            <div className="toast-stack" aria-live="polite">
              {toasts.map((toast) => (
                <div key={toast.id} className={`toast ${toast.tone}`}>
                  {toast.message}
                </div>
              ))}
            </div>
          </>
        )}
      </main>

      {showUploadWarning ? (
        <div className="modal-backdrop" role="presentation">
          <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="upload-warning-title">
            <p className="eyebrow">Upload Warning</p>
            <h2 id="upload-warning-title">Do not upload critical or PII data</h2>
            <p className="modal-copy">
              This demo portal is only for non-sensitive testing. Do not upload critical business data, personal data,
              customer data, health data, financial data, or any document containing PII.
            </p>
            <ul className="policy-list modal-policy-list">
              <li>Supported file types: {(uploadPolicy?.supported_types ?? ['pdf', 'txt', 'docx', 'xlsx']).map((item) => item.toUpperCase()).join(', ')}.</li>
              <li>Workspace upload size limit: {uploadPolicy?.max_upload_mb ?? 5} MB.</li>
              {uploadPolicy?.workspace_document_limit ? (
                <li>Workspace quota: {uploadPolicy.workspace_document_count} of {uploadPolicy.workspace_document_limit} indexed documents already used.</li>
              ) : null}
              {uploadPolicy?.pdf_text_only_threshold ? (
                <li>Large PDFs over {uploadPolicy.pdf_text_only_threshold} pages switch to text-only processing in standard workspaces.</li>
              ) : null}
              {uploadPolicy?.pdf_page_hard_limit ? (
                <li>PDFs over {uploadPolicy.pdf_page_hard_limit} pages are blocked in standard workspaces.</li>
              ) : null}
              {(uploadPolicy?.warnings ?? []).map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
            <div className="modal-actions">
              <button
                className="ghost-button"
                onClick={() => {
                  setShowUploadWarning(false)
                  pushToast('Upload cancelled.', 'info')
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
    </div>
  )
}

export default App
