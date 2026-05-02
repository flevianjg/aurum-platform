import { Badge } from "@/components/ui/badge";
import type { BrokerAccount } from "@/types/api";

export function StatusPill({ active }: { active: boolean }) {
  return (
    <Badge variant={active ? "success" : "secondary"}>
      {active ? "Active" : "Inactive"}
    </Badge>
  );
}

export function TestStatusPill({ status }: { status: string | null }) {
  if (!status) return <Badge variant="outline">never tested</Badge>;
  if (status === "success") return <Badge variant="success">connected</Badge>;
  if (status === "auth_failed") return <Badge variant="destructive">auth failed</Badge>;
  if (status === "connection_error")
    return <Badge variant="destructive">connection error</Badge>;
  return <Badge variant="outline">{status}</Badge>;
}

export function BrokerTypeBadge({ type }: { type: BrokerAccount["broker_type"] }) {
  return <Badge variant="outline">{type}</Badge>;
}
