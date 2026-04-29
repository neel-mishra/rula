"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  FlaskConical,
  Plus,
  RefreshCw,
  CircleDot,
  Pause,
  CheckCircle2,
  FileEdit,
  AlertCircle,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  api,
  type ExperimentCreate,
  type ExperimentMetric,
  type ExperimentOut,
  type ExperimentStatus,
  type RegistryPrompt,
  type VariantCreate,
} from "@/lib/api";
import { useDraft } from "@/lib/use-draft";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const statusMeta: Record<
  ExperimentStatus,
  {
    icon: React.ElementType;
    variant: "default" | "secondary" | "outline" | "destructive";
    label: string;
  }
> = {
  draft: { icon: FileEdit, variant: "outline", label: "Draft" },
  active: { icon: CircleDot, variant: "default", label: "Active" },
  paused: { icon: Pause, variant: "secondary", label: "Paused" },
  completed: { icon: CheckCircle2, variant: "outline", label: "Completed" },
};

const METRIC_OPTIONS: { value: ExperimentMetric; label: string }[] = [
  { value: "triage_correction_rate", label: "Triage correction rate (lower better)" },
  { value: "draft_acceptance_rate", label: "Draft acceptance rate (higher better)" },
  { value: "avg_confidence", label: "Avg confidence (higher better)" },
];

