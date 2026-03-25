import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer, 
  PieChart, 
  Pie, 
  Cell,
  LineChart,
  Line,
  AreaChart,
  Area
} from 'recharts';
import { 
  Download, 
  RefreshCw, 
  TrendingUp, 
  Database, 
  FileText, 
  Code, 
  ChevronDown, 
  Maximize2,
  AlertCircle,
  BarChart3,
  PieChart as PieChartIcon,
  LineChart as LineChartIcon,
  Table as TableIcon
} from 'lucide-react';
import { AnalyticsQueryResult } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';
import { useState } from 'react';

interface ResultCardProps {
  result: AnalyticsQueryResult;
  onRefresh: () => void;
}

const COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#6366F1'];

export default function ResultCard({ result, onRefresh }: ResultCardProps) {
  const [showSql, setShowSql] = useState(false);
  const [viewMode, setViewMode] = useState<'viz' | 'table'>('viz');

  const renderVisualization = () => {
    switch (result.type) {
      case 'number':
        return (
          <div className="h-64 flex flex-col items-center justify-center text-center">
            <h3 className="text-4xl font-bold text-foreground tracking-tight mb-2 tabular-nums">
              {result.data[0]?.value || '0'}
            </h3>
            <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">
              {result.data[0]?.name || 'Result Summary'}
            </p>
          </div>
        );
      case 'bar':
        return (
          <div className="h-64 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={result.data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} opacity={0.2} />
                <XAxis 
                  dataKey="name" 
                  stroke="var(--muted-foreground)" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false} 
                  tick={{ fill: 'var(--muted-foreground)', opacity: 0.7 }}
                />
                <YAxis 
                  stroke="var(--muted-foreground)" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false} 
                  tick={{ fill: 'var(--muted-foreground)', opacity: 0.7 }}
                />
                <Tooltip 
                  cursor={{ fill: 'var(--accent)', opacity: 0.05 }}
                  contentStyle={{ backgroundColor: 'var(--surface-secondary)', border: '1px solid var(--border)', borderRadius: '6px' }}
                  itemStyle={{ color: 'var(--accent)', fontWeight: 600, fontSize: '11px' }}
                  labelStyle={{ color: 'var(--foreground)', fontWeight: 700, marginBottom: '2px', fontSize: '10px' }}
                />
                <Bar dataKey="value" fill="var(--accent)" radius={[2, 2, 0, 0]} barSize={24} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      case 'pie':
        return (
          <div className="h-64 w-full flex items-center gap-8 px-4">
            <div className="flex-1 h-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={result.data}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={4}
                    dataKey="value"
                    stroke="none"
                  >
                    {result.data.map((_, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'var(--surface-secondary)', border: '1px solid var(--border)', borderRadius: '6px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-col gap-2 max-h-full overflow-y-auto custom-scrollbar w-48">
              {result.data.map((item, i) => (
                <div key={item.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-2 h-2 rounded-sm shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                    <span className="text-[10px] font-medium text-muted-foreground truncate">{item.name}</span>
                  </div>
                  <span className="text-[10px] font-bold text-foreground tabular-nums">{item.value.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        );
      case 'line':
        return (
          <div className="h-64 w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={result.data}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} opacity={0.2} />
                <XAxis 
                  dataKey="name" 
                  stroke="var(--muted-foreground)" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false} 
                  tick={{ fill: 'var(--muted-foreground)', opacity: 0.7 }}
                />
                <YAxis 
                  stroke="var(--muted-foreground)" 
                  fontSize={10} 
                  tickLine={false} 
                  axisLine={false} 
                  tick={{ fill: 'var(--muted-foreground)', opacity: 0.7 }}
                />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--surface-secondary)', border: '1px solid var(--border)', borderRadius: '6px' }}
                />
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke="var(--accent)" 
                  strokeWidth={2} 
                  dot={{ r: 3, fill: 'var(--accent)' }} 
                  activeDot={{ r: 5 }} 
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        );
      case 'table':
      default:
        return renderTable();
    }
  };

  const renderTable = () => {
    if (!result.data || result.data.length === 0) return null;
    const headers = Object.keys(result.data[0]);
    
    return (
      <div className="overflow-x-auto custom-scrollbar max-h-64 rounded-md border border-border">
        <table className="w-full text-left text-[11px]">
          <thead>
            <tr className="text-muted-foreground uppercase tracking-wider border-b border-border bg-surface-secondary/50 sticky top-0 z-10">
              {headers.map(h => (
                <th key={h} className="px-4 py-3 font-bold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/10">
            {result.data.map((row, i) => (
              <tr key={i} className="text-foreground hover:bg-white/5 transition-colors">
                {headers.map(h => (
                  <td key={h} className="px-4 py-3 font-medium">{row[h]}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-surface-secondary/20 border border-border rounded-lg overflow-hidden shadow-sm hover:border-border/80 transition-all"
    >
      {/* Card Header */}
      <div className="px-5 py-4 border-b border-border flex items-center justify-between bg-surface-secondary/30">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-background border border-border rounded flex items-center justify-center">
            {result.type === 'bar' && <BarChart3 className="w-4 h-4 text-accent" />}
            {result.type === 'pie' && <PieChartIcon className="w-4 h-4 text-accent" />}
            {result.type === 'line' && <LineChartIcon className="w-4 h-4 text-accent" />}
            {result.type === 'table' && <TableIcon className="w-4 h-4 text-accent" />}
            {result.type === 'number' && <TrendingUp className="w-4 h-4 text-accent" />}
          </div>
          <div>
            <h4 className="text-xs font-bold text-foreground tracking-tight">{result.query}</h4>
            <p className="text-[10px] text-muted-foreground mt-0.5">
              {new Date(result.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-background border border-border rounded p-0.5">
            <button 
              onClick={() => setViewMode('viz')}
              className={cn(
                "p-1.5 rounded transition-all",
                viewMode === 'viz' ? "bg-accent text-white" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <BarChart3 className="w-3.5 h-3.5" />
            </button>
            <button 
              onClick={() => setViewMode('table')}
              className={cn(
                "p-1.5 rounded transition-all",
                viewMode === 'table' ? "bg-accent text-white" : "text-muted-foreground hover:text-foreground"
              )}
            >
              <TableIcon className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="h-4 w-px bg-border mx-1" />
          <button 
            onClick={onRefresh}
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-white/5 rounded transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button className="p-2 text-muted-foreground hover:text-foreground hover:bg-white/5 rounded transition-all">
            <Download className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Card Body */}
      <div className="p-5">
        <AnimatePresence mode="wait">
          <motion.div
            key={viewMode}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            {viewMode === 'viz' ? renderVisualization() : renderTable()}
          </motion.div>
        </AnimatePresence>

        {/* Explanation */}
        {result.explanation && (
          <div className="mt-6 p-4 bg-background border border-border rounded-md">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="w-3.5 h-3.5 text-accent" />
              <span className="text-[10px] font-bold text-foreground uppercase tracking-wider">Analysis Summary</span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {result.explanation}
            </p>
          </div>
        )}

        {/* SQL Preview */}
        {result.sql && (
          <div className="mt-4">
            <button 
              onClick={() => setShowSql(!showSql)}
              className="flex items-center gap-2 text-[10px] font-bold text-muted-foreground hover:text-accent transition-all"
            >
              <Code className="w-3.5 h-3.5" />
              {showSql ? 'Hide SQL' : 'View SQL'}
              <ChevronDown className={cn("w-3.5 h-3.5 transition-transform", showSql && "rotate-180")} />
            </button>
            <AnimatePresence>
              {showSql && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="mt-3 p-4 bg-black/20 border border-border rounded-md">
                    <pre className="text-[10px] font-mono text-accent/90 overflow-x-auto custom-scrollbar leading-relaxed">
                      {result.sql}
                    </pre>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>
    </motion.div>
  );
}
