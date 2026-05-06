import type { Metadata } from "next";
import { Spinner } from "@/components/ui/spinner";

export const metadata: Metadata = {
  title: "Connecting...",
};

export default function CallbackPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="flex flex-col items-center gap-4 text-center">
        <Spinner size="lg" />
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Connecting your inbox...
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            This should only take a moment.
          </p>
        </div>
      </div>
    </div>
  );
}
