import { AuthGuard } from "@/components/auth/auth-guard";
import { AppShell } from "@/components/nav/app-shell";

export default function AuthedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
