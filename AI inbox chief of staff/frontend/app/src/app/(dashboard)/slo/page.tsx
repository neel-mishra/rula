"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  RefreshCw,
  Rocket,
  ShieldAlert,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  api,
  type SLOCategory,
  type SLOMetric,
  type SLOStatus,
  type SLOStatusResponse,
} from "@/lib/api";
import { toast } from "sonner";

const statusMeta: Record<
  SLOStatus,
  {
    icon: React.ElementType;
    variant: "default" | "secondary" | "outline" | "destructive" | "success" | "warning";
    label: string;
    tone: string;
  }
> = {
  pass: {
    icon: CheckCircle2,
    variant: "success",
    label: "Pass",
    tone: "text-success",
  },
  warn: {
    icon: AlertTriangle,
    variant: "warning",
    label: "Warn",
    tone: "text-warning",
  },
  fail: {
    icon: XCircle,
    variant: "destructive",
    label: "Fail",
    tone: "text-destructive",
  },
  not_measured: {
    icon: HelpCircle,
    variant: "outline",
    label: "Not measured",
    tone: "text-muted-foreground",
  },
};

const categoryLabel: Record<SLOCategory, string> = {
  quality: "Quality & Safety",
  latency: "Latency",
  undo: "Undo & Reversibility",
  reliability: "Reliability",
  cost: "Cost & Efficiency",
};

const categoryOrder: SLOCategory[] = [
  "quality",
  "latency",
  "reliability",
  "undo",
  "cost",
];

const WINDOW_OPTIONS = [
  { value: "7", label: "Last 7 days" },
  { value: "14", label: "Last 14 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

export default function SLOPage() {
  const [status, setStatus] = useState<SLOStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [window, setWindow] = useState("7");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.slo.status({ window_days: Number(window) });
      setStatus(data);
    } catch {
      toast.error("Failed to load SLO status");
    } finally {
      setLoading(false);
    }
  }, [window]);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    if (!status) return new Map<SLOCategory, SLOMetric[]>();
    const out = new Map<SLOCategory, SLOMetric[]>();
    for (const metric of status.metrics) {
      const list = out.get(metric.category) || [];
      list.push(metric);
      out.set(metric.category, list);
    }
    return out;
  }, [status]);

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Launch SLOs</h1>
          <p className="text-sm text-muted-foreground">
            Numeric targets from the launch plan, measured against your own
            data
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={window} onValueChange={(v) => v && setWindow(v)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {WINDOW_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={loading}
          >
            <RefreshCw
              className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
        </div>
      </div>

      {/* Launch readiness banner */}
      {status && (
        <Card
          className={
            status.launch_ready
              ? "border-success/40 bg-success/5"
              : "border-warning/40 bg-warning/5"
          }
        >
          <CardContent className="pt-4 pb-4 flex items-center gap-3">
            {status.launch_ready ? (
              <Rocket className="h-5 w-5 text-success shrink-0" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-warning shrink-0" />
            )}
            <div className="flex-1">
              <p className="font-medium text-sm">
                {status.launch_ready
                  ? "Critical SLOs pass — launch criteria met."
                  : "Launch blocked on critical SLOs."}
              </p>
              <p className="text-xs text-muted-foreground">
                Critical gates: false-archive rate, prompt-injection pass rate,
                undo success rate.
              </p>
            </div>
            <SummaryRow summary={status.summary} />
          </CardContent>
        </Card>
      )}

      {loading && !status ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader>
                <div className="h-5 w-1/3 bg-muted rounded" />
              </CardHeader>
              <CardContent>
                <div className="h-16 w-full bg-muted rounded" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {categoryOrder.map((cat) => {
            const metrics = grouped.get(cat);
            if (!metrics || metrics.length === 0) return null;
            return (
              <div key={cat}>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                  {categoryLabel[cat]}
                </h2>
                <div className="space-y-2">
                  {metrics.map((m) => (
                    <MetricRow key={m.id} metric={m} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function SummaryRow({
  summary,
}: {
  summary: Record<SLOStatus, number>;
}) {
  const statuses: SLOStatus[] = ["pass", "warn", "fail", "not_measured"];
  return (
    <div className="flex items-center gap-3 shrink-0">
      {statuses.map((s) => {
        const meta = statusMeta[s];
        const Icon = meta.icon;
        return (
          <div
            key={s}
            className="flex items-center gap-1 text-xs"
            title={meta.label}
          >
            <Icon className={`h-3.5 w-3.5 ${meta.tone}`} />
            <span className="tabular-nums">{summary[s] ?? 0}</span>
          </div>
        );
      })}
    </div>
  );
}

function MetricRow({ metric }: { metric: SLOMetric }) {
  const meta = statusMeta[metric.status];
  const Icon = meta.icon;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm flex items-center gap-2">
              <Icon className={`h-4 w-4 shrink-0 ${meta.tone}`} />
              {metric.name}
            </CardTitle>
            <CardDescription className="mt-1 text-xs">
              {metric.description}
            </CardDescription>
          </div>
          <Badge variant={meta.variant} className="shrink-0">
            {meta.label}
          </Badge>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="py-3">
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Current</p>
            <p className={`font-mono text-base tabular-nums ${meta.tone}`}>
              {formatValue(metric.value, metric.unit)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Target</p>
            <p className="font-mono text-base tabular-nums">
              {metric.operator} {formatValue(metric.target_value, metric.unit)}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Samples</p>
            <p className="font-mono text-base tabular-nums">
              {metric.sample_size}
            </p>
          </div>
        </div>
        {metric.note && (
          <p className="text-xs text-muted-foreground mt-3 italic">
            {metric.note}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function formatValue(value: number | null, unit: string): string {
  if (value === null || value === undefined) return "—";
  if (unit === "rate") return `${(value * 100).toFixed(2)}%`;
  if (unit === "seconds") {
    if (value < 60) return `${value.toFixed(1)}s`;
    return `${(value / 60).toFixed(1)}m`;
  }
  if (unit === "usd_per_day") return `$${value.toFixed(2)}`;
  return String(value);
}
