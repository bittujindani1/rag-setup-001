import { FileUp, Loader2, CheckCircle2, AlertCircle, X, FileSpreadsheet, Plus } from 'lucide-react';
import { useState, useRef } from 'react';
import { Dataset } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';

interface DatasetUploadPanelProps {
  onUpload: (file: File) => void;
  isUploading: boolean;
  uploadStatus: 'idle' | 'uploading' | 'processing' | 'success' | 'error';
  errorMessage?: string;
  selectedFile: File | null;
  onRemoveFile: () => void;
}

export default function DatasetUploadPanel({ 
  onUpload, 
  isUploading, 
  uploadStatus, 
  errorMessage,
  selectedFile,
  onRemoveFile
}: DatasetUploadPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="px-6 py-3 border-b border-border bg-surface-secondary/10 backdrop-blur-md sticky top-0 z-30">
      <div className="max-w-[1200px] mx-auto flex items-center justify-between gap-6">
        {/* Header Info */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="w-8 h-8 bg-accent/10 rounded flex items-center justify-center border border-accent/20">
            <FileSpreadsheet className="w-4 h-4 text-accent" />
          </div>
          <div>
            <h2 className="text-[10px] font-bold text-foreground uppercase tracking-wider">Analytics Workspace</h2>
            <p className="text-[9px] text-muted-foreground/50 font-medium uppercase tracking-widest">
              CSV, XLSX, JSON • MAX 100MB
            </p>
          </div>
        </div>

        {/* Upload Control */}
        <div className="flex-1 flex items-center gap-4">
          <div className="flex items-center gap-3 shrink-0">
            <button 
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="px-4 py-1.5 bg-accent hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed text-white text-[10px] font-bold rounded transition-all flex items-center gap-2 uppercase tracking-wider border border-accent/20"
            >
              {isUploading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
              Upload Dataset
            </button>
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={(e) => e.target.files && onUpload(e.target.files[0])} 
              className="hidden" 
              accept=".csv,.xlsx,.json"
            />
            <div className="h-4 w-px bg-border/50" />
          </div>

          {/* Upload Status Card */}
          <div className="flex-1 flex items-center gap-3 overflow-hidden">
            <AnimatePresence mode="popLayout">
              {uploadStatus === 'idle' ? (
                <span className="text-[10px] text-muted-foreground/40 font-medium uppercase tracking-widest animate-in fade-in slide-in-from-left-2">
                  Select a structured dataset to begin analysis
                </span>
              ) : (
                <motion.div 
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  className={cn(
                    "flex items-center gap-3 bg-background border rounded px-3 py-1.5 min-w-[280px] max-w-[400px] shrink-0 group relative",
                    uploadStatus === 'error' ? "border-error/30 bg-error/5" : "border-border"
                  )}
                >
                  <div className={cn(
                    "w-6 h-6 rounded flex items-center justify-center shrink-0",
                    uploadStatus === 'success' ? "bg-success/10 text-success" : 
                    uploadStatus === 'error' ? "bg-error/10 text-error" : "bg-accent/10 text-accent"
                  )}>
                    {isUploading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : uploadStatus === 'success' ? (
                      <CheckCircle2 className="w-3.5 h-3.5" />
                    ) : (
                      <AlertCircle className="w-3.5 h-3.5" />
                    )}
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] font-bold text-foreground truncate uppercase tracking-tight">
                      {selectedFile?.name || 'Processing dataset...'}
                    </p>
                    <div className="flex items-center gap-2">
                      <span className={cn(
                        "text-[8px] font-bold uppercase tracking-wider",
                        uploadStatus === 'error' ? "text-error" : "text-success"
                      )}>
                        {uploadStatus === 'error' ? errorMessage : uploadStatus}
                      </span>
                    </div>
                  </div>

                  <button 
                    onClick={onRemoveFile}
                    className="p-1 hover:text-error text-muted-foreground/30 transition-all opacity-0 group-hover:opacity-100 hover:bg-error/10 rounded"
                  >
                    <X className="w-3 h-3" />
                  </button>
                  
                  {/* Progress Bar */}
                  {isUploading && (
                    <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-white/5 overflow-hidden rounded-b">
                      <motion.div 
                        initial={{ x: '-100%' }}
                        animate={{ x: '0%' }}
                        transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                        className="w-full h-full bg-accent"
                      />
                    </div>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}
