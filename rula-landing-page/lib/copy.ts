/**
 * Landing copy aligned to Rula business DNA (employer GTM / RevOps context).
 * Tone: compassionate, clear, credible — no unsourced clinical or revenue guarantees.
 */

export const site = {
  title: "Rula Revenue Intelligence",
  tagline: "GTM tools for employer-channel prospecting and MAP verification",
  eyebrow: "Interactive resources",
  heroLead:
    "Pick who you are in the demo, then launch Prospecting or MAP Review. You will continue in the Streamlit app with that role and starting page—same agent behavior as running the repo locally.",
  footerNote:
    "Rula expands access to quality mental healthcare for members and partners. These internal tools support operational GTM workflows; they are not patient-facing care interfaces.",
  journeySteps: [
    { id: "role", label: "Choose role" },
    { id: "tool", label: "Launch tool" },
  ],
} as const;

export type RoleId = "admin" | "user" | "viewer";

export const roles: {
  id: RoleId;
  label: string;
  description: string;
}[] = [
  {
    id: "admin",
    label: "Admin",
    description:
      "Governance and oversight—retention, shadow compare, incidents, and configuration visibility when running the full app.",
  },
  {
    id: "user",
    label: "User",
    description:
      "Run prospecting and MAP verification with exports and handoff flows aligned to RevOps and AE workflows.",
  },
  {
    id: "viewer",
    label: "Viewer",
    description:
      "Review outputs and lineage with read-oriented permissions—ideal for stakeholders who need transparency without running pipelines.",
  },
];

export const tools: {
  id: "prospecting" | "map";
  title: string;
  description: string;
  cta: string;
}[] = [
  {
    id: "prospecting",
    title: "Prospecting",
    description:
      "Generate and refine employer-channel outreach from account context, with explainable value-prop matching and CRM-ready exports.",
    cta: "Launch Prospecting",
  },
  {
    id: "map",
    title: "MAP Review",
    description:
      "Verify commitment evidence, confidence tiers, and recommended actions—so MAP quality supports forecasting and partner execution.",
    cta: "Launch MAP Review",
  },
];
