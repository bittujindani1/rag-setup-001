import { FileUp, Loader2, CheckCircle2, AlertCircle, X, FileText, Image as ImageIcon, Plus } from 'lucide-react';
import { useState, useRef } from 'react';
import { Attachment } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';

interface UploadPanelProps {
  onUpload: (files: FileList) => void;
  isUploading: boolean;
  attachments: Attachment[];
  onRemove: (id: string) => void;
}

export default function UploadPanel({ 
  onUpload, 
  isUploading, 
  attachments, 
  onRemove 
}: UploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="px-6 py-3 border border-border bg-surface-secondary rounded-2xl">
      <div className="max-w-5xl mx-auto flex items-center gap-4">
        {/* Compact Upload Trigger */}
        <div className="flex items-center gap-3 shrink-0">
          <button 
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="px-3 py-2.5 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
          >
            {isUploading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
            Upload Docs
          </button>
          <input 
            type="file" 
            multiple 
            ref={fileInputRef} 
            onChange={(e) => e.target.files && onUpload(e.target.files)} 
            className="hidden" 
          />
          <div className="h-4 w-px bg-border" />
        </div>

        {/* Compact File List (Horizontal) */}
        <div className="flex-1 flex items-center gap-2 overflow-x-auto no-scrollbar py-1">
          <AnimatePresence mode="popLayout">
            {attachments.length === 0 ? (
              <span className="text-[11px] text-muted font-medium">
                No documents indexed for this session
              </span>
            ) : (
              attachments.map((att) => (
                <motion.div 
                  key={att.id}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                    className="flex items-center gap-2 bg-background border border-border rounded-lg px-2 py-1.5 min-w-[140px] max-w-[220px] shrink-0 group relative"
                >
                  <div className={cn(
                    "w-5 h-5 rounded flex items-center justify-center shrink-0",
                    att.status === 'success' ? "bg-emerald-500/10 text-emerald-500" : 
                    att.status === 'error' ? "bg-red-500/10 text-red-500" : "bg-blue-600/10 text-blue-500"
                  )}>
                    {att.status === 'uploading' || att.status === 'indexing' ? (
                      <Loader2 className="w-2.5 h-2.5 animate-spin" />
                    ) : att.status === 'success' ? (
                      <CheckCircle2 className="w-2.5 h-2.5" />
                    ) : (
                      <AlertCircle className="w-2.5 h-2.5" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[11px] font-medium text-foreground truncate">{att.name}</p>
                  </div>
                  <button 
                    onClick={() => onRemove(att.id)}
                    className="p-0.5 hover:text-red-400 text-muted transition-all opacity-0 group-hover:opacity-100"
                  >
                    <X className="w-2.5 h-2.5" />
                  </button>
                  
                  {/* Progress Bar for individual items */}
                  {(att.status === 'uploading' || att.status === 'indexing') && (
                    <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-muted overflow-hidden rounded-b-lg">
                      <motion.div 
                        initial={{ x: '-100%' }}
                        animate={{ x: '0%' }}
                        transition={{ duration: 2, repeat: Infinity }}
                        className="w-full h-full bg-blue-500"
                      />
                    </div>
                  )}
                </motion.div>
              ))
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
