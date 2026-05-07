"use client";

import { useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Tag } from "@/components/ui/tag";
import { Field } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/utils";

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 rounded-full border-2 border-transparent transition-colors",
        checked ? "bg-brand" : "bg-line",
      )}
    >
      <span
        className={cn(
          "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-4" : "translate-x-0",
        )}
      />
    </button>
  );
}

function TrustRow({
  title,
  desc,
  checked,
  onChange,
  locked,
}: {
  title: string;
  desc: string;
  checked?: boolean;
  onChange?: (v: boolean) => void;
  locked?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-4 border-b border-line last:border-b-0">
      <div className="flex-1 min-w-0">
        <p className="text-[14px] font-medium text-navy">{title}</p>
        <p className="text-[13px] text-ink-2 mt-0.5">{desc}</p>
      </div>
      {locked ? (
        <Tag tone="err">Always off</Tag>
      ) : (
        <Toggle checked={checked!} onChange={onChange!} />
      )}
    </div>
  );
}

const MOCK_EMAIL = "user@example.com";

export default function SettingsPage() {
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [autoArchive, setAutoArchive] = useState(false);
  const [autoApproveBrief, setAutoApproveBrief] = useState(false);
  const [briefMorning, setBriefMorning] = useState("08:00");
  const [briefAfternoon, setBriefAfternoon] = useState("13:00");

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader title="Settings" />

      <div className="flex-1 overflow-y-auto scroll-pretty">
        <div className="max-w-2xl mx-auto px-6 py-8 flex flex-col gap-6">
          {/* Account */}
          <section className="rounded-2xl border border-line bg-surface p-6">
            <h2 className="text-base font-semibold text-navy mb-4">Account</h2>
            <div className="flex items-center gap-3">
              <Avatar name={MOCK_EMAIL.split("@")[0]} size="md" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-navy truncate">{MOCK_EMAIL}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <Tag tone="ok">Connected</Tag>
                  <span className="text-xs text-ink-3">Gmail</span>
                </div>
              </div>
              <Button
                variant="danger-ghost"
                size="sm"
                onClick={() => setDisconnectOpen(true)}
              >
                Disconnect
              </Button>
            </div>
          </section>

          {/* Trust controls */}
          <section className="rounded-2xl border border-line bg-surface p-6">
            <h2 className="text-base font-semibold text-navy mb-2">Automation trust</h2>
            <TrustRow
              title="Auto-archive Brief category"
              desc="Emails triaged as Brief are automatically archived in Gmail after generating the brief."
              checked={autoArchive}
              onChange={setAutoArchive}
            />
            <TrustRow
              title="Auto-approve Brief drafts"
              desc="Drafts for Brief-category replies are saved directly to Gmail Drafts without your review."
              checked={autoApproveBrief}
              onChange={setAutoApproveBrief}
            />
            <TrustRow
              title="Autonomous send"
              desc="Allow the assistant to send emails on your behalf without draft review."
              locked
            />
          </section>

          {/* Brief schedule */}
          <section className="rounded-2xl border border-line bg-surface p-6">
            <h2 className="text-base font-semibold text-navy mb-4">Brief schedule</h2>
            <div className="grid grid-cols-2 gap-4">
              <Field
                type="time"
                label="Morning brief"
                value={briefMorning}
                onChange={(e) => setBriefMorning(e.target.value)}
              />
              <Field
                type="time"
                label="Afternoon brief"
                value={briefAfternoon}
                onChange={(e) => setBriefAfternoon(e.target.value)}
              />
            </div>
            <p className="text-xs text-ink-3 mt-2">Times are in your account timezone.</p>
          </section>

          {/* Gmail scopes */}
          <section className="rounded-2xl border border-line bg-surface p-6">
            <h2 className="text-base font-semibold text-navy mb-4">Gmail access</h2>
            <div className="grid grid-cols-2 gap-4 text-sm mb-4">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-3 mb-2">Granted</p>
                {["Read messages", "Manage labels", "Save drafts"].map((s) => (
                  <div key={s} className="flex items-center gap-2 py-1">
                    <Tag tone="ok" className="text-[10px]">✓</Tag>
                    <span className="text-sm text-navy">{s}</span>
                  </div>
                ))}
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-widest text-ink-3 mb-2">Not requested</p>
                {["Send messages", "Delete messages"].map((s) => (
                  <div key={s} className="flex items-center gap-2 py-1">
                    <Tag tone="err" className="text-[10px]">✗</Tag>
                    <span className="text-sm text-navy">{s}</span>
                  </div>
                ))}
              </div>
            </div>
            <p className="text-xs text-ink-3 italic">
              We never request send or delete permissions. All email actions go through Gmail's own interface.
            </p>
          </section>
        </div>
      </div>

      {/* Disconnect modal */}
      <Modal open={disconnectOpen} onClose={() => setDisconnectOpen(false)} title="Disconnect Gmail">
        <p className="text-sm text-ink-2 mb-6">
          Disconnecting will stop all inbox triage, draft generation, and briefings. Your data
          will be preserved and you can reconnect at any time.
        </p>
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" size="sm" onClick={() => setDisconnectOpen(false)}>Cancel</Button>
          <Button variant="danger" size="sm" onClick={() => setDisconnectOpen(false)}>
            Disconnect Gmail
          </Button>
        </div>
      </Modal>
    </div>
  );
}
