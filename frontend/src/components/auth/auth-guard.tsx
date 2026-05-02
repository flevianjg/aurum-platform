"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useCurrentUser } from "@/lib/hooks/use-current-user";
import { ApiError } from "@/lib/api/client";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * Client-side auth gate. Renders a skeleton while the /me query is in flight,
 * pushes to /login if unauthenticated. Server-side enforcement still happens
 * at the backend — this is just UX.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data, isLoading, error } = useCurrentUser();

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      router.replace("/login");
    }
  }, [error, router]);

  if (isLoading || !data) {
    return (
      <div className="container space-y-4 py-8">
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  return <>{children}</>;
}
