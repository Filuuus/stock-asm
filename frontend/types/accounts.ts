import type { Role } from "@/hooks/use-auth";
import type { Zone } from "@/types/commissions";

export interface ManagedUser {
  id: number;
  username: string;
  role: Role;
  zone: Zone | "";
  is_active: boolean;
  date_joined: string;
  last_login: string | null;
}

export type AuditAction =
  | "CREATED"
  | "ROLE_CHANGED"
  | "ZONE_CHANGED"
  | "ACTIVATED"
  | "DEACTIVATED"
  | "PASSWORD_RESET";

export interface AuditLogEntry {
  id: number;
  actor_username: string;
  target_username: string;
  action: AuditAction;
  detail: string;
  created_at: string;
}
