"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getToken } from "@/helpers/auth";

// Wraps the whole app (mounted from layout.tsx). Redirects to /login when
// there's no token in localStorage. The /login page itself is excluded so
// it doesn't redirect to itself.
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      setChecked(true);
      return;
    }

    try {
      const token = getToken();
      if (!token) {
        setChecked(true);
        router.replace("/login");
        return;
      }

      setChecked(true);
    } catch (error) {
      console.error("Auth check failed:", error);
      setChecked(true);
      router.replace("/login");
    }
  }, [pathname, router]);

  if (!checked) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-white text-sm text-gray-500">
        Loading Bunny Research...
      </div>
    );
  }

  return <>{children}</>;
}
