"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  RefreshCw,
  Trophy,
  CircleDot,
  Pause,
  CheckCircle2,
  FileEdit,
  Trash2,
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  api,
  type ExperimentOut,
  type ExperimentRollup,
  type ExperimentStatus,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const statusMeta: Record<
  ExperimentStatus,
  { icon: React.ElementType; label: string }
> = {
  draft: { icon: FileEdit, label: "Draft" },
  active: { icon: CircleDot, label: "Active" },
  paused: { icon: Pause, label: "Paused" },
  completed: { icon: CheckCircle2, label: "Completed" },
};

export default function ExperimentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [experiment, setExperiment] = useState<ExperimentOut | null>(null);
  const [rollup, setRollup] = useState<ExperimentRollup | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [exp, roll] = await Promise.all([
        api.experiments.get(id),
        api.experiments.results(id),
      ]);
      setExperiment(exp);
      setRollup(roll);
    } catch {
      toast.error("Failed to load experiment");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function updateStatus(status: ExperimentStatus) {
    try {
      await api.experiments.update(id, { status });
      toast.success(`Status: ${status}`);
      await load();
    } catch {
      toast.error("Update failed");
    }
  }

  async function handleDelete() {
    try {
      await api.experiments.delete(id);
      toast.success("Experiment deleted");
      router.push("/experiments");
    } catch {
      toast.error("Delete failed");
    }
  }

  if (loading || !experiment) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 animate-pulse rounded bg-muted" />
        <div className="h-48 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const meta = statusMeta[experiment.status];
  const MetaIcon = meta.icon;

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.push("/experiments")}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight truncate">
              {experiment.name}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-muted-foreground">
              <Badge variant="outline" className="gap-1">
                <MetaIcon className="h-3 w-3" />
                {meta.label}
              </Badge>
              <Badge variant="outline">{experiment.prompt_name}</Badge>
              <span>{experiment.primary_metric.replace(/_/g, " ")}</span>
              {experiment.started_at && (
                <span>· started {formatRelativeTime(experiment.started_at)}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button size="sm" variant="outline" onClick={load}>
            <RefreshCw className="mr-2 h-3 w-3" />
            Refresh
          </Button>
          {experiment.status === "draft" && (
            <Button size="sm" onClick={() => updateStatus("active")}>
              Activate
            </Button>
          )}
          {experiment.status === "active" && (
            <>
              <Button size="sm" variant="outline" onClick={() => updateStatus("paused")}>
                Pause
              </Button>
              <Button size="sm" variant="outline" onClick={() => updateStatus("completed")}>
                Stop
              </Button>
            </>
          )}
          {experiment.status === "paused" && (
            <Button size="sm" onClick={() => updateStatus("active")}>
              Resume
            </Button>
          )}
          <AlertDialog>
            <AlertDialogTrigger
              render={<Button size="sm" variant="destructive" />}
            >
              <Trash2 className="mr-2 h-3 w-3" />
              Delete
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete experiment?</AlertDialogTitle>
                <AlertDialogDescription>
                  This removes the experiment and its variant assignments.
                  Triage and draft records tagged with a variant&apos;s
                  prompt_version stay intact — rollup history for this
                  experiment becomes unreachable.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={handleDelete}>
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {experiment.description && (
        <Card>
          <CardContent className="pt-4 text-sm text-muted-foreground whitespace-pre-wrap">
            {experiment.description}
          </CardContent>
        </Card>
      )}

      {/* Results */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Results</CardTitle>
          <CardDescription>
            Computed from records tagged with each variant&apos;s prompt_version
            {rollup?.window_start && (
              <>
                {" · window: "}
                {new Date(rollup.window_start).toLocaleString()}
                {" → "}
                {new Date(rollup.window_end).toLocaleString()}
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!rollup || rollup.variants.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No data yet. Activate the experiment and let agents produce
              tagged records.
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground border-b">
                      <th className="py-2 pr-3 font-medium">Variant</th>
                      <th className="py-2 pr-3 font-medium">Version</th>
                      <th className="py-2 pr-3 font-medium text-right">Samples</th>
                      <th className="py-2 pr-3 font-medium text-right">
                        {metricLabel(rollup.primary_metric)}
                      </th>
                      <th className="py-2 pr-3 font-medium text-right">z-score</th>
                      <th className="py-2 pr-3 font-medium text-right">p-value</th>
                      <th className="py-2 pr-3 font-medium">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rollup.variants.map((v) => {
                      const isWinner = v.variant_id === rollup.winner_variant_id;
                      return (
                        <tr key={v.variant_id} className="border-b last:border-b-0">
                          <td className="py-2 pr-3">
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{v.label}</span>
                              {v.is_control && (
                                <Badge variant="secondary" className="text-[10px]">
                                  control
                                </Badge>
                              )}
                              {isWinner && (
                                <Badge variant="default" className="text-[10px] gap-1">
                                  <Trophy className="h-3 w-3" />
                                  winner
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="py-2 pr-3 font-mono text-xs">
                            {v.prompt_version}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {v.sample_size}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">
                            {formatMetric(v.metric_value, rollup.primary_metric)}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                            {v.z_score_vs_control !== null
                              ? v.z_score_vs_control.toFixed(2)
                              : "—"}
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                            {v.p_value_vs_control !== null
                              ? v.p_value_vs_control.toFixed(3)
                              : "—"}
                          </td>
                          <td className="py-2 pr-3">
                            {v.is_control ? (
                              <span className="text-xs text-muted-foreground">
                                baseline
                              </span>
                            ) : v.is_significant ? (
                              <Badge variant="default" className="text-xs">
                                significant
                              </Badge>
                            ) : v.sample_size < 5 ? (
                              <span className="text-xs text-muted-foreground">
                                too few samples
                              </span>
                            ) : (
                              <Badge variant="outline" className="text-xs">
                                no effect
                              </Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {rollup.notes.length > 0 && (
                <>
                  <Separator className="my-3" />
                  <ul className="space-y-1">
                    {rollup.notes.map((n, i) => (
                      <li key={i} className="text-xs text-muted-foreground">
                        · {n}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Variants config */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Variant configuration</CardTitle>
          <CardDescription>
            Deterministic mailbox-level assignment via hash(experiment_id +
            mailbox_id)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {experiment.variants.map((v) => (
              <li
                key={v.id}
                className="flex items-center justify-between py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{v.label}</span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {v.prompt_version}
                  </span>
                  {v.is_control && (
                    <Badge variant="secondary" className="text-[10px]">
                      control
                    </Badge>
                  )}
                </div>
                <span className="text-sm tabular-nums">{v.traffic_pct}%</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function metricLabel(metric: string): string {
  if (metric === "triage_correction_rate") return "Correction rate";
  if (metric === "draft_acceptance_rate") return "Acceptance rate";
  if (metric === "avg_confidence") return "Avg confidence";
  return metric;
}

function formatMetric(value: number | null, metric: string): string {
  if (value === null || value === undefined) return "—";
  if (metric === "avg_confidence") {
    return value.toFixed(3);
  }
  return `${(value * 100).toFixed(1)}%`;
}
