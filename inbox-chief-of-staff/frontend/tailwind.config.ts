import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        /* brand */
        brand:         "var(--brand)",
        "brand-hover": "var(--brand-hover)",
        "brand-soft":  "var(--brand-soft)",
        /* accent */
        accent:        "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        /* surfaces */
        canvas:        "var(--canvas)",
        surface:       "var(--surface)",
        "surface-muted": "var(--surface-muted)",
        lavender:      "var(--lavender)",
        /* lines */
        line:          "var(--line)",
        "line-strong": "var(--line-strong)",
        /* text */
        navy:          "var(--navy)",
        "ink-2":       "var(--ink-2)",
        "ink-3":       "var(--ink-3)",
        /* status */
        ok:            "var(--ok)",
        "ok-soft":     "var(--ok-soft)",
        warn:          "var(--warn)",
        "warn-soft":   "var(--warn-soft)",
        err:           "var(--err)",
        "err-soft":    "var(--err-soft)",
        /* priority badges */
        "urgent-bg":   "var(--urgent-bg)",
        "urgent-fg":   "var(--urgent-fg)",
        "normal-bg":   "var(--normal-bg)",
        "normal-fg":   "var(--normal-fg)",
        "brief-bg":    "var(--brief-bg)",
        "brief-fg":    "var(--brief-fg)",
        "archive-bg":  "var(--archive-bg)",
        "archive-fg":  "var(--archive-fg)",
        /* legacy aliases so existing bg-background/text-foreground keep working */
        background:    "var(--canvas)",
        foreground:    "var(--navy)",
      },
      boxShadow: {
        sm:    "var(--shadow-sm)",
        md:    "var(--shadow-md)",
        lg:    "var(--shadow-lg)",
        brand: "var(--shadow-brand)",
      },
      keyframes: {
        shimmer: {
          "0%, 100%": { opacity: "0.5" },
          "50%":      { opacity: "1" },
        },
        slideIn: {
          from: { transform: "translateX(100%)" },
          to:   { transform: "translateX(0)" },
        },
        toastIn: {
          from: { transform: "translateY(8px)", opacity: "0" },
          to:   { transform: "translateY(0)",   opacity: "1" },
        },
        spin: {
          from: { transform: "rotate(0deg)" },
          to:   { transform: "rotate(360deg)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.2s ease-in-out infinite",
        slideIn: "slideIn 220ms ease-out",
        toastIn: "toastIn 200ms cubic-bezier(.2,.9,.3,1.2) both",
        spin:    "spin 0.8s linear infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
