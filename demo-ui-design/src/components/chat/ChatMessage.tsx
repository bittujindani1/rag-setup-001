import { User, Copy, Check, FileText, Image as ImageIcon, ExternalLink, Sparkles, Clock } from 'lucide-react';
import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';
import { Message, Citation } from '../../types';

interface ChatMessageProps {
  message: Message;
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const [copied, setCopied] = useState(false);

  const copyToClipboard = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "flex gap-4 group py-3",
        message.role === 'user' ? "flex-row-reverse" : "flex-row"
      )}
    >
      <div className={cn(
        "w-8 h-8 rounded-xl flex items-center justify-center shrink-0 border transition-all group-hover:scale-105",
        message.role === 'assistant' 
          ? "bg-accent text-white border-accent/70" 
          : "bg-surface-secondary border-border text-muted"
      )}>
        {message.role === 'assistant' ? (
          <Sparkles className="w-4 h-4 text-white" />
        ) : (
          <User className="w-4 h-4" />
        )}
      </div>

      <div className={cn(
        "flex flex-col gap-2 w-full",
        message.role === 'user' ? "items-end text-right" : "items-start text-left"
      )}>
        <div className={cn(
          "rounded-[24px] p-5 text-[14px] leading-7 transition-colors relative overflow-hidden border",
          message.role === 'assistant' 
            ? "bg-surface-secondary text-foreground border-border group-hover:border-accent/25 w-full max-w-[min(100%,1220px)]" 
            : "bg-accent text-white border-accent/70 max-w-[min(82%,760px)]"
        )}>
          {/* Attachments */}
          {message.attachments && message.attachments.length > 0 && (
            <div className={cn(
              "flex flex-wrap gap-2 mb-4",
              message.role === 'user' ? "justify-end" : "justify-start"
            )}>
              {message.attachments.map(att => (
                <div 
                  key={att.id} 
                  className={cn(
                    "flex items-center gap-2 rounded-lg px-3 py-1.5 text-[11px] font-medium border transition-colors",
                    message.role === 'user' ? "bg-white/10 text-white border-white/20" : "bg-background text-muted border-border hover:border-accent/20"
                  )}
                >
                  {att.type === 'image' ? <ImageIcon className="w-3 h-3" /> : <FileText className="w-3 h-3" />}
                  <span className="max-w-[150px] truncate">{att.name}</span>
                </div>
              ))}
            </div>
          )}
          
          <div className="markdown-body max-w-none font-medium">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        </div>

        {/* Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className={cn(
            "flex flex-wrap gap-3 mt-2",
            message.role === 'user' ? "justify-end" : "justify-start"
          )}>
            {message.citations.map((cit, idx) => (
              <CitationPill key={`${cit.filename || cit.source}-${idx}`} citation={cit} />
            ))}
          </div>
        )}

        {/* Footer Actions */}
        <div className={cn(
          "flex items-center gap-4 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-1 group-hover:translate-y-0",
          message.role === 'user' ? "flex-row-reverse" : "flex-row"
        )}>
          <button 
            onClick={copyToClipboard}
            className="text-[11px] text-muted hover:text-accent flex items-center gap-1.5 font-medium transition-colors"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
            {copied ? 'Copied' : 'Copy'}
          </button>
          <div className="flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-muted" />
            <span className="text-[11px] text-muted font-medium">
              {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function CitationPill({ citation }: { citation: Citation }) {
  const name = citation.filename || citation.source || 'Source';
  const pages = (citation.page_numbers ?? []).filter(p => p && p !== 'N/A');
  const label = pages.length > 0 ? `${name} (p. ${pages.join(', ')})` : name;
  const href = citation.pdf_url && citation.pdf_url !== 'N/A' ? citation.pdf_url : undefined;

  return (
    <div className="group/cit relative">
      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 px-2.5 py-1.5 bg-background border border-border rounded-md text-[11px] text-muted hover:text-accent hover:border-accent/40 transition-colors font-medium"
        >
          <div className="w-1.5 h-1.5 rounded-full bg-accent/70 group-hover/cit:bg-accent transition-colors" />
          <span>{label}</span>
          <ExternalLink className="w-3 h-3 opacity-70" />
        </a>
      ) : (
        <span className="flex items-center gap-1.5 px-2.5 py-1.5 bg-background border border-border rounded-md text-[11px] text-muted font-medium">
          <div className="w-1.5 h-1.5 rounded-full bg-accent/70" />
          <span>{label}</span>
        </span>
      )}
    </div>
  );
}
