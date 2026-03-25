import { 
  Download, 
  FileJson, 
  TrendingUp, 
  TrendingDown, 
  Minus, 
  CheckCircle2, 
  ArrowRight,
  Sparkles,
  ExternalLink,
  Share2
} from 'lucide-react';
import { FinalReport, KpiCardData } from '../../types';
import { cn } from '../../lib/utils';
import ReactMarkdown from 'react-markdown';
import { motion } from 'motion/react';

interface FinalReportCardProps {
  report: FinalReport;
  timestamp: string;
}

export default function FinalReportCard({ report, timestamp }: FinalReportCardProps) {
  const date = new Date(timestamp).toLocaleDateString('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="bg-background border border-border rounded-3xl overflow-hidden shadow-2xl shadow-accent/5 relative group">
      <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-1000" />
      
      {/* Header */}
      <div className="px-8 py-10 border-b border-border bg-surface-secondary/20 relative z-10">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3 px-4 py-1.5 bg-accent/10 text-accent rounded-full text-[10px] font-bold border border-accent/20">
            <Sparkles className="w-3.5 h-3.5" />
            Synthesized Intelligence
          </div>
          <div className="flex items-center gap-3">
            <button className="p-2 rounded-xl hover:bg-accent/10 text-muted-foreground hover:text-accent transition-all border border-transparent hover:border-accent/20">
              <Download className="w-4 h-4" />
            </button>
            <button className="p-2 rounded-xl hover:bg-accent/10 text-muted-foreground hover:text-accent transition-all border border-transparent hover:border-accent/20">
              <Share2 className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        <div className="space-y-4">
          <h2 className="text-3xl font-bold text-foreground tracking-tight leading-tight max-w-2xl">
            {report.title}
          </h2>
          <div className="flex items-center gap-4 text-[11px] text-muted-foreground/60 font-medium uppercase tracking-widest">
            <span>{date}</span>
            <div className="w-1 h-1 rounded-full bg-border" />
            <span>Executive Summary</span>
          </div>
        </div>
      </div>

      {/* Integrated KPIs */}
      {report.kpis && report.kpis.length > 0 && (
        <div className="px-8 py-8 bg-surface-secondary/10 border-b border-border relative z-10">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            {report.kpis.map((kpi, idx) => (
              <motion.div 
                key={idx}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                className="space-y-2"
              >
                <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest opacity-60">
                  {kpi.label}
                </p>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-bold text-foreground tracking-tight">
                    {kpi.value}
                  </span>
                  {kpi.subtitle && (
                    <span className="text-[10px] text-muted-foreground/40 font-medium uppercase tracking-widest">
                      {kpi.subtitle}
                    </span>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      <div className="px-8 py-10 space-y-12 relative z-10">
        {/* Overview */}
        <section className="space-y-4">
          <h3 className="text-sm font-bold text-foreground uppercase tracking-widest flex items-center gap-3">
            <div className="w-1.5 h-1.5 rounded-full bg-accent" />
            Overview
          </h3>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-3xl">
            {report.overview}
          </p>
        </section>

        {/* Key Findings & Recommendations */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
          <section className="space-y-6">
            <h3 className="text-sm font-bold text-foreground uppercase tracking-widest flex items-center gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
              Key Findings
            </h3>
            <div className="space-y-4">
              {report.keyFindings.map((finding, i) => (
                <div key={i} className="flex gap-4 group/item">
                  <div className="w-6 h-6 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0 border border-blue-500/20 group-hover/item:bg-blue-500 group-hover/item:text-white transition-all">
                    <TrendingUp className="w-3.5 h-3.5" />
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {finding}
                  </p>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-6">
            <h3 className="text-sm font-bold text-foreground uppercase tracking-widest flex items-center gap-3">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Recommendations
            </h3>
            <div className="space-y-4">
              {report.recommendations.map((rec, i) => (
                <div key={i} className="flex gap-4 group/item">
                  <div className="w-6 h-6 rounded-lg bg-emerald-500/10 flex items-center justify-center shrink-0 border border-emerald-500/20 group-hover/item:bg-emerald-500 group-hover/item:text-white transition-all">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed">
                    {rec}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* Detailed Content */}
        <section className="pt-12 border-t border-border space-y-6">
          <h3 className="text-sm font-bold text-foreground uppercase tracking-widest flex items-center gap-3">
            <div className="w-1.5 h-1.5 rounded-full bg-purple-500" />
            Deep Analysis
          </h3>
          <div className="bg-surface-secondary/20 rounded-2xl p-8 border border-border/50 relative group/analysis">
            <div className="absolute top-6 right-6 opacity-0 group-hover/analysis:opacity-100 transition-opacity">
              <button className="p-2 rounded-xl hover:bg-accent/10 text-muted-foreground hover:text-accent transition-all border border-transparent hover:border-accent/20">
                <ExternalLink className="w-4 h-4" />
              </button>
            </div>
            
            <div className="prose prose-invert prose-sm max-w-none prose-p:text-muted-foreground prose-headings:text-foreground prose-headings:font-bold prose-headings:tracking-tight prose-strong:text-foreground prose-code:text-accent prose-code:bg-accent/5 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:before:content-none prose-code:after:content-none leading-relaxed">
              <ReactMarkdown>{report.content}</ReactMarkdown>
            </div>
          </div>
        </section>
      </div>

      {/* Footer Actions */}
      <div className="px-8 py-6 bg-surface-secondary/30 border-t border-border flex items-center justify-between relative z-10">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground/40 font-bold uppercase tracking-widest">
            <FileJson className="w-3.5 h-3.5" />
            Raw Data Export
          </div>
          <div className="flex items-center gap-2 text-[10px] text-muted-foreground/40 font-bold uppercase tracking-widest">
            <TrendingUp className="w-3.5 h-3.5" />
            Analytics Ready
          </div>
        </div>
        <button className="flex items-center gap-2 text-[11px] font-bold text-accent uppercase tracking-widest hover:gap-3 transition-all group">
          View Full Dataset
          <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
        </button>
      </div>
    </div>
  );
}
