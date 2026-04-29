"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, ExternalLink, Star, Sun, Sunset } from "lucide-react";
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
import { api, type Brief } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

const windowIcon: Record<string, React.ElementType> = {
  morning: Sun,
  afternoon: Sunset,
};

export default function BriefDetailPage() {
  const params = useParams();
  const router = useRouter();
  const briefId = params.id as string;

  const [brief, setBrief] = useState<Brief | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.briefs.get(briefId);
      setBrief(data);
    } catch {
      toast.error("Failed to load brief");
    } finally {
      setLoading(false);
    }
  }, [briefId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading || !brief) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-48 animate-pulse rounded bg-muted" />
        <div className="h-64 animate-pulse rounded bg-muted" />
      </div>
    );
  }

  const WinIcon = windowIcon[brief.window] || Star;
  const byCategory = brief.items.reduce<Record<string, typeof brief.items>>(
    (acc, item) => {
      const key = item.category || "other";
      acc[key] = acc[key] || [];
      acc[key].push(item);
      return acc;
    },
    {},
  );

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => router.push("/briefs")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight truncate">
            {brief.subject_line || `${brief.window} brief`}
          </h1>
          <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground">
            <WinIcon className="h-4 w-4" />
            <span className="capitalize">{brief.window}</span>
            <span>·</span>
            <Badge variant="outline">{brief.status}</Badge>
            {brief.delivered_at && (
              <>
                <span>·</span>
                <span>
                  delivered {formatRelativeTime(brief.delivered_at)}
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {brief.items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-sm text-muted-foreground">
              No items in this brief
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {Object.entries(byCategory).map(([category, items]) => (
            <div key={category}>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3">
                {category} · {items.length}
              </h2>
              <div className="space-y-3">
                {items.map((item) => (
                  <Card key={item.id}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <CardTitle className="text-sm">
                            {item.summary || "(no summary)"}
                          </CardTitle>
                          {item.importance_score !== null &&
                            item.importance_score !== undefined && (
                              <CardDescription className="mt-1 flex items-center gap-1">
                                <Star className="h-3 w-3" />
                                importance {(item.importance_score * 100).toFixed(0)}%
                              </CardDescription>
                            )}
                        </div>
                        {item.gmail_open_url && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="shrink-0"
                            render={
                              <a
                                href={item.gmail_open_url}
                                target="_blank"
                                rel="noopener noreferrer"
                              />
                            }
                          >
                            Open
                            <ExternalLink className="ml-1 h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </CardHeader>
                    {item.key_points && item.key_points.length > 0 && (
                      <>
                        <Separator />
                        <CardContent className="pt-3">
                          <ul className="list-disc list-inside space-y-1 text-sm text-muted-foreground">
                            {item.key_points.map((pt, i) => (
                              <li key={i}>{pt}</li>
                            ))}
                          </ul>
                        </CardContent>
                      </>
                    )}
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
