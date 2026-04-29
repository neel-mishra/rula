"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Lightbulb,
  MessageCircle,
  Plus,
  Send,
  Sparkles,
  Trash2,
  Globe,
  Inbox,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  api,
  type AssistantMessage,
  type AssistantSuggestion,
  type ConversationDetail,
  type ConversationSummary,
  type MailboxSummary,
} from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";
import { toast } from "sonner";

export default function AssistantPage() {
  return (
    <Suspense fallback={null}>
      <AssistantPageContent />
    </Suspense>
  );
}

function AssistantPageContent() {
  const searchParams = useSearchParams();
  const prefill = searchParams.get("prefill") || "";
  const prefillScope = searchParams.get("scope") || "";
  const [mailboxes, setMailboxes] = useState<MailboxSummary[]>([]);
  const [scope, setScope] = useState<string>("global");

  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadingConvos, setLoadingConvos] = useState(true);

  const [activeConvoId, setActiveConvoId] = useState<string | null>(null);
  const [activeConvo, setActiveConvo] = useState<ConversationDetail | null>(
    null,
  );
  const [loadingActive, setLoadingActive] = useState(false);

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const [suggestions, setSuggestions] = useState<AssistantSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [dismissedSuggestions, setDismissedSuggestions] = useState<Set<string>>(
    new Set(),
  );

  const mailboxEmailMap = useMemo(
    () => Object.fromEntries(mailboxes.map((m) => [m.id, m.gmail_email])),
    [mailboxes],
  );

  useEffect(() => {
    api.mailboxes
      .list()
      .then(setMailboxes)
      .catch(() => {
        /* non-critical */
      });
  }, []);

  const loadConversations = useCallback(async () => {
    setLoadingConvos(true);
    try {
      const res = await api.assistant.listConversations({ limit: 40 });
      setConversations(res.conversations);
      return res.conversations;
    } catch {
      toast.error("Failed to load conversations");
      return [];
    } finally {
      setLoadingConvos(false);
    }
  }, []);

  const loadConversation = useCallback(async (id: string) => {
    setLoadingActive(true);
    try {
      const data = await api.assistant.getConversation(id);
      setActiveConvo(data);
    } catch {
      toast.error("Failed to load conversation");
      setActiveConvo(null);
    } finally {
      setLoadingActive(false);
    }
  }, []);

  useEffect(() => {
    loadConversations().then((list) => {
      // If a prefill is present, jump straight into a fresh thread instead
      // of resuming the most recent one.
      if (prefill) {
        setActiveConvoId(null);
        setActiveConvo(null);
        setInput(prefill);
        if (prefillScope) setScope(prefillScope);
      } else if (list.length > 0 && !activeConvoId) {
        setActiveConvoId(list[0].id);
      }
    });
    // intentionally run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load proactive suggestions when the user is composing a fresh chat.
  useEffect(() => {
    if (activeConvoId) {
      setSuggestions([]);
      return;
    }
    setLoadingSuggestions(true);
    api.assistant
      .suggestions({
        mailbox_id: scope !== "global" ? scope : undefined,
        window_days: 30,
      })
      .then((res) => setSuggestions(res.suggestions))
      .catch(() => {
        /* non-critical */
      })
      .finally(() => setLoadingSuggestions(false));
  }, [activeConvoId, scope]);

  function applySuggestion(s: AssistantSuggestion) {
    setInput(s.instruction_text);
    setDismissedSuggestions((prev) => new Set(prev).add(s.id));
  }

  function dismissSuggestion(id: string) {
    setDismissedSuggestions((prev) => new Set(prev).add(id));
  }

  useEffect(() => {
    if (activeConvoId) {
      loadConversation(activeConvoId);
    } else {
      setActiveConvo(null);
    }
  }, [activeConvoId, loadConversation]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConvo?.messages.length]);

  function startNewConversation() {
    setActiveConvoId(null);
    setActiveConvo(null);
    setInput("");
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);

    // Optimistic append for snappy UX
    const optimisticMsg: AssistantMessage = {
      id: `optimistic-${crypto.randomUUID()}`,
      role: "user",
      content: text,
      response_data: {},
      feedback_event_id: null,
      created_at: new Date().toISOString(),
    };
    if (activeConvo) {
      setActiveConvo({
        ...activeConvo,
        messages: [...activeConvo.messages, optimisticMsg],
      });
    }
    setInput("");

    try {
      const res = await api.assistant.instruct({
        instruction: text,
        mailbox_id: activeConvo?.mailbox_id ?? (scope === "global" ? null : scope),
        conversation_id: activeConvoId ?? undefined,
      });

      // Reload the now-current conversation (handles both new + existing)
      setActiveConvoId(res.conversation_id);
      await loadConversation(res.conversation_id);
      await loadConversations();
    } catch {
      toast.error("Failed to send");
      // Roll back optimistic message
      if (activeConvo) {
        setActiveConvo({
          ...activeConvo,
          messages: activeConvo.messages.filter(
            (m) => m.id !== optimisticMsg.id,
          ),
        });
      }
    } finally {
      setSending(false);
    }
  }

  async function handleDeleteConversation(id: string) {
    try {
      await api.assistant.deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (id === activeConvoId) {
        setActiveConvoId(null);
        setActiveConvo(null);
      }
      toast.success("Conversation deleted");
    } catch {
      toast.error("Delete failed");
    }
  }

  const activeMailboxLabel = activeConvo?.mailbox_id
    ? mailboxEmailMap[activeConvo.mailbox_id] || "mailbox"
    : "all mailboxes";

  return (
    <div className="flex flex-col lg:flex-row gap-4 lg:h-[calc(100vh-6rem)] min-h-[70vh]">
      {/* ── Sidebar: conversation list ───────────────────────── */}
      <div className="w-full lg:w-72 flex flex-col border rounded-lg overflow-hidden shrink-0 max-h-72 lg:max-h-none">
        <div className="p-3 border-b flex items-center justify-between">
          <h2 className="text-sm font-semibold">Conversations</h2>
          <Button size="xs" onClick={startNewConversation}>
            <Plus className="mr-1 h-3 w-3" />
            New
          </Button>
        </div>
        <ScrollArea className="flex-1">
          {loadingConvos ? (
            <div className="p-3 space-y-2">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-12 rounded bg-muted animate-pulse"
                />
              ))}
            </div>
          ) : conversations.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground">
              No conversations yet. Start one on the right.
            </div>
          ) : (
            <ul className="divide-y">
              {conversations.map((c) => (
                <li key={c.id}>
                  <div
                    className={`group flex items-start gap-2 p-3 cursor-pointer hover:bg-muted/40 ${
                      c.id === activeConvoId ? "bg-muted/60" : ""
                    }`}
                    onClick={() => setActiveConvoId(c.id)}
                  >
                    <MessageCircle className="h-3.5 w-3.5 mt-1 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">
                        {c.title}
                      </p>
                      {c.last_message_preview && (
                        <p className="text-xs text-muted-foreground truncate">
                          {c.last_message_preview}
                        </p>
                      )}
                      <div className="flex items-center gap-1 mt-1 text-xs text-muted-foreground">
                        {c.mailbox_id ? (
                          <Inbox className="h-3 w-3" />
                        ) : (
                          <Globe className="h-3 w-3" />
                        )}
                        <span>
                          {c.mailbox_id
                            ? mailboxEmailMap[c.mailbox_id] || "mailbox"
                            : "all mailboxes"}
                        </span>
                        <span>·</span>
                        <span>
                          {formatRelativeTime(
                            c.last_message_at || c.updated_at,
                          )}
                        </span>
                      </div>
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={(e) => e.stopPropagation()}
                            className="opacity-0 group-hover:opacity-100 transition-opacity"
                          />
                        }
                      >
                        <Trash2 className="h-3 w-3" />
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            Delete conversation?
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            Deleting &quot;{c.title}&quot; removes its
                            messages. Memories it created stay intact.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleDeleteConversation(c.id)}
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </div>

      {/* ── Main: thread ─────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="mb-3">
          {activeConvo ? (
            <>
              <h1 className="text-2xl font-semibold tracking-tight truncate">
                {activeConvo.title}
              </h1>
              <p className="text-sm text-muted-foreground flex items-center gap-1.5 mt-1">
                {activeConvo.mailbox_id ? (
                  <Inbox className="h-3.5 w-3.5" />
                ) : (
                  <Globe className="h-3.5 w-3.5" />
                )}
                {activeMailboxLabel}
                <span>·</span>
                <span>{activeConvo.message_count} messages</span>
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-semibold tracking-tight">
                New conversation
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                Give the assistant a natural-language instruction
              </p>
            </>
          )}
        </div>

        <div className="mb-3 flex items-center gap-2">
          <Tooltip>
            <TooltipTrigger
              render={
                <div>
                  <Select
                    value={
                      activeConvo
                        ? activeConvo.mailbox_id ?? "global"
                        : scope
                    }
                    onValueChange={(v) => !activeConvo && setScope(v ?? "global")}
                    disabled={!!activeConvo}
                  >
                    <SelectTrigger className="w-64">
                      <SelectValue placeholder="Scope" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="global">All mailboxes</SelectItem>
                      {mailboxes.map((mb) => (
                        <SelectItem key={mb.id} value={mb.id}>
                          {mb.gmail_email}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              }
            />
            {activeConvo && (
              <TooltipContent>
                Scope is locked for this conversation. Start a new chat to
                change it.
              </TooltipContent>
            )}
          </Tooltip>
          {activeConvo && (
            <Button size="sm" variant="outline" onClick={startNewConversation}>
              <Plus className="mr-1 h-3 w-3" />
              New chat
            </Button>
          )}
        </div>

        <Card className="flex-1 flex flex-col min-h-0">
          <ScrollArea className="flex-1 p-4">
            {loadingActive ? (
              <div className="space-y-4">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-16 rounded bg-muted animate-pulse"
                  />
                ))}
              </div>
            ) : !activeConvo || activeConvo.messages.length === 0 ? (
              <div className="space-y-4">
                <SuggestionsPanel
                  suggestions={suggestions.filter(
                    (s) => !dismissedSuggestions.has(s.id),
                  )}
                  loading={loadingSuggestions}
                  onApply={applySuggestion}
                  onDismiss={dismissSuggestion}
                />
                <EmptyThreadHints />
              </div>
            ) : (
              <div className="space-y-4">
                {activeConvo.messages.map((msg) => (
                  <MessageBubble key={msg.id} msg={msg} />
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </ScrollArea>
          <Separator />
          <CardContent className="p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex gap-2"
            >
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  activeConvo
                    ? "Reply..."
                    : "Tell me how to handle your email..."
                }
                className="min-h-[44px] max-h-32 resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
              />
              <Button
                type="submit"
                size="icon"
                disabled={!input.trim() || sending}
                className="shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SuggestionsPanel({
  suggestions,
  loading,
  onApply,
  onDismiss,
}: {
  suggestions: AssistantSuggestion[];
  loading: boolean;
  onApply: (s: AssistantSuggestion) => void;
  onDismiss: (id: string) => void;
}) {
  if (loading || suggestions.length === 0) return null;
  return (
    <div className="rounded-lg border border-dashed p-3 space-y-2 bg-muted/30">
      <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
        <Lightbulb className="h-3.5 w-3.5" />
        Suggested rules from your recent activity
      </div>
      <ul className="space-y-2">
        {suggestions.map((s) => (
          <li
            key={s.id}
            className="rounded border bg-background p-2.5 text-sm"
          >
            <p className="font-medium">{s.headline}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {s.rationale}
            </p>
            <p className="text-xs italic mt-1.5">
              &ldquo;{s.instruction_text}&rdquo;
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="xs" onClick={() => onApply(s)}>
                Use this
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={() => onDismiss(s.id)}
              >
                Dismiss
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EmptyThreadHints() {
  const examples = [
    "Always keep emails from my manager in the inbox",
    "Archive all marketing newsletters",
    "Flag emails from @acme.com as high priority",
    "Never draft replies to automated receipts",
  ];
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-12">
      <Sparkles className="h-8 w-8 text-muted-foreground mb-3" />
      <p className="text-sm font-medium mb-1">
        What should the assistant do?
      </p>
      <p className="text-xs text-muted-foreground mb-4 max-w-sm">
        Natural-language instructions become persistent rules and memories.
      </p>
      <div className="space-y-1 max-w-md">
        {examples.map((ex) => (
          <p
            key={ex}
            className="text-xs text-muted-foreground italic"
          >
            &ldquo;{ex}&rdquo;
          </p>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: AssistantMessage }) {
  const isUser = msg.role === "user";
  const data = msg.response_data || {};
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
        }`}
      >
        <p className="whitespace-pre-wrap">{msg.content}</p>
        {!isUser &&
          data.rules_created !== undefined &&
          data.rules_created > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              <Badge variant="secondary" className="text-xs">
                {data.rules_created} rule{data.rules_created === 1 ? "" : "s"}{" "}
                created
              </Badge>
              <Link
                href="/memories"
                className="text-xs underline underline-offset-2 text-muted-foreground hover:text-foreground"
              >
                view memories →
              </Link>
            </div>
          )}
        {!isUser && data.needs_clarification && (
          <Badge variant="outline" className="mt-2 text-xs">
            Needs clarification
          </Badge>
        )}
        <p
          className={`text-[10px] mt-1 ${
            isUser ? "text-primary-foreground/60" : "text-muted-foreground"
          }`}
        >
          {formatRelativeTime(msg.created_at)}
        </p>
      </div>
    </div>
  );
}
