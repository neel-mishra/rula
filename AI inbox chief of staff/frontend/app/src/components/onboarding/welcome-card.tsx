"use client";

import { useEffect, useState } from "react";
import { Brain, FileText, MessageSquare, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { FeatureCallout } from "./feature-callout";

const STORAGE_KEY = "onboarding-dismissed:v1";

export function WelcomeCard() {
  const [dismissed, setDismissed] = useState<boolean | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setDismissed(localStorage.getItem(STORAGE_KEY) === "true");
  }, []);

  if (dismissed === null || dismissed) return null;

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // ignore
    }
    setDismissed(true);
  }

  return (
    <Card className="border-info/40 bg-info/5">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2">
            <Sparkles className="h-4 w-4 text-info mt-0.5 shrink-0" />
            <div>
              <CardTitle className="text-base">
                Welcome to Inbox Chief of Staff
              </CardTitle>
              <CardDescription className="mt-1">
                Connect a Gmail mailbox to start. While you&apos;re here, here&apos;s what
                the system can do once it&apos;s running.
              </CardDescription>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={dismiss}
            aria-label="Dismiss welcome"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-3">
        <FeatureCallout
          icon={MessageSquare}
          title="Assistant"
          description="Give natural-language rules. The assistant remembers them."
          href="/assistant"
        />
        <FeatureCallout
          icon={Brain}
          title="Memories"
          description="Every learned preference is visible and editable."
          href="/memories"
        />
        <FeatureCallout
          icon={FileText}
          title="Briefs"
          description="Twice-daily summaries of what you can safely skip."
          href="/briefs"
        />
      </CardContent>
    </Card>
  );
}
