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
    const token = getToken();
    if (!token) {
      router.replace("/login");
      return;
    }
    setChecked(true);
  }, [pathname, router]);

  if (!checked) {
    return <div className="min-h-screen w-full bg-white" />;
  }

  return <>{children}</>;
}
