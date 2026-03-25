import { useState, useRef, useEffect, useCallback } from 'react';
import { Sparkles, Search, MoreHorizontal } from 'lucide-react';
import { Message, Attachment, Workspace, DocumentRecord } from '../types';
import { toast } from 'sonner';
import { cn } from '../lib/utils';
import * as api from '../lib/api';
import ChatMessage from './chat/ChatMessage';
import ChatComposer from './chat/ChatComposer';
import UploadPanel from './chat/UploadPanel';
import IndexedDocumentsPanel from './chat/IndexedDocumentsPanel';

interface ChatTabProps {
  workspace: Workspace;
  activeThreadId: string | null;
  sessionId: string;
  setSessionId: (s: string) => void;
  setActiveThreadId: (id: string | null) => void;
  refreshThreads: (wsId?: string) => Promise<any>;
}

function formatBytes(size: number): string {
  if (!size) return '0 B';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ChatTab({ workspace, activeThreadId, sessionId, setSessionId, setActiveThreadId, refreshThreads }: ChatTabProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [indexedDocs, setIndexedDocs] = useState<Attachment[]>([]);
  const [activeAttachments, setActiveAttachments] = useState<Attachment[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(scrollToBottom, [messages]);

  const refreshDocuments = useCallback(async () => {
    try {
      const data = await api.listDocuments(workspace.id);
      const docs: Attachment[] = (data.documents || []).map((d: DocumentRecord) => ({
        id: d.filename,
        name: d.filename,
        type: d.content_type?.startsWith('image/') ? 'image' as const : 'document' as const,
        url: '#',
        status: 'success' as const,
        size: formatBytes(d.size_bytes),
        category: d.category || 'General',
        timestamp: d.updated_at ? new Date(d.updated_at * 1000).toLocaleDateString() : '',
      }));
      setIndexedDocs(docs);
    } catch { /* silent */ }
  }, [workspace.id]);

  useEffect(() => {
    refreshDocuments();
  }, [refreshDocuments]);

  const renderPayloadToMessage = useCallback((payload: any): Message => ({
    id: (Date.now() + 1).toString(),
    role: 'assistant',
    content: payload?.response?.content || 'No response generated.',
    timestamp: new Date().toISOString(),
    citations: (payload?.citation || []).map((c: any) => ({
      filename: c.filename,
      pdf_url: c.pdf_url,
      page_numbers: c.page_numbers,
      type: c.type,
      source: c.filename,
      content: c.text || '',
    })),
  }), []);

  // Load thread messages
  useEffect(() => {
    if (!activeThreadId) {
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: workspace.type === 'servicenow'
          ? 'Hello. You are in the ServiceNow workspace. Ask about recurring incidents, priorities, assignment groups, or SLA patterns.'
          : workspace.type === 'shared'
            ? 'Hello. You are in the shared demo workspace. Ask for a summary, key themes, policy details, or evidence-backed answers.'
            : 'Hello. Upload a document or ask a question about your workspace.',
        timestamp: new Date().toISOString(),
      }]);
      return;
    }
    api.getThread(activeThreadId, workspace.id).then((t: any) => {
      const steps = t?.steps || [];
      const mapped: Message[] = steps.map((s: any, i: number) => ({
        id: `${activeThreadId}-${i}`,
        role: s.type === 'user_message' ? 'user' as const : 'assistant' as const,
        content: (s.output ?? s.input ?? '').trim(),
        timestamp: s.createdAt ?? new Date().toISOString(),
      }));
      setMessages(mapped.length ? mapped : [{
        id: 'welcome',
        role: 'assistant',
        content: 'Start a conversation by asking a question.',
        timestamp: new Date().toISOString(),
      }]);
    }).catch(() => {
      setMessages([]);
    });
  }, [activeThreadId, workspace.id, workspace.type]);

  const ensureThread = useCallback(async (questionSeed?: string): Promise<{ threadId: string; sid: string }> => {
    if (activeThreadId && sessionId) return { threadId: activeThreadId, sid: sessionId };
    const created = await api.createThread(workspace.id, questionSeed?.slice(0, 80) || 'New chat');
    setActiveThreadId(created.thread_id);
    setSessionId(created.session_id);
    await refreshThreads(workspace.id);
    return { threadId: created.thread_id, sid: created.session_id };
  }, [activeThreadId, sessionId, workspace.id, setActiveThreadId, setSessionId, refreshThreads]);

  const handleSend = async (content: string, attachments: Attachment[]) => {
    const imageAttachment = attachments.find((attachment) => attachment.type === 'image' && attachment.file);
    const userContent = imageAttachment
      ? (content.trim() || `Analyze this image: ${imageAttachment.name}`)
      : content;
    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: userContent,
      timestamp: new Date().toISOString(),
      attachments: attachments.length > 0 ? attachments : undefined,
      hasImage: Boolean(imageAttachment),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsThinking(true);

    try {
      const { threadId, sid } = await ensureThread(userContent);
      let payload: any;

      if (imageAttachment?.file) {
        const form = new FormData();
        form.append('index_name', workspace.id);
        form.append('session_id', sid);
        form.append('thread_id', threadId);
        if (content.trim()) {
          form.append('prompt', content.trim());
        }
        form.append('file', imageAttachment.file);
        payload = await api.queryRetrievalImage(form);
      } else {
        payload = await api.queryRetrieval({
          user_query: content,
          index_name: workspace.id,
          session_id: sid,
          thread_id: threadId,
        });
      }

      setMessages(prev => [...prev, renderPayloadToMessage(payload)]);
      await refreshThreads(workspace.id);
    } catch (err) {
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Error: ${err instanceof Error ? err.message : 'Query failed'}`,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsThinking(false);
    }
  };

  const handleUpload = async (files: FileList) => {
    setIsUploading(true);
    const toastId = toast.loading('Uploading and indexing...');
    try {
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append('file', file);
        form.append('index_name', workspace.id);
        await api.ingestDocument(form);
      }
      await refreshDocuments();
      toast.success('Documents indexed and ready for RAG', { id: toastId });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Upload failed', { id: toastId });
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveDoc = (_id: string) => {
    toast.info('Document removal requires admin access');
  };

  const promptChips = workspace.type === 'servicenow'
    ? ['Analyze open incidents', 'Check SLA breaches', 'Show ticket counts by category']
    : indexedDocs.length > 0
      ? ['Summarize indexed docs', 'Key risks and actions', 'What are the types of coverage?']
      : ['How can you help?', 'What are your capabilities?'];

  return (
    <div className="flex flex-col h-full bg-background relative overflow-hidden">
      {/* Header */}
      <div className="h-20 border-b border-border flex items-center justify-between px-10 bg-background sticky top-0 z-30">
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className={cn(
              "w-3.5 h-3.5 rounded-full animate-pulse shadow-lg",
              workspace.isReadOnly ? "bg-amber-500 shadow-amber-500/40" : "bg-emerald-500 shadow-emerald-500/40"
            )} />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-3">
              <span className="text-base font-black text-foreground uppercase tracking-wider">{workspace.name}</span>
              <span className={cn(
              "text-[11px] px-2.5 py-0.5 rounded-lg font-medium",
              workspace.isReadOnly ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" : "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
            )}>
                {workspace.isReadOnly ? 'Read Only' : 'Active'}
              </span>
            </div>
            <span className="text-[12px] text-muted mt-1">
              {workspace.type === 'personal' ? 'Personal RAG Workspace' : 'Enterprise Shared Knowledge Base'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[12px] text-muted font-medium">{indexedDocs.length} docs indexed</span>
          <button className="p-3 text-muted hover:text-foreground transition-colors rounded-2xl hover:bg-surface-secondary border border-transparent hover:border-border">
            <MoreHorizontal className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 flex flex-col relative">
        <div className="sticky top-20 z-20 border-b border-border/70 bg-background/95 backdrop-blur-sm">
          <div className="max-w-[1560px] mx-auto w-full px-8 pt-6 pb-5 space-y-4">
            {!workspace.isReadOnly && (
              <UploadPanel
                onUpload={handleUpload}
                isUploading={isUploading}
                attachments={activeAttachments}
                onRemove={(id) => setActiveAttachments(prev => prev.filter(a => a.id !== id))}
              />
            )}

            {indexedDocs.length > 0 && (
              <IndexedDocumentsPanel documents={indexedDocs} onRemove={handleRemoveDoc} />
            )}
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar">
          <div className="px-8 py-10 space-y-12 max-w-[1560px] mx-auto w-full relative z-10">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full py-32 opacity-20">
              <div className="w-20 h-20 bg-accent/10 rounded-3xl flex items-center justify-center mb-8 border border-accent/20">
                <Sparkles className="w-10 h-10 text-accent" />
              </div>
              <h3 className="text-2xl font-bold tracking-tight text-foreground">Initialize Session</h3>
              <p className="text-sm font-medium mt-4 text-muted">Select a workspace or upload documents to begin analysis.</p>
            </div>
          ) : (
            messages.map((msg) => <ChatMessage key={msg.id} message={msg} />)
          )}

          {isThinking && (
            <div className="flex gap-6 py-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
              <div className="w-11 h-11 rounded-2xl bg-accent/10 flex items-center justify-center shrink-0 border border-accent/20">
                <Sparkles className="w-5 h-5 text-accent animate-pulse" />
              </div>
              <div className="bg-surface-secondary border border-border rounded-[24px] p-6 max-w-[80%]">
                <div className="flex gap-2">
                  <span className="w-2 h-2 bg-accent/70 rounded-full animate-bounce" />
                  <span className="w-2 h-2 bg-accent/70 rounded-full animate-bounce [animation-delay:0.2s]" />
                  <span className="w-2 h-2 bg-accent/70 rounded-full animate-bounce [animation-delay:0.4s]" />
                </div>
                <p className="text-[12px] font-medium mt-3 text-muted">Synthesizing response...</p>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
          </div>
        </div>
      </div>

      {/* Composer */}
      <div className="bg-gradient-to-t from-background via-background/95 to-transparent pt-8 pb-8 sticky bottom-0 z-20">
        <div className="max-w-[1560px] mx-auto px-8">
          <div className="flex gap-3 mb-6 overflow-x-auto pb-3 no-scrollbar px-2">
            {promptChips.map((chip) => (
              <button
                key={chip}
                onClick={() => handleSend(chip, [])}
                className="whitespace-nowrap px-5 py-2.5 bg-surface-secondary border border-border rounded-2xl text-[12px] font-medium text-muted hover:bg-accent/10 hover:text-accent hover:border-accent/30 transition-colors active:scale-95"
              >
                {chip}
              </button>
            ))}
          </div>
          <div className="relative group max-w-[1220px] mx-auto">
            <ChatComposer
              onSend={handleSend}
              isThinking={isThinking}
              isReadOnly={workspace.isReadOnly}
              placeholder={workspace.type === 'servicenow' ? "Search ServiceNow incidents..." : "Ask about your indexed documents..."}
            />
          </div>
          <p className="text-[11px] text-center mt-4 text-muted font-medium">
            Enterprise AI may produce inaccurate results. Verify critical information.
          </p>
        </div>
      </div>
    </div>
  );
}
