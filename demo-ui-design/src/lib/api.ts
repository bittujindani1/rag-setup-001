const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/+$/, '');
const AUTH_KEY = 'rag-v2-auth';
const PREFIX = '/SFRAG';

/* ---------- helpers ---------- */

export function getAuth(): { username: string; role: string; authorization: string } | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setAuth(username: string, role: string, authorization: string) {
  localStorage.setItem(AUTH_KEY, JSON.stringify({ username, role, authorization }));
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
}

function authHeaders(): Record<string, string> {
  const auth = getAuth();
  return auth?.authorization ? { Authorization: auth.authorization } : {};
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const ah = authHeaders();
  Object.entries(ah).forEach(([k, v]) => headers.set(k, v));

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

/* ---------- auth ---------- */

export async function login(username: string, password: string) {
  const res = await fetch(`${API_BASE}${PREFIX}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error('Invalid credentials');
  const data = await res.json();
  const authorization = `Basic ${btoa(`${username}:${password}`)}`;
  setAuth(data.username ?? username, data.role ?? 'user', authorization);
  return { username: data.username ?? username, role: data.role ?? 'user', authorization };
}

/* ---------- threads ---------- */

export function listThreads(workspaceId: string) {
  return apiFetch<{ threads: any[] }>(`${PREFIX}/threads?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function getThread(threadId: string, workspaceId: string) {
  return apiFetch<any>(`${PREFIX}/threads/${threadId}?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function createThread(workspaceId: string, name?: string) {
  return apiFetch<{ thread_id: string; session_id: string; name: string }>(`${PREFIX}/threads`, {
    method: 'POST',
    body: JSON.stringify({ name: name ?? 'New chat', workspace_id: workspaceId }),
  });
}

export function deleteThread(threadId: string, workspaceId: string) {
  return apiFetch<void>(`${PREFIX}/threads/${threadId}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE',
  });
}

/* ---------- documents / workspace ---------- */

export function listDocuments(indexName: string) {
  return apiFetch<{ documents: any[] }>(`${PREFIX}/documents/${indexName}`);
}

export function listCategories(indexName: string) {
  return apiFetch<{ categories: any[] }>(`${PREFIX}/categories/${indexName}`);
}

export function getUploadPolicy(indexName: string) {
  return apiFetch<any>(`${PREFIX}/upload-policy/${indexName}`);
}

export function deleteWorkspace(workspaceId: string) {
  return apiFetch<any>(`${PREFIX}/workspaces/${encodeURIComponent(workspaceId)}`, { method: 'DELETE' });
}

export function listWorkspaces() {
  return apiFetch<{ workspaces: string[] }>(`${PREFIX}/workspaces`);
}

/* ---------- retrieval ---------- */

export async function queryRetrieval(payload: {
  user_query: string;
  index_name: string;
  session_id: string;
  thread_id?: string | null;
  selected_category?: string | null;
  document_filter?: string | null;
}) {
  return apiFetch<any>(`${PREFIX}/retrieval`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function queryRetrievalImage(formData: FormData) {
  return apiFetch<any>(`${PREFIX}/retrieval-image`, {
    method: 'POST',
    body: formData,
  });
}

/* ---------- ingest ---------- */

export async function ingestDocument(formData: FormData) {
  return apiFetch<any>(`${PREFIX}/ingest`, { method: 'POST', body: formData });
}

/* ---------- feedback ---------- */

export function submitFeedback(userId: string, workspaceId: string, feedback: string) {
  return apiFetch<any>(`${PREFIX}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, workspace_id: workspaceId, feedback }),
  });
}

/* ---------- analytics ---------- */

export function listDatasets() {
  return apiFetch<{ datasets: any[] }>(`${PREFIX}/analytics/datasets`);
}

export function deleteDataset(datasetId: string) {
  return apiFetch<any>(`${PREFIX}/analytics/datasets/${datasetId}`, { method: 'DELETE' });
}

export function getAnalyticsSummary(datasetId: string) {
  return apiFetch<any>(`${PREFIX}/analytics/summary/${datasetId}`);
}

export function getAnalyticsMetrics(datasetId: string) {
  return apiFetch<any>(`${PREFIX}/analytics/metrics/${datasetId}`);
}

export function uploadAnalyticsDataset(datasetId: string, file: File) {
  const form = new FormData();
  form.append('dataset_id', datasetId);
  form.append('file', file);
  return apiFetch<any>(`${PREFIX}/analytics/upload`, { method: 'POST', body: form });
}

export function queryAnalytics(datasetId: string, question: string) {
  return apiFetch<any>(`${PREFIX}/analytics/query`, {
    method: 'POST',
    body: JSON.stringify({ dataset_id: datasetId, question }),
  });
}

/* ---------- agents ---------- */

export function getAgentPresets() {
  return apiFetch<{ presets: any[] }>(`${PREFIX}/agents/presets`);
}

export function listAgentRuns(workspaceId: string) {
  return apiFetch<{ runs: any[] }>(`${PREFIX}/agents/runs?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function getAgentRun(runId: string, workspaceId: string) {
  return apiFetch<any>(`${PREFIX}/agents/runs/${runId}?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function startAgentRunStream(
  goal: string,
  workspaceId: string,
  datasetId?: string,
  indexName?: string,
): { response: Promise<Response>; abort: () => void } {
  const controller = new AbortController();
  const ah = authHeaders();
  const response = fetch(`${API_BASE}${PREFIX}/agents/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...ah },
    body: JSON.stringify({
      goal,
      workspace_id: workspaceId,
      dataset_id: datasetId || undefined,
      index_name: indexName || undefined,
    }),
    signal: controller.signal,
  });
  return { response, abort: () => controller.abort() };
}

/* ---------- admin ---------- */

export function resetDemo() {
  return apiFetch<any>(`${PREFIX}/admin/reset-demo`, { method: 'POST' });
}

export function getHealth() {
  return apiFetch<any>('/health');
}
