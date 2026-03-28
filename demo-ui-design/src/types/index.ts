export type UserRole = 'admin' | 'user';

export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  avatar?: string;
}

export type WorkspaceType = 'personal' | 'shared' | 'servicenow';

export interface Workspace {
  id: string;
  name: string;
  type: WorkspaceType;
  isReadOnly: boolean;
  description?: string;
  indexedDocsCount?: number;
}

export interface ChatThread {
  id: string;
  title: string;
  workspaceId: string;
  updatedAt: string;
  lastMessage?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  citations?: Citation[];
  attachments?: Attachment[];
  hasImage?: boolean;
}

export interface Citation {
  filename?: string;
  pdf_url?: string;
  page_numbers?: string[];
  type?: string;
  source?: string;
  content?: string;
  page?: number;
  url?: string;
}

export interface Attachment {
  id: string;
  name: string;
  type: 'document' | 'image';
  url: string;
  file?: File;
  status: 'uploading' | 'indexing' | 'success' | 'error';
  size?: string;
  category?: string;
  contentType?: string;
  timestamp?: string;
  errorMessage?: string;
}

export interface DocumentRecord {
  filename: string;
  category: string;
  content_type: string;
  size_bytes: number;
  updated_at: number;
}

export interface CategorySummary {
  category: string;
  count: number;
}

export interface Dataset {
  id: string;
  name: string;
  source: string;
  rowCount: number;
  columnCount: number;
  updatedAt: string;
  description?: string;
  status: 'processing' | 'ready' | 'failed';
  schema_columns?: string[];
  errorMessage?: string;
}

export interface KpiCardData {
  label: string;
  value: string | number;
  subtitle?: string;
  type: 'numeric' | 'text';
  icon?: string;
}

export interface AnalyticsQueryResult {
  id: string;
  query: string;
  timestamp: string;
  datasetId: string;
  type: 'number' | 'bar' | 'pie' | 'line' | 'table';
  data: any[];
  columns?: string[];
  explanation?: string;
  grounded_explanation?: string | null;
  sql?: string;
  answer?: string;
  error?: string;
}

export interface AgentRunSummary {
  run_id: string;
  goal: string;
  workspace_id: string;
  created_at: number;
  status: string;
  step_count: number;
}

export interface AgentMessage {
  type: 'plan' | 'agent_message' | 'analytics_snapshot' | 'synthesis' | 'done';
  run_id?: string;
  goal?: string;
  steps?: Array<{ agent: string; task: string }>;
  agent?: string;
  agent_name?: string;
  icon?: string;
  color?: string;
  task?: string;
  thought?: string | null;
  tool_used?: string | null;
  tool_result?: string | null;
  output?: string;
  snapshot?: string;
  dataset_id?: string;
  timestamp?: number;
  total_steps?: number;
  created_at?: number;
  workspace_id?: string;
}

export interface AgentStep {
  id: string;
  agent: 'planner' | 'analyst' | 'researcher' | 'executor' | 'synthesizer';
  status: 'pending' | 'running' | 'completed' | 'failed';
  summary: string;
  details?: string;
  timestamp: string;
  output?: string;
  tool_used?: string | null;
  tool_result?: string | null;
}

export interface AgentRun {
  id: string;
  goal: string;
  datasetId?: string;
  ragIndex?: string;
  status: 'running' | 'completed' | 'failed';
  timestamp: string;
  steps: AgentStep[];
  finalReport?: FinalReport;
}

export interface FinalReport {
  title: string;
  overview: string;
  keyFindings: string[];
  recommendations: string[];
  content: string;
  kpis?: KpiCardData[];
}

export interface ModernizationGraphLink {
  source: string;
  target: string;
  relation: string;
  file?: string;
}

export interface ExecutionState {
  executionId: string;
  status: 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'UNKNOWN';
  startedAt?: string;
  updatedAt?: string;
  rawStatus?: string;
}

export interface ParagraphTranslationRecord {
  paragraph_id: string;
  status: 'translated' | 'flagged' | 'error';
  cobol: string;
  translated_code: string;
  notes: string;
  confidence?: number;
}

export interface ModernizationProgramSummary {
  file_id: string;
  status: string;
  wave_plan?: Array<{ wave: number; programs: string[] }>;
  risk_flags?: string[];
  paragraph_status?: Record<string, string>;
  execution_state?: ExecutionState;
}

export interface ModernizationProgramDetail {
  program_id: string;
  status: string;
  artifacts: any;
  execution_state?: ExecutionState;
  paragraph_translation: {
    paragraphs: ParagraphTranslationRecord[];
    paragraph_status: Record<string, string>;
  };
}
