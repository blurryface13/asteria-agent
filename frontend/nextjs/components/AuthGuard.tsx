"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getToken, getAuthEmail, isLocalAuthBypassEnabled, authFetch } from "@/helpers/auth";
import {getHost} from '@/helpers/getHost';
import {ResearchHistoryProvider} from '@/hooks/ResearchHistoryContext';

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

    if (isLocalAuthBypassEnabled()) {
      setChecked(true);
      return;
    }

    try {
      const token = getToken();
      if (!token) {
        setChecked(false);
        router.replace("/login");
        return;
      }

      setChecked(false);
      authFetch(getHost()+'/api/auth/me').then(r=>setChecked(r.ok)).catch(()=>setChecked(false));
    } catch (error) {
      console.error("Auth check failed:", error);
      setChecked(true);
      router.replace("/login");
    }
  }, [pathname, router]);

  if(pathname==='/login')return <>{children}</>;
  if (!checked) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center bg-white text-sm text-gray-500">
        Loading Asteria Research...
      </div>
    );
  }

  return <ResearchHistoryProvider key={getAuthEmail()||'local'}>{children}</ResearchHistoryProvider>;
}
