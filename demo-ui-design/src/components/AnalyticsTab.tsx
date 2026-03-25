import { useState, useEffect, useCallback } from 'react';
import { Dataset, KpiCardData, AnalyticsQueryResult } from '../types';
import { cn } from '../lib/utils';
import { motion, AnimatePresence } from 'motion/react';
import { toast } from 'sonner';
import { BarChart3 } from 'lucide-react';
import * as api from '../lib/api';

import AnalyticsSidebar from './analytics/AnalyticsSidebar';
import DatasetUploadPanel from './analytics/DatasetUploadPanel';
import KpiStrip from './analytics/KpiStrip';
import AnalyticsQueryBox from './analytics/AnalyticsQueryBox';
import ResultCard from './analytics/ResultCard';

function inferChartType(chartType: string, rows: any[]): 'number' | 'bar' | 'pie' | 'line' | 'table' {
  if (!rows.length) return 'table';
  if (chartType === 'number' || (rows.length === 1 && Object.keys(rows[0] ?? {}).length === 1)) return 'number';
  if (chartType === 'line') return 'line';
  if (chartType === 'pie') return 'pie';
  if (chartType === 'table') return 'table';
  return rows.length <= 6 ? 'pie' : 'bar';
}

export default function AnalyticsTab() {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'processing' | 'success' | 'error'>('idle');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | undefined>();
  const [kpis, setKpis] = useState<KpiCardData[]>([]);
  const [dashboardResults, setDashboardResults] = useState<AnalyticsQueryResult[]>([]);
  const [isQueryLoading, setIsQueryLoading] = useState(false);
  const [recentQueries, setRecentQueries] = useState<AnalyticsQueryResult[]>([]);
  const [currentResults, setCurrentResults] = useState<AnalyticsQueryResult[]>([]);

  const loadDatasets = useCallback(async (selectId?: string) => {
    try {
      const data = await api.listDatasets();
      const mapped: Dataset[] = (data.datasets || []).map((d: any) => ({
        id: d.dataset_id,
        name: d.source_name || d.dataset_id,
        source: 'S3 / Athena',
        rowCount: d.row_count ?? 0,
        columnCount: d.schema_columns?.length ?? 0,
        updatedAt: d.updated_at ? new Date(d.updated_at * 1000).toISOString() : new Date().toISOString(),
        status: 'ready' as const,
        schema_columns: d.schema_columns,
      }));
      setDatasets(mapped);
      if (selectId) setSelectedDatasetId(selectId);
      else if (!selectedDatasetId && mapped.length > 0) setSelectedDatasetId(mapped[0].id);
      return mapped;
    } catch {
      return [];
    }
  }, [selectedDatasetId]);

  const hydrateDashboard = useCallback(async (datasetId: string) => {
    try {
      const summary = await api.getAnalyticsSummary(datasetId);
      const metrics: KpiCardData[] = Object.entries(summary.summary || {}).map(([key, val]: [string, any]) => {
        const label = key.replace(/^top_/, 'Top ').replace(/_/g, ' ');
        let primary = '';
        let subtitle = '';
        if (val && typeof val === 'object' && !Array.isArray(val)) {
          primary = String(val.label ?? val.value ?? val.name ?? '');
          subtitle = val.count !== undefined ? `${val.count} records` : '';
        } else {
          primary = typeof val === 'number' ? val.toLocaleString() : String(val ?? '');
        }
        return { label, value: primary, subtitle, type: typeof val === 'number' ? 'numeric' as const : 'text' as const };
      });
      setKpis(metrics);
      const defaultMetrics = (summary.metrics || []).filter((metric: any) => metric.type !== 'summary').slice(0, 4);
      const metricResponses = await Promise.all(
        defaultMetrics.map(async (metric: any) => {
          try {
            const res = await api.queryAnalytics(datasetId, metric.title);
            const rows = res.result?.rows || [];
            const cols = res.result?.columns || [];
            const chartType = inferChartType(res.chart_type || metric.chart_type || 'bar', rows);
            const mappedData = chartType === 'table'
              ? rows
              : rows.map((r: any) => {
                  const entries = Object.entries(r);
                  return { name: String(entries[0]?.[1] ?? ''), value: Number(entries[1]?.[1] ?? 0) };
                });
            return {
              id: `metric-${metric.metric_id}`,
              query: metric.title,
              timestamp: new Date().toISOString(),
              datasetId,
              type: chartType,
              data: mappedData,
              columns: cols,
              explanation: res.grounded_explanation || res.answer || metric.description || '',
              sql: res.sql,
            } as AnalyticsQueryResult;
          } catch {
            return null;
          }
        }),
      );
      setDashboardResults(metricResponses.filter(Boolean) as AnalyticsQueryResult[]);
    } catch {
      setKpis([]);
      setDashboardResults([]);
    }
  }, []);

  useEffect(() => { loadDatasets(); }, [loadDatasets]);
  useEffect(() => { if (selectedDatasetId) hydrateDashboard(selectedDatasetId); }, [selectedDatasetId, hydrateDashboard]);

  const handleUpload = async (file: File) => {
    setSelectedFile(file);
    setIsUploading(true);
    setUploadStatus('uploading');
    try {
      const datasetId = file.name.replace(/\.[^/.]+$/, '').toLowerCase().replace(/[^a-z0-9_-]+/g, '_');
      setUploadStatus('processing');
      const result = await api.uploadAnalyticsDataset(datasetId, file);
      await loadDatasets(result.dataset_id);
      await hydrateDashboard(result.dataset_id);
      setUploadStatus('success');
      toast.success(`Dataset ${result.dataset_id} uploaded with ${result.row_count} rows.`);
    } catch (err) {
      setUploadStatus('error');
      setErrorMessage(err instanceof Error ? err.message : 'Upload failed');
      toast.error(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  const handleQuery = async (question: string) => {
    if (!selectedDatasetId) { toast.error('Select a dataset first'); return; }
    setIsQueryLoading(true);
    try {
      const res = await api.queryAnalytics(selectedDatasetId, question);
      const rows = res.result?.rows || [];
      const cols = res.result?.columns || [];
      const chartType = inferChartType(res.chart_type || 'bar', rows);
      const mappedData = chartType === 'table'
        ? rows
        : rows.map((r: any) => {
            const entries = Object.entries(r);
            return { name: String(entries[0]?.[1] ?? ''), value: Number(entries[1]?.[1] ?? 0) };
          });
      const result: AnalyticsQueryResult = {
        id: `res-${Date.now()}`,
        query: question,
        timestamp: new Date().toISOString(),
        datasetId: selectedDatasetId,
        type: chartType,
        data: mappedData,
        columns: cols,
        explanation: res.grounded_explanation || res.answer || '',
        sql: res.sql,
      };
      setCurrentResults(prev => [result, ...prev]);
      setRecentQueries(prev => [result, ...prev.filter(q => q.query !== question)].slice(0, 10));
      toast.success('Analysis complete');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Query failed');
    } finally {
      setIsQueryLoading(false);
    }
  };

  const handleDeleteDataset = async (id: string) => {
    try {
      await api.deleteDataset(id);
      await loadDatasets();
      if (selectedDatasetId === id) { setSelectedDatasetId(null); setKpis([]); setCurrentResults([]); setDashboardResults([]); }
      toast.success('Dataset deleted');
    } catch (err) { toast.error(err instanceof Error ? err.message : 'Delete failed'); }
  };

  const handleDeleteHistory = (id: string) => {
    setRecentQueries(prev => prev.filter(q => q.id !== id));
    setCurrentResults(prev => prev.filter(q => q.id !== id));
  };

  return (
    <div className="flex h-full bg-background overflow-hidden relative">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_100%_0%,rgba(59,130,246,0.03),transparent_40%)] pointer-events-none" />
      <AnalyticsSidebar
        datasets={datasets}
        selectedDatasetId={selectedDatasetId}
        onSelectDataset={setSelectedDatasetId}
        onDeleteDataset={handleDeleteDataset}
        onUploadClick={() => setUploadStatus('idle')}
      />
      <main className="flex-1 flex flex-col overflow-hidden relative z-10">
        <DatasetUploadPanel
          onUpload={handleUpload}
          isUploading={isUploading}
          uploadStatus={uploadStatus}
          errorMessage={errorMessage}
          selectedFile={selectedFile}
          onRemoveFile={() => { setSelectedFile(null); setUploadStatus('idle'); }}
        />
        <div className="flex-1 overflow-y-auto custom-scrollbar bg-background">
          <div className="max-w-[1200px] mx-auto px-6 py-8 space-y-8">
            <div className="flex items-center justify-between border-b border-border pb-6">
              <div>
                <h1 className="text-2xl font-bold text-foreground tracking-tight">Analytics Dashboard</h1>
                <p className="text-sm text-muted mt-2">Real-time insights and structured data exploration.</p>
              </div>
            </div>
            {kpis.length > 0 && (
              <div className="animate-in fade-in slide-in-from-top-4 duration-500">
                <KpiStrip metrics={kpis} />
              </div>
            )}
            {dashboardResults.length > 0 && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {dashboardResults.map((result, idx) => (
                  <motion.div
                    key={result.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                    className={result.type === 'table' ? 'xl:col-span-2' : ''}
                  >
                    <ResultCard
                      result={result}
                      onRefresh={() => handleQuery(result.query)}
                    />
                  </motion.div>
                ))}
              </div>
            )}
            <div className="animate-in fade-in slide-in-from-bottom-4 duration-500 delay-100">
              <AnalyticsQueryBox
                onQuery={handleQuery}
                isLoading={isQueryLoading}
                recentQueries={recentQueries}
                onRerunQuery={handleQuery}
                onDeleteHistory={handleDeleteHistory}
              />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pb-20">
              <AnimatePresence mode="popLayout">
                {currentResults.length === 0 ? (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="col-span-full py-32 text-center border border-dashed border-border rounded-xl bg-surface-secondary">
                    <BarChart3 className="w-10 h-10 text-muted mx-auto mb-4" />
                    <h3 className="text-lg font-semibold text-foreground mb-2">Awaiting Analysis</h3>
                    <p className="text-sm text-muted">Execute a query above to generate insights.</p>
                  </motion.div>
                ) : (
                  currentResults.map((result, idx) => (
                    <motion.div key={result.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: idx * 0.05 }} className={cn("h-full", result.type === 'table' ? "col-span-full" : "")}>
                      <ResultCard result={result} onRefresh={() => handleQuery(result.query)} />
                    </motion.div>
                  ))
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
