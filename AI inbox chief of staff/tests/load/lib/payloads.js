// Payload builders for load tests. PII-free fixtures only.

import encoding from 'k6/encoding';

const SAMPLE_DOMAINS = [
  'example.com',
  'partner.example.com',
  'updates.example.com',
  'noreply.example.com',
];

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randId(prefix) {
  return `${prefix}-${Math.floor(Math.random() * 1e9)}`;
}

// Build a Gmail Pub/Sub envelope for the /webhooks/gmail endpoint.
// `emailAddress` is the bound mailbox; `historyId` triggers an
// incremental sync starting from that point.
export function gmailPushEnvelope({ emailAddress, historyId }) {
  const inner = JSON.stringify({
    emailAddress: emailAddress || `loadtest-${Math.floor(Math.random() * 5)}@example.com`,
    historyId: historyId || String(Math.floor(Math.random() * 1e6)),
  });
  return {
    message: {
      data: encoding.b64encode(inner),
      messageId: randId('msg'),
      publishTime: new Date().toISOString(),
    },
    subscription: 'projects/dev/subscriptions/gmail-push-loadtest',
  };
}

const ASSISTANT_INSTRUCTIONS = [
  'Always archive newsletters from updates.example.com',
  'Mark anything from partner.example.com as urgent',
  'Brief me on calendar invites in the morning',
  'Never auto-archive direct replies',
  'Summarize threads with more than 5 messages',
];

export function assistantInstruction({ mailboxId } = {}) {
  return {
    instruction: pick(ASSISTANT_INSTRUCTIONS),
    mailbox_id: mailboxId || null,
  };
}

export function randomMailboxFromList(mailboxIds) {
  if (!mailboxIds || mailboxIds.length === 0) return null;
  return mailboxIds[Math.floor(Math.random() * mailboxIds.length)];
}
