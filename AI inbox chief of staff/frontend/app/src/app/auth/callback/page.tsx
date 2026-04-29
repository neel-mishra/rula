"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";

function CallbackHandler() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const attempt = useCallback(async () => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");

    if (!code || !state) {
      setError("Missing authorization parameters.");
      return;
    }
    if (!isAuthenticated) {
      setError("Please sign in before connecting Gmail.");
      return;
    }

    setRetrying(true);
    try {
      await api.mailboxConnect.callback(code, state);
      router.replace("/");
    } catch {
      setError("Failed to complete Gmail connection. Please try again.");
    } finally {
      setRetrying(false);
    }
  }, [searchParams, router, isAuthenticated]);

  useEffect(() => {
    attempt();
  }, [attempt]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="text-center space-y-4 max-w-sm">
          <AlertCircle className="h-10 w-10 text-destructive mx-auto" />
          <p className="font-medium">Connection failed</p>
          <p className="text-sm text-muted-foreground">{error}</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-2 pt-2">
            <Button onClick={attempt} disabled={retrying} size="sm">
              <RefreshCw
                className={`mr-2 h-3 w-3 ${retrying ? "animate-spin" : ""}`}
              />
              Retry
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => router.replace("/login")}
            >
              Back to login
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="animate-pulse text-muted-foreground">
        Connecting your Gmail account...
      </div>
    </div>
  );
}

export default function CallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <div className="animate-pulse text-muted-foreground">Loading...</div>
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  );
}
