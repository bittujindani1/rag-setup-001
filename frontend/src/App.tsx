import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import './App.css'

type Message = {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
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

type RetrievalResponse = {
  mode: 'answer' | 'clarify'
  response: { content: string }
  citation?: Array<{ pdf_url?: string; filename?: string }>
  categories?: CategorySummary[]
  selected_category?: string | null
}

type PresignedUploadResponse = {
  url: string
  fields: Record<string, string>
  bucket: string
  object_key: string
}

type IngestJobResponse = {
  job_id: string
  status: string
  result?: { category?: string }
  error?: string
}

type FeedbackResponse = {
  status: string
}

type Toast = {
  id: string
  tone: 'info' | 'success' | 'error'
  message: string
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '')
const DEFAULT_INDEX = import.meta.env.VITE_INDEX_NAME ?? 'statefarm_rag'
const SHARED_WORKSPACE = import.meta.env.VITE_SHARED_INDEX_NAME ?? 'demo-shared'
const PERSONAL_WORKSPACE_KEY = 'rag-demo-personal-workspace'
const ACTIVE_WORKSPACE_KEY = 'rag-demo-active-workspace'
const FEEDBACK_USER_KEY = 'rag-demo-feedback-user'
const THEME_KEY = 'rag-demo-theme'

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

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
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

function App() {
  const [personalWorkspace, setPersonalWorkspace] = useState(DEFAULT_INDEX)
  const [workspaceDraft, setWorkspaceDraft] = useState(DEFAULT_INDEX)
  const [activeWorkspace, setActiveWorkspace] = useState<'personal' | 'shared'>('personal')
  const [threads, setThreads] = useState<Thread[]>([])
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string>('')
  const [messages, setMessages] = useState<Message[]>([])
  const [question, setQuestion] = useState('')
  const [documents, setDocuments] = useState<DocumentRecord[]>([])
  const [categories, setCategories] = useState<CategorySummary[]>([])
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [feedbackUserId, setFeedbackUserId] = useState('')
  const [feedbackText, setFeedbackText] = useState('')
  const [showUploadWarning, setShowUploadWarning] = useState(false)
  const [openMenuThreadId, setOpenMenuThreadId] = useState<string | null>(null)
  const [confirmDeleteThreadId, setConfirmDeleteThreadId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState('Ready')
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  const [documentsOpen, setDocumentsOpen] = useState(true)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])
  const chatLogRef = useRef<HTMLDivElement | null>(null)
  const menuContainerRef = useRef<HTMLDivElement | null>(null)

  const indexName = useMemo(
    () => (activeWorkspace === 'shared' ? SHARED_WORKSPACE : personalWorkspace),
    [activeWorkspace, personalWorkspace],
  )
  const isSharedWorkspace = activeWorkspace === 'shared'
  const sortedThreads = useMemo(
    () =>
      [...threads].sort(
        (left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime(),
      ),
    [threads],
  )
  const activeThread = useMemo(
    () => sortedThreads.find((thread) => thread.id === activeThreadId) ?? null,
    [activeThreadId, sortedThreads],
  )
  const historicalThreads = useMemo(
    () => sortedThreads.filter((thread) => thread.id !== activeThreadId),
    [activeThreadId, sortedThreads],
  )
  const orderedMessages = useMemo(() => [...messages], [messages])
  const logoSrc = theme === 'dark' ? '/logo_dark.PNG' : '/logo_light.PNG'

  function pushToast(message: string, tone: Toast['tone']) {
    const id = crypto.randomUUID()
    setToasts((current) => [...current, { id, tone, message }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 3500)
  }

  async function refreshThreads(workspaceId = indexName) {
    const data = await apiFetch<{ threads: Thread[] }>(
      `/SFRAG/threads?workspace_id=${encodeURIComponent(workspaceId)}`,
    )
    setThreads(data.threads)
    return data.threads
  }

  async function refreshDocuments(workspaceId = indexName) {
    const [documentResponse, categoryResponse] = await Promise.all([
      apiFetch<{ documents: DocumentRecord[] }>(`/SFRAG/documents/${workspaceId}`),
      apiFetch<{ categories: CategorySummary[] }>(`/SFRAG/categories/${workspaceId}`),
    ])
    setDocuments(documentResponse.documents)
    setCategories(categoryResponse.categories)
  }

  function resetWorkspaceState() {
    setThreads([])
    setActiveThreadId(null)
    setSessionId('')
    setMessages([])
    setSelectedCategory(null)
    setPendingQuestion(null)
    setQuestion('')
    setUploadFile(null)
    setOpenMenuThreadId(null)
    setConfirmDeleteThreadId(null)
  }

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
      await refreshThreads(indexName)
      pushToast('New chat started.', 'success')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : 'Could not start a new chat.', 'error')
    } finally {
      setBusy(false)
      setLoadingMessage('Ready')
    }
  }

  async function openThread(threadId: string) {
    const thread = await apiFetch<Thread>(
      `/SFRAG/threads/${threadId}?workspace_id=${encodeURIComponent(indexName)}`,
    )
    setActiveThreadId(threadId)
    setSessionId(thread.metadata?.session_id ?? '')
    setMessages(mapStepsToMessages(thread))
    setPendingQuestion(null)
    setOpenMenuThreadId(null)
    setConfirmDeleteThreadId(null)
  }

  async function handleDeleteThread(threadId: string) {
    await apiFetch(`/SFRAG/threads/${threadId}?workspace_id=${encodeURIComponent(indexName)}`, { method: 'DELETE' })
    setOpenMenuThreadId(null)
    setConfirmDeleteThreadId(null)
    const updated = await refreshThreads(indexName)
    if (activeThreadId === threadId) {
      setActiveThreadId(updated[0]?.id ?? null)
      if (updated[0]?.id) {
        await openThread(updated[0].id)
      } else {
        setMessages([])
        setSessionId('')
      }
    }
    pushToast('Chat deleted.', 'success')
  }

  useEffect(() => {
    if (chatLogRef.current) {
      chatLogRef.current.scrollTo({ top: chatLogRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [orderedMessages])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    const onDocumentClick = (event: MouseEvent) => {
      if (!menuContainerRef.current?.contains(event.target as Node)) {
        setOpenMenuThreadId(null)
      }
    }
    document.addEventListener('mousedown', onDocumentClick)
    return () => document.removeEventListener('mousedown', onDocumentClick)
  }, [])

  async function handleSend(rawQuestion?: string, forcedCategory?: string | null) {
    const finalQuestion = (rawQuestion ?? question).trim()
    if (!finalQuestion) return
    try {
      setBusy(true)
      setLoadingMessage(`Searching ${indexName}...`)
      const { threadId, sessionId: currentSessionId } = await ensureThread(finalQuestion)

      setMessages((current) => [...current, { role: 'user', content: finalQuestion, timestamp: nowIso() }])
      setQuestion('')
      const payload = await apiFetch<RetrievalResponse>('/SFRAG/retrieval', {
        method: 'POST',
        body: JSON.stringify({
          user_query: finalQuestion,
          index_name: indexName,
          session_id: currentSessionId,
          thread_id: threadId,
          selected_category: forcedCategory ?? selectedCategory,
        }),
      })

      if (payload.mode === 'clarify') {
        setPendingQuestion(finalQuestion)
        setMessages((current) => [...current, { role: 'assistant', content: payload.response.content, timestamp: nowIso() }])
        setCategories(payload.categories ?? categories)
        pushToast('Multiple categories found. Pick one to continue.', 'info')
      } else {
        setPendingQuestion(null)
        setSelectedCategory(payload.selected_category ?? forcedCategory ?? null)
        setMessages((current) => [...current, { role: 'assistant', content: payload.response.content, timestamp: nowIso() }])
        pushToast('Answer ready.', 'success')
      }

      await refreshThreads(indexName)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Request failed.'
      pushToast(message, 'error')
    } finally {
      setBusy(false)
      setLoadingMessage('Ready')
    }
  }

  async function performUpload() {
    if (!uploadFile || isSharedWorkspace) return
    if (uploadFile.size > 5 * 1024 * 1024) {
      pushToast('Upload blocked: file is larger than 5 MB.', 'error')
      return
    }
    try {
      setBusy(true)
      setLoadingMessage(`Uploading ${uploadFile.name}...`)
      const presign = await apiFetch<PresignedUploadResponse>('/SFRAG/uploads/presign', {
        method: 'POST',
        body: JSON.stringify({
          index_name: indexName,
          filename: uploadFile.name,
          content_type: uploadFile.type || 'application/octet-stream',
        }),
      })
      const uploadForm = new FormData()
      Object.entries(presign.fields).forEach(([key, value]) => uploadForm.append(key, value))
      uploadForm.append('Content-Type', uploadFile.type || 'application/octet-stream')
      uploadForm.append('file', uploadFile)
      const uploadResponse = await fetch(presign.url, {
        method: 'POST',
        body: uploadForm,
      })
      if (!uploadResponse.ok) {
        throw new Error('S3 upload failed.')
      }
      const job = await apiFetch<IngestJobResponse>('/SFRAG/ingest-async', {
        method: 'POST',
        body: JSON.stringify({
          index_name: indexName,
          s3_key: presign.object_key,
          content_type: uploadFile.type || 'application/octet-stream',
        }),
      })

      let finalJob = job
      for (let attempt = 0; attempt < 12; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1000))
        finalJob = await apiFetch<IngestJobResponse>(`/SFRAG/ingest-status/${job.job_id}`)
        if (finalJob.status === 'completed') break
        if (finalJob.status === 'failed') {
          throw new Error(finalJob.error || 'Ingest job failed.')
        }
      }

      if (finalJob.status !== 'completed') {
        throw new Error('Ingest job did not complete in time.')
      }
      setUploadFile(null)
      await refreshDocuments(indexName)
      pushToast(
        `Indexed ${uploadFile.name} as ${finalJob.result?.category ?? 'uncategorized'}.`,
        'success',
      )
    } catch (error) {
      try {
        const fallbackForm = new FormData()
        fallbackForm.append('index_name', indexName)
        fallbackForm.append('file', uploadFile)
        const fallbackResponse = await fetch(`${API_BASE_URL}/SFRAG/ingest`, {
          method: 'POST',
          body: fallbackForm,
        })
        const fallbackPayload = await fallbackResponse.json()
        if (!fallbackResponse.ok || fallbackPayload.status === 'Error') {
          throw new Error(fallbackPayload.detail || fallbackPayload.message || 'Upload failed.')
        }
        setUploadFile(null)
        await refreshDocuments(indexName)
        pushToast(`Indexed ${uploadFile.name} as ${fallbackPayload.category}.`, 'success')
      } catch (fallbackError) {
        pushToast(fallbackError instanceof Error ? fallbackError.message : String(error), 'error')
      }
    } finally {
      setBusy(false)
      setLoadingMessage('Ready')
    }
  }

  async function handleUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!uploadFile || isSharedWorkspace) return
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
      pushToast('Feedback submitted. Thank you.', 'success')
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
    const normalizedWorkspace = normalizeWorkspace(storedWorkspace || generateWorkspaceName())
    const storedMode = localStorage.getItem(ACTIVE_WORKSPACE_KEY)
    const storedUserId = localStorage.getItem(FEEDBACK_USER_KEY)
    const storedTheme = localStorage.getItem(THEME_KEY)
    setPersonalWorkspace(normalizedWorkspace)
    setWorkspaceDraft(normalizedWorkspace)
    setActiveWorkspace(storedMode === 'shared' ? 'shared' : 'personal')
    setFeedbackUserId(storedUserId ?? '')
    setTheme(storedTheme === 'dark' ? 'dark' : 'light')
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
      }
    })
    void refreshDocuments(indexName)
  }, [indexName])

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="panel brand-panel">
          <div className="brand-row">
            <img className="brand-logo" src={logoSrc} alt="RAG demo logo" />
            <button className="ghost-button theme-toggle" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>
              {theme === 'light' ? 'Dark mode' : 'Light mode'}
            </button>
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
          <div className="workspace-switcher">
            <button
              className={`workspace-tab ${!isSharedWorkspace ? 'active' : ''}`}
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
          </div>
          <label className="field">
            <span>{isSharedWorkspace ? 'Shared workspace' : 'Personal workspace'}</span>
            <input
              value={isSharedWorkspace ? indexName : workspaceDraft}
              disabled={isSharedWorkspace}
              onChange={(event) => setWorkspaceDraft(event.target.value)}
              onBlur={() => setPersonalWorkspace(normalizeWorkspace(workspaceDraft))}
            />
          </label>
          <p className="helper-text">
            {isSharedWorkspace
              ? 'Read-only workspace with preloaded demo content.'
              : 'Only your uploads and queries use this workspace.'}
          </p>
        </div>

        <div className="panel current-thread-panel">
          <div className="panel-head tight">
            <h2>Current chat</h2>
            <span className="current-thread-badge">{activeThread ? 'Active' : 'Idle'}</span>
          </div>
          {activeThread ? (
            <div className="current-thread-summary">
              <strong>{summarizeThread(activeThread)}</strong>
              <span>{new Date(activeThread.createdAt).toLocaleString()}</span>
            </div>
          ) : (
            <p className="history-empty">Start a new chat to create the active thread.</p>
          )}
        </div>

        <div className="panel grow">
          <div className="panel-head">
            <h2>History</h2>
          </div>
          <div className="thread-list" ref={menuContainerRef}>
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
      </aside>

      <main className="workspace">
        <section className="hero-card">
          <div>
            <p className="eyebrow">Cost-lean local implementation</p>
            <h2>{isSharedWorkspace ? 'Explore shared demo documents safely' : 'Upload docs and test your own isolated workspace'}</h2>
            <p className="helper-text strong">Active workspace: {indexName}</p>
            <div className="workspace-meta-row">
              <span className="hero-badge">{isSharedWorkspace ? 'Read-only' : 'Read / Write'}</span>
              <span className="hero-badge subtle">{loadingMessage}</span>
            </div>
          </div>
          <form className="upload-form" onSubmit={(event) => void handleUpload(event)}>
            <input
              type="file"
              accept=".pdf,.txt,.docx,.xlsx"
              disabled={isSharedWorkspace}
              onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
            />
            <button type="submit" disabled={busy || !uploadFile || isSharedWorkspace}>
              {busy ? 'Working...' : isSharedWorkspace ? 'Read-only' : 'Upload'}
            </button>
          </form>
        </section>

        <section className="content-grid">
          <div className="chat-card">
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
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                      ) : (
                        <p>{message.content}</p>
                      )}
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
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about coverage, claims, policy details, or similar support tickets..."
              />
              <button type="submit" disabled={busy || !question.trim()}>
                {busy ? 'Thinking...' : 'Send'}
              </button>
            </form>
          </div>

          <div className="side-stack">
            <div className="side-card">
              <button className="accordion-toggle" onClick={() => setDocumentsOpen((current) => !current)}>
                <span>Indexed documents</span>
                <div className="accordion-meta">
                  <span className="accordion-count">{documents.length}</span>
                  <span className={`accordion-chevron ${documentsOpen ? 'open' : ''}`}>⌄</span>
                </div>
              </button>
              {documentsOpen ? (
                <div className="document-list">
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
                <span className={`accordion-chevron ${feedbackOpen ? 'open' : ''}`}>⌄</span>
              </button>
              {feedbackOpen ? (
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
