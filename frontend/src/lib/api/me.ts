import { api } from "@/lib/api/client";
import type { UserOut } from "@/types/api";

export function getMe(): Promise<UserOut> {
  return api<UserOut>("/me");
}
