import { Users, Package, Calendar, MapPin, DollarSign, Lightbulb, Database } from 'lucide-react';
import { KpiCardData } from '../../types';
import { cn } from '../../lib/utils';
import { motion } from 'motion/react';

interface KpiStripProps {
  metrics: KpiCardData[];
}

const ICON_MAP: Record<string, any> = {
  'Total Rows': Database,
  'Top Month': Calendar,
  'Top Service Name': Package,
  'Top Owner Team': Users,
  'Top Environment': MapPin,
  'Top Cost Category': DollarSign,
  'Top Optimization Hint': Lightbulb,
};

export default function KpiStrip({ metrics }: KpiStripProps) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(170px,1fr))] gap-3">
      {metrics.map((metric, i) => {
        const Icon = ICON_MAP[metric.label] || Database;
        const isNumeric = metric.type === 'numeric';
        
        return (
          <motion.div
            key={metric.label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="bg-surface-secondary border border-border rounded-xl p-4 flex flex-col h-full hover:border-accent/30 transition-colors group min-h-[146px] max-w-[220px]"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-semibold text-muted uppercase tracking-[0.14em] truncate">
                {metric.label}
              </span>
              <Icon className="w-4 h-4 text-muted group-hover:text-accent transition-colors" />
            </div>
            
            <div className="flex flex-1 flex-col justify-end">
              <h3 className={cn(
                "font-semibold text-foreground tracking-tight break-words [overflow-wrap:anywhere]",
                isNumeric ? "text-[30px] leading-none tabular-nums" : "text-[18px] leading-[1.45]"
              )}>
                {metric.value}
              </h3>
              {metric.subtitle && (
                <span className="text-[11px] text-muted font-medium mt-3 pt-3 border-t border-border/70">
                  {metric.subtitle}
                </span>
              )}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
