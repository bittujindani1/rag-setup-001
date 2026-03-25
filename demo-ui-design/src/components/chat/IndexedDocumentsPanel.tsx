import { FileText, ChevronDown, ChevronUp, Database, Clock, MoreVertical, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Attachment } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';

interface IndexedDocumentsPanelProps {
  documents: Attachment[];
  onRemove: (id: string) => void;
}

export default function IndexedDocumentsPanel({ 
  documents, 
  onRemove 
}: IndexedDocumentsPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  if (documents.length === 0) return null;

  return (
    <div className="px-4 py-3 border border-border bg-surface rounded-2xl">
      <div className="w-full">
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center justify-between w-full group py-1"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 bg-emerald-500/10 rounded-lg flex items-center justify-center">
              <Database className="w-3 h-3 text-emerald-500" />
            </div>
            <div className="text-left">
              <h3 className="text-sm font-semibold text-foreground">Indexed Documents</h3>
              <p className="text-[11px] text-muted font-medium">
                {documents.length} {documents.length === 1 ? 'document' : 'documents'} active
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted font-medium opacity-0 group-hover:opacity-100 transition-opacity">
              {isExpanded ? 'Hide' : 'Show'}
            </span>
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5 text-muted" /> : <ChevronDown className="w-3.5 h-3.5 text-muted" />}
          </div>
        </button>

        <AnimatePresence>
          {isExpanded && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 mt-2 pb-2">
                {documents.map((doc) => (
                  <div 
                    key={doc.id} 
                    className="flex items-center gap-2 p-2 bg-background border border-border rounded-lg hover:border-emerald-500/30 transition-colors group relative"
                  >
                    <div className="w-7 h-7 rounded-md bg-surface-secondary flex items-center justify-center shrink-0">
                      <FileText className="w-3.5 h-3.5 text-muted" />
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] font-medium text-foreground truncate">{doc.name}</span>
                        {doc.category && (
                          <span className="text-[10px] bg-emerald-500/10 text-emerald-500 px-1.5 py-0.5 rounded-sm font-medium">
                            {doc.category}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-0.5">
                      <button 
                        onClick={() => onRemove(doc.id)}
                        className="p-1 hover:text-red-400 text-muted transition-colors"
                      >
                        <Trash2 className="w-2.5 h-2.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
