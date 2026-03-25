import { Search, Database, MoreVertical, Trash2, Clock, FileSpreadsheet, Plus } from 'lucide-react';
import { useState } from 'react';
import { Dataset } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';

interface AnalyticsSidebarProps {
  datasets: Dataset[];
  selectedDatasetId: string | null;
  onSelectDataset: (id: string) => void;
  onDeleteDataset: (id: string) => void;
  onUploadClick: () => void;
}

export default function AnalyticsSidebar({
  datasets,
  selectedDatasetId,
  onSelectDataset,
  onDeleteDataset,
  onUploadClick
}: AnalyticsSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const filteredDatasets = datasets.filter(ds => 
    ds.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    ds.source.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const selectedDataset = datasets.find(ds => ds.id === selectedDatasetId);

  return (
    <aside className="w-64 bg-surface border-r border-border flex flex-col h-full overflow-hidden relative z-30">
      {/* Header */}
      <div className="p-4 border-b border-border bg-surface-secondary">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Database className="w-3.5 h-3.5 text-accent" />
            <h2 className="text-sm font-semibold text-foreground tracking-tight">Datasets</h2>
          </div>
          <button 
            onClick={onUploadClick}
            className="p-1.5 bg-accent/10 text-accent rounded hover:bg-accent hover:text-white transition-colors border border-accent/20"
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
        
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted" />
          <input 
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search..."
            className="w-full bg-background border border-border rounded py-2 pl-9 pr-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-accent/50 transition-colors placeholder:text-muted"
          />
        </div>
      </div>

      {/* Dataset List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 custom-scrollbar">
        <AnimatePresence mode="popLayout">
          {filteredDatasets.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-muted font-medium">No datasets found</p>
            </div>
          ) : (
            filteredDatasets.map((ds) => (
              <motion.div
                layout
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                key={ds.id}
                className="group relative"
              >
                <button
                  onClick={() => onSelectDataset(ds.id)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-3 rounded-lg transition-colors border",
                    selectedDatasetId === ds.id 
                      ? "bg-accent/10 text-accent border-accent/20" 
                      : "text-muted border-transparent hover:bg-background hover:text-foreground hover:border-border"
                  )}
                >
                  <FileSpreadsheet className={cn(
                    "w-4 h-4 shrink-0",
                    selectedDatasetId === ds.id ? "text-accent" : "text-muted"
                  )} />
                  <div className="flex flex-col items-start min-w-0">
                    <span className="text-sm font-medium truncate w-full tracking-tight">{ds.name}</span>
                    <span className="text-[9px] text-muted-foreground/50 truncate w-full">{ds.source} • {ds.rowCount.toLocaleString()} rows</span>
                  </div>
                </button>

                {/* Actions */}
                <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                  {confirmDelete === ds.id ? (
                    <div className="flex items-center gap-1 bg-background border border-border rounded p-0.5 shadow-lg">
                      <button 
                        onClick={() => {
                          onDeleteDataset(ds.id);
                          setConfirmDelete(null);
                        }}
                        className="p-1 text-error hover:bg-error/10 rounded transition-all"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                      <button 
                        onClick={() => setConfirmDelete(null)}
                        className="p-1 text-muted hover:bg-background rounded transition-colors"
                      >
                        <MoreVertical className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <button 
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(ds.id);
                      }}
                      className="p-1.5 hover:text-error text-muted transition-colors hover:bg-error/10 rounded"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>
      </div>

      {/* Selected Dataset Meta Card - Tighter */}
      {selectedDataset && (
        <div className="p-3 border-t border-border bg-surface-secondary">
          <div className="bg-background border border-border rounded-lg p-3">
            <h3 className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em] mb-2">Active Context</h3>
            <p className="text-sm font-semibold text-foreground truncate mb-3">{selectedDataset.name}</p>
            
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/50">
              <div className="flex flex-col">
                <span className="text-[11px] text-muted uppercase font-semibold">Rows</span>
                <span className="text-[13px] font-semibold text-foreground tabular-nums">{selectedDataset.rowCount.toLocaleString()}</span>
              </div>
              <div className="flex flex-col text-right">
                <span className="text-[11px] text-muted uppercase font-semibold">Cols</span>
                <span className="text-[13px] font-semibold text-foreground tabular-nums">{selectedDataset.columnCount}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
