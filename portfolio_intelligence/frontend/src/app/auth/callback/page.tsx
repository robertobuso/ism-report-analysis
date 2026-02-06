"use client";

import { useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function CallbackHandler() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const processed = useRef(false);

  useEffect(() => {
    // Prevent double-processing in React Strict Mode
    if (processed.current) return;
    processed.current = true;

    const token = searchParams.get("token");
    if (token) {
      // Store token
      localStorage.setItem("token", token);
      // Redirect immediately
      router.replace("/");
    } else {
      router.replace("/login");
    }
  }, []);

  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="animate-pulse text-muted">Signing you in...</div>
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <div className="animate-pulse text-muted">Loading...</div>
        </div>
      }
    >
      <CallbackHandler />
    </Suspense>
  );
}
