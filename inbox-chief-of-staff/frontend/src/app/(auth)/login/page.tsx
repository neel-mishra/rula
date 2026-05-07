import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Sign In",
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-canvas">
      <div className="max-w-md w-full mx-auto px-4">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-semibold text-navy mb-2">
            Inbox Chief of Staff
          </h1>
          <p className="text-ink-2 text-sm">
            AI-powered triage, drafts, and daily briefings for your inbox.
          </p>
        </div>

        <div className="bg-surface rounded-2xl shadow-sm border border-line p-8">
          <h2 className="text-lg font-semibold text-navy mb-6 text-center">
            Sign in to your account
          </h2>

          <a
            href={`${API_BASE_URL}/auth/login`}
            className="flex items-center justify-center gap-3 w-full px-4 py-3 border border-line rounded-lg text-sm font-medium text-navy bg-surface hover:bg-lavender transition-colors"
          >
            <svg
              width="18"
              height="18"
              viewBox="0 0 18 18"
              aria-hidden="true"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z" fill="#4285F4" />
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z" fill="#34A853" />
              <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z" fill="#FBBC05" />
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58Z" fill="#EA4335" />
            </svg>
            Sign in with Google
          </a>

          <p className="mt-6 text-xs text-center text-ink-3">
            By signing in, you grant read-only and draft access to your Gmail inbox.
            Your data is processed solely to provide triage and drafting features.
          </p>
        </div>
      </div>
    </div>
  );
}
