import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type Message = {
  role: 'user' | 'assistant'
  content: string
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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
const DEFAULT_INDEX = import.meta.env.VITE_INDEX_NAME ?? 'statefarm_rag'
const SHARED_WORKSPACE = import.meta.env.VITE_SHARED_INDEX_NAME ?? 'demo-shared'
const PERSONAL_WORKSPACE_KEY = 'rag-demo-personal-workspace'
const ACTIVE_WORKSPACE_KEY = 'rag-demo-active-workspace'
const FEEDBACK_USER_KEY = 'rag-demo-feedback-user'

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
    thread?.steps?.map((step) => ({
      role: step.type === 'user_message' ? 'user' : 'assistant',
      content: (step.output ?? step.input ?? '').trim(),
    })) ?? []
  )
}

function formatBytes(size: number): string {
  if (!size) return '0 B'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
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
  const [status, setStatus] = useState('Ready')
  const [busy, setBusy] = useState(false)

  const indexName = useMemo(
    () => (activeWorkspace === 'shared' ? SHARED_WORKSPACE : personalWorkspace),
    [activeWorkspace, personalWorkspace],
  )
  const isSharedWorkspace = activeWorkspace === 'shared'

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
  }

  async function ensureThread(): Promise<{ threadId: string; sessionId: string }> {
    if (activeThreadId && sessionId) {
      return { threadId: activeThreadId, sessionId }
    }
    const created = await apiFetch<{ thread_id: string; session_id: string; name: string }>('/SFRAG/threads', {
      method: 'POST',
      body: JSON.stringify({ name: 'New chat', workspace_id: indexName }),
    })
    setActiveThreadId(created.thread_id)
    setSessionId(created.session_id)
    await refreshThreads(indexName)
    return { threadId: created.thread_id, sessionId: created.session_id }
  }

  async function openThread(threadId: string) {
    const thread = await apiFetch<Thread>(
      `/SFRAG/threads/${threadId}?workspace_id=${encodeURIComponent(indexName)}`,
    )
    setActiveThreadId(threadId)
    setSessionId(thread.metadata?.session_id ?? '')
    setMessages(mapStepsToMessages(thread))
  }

  async function handleDeleteThread(threadId: string) {
    await apiFetch(`/SFRAG/threads/${threadId}?workspace_id=${encodeURIComponent(indexName)}`, { method: 'DELETE' })
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
  }

  async function handleSend(rawQuestion?: string, forcedCategory?: string | null) {
    const finalQuestion = (rawQuestion ?? question).trim()
    if (!finalQuestion) return
    try {
      setBusy(true)
      setStatus(`Searching ${indexName}...`)
      const { threadId, sessionId: currentSessionId } = await ensureThread()

      setMessages((current) => [...current, { role: 'user', content: finalQuestion }])
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
        setMessages((current) => [...current, { role: 'assistant', content: payload.response.content }])
        setCategories(payload.categories ?? categories)
        setStatus('Select a category to continue.')
      } else {
        setPendingQuestion(null)
        setSelectedCategory(payload.selected_category ?? forcedCategory ?? null)
        setMessages((current) => [...current, { role: 'assistant', content: payload.response.content }])
        setStatus('Answer ready.')
      }

      await refreshThreads(indexName)
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Request failed.')
    } finally {
      setBusy(false)
    }
  }

  async function performUpload() {
    if (!uploadFile || isSharedWorkspace) return
    if (uploadFile.size > 5 * 1024 * 1024) {
      setStatus('Upload blocked: file is larger than 5 MB.')
      return
    }
    try {
      setBusy(true)
      setStatus(`Uploading ${uploadFile.name} to ${indexName}...`)
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
      setStatus(`Indexed ${uploadFile.name} in ${indexName} as ${finalJob.result?.category ?? 'uncategorized'}.`)
      setUploadFile(null)
      await refreshDocuments(indexName)
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
        setStatus(`Indexed ${uploadFile.name} in ${indexName} as ${fallbackPayload.category}.`)
        setUploadFile(null)
        await refreshDocuments(indexName)
      } catch (fallbackError) {
        setStatus(fallbackError instanceof Error ? fallbackError.message : String(error))
      }
    } finally {
      setBusy(false)
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
      setStatus('Feedback needs both your ID and a short note.')
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
      setStatus('Feedback submitted. Thank you.')
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Feedback submission failed.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const storedWorkspace = localStorage.getItem(PERSONAL_WORKSPACE_KEY)
    const normalizedWorkspace = normalizeWorkspace(storedWorkspace || generateWorkspaceName())
    const storedMode = localStorage.getItem(ACTIVE_WORKSPACE_KEY)
    const storedUserId = localStorage.getItem(FEEDBACK_USER_KEY)
    setPersonalWorkspace(normalizedWorkspace)
    setWorkspaceDraft(normalizedWorkspace)
    setActiveWorkspace(storedMode === 'shared' ? 'shared' : 'personal')
    setFeedbackUserId(storedUserId ?? '')
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
        <div className="panel">
          <div className="panel-head">
            <div>
              <p className="eyebrow">MVP Console</p>
              <h1>RAG Demo</h1>
            </div>
            <button className="ghost-button" onClick={() => void ensureThread()}>
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

        <div className="panel grow">
          <div className="panel-head">
            <h2>History</h2>
          </div>
          <div className="thread-list">
            {threads.map((thread) => (
              <div key={thread.id} className={`thread-item ${thread.id === activeThreadId ? 'active' : ''}`}>
                <button className="thread-link" onClick={() => void openThread(thread.id)}>
                  <strong>{thread.name || 'New chat'}</strong>
                  <span>{new Date(thread.createdAt).toLocaleString()}</span>
                </button>
                <button className="menu-button" onClick={() => void handleDeleteThread(thread.id)}>
                  ...
                </button>
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
          </div>
          <form className="upload-form" onSubmit={(event) => void handleUpload(event)}>
            <input
              type="file"
              accept=".pdf,.txt,.docx,.xlsx"
              disabled={isSharedWorkspace}
              onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
            />
            <button type="submit" disabled={busy || !uploadFile || isSharedWorkspace}>
              {isSharedWorkspace ? 'Read-only' : 'Upload'}
            </button>
          </form>
        </section>

        <section className="content-grid">
          <div className="chat-card">
            <div className="chat-log">
              {messages.length === 0 ? (
                <div className="empty-state">
                  {isSharedWorkspace
                    ? 'Ask questions against the shared demo workspace.'
                    : 'Start a thread or upload a document to begin.'}
                </div>
              ) : (
                messages.map((message, index) => (
                  <article key={`${message.role}-${index}`} className={`bubble ${message.role}`}>
                    <span>{message.role === 'user' ? 'You' : 'Assistant'}</span>
                    <p>{message.content}</p>
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
                {busy ? 'Working...' : 'Send'}
              </button>
            </form>
          </div>

          <div className="side-stack">
            <div className="side-card">
              <div className="panel-head">
                <h2>Indexed documents</h2>
                <span>{documents.length}</span>
              </div>
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
            </div>

            <div className="side-card">
              <div className="panel-head">
                <h2>Feedback</h2>
              </div>
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
          </div>
        </section>

        <footer className="status-bar">{status}</footer>
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
                  setStatus('Upload cancelled.')
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
