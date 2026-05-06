import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Settings",
};

function SettingsSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <h2 className="text-base font-semibold text-gray-900 mb-3 pb-2 border-b border-gray-200">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-8">Settings</h1>

      <SettingsSection title="Mailbox">
        {/* TODO: implement — show connected Gmail account, reconnect / revoke button */}
        <p className="text-sm text-gray-500">
          Manage your connected Gmail mailbox.
        </p>
        <div className="rounded-lg bg-gray-100 p-4 text-sm text-gray-400 italic">
          TODO: connected mailbox card + reconnect flow
        </div>
      </SettingsSection>

      <SettingsSection title="Preferences">
        {/* TODO: implement — timezone selector, briefing time windows, notification preferences */}
        <p className="text-sm text-gray-500">
          Configure timezone, briefing schedule, and notification preferences.
        </p>
        <div className="rounded-lg bg-gray-100 p-4 text-sm text-gray-400 italic">
          TODO: timezone selector, morning/afternoon window toggles
        </div>
      </SettingsSection>

      <SettingsSection title="Policy (read-only)">
        {/* TODO: implement — show active triage policy version + rules summary */}
        <p className="text-sm text-gray-500">
          View the active triage and drafting policy applied to your inbox.
          Contact support to request changes.
        </p>
        <div className="rounded-lg bg-gray-100 p-4 text-sm text-gray-400 italic">
          TODO: fetch and render active policy from /admin/policy endpoint
        </div>
      </SettingsSection>

      <SettingsSection title="Feedback history">
        {/* TODO: implement — paginated list of past triage overrides and draft ratings */}
        <p className="text-sm text-gray-500">
          Review the triage corrections and draft ratings you have submitted.
        </p>
        <div className="rounded-lg bg-gray-100 p-4 text-sm text-gray-400 italic">
          TODO: paginated feedback history table from /feedback endpoint
        </div>
      </SettingsSection>
    </div>
  );
}