export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState<ExperimentOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.experiments.list();
      setExperiments(res.experiments);
    } catch {
      toast.error("Failed to load experiments");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleStatusChange(
    experiment: ExperimentOut,
    status: ExperimentStatus,
  ) {
    try {
      await api.experiments.update(experiment.id, { status });
      toast.success(`${experiment.name}: ${status}`);
      await load();
    } catch {
      toast.error("Status change failed");
    }
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Experiments</h1>
          <p className="text-sm text-muted-foreground">
            A/B test prompt versions across mailboxes
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw
              className={`mr-2 h-3 w-3 ${loading ? "animate-spin" : ""}`}
            />
            Refresh
          </Button>
          <Sheet open={createOpen} onOpenChange={setCreateOpen}>
            <SheetTrigger render={<Button size="sm" />}>
              <Plus className="mr-2 h-3 w-3" />
              New experiment
            </SheetTrigger>
            <SheetContent className="sm:max-w-xl overflow-y-auto">
              <SheetHeader>
                <SheetTitle>New experiment</SheetTitle>
              </SheetHeader>
              <CreateExperimentForm
                onCreated={async () => {
                  setCreateOpen(false);
                  await load();
                }}
              />
            </SheetContent>
          </Sheet>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader>
                <div className="h-5 w-2/3 bg-muted rounded" />
                <div className="h-4 w-1/3 bg-muted rounded" />
              </CardHeader>
            </Card>
          ))}
        </div>
      ) : experiments.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <FlaskConical className="h-10 w-10 text-muted-foreground mb-4" />
            <p className="font-medium">No experiments yet</p>
            <p className="text-sm text-muted-foreground mt-1 max-w-md">
              Create an experiment to compare prompt versions across a share of
              your mailboxes. Results are computed from existing triage and
              draft records tagged with each variant&apos;s prompt_version.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {experiments.map((e) => {
            const meta = statusMeta[e.status];
            const MetaIcon = meta.icon;
            const control = e.variants.find((v) => v.is_control);
            return (
              <Card key={e.id}>
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/experiments/${e.id}`}
                        className="hover:underline underline-offset-2"
                      >
                        <CardTitle className="text-base truncate">
                          {e.name}
                        </CardTitle>
                      </Link>
                      <CardDescription className="flex flex-wrap items-center gap-2 mt-1">
                        <Badge variant="outline">{e.prompt_name}</Badge>
                        <Badge variant="outline">
                          {e.primary_metric.replace(/_/g, " ")}
                        </Badge>
                        <span>
                          {e.variants.length} variants
                          {control && ` · control: ${control.prompt_version}`}
                        </span>
                        <span>·</span>
                        <span>
                          {e.started_at
                            ? `started ${formatRelativeTime(e.started_at)}`
                            : `created ${formatRelativeTime(e.created_at)}`}
                        </span>
                      </CardDescription>
                    </div>
                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <Badge variant={meta.variant} className="gap-1">
                        <MetaIcon className="h-3 w-3" />
                        {meta.label}
                      </Badge>
                      <StatusButtons
                        experiment={e}
                        onChange={handleStatusChange}
                      />
                    </div>
                  </div>
                </CardHeader>
                <Separator />
                <CardContent className="py-3">
                  <div className="flex flex-wrap gap-2">
                    {e.variants.map((v) => (
                      <div
                        key={v.id}
                        className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs"
                      >
                        <span className="font-medium">{v.label}</span>
                        <span className="text-muted-foreground">
                          {v.prompt_version}
                        </span>
                        <span className="text-muted-foreground">
                          · {v.traffic_pct}%
                        </span>
                        {v.is_control && (
                          <Badge
                            variant="secondary"
                            className="text-[10px] ml-1"
                          >
                            control
                          </Badge>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatusButtons({
  experiment,
  onChange,
}: {
  experiment: ExperimentOut;
  onChange: (e: ExperimentOut, s: ExperimentStatus) => void | Promise<void>;
}) {
  if (experiment.status === "draft") {
    return (
      <Button
        size="xs"
        variant="outline"
        onClick={() => onChange(experiment, "active")}
      >
        Activate
      </Button>
    );
  }
  if (experiment.status === "active") {
    return (
      <div className="flex gap-1">
        <Button
          size="xs"
          variant="outline"
          onClick={() => onChange(experiment, "paused")}
        >
          Pause
        </Button>
        <Button
          size="xs"
          variant="outline"
          onClick={() => onChange(experiment, "completed")}
        >
          Stop
        </Button>
      </div>
    );
  }
  if (experiment.status === "paused") {
    return (
      <Button
        size="xs"
        variant="outline"
        onClick={() => onChange(experiment, "active")}
      >
        Resume
      </Button>
    );
  }
  return null;
}

interface ExperimentDraft {
  name: string;
  description: string;
  promptName: string;
  metric: ExperimentMetric;
  variants: VariantCreate[];
}

const INITIAL_DRAFT: ExperimentDraft = {
  name: "",
  description: "",
  promptName: "",
  metric: "triage_correction_rate",
  variants: [
    { label: "control", prompt_version: "", traffic_pct: 50, is_control: true },
    { label: "variant_a", prompt_version: "", traffic_pct: 50, is_control: false },
  ],
};

function CreateExperimentForm({ onCreated }: { onCreated: () => void }) {
  const [prompts, setPrompts] = useState<RegistryPrompt[]>([]);
  const { draft, patchDraft, clearDraft, hasRestored } = useDraft<ExperimentDraft>(
    "experiment-draft:v1",
    INITIAL_DRAFT,
  );
  const { name, description, promptName, metric, variants } = draft;
  const [submitting, setSubmitting] = useState(false);

  const hasUserContent =
    hasRestored &&
    (name.trim() ||
      description.trim() ||
      variants.some((v, i) => v.label !== INITIAL_DRAFT.variants[i]?.label));

  useEffect(() => {
    api.experiments
      .registryPrompts()
      .then((p) => {
        setPrompts(p);
        if (p.length === 0) return;
        // Only seed defaults if the form is pristine — don't clobber a restored draft.
        const defaultVer = p[0].active_version || p[0].versions[0] || "";
        patchDraft({
          promptName: promptName || p[0].name,
          variants: variants.map((v) => ({
            ...v,
            prompt_version: v.prompt_version || defaultVer,
          })),
        });
      })
      .catch(() => toast.error("Failed to load prompts"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const availableVersions = useMemo(() => {
    const prompt = prompts.find((p) => p.name === promptName);
    return prompt?.versions || [];
  }, [prompts, promptName]);

  function updateVariant(idx: number, changes: Partial<VariantCreate>) {
    patchDraft({
      variants: variants.map((v, i) => (i === idx ? { ...v, ...changes } : v)),
    });
  }

  function addVariant() {
    const defaultVer = availableVersions[0] || "";
    patchDraft({
      variants: [
        ...variants,
        {
          label: `variant_${String.fromCharCode(97 + variants.length - 1)}`,
          prompt_version: defaultVer,
          traffic_pct: 0,
          is_control: false,
        },
      ],
    });
  }

  function removeVariant(idx: number) {
    patchDraft({ variants: variants.filter((_, i) => i !== idx) });
  }

  function setControl(idx: number) {
    patchDraft({
      variants: variants.map((v, i) => ({ ...v, is_control: i === idx })),
    });
  }

  const trafficSum = variants.reduce((s, v) => s + v.traffic_pct, 0);
  const controlCount = variants.filter((v) => v.is_control).length;
  const allVariantsHaveVersion = variants.every((v) => v.prompt_version);
  const canSubmit =
    !!name.trim() &&
    !!promptName &&
    variants.length >= 2 &&
    trafficSum === 100 &&
    controlCount === 1 &&
    allVariantsHaveVersion;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const payload: ExperimentCreate = {
        name: name.trim(),
        description: description.trim() || null,
        prompt_name: promptName,
        primary_metric: metric,
        variants,
      };
      await api.experiments.create(payload);
      toast.success("Experiment created");
      clearDraft();
      onCreated();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Creation failed";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 mt-4">
      {hasUserContent && (
        <div className="flex items-start justify-between gap-3 rounded-md border border-info/40 bg-info/5 px-3 py-2 text-xs">
          <span>Draft restored from your last visit.</span>
          <button
            type="button"
            className="text-info hover:underline font-medium"
            onClick={clearDraft}
          >
            Discard draft
          </button>
        </div>
      )}

      <div className="space-y-1">
        <Label htmlFor="name">Name</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => patchDraft({ name: e.target.value })}
          placeholder="triage_classifier v1 vs v2"
        />
      </div>

      <div className="space-y-1">
        <Label htmlFor="description">Description</Label>
        <Textarea
          id="description"
          value={description}
          onChange={(e) => patchDraft({ description: e.target.value })}
          placeholder="What hypothesis are you testing?"
          className="min-h-[60px]"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="space-y-1">
          <Label>Prompt</Label>
          <Select
            value={promptName}
            onValueChange={(v) => v && patchDraft({ promptName: v })}
          >
            <SelectTrigger>
              <SelectValue placeholder="Prompt" />
            </SelectTrigger>
            <SelectContent>
              {prompts.map((p) => (
                <SelectItem key={p.name} value={p.name}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Primary metric</Label>
          <Select
            value={metric}
            onValueChange={(v) =>
              v && patchDraft({ metric: v as ExperimentMetric })
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {METRIC_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>
                  {o.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <Separator />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label>Variants</Label>
          <span
            className={`text-xs ${
              trafficSum === 100 ? "text-muted-foreground" : "text-destructive"
            }`}
          >
            Traffic {trafficSum}/100
          </span>
        </div>
        {variants.map((v, i) => (
          <div
            key={i}
            className="rounded-md border p-3 sm:border-0 sm:p-0 sm:grid sm:grid-cols-[1fr_1fr_80px_auto_auto] sm:gap-2 sm:items-end space-y-2 sm:space-y-0"
          >
            <div className="space-y-1">
              <Label className="text-xs">Label</Label>
              <Input
                value={v.label}
                onChange={(e) =>
                  updateVariant(i, { label: e.target.value })
                }
                className="h-8"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Version</Label>
              <Select
                value={v.prompt_version}
                onValueChange={(val) =>
                  updateVariant(i, { prompt_version: val ?? "" })
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  {availableVersions.map((ver) => (
                    <SelectItem key={ver} value={ver}>
                      {ver}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">% traffic</Label>
              <Input
                type="number"
                min={0}
                max={100}
                value={v.traffic_pct}
                onChange={(e) =>
                  updateVariant(i, {
                    traffic_pct: Math.max(
                      0,
                      Math.min(100, Number(e.target.value) || 0),
                    ),
                  })
                }
                className="h-8"
              />
            </div>
            <div className="flex gap-2 sm:contents">
              <Button
                type="button"
                size="xs"
                variant={v.is_control ? "default" : "outline"}
                onClick={() => setControl(i)}
              >
                {v.is_control ? "Control" : "Set control"}
              </Button>
              <Button
                type="button"
                size="xs"
                variant="ghost"
                onClick={() => removeVariant(i)}
                disabled={variants.length <= 2}
              >
                ×
              </Button>
            </div>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addVariant}
          disabled={!availableVersions.length}
        >
          <Plus className="mr-1 h-3 w-3" />
          Add variant
        </Button>
      </div>

      {!canSubmit && (name || description) && (
        <p className="text-xs text-muted-foreground flex items-start gap-1">
          <AlertCircle className="h-3 w-3 mt-0.5 shrink-0" />
          <span>
            Requirements: name set, traffic sums to 100, exactly one control,
            all variants have a version.
          </span>
        </p>
      )}

      <Button type="submit" disabled={!canSubmit || submitting} size="sm">
        {submitting ? "Creating..." : "Create experiment"}
      </Button>
    </form>
  );
}
