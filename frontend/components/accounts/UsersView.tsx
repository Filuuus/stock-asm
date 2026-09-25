"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound, Loader2, Plus, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { generatePassword } from "@/lib/password";
import { useAuth, Role } from "@/hooks/use-auth";
import { AuditAction, AuditLogEntry, ManagedUser } from "@/types/accounts";
import { Zone } from "@/types/commissions";

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "SALESPERSON", label: "Vendedor" },
  { value: "ACCOUNTING", label: "Contabilidad" },
  { value: "MANAGEMENT", label: "Gerencia" },
];

const ZONE_OPTIONS: { value: Zone | ""; label: string }[] = [
  { value: "", label: "Sin zona" },
  { value: "ZONA1", label: "Zona 1" },
  { value: "ZONA2", label: "Zona 2" },
  { value: "OFICINA", label: "Oficina" },
  { value: "SERVICIOS", label: "Servicios" },
  { value: "PUNTOVENTA", label: "Punto de Venta" },
];

const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
  CREATED: "creó la cuenta de",
  ROLE_CHANGED: "cambió el rol de",
  ZONE_CHANGED: "cambió la zona de",
  ACTIVATED: "activó la cuenta de",
  DEACTIVATED: "desactivó la cuenta de",
  PASSWORD_RESET: "restableció la contraseña de",
};

function formatDateTime(value: string | null) {
  if (!value) return "Nunca";
  return new Date(value).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
}

function RoleSelect({
  id,
  value,
  disabled,
  onChange,
}: {
  id?: string;
  value: Role;
  disabled?: boolean;
  onChange: (role: Role) => void;
}) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as Role)}
      className="h-9 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-50"
    >
      {ROLE_OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

function ZoneSelect({
  id,
  value,
  disabled,
  onChange,
}: {
  id?: string;
  value: Zone | "";
  disabled?: boolean;
  onChange: (zone: Zone | "") => void;
}) {
  return (
    <select
      id={id}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value as Zone | "")}
      className="h-9 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-50"
    >
      {ZONE_OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

function PasswordField({
  id,
  value,
  onChange,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex gap-2">
      <Input
        id={id}
        type={show ? "text" : "password"}
        autoComplete="new-password"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <Button
        type="button"
        variant="outline"
        size="icon"
        title="Generar contraseña"
        onClick={() => {
          onChange(generatePassword());
          setShow(true);
        }}
      >
        <Wand2 className="w-4 h-4" />
      </Button>
      <Button type="button" variant="outline" size="icon" onClick={() => setShow((v) => !v)}>
        {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </Button>
    </div>
  );
}

export default function UsersView() {
  const { loading: authLoading, isWorker, isManagement, user: currentUser } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);

  const [createOpen, setCreateOpen] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("SALESPERSON");
  const [newZone, setNewZone] = useState<Zone | "">("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [passwordTarget, setPasswordTarget] = useState<ManagedUser | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [resetError, setResetError] = useState<string | null>(null);
  const [resetSubmitting, setResetSubmitting] = useState(false);

  const [deactivateTarget, setDeactivateTarget] = useState<ManagedUser | null>(null);

  const fetchUsers = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/auth/users/");
      if (!res.ok) throw new Error("No se pudo cargar la lista de usuarios.");
      setUsers(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la lista de usuarios.");
    } finally {
      setLoading(false);
    }
  };

  const fetchAuditLog = async () => {
    try {
      const res = await apiFetch("/api/auth/audit-log/");
      if (!res.ok) return;
      setAuditLog(await res.json());
    } catch {
      // Non-critical - the history panel just stays as-is if this fails.
    }
  };

  useEffect(() => {
    if (!isManagement) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchUsers();
    fetchAuditLog();
  }, [isManagement]);

  const updateUser = async (id: number, body: Record<string, unknown>) => {
    const res = await apiFetch(`/api/auth/users/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error ?? "No se pudo actualizar el usuario.");
    setUsers((prev) => prev.map((u) => (u.id === id ? json : u)));
    fetchAuditLog();
    return json;
  };

  const handleRoleChange = async (targetUser: ManagedUser, role: Role) => {
    try {
      await updateUser(targetUser.id, { role });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cambiar el rol.");
    }
  };

  const handleZoneChange = async (targetUser: ManagedUser, zone: Zone | "") => {
    try {
      await updateUser(targetUser.id, { zone });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cambiar la zona.");
    }
  };

  const handleActiveChange = async (targetUser: ManagedUser, isActive: boolean) => {
    // Turning an account back on is always immediate - the risky direction
    // (locking someone out) is the one that gets a confirmation step.
    if (!isActive) {
      setDeactivateTarget(targetUser);
      return;
    }
    try {
      await updateUser(targetUser.id, { is_active: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar el usuario.");
    }
  };

  const confirmDeactivate = async () => {
    if (!deactivateTarget) return;
    try {
      await updateUser(deactivateTarget.id, { is_active: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo desactivar el usuario.");
    } finally {
      setDeactivateTarget(null);
    }
  };

  const openCreateDialog = () => {
    setNewUsername("");
    setNewPassword("");
    setNewRole("SALESPERSON");
    setNewZone("");
    setCreateError(null);
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    setCreating(true);
    setCreateError(null);
    try {
      const res = await apiFetch("/api/auth/users/", {
        method: "POST",
        body: JSON.stringify({ username: newUsername, password: newPassword, role: newRole, zone: newZone }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "No se pudo crear el usuario.");
      setUsers((prev) => [...prev, json].sort((a, b) => a.username.localeCompare(b.username)));
      fetchAuditLog();
      setCreateOpen(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "No se pudo crear el usuario.");
    } finally {
      setCreating(false);
    }
  };

  const openPasswordDialog = (targetUser: ManagedUser) => {
    setPasswordTarget(targetUser);
    setResetPassword("");
    setResetError(null);
  };

  const handleResetPassword = async () => {
    if (!passwordTarget) return;
    setResetSubmitting(true);
    setResetError(null);
    try {
      await updateUser(passwordTarget.id, { password: resetPassword });
      setPasswordTarget(null);
    } catch (err) {
      setResetError(err instanceof Error ? err.message : "No se pudo cambiar la contraseña.");
    } finally {
      setResetSubmitting(false);
    }
  };

  if (!authLoading && !isWorker) {
    return (
      <main className="max-w-4xl mx-auto w-full p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">
            Debe iniciar sesión para ver esta página.
          </p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  if (!authLoading && !isManagement) {
    return (
      <main className="max-w-4xl mx-auto w-full p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">
            No tiene permiso para ver esta página.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-4xl mx-auto w-full p-6 flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold text-gray-900">Usuarios</h1>
          <p className="text-sm text-gray-500">
            Cuentas del personal - vendedores y gerencia.
          </p>
        </div>
        <Button onClick={openCreateDialog}>
          <Plus className="w-4 h-4" />
          Crear usuario
        </Button>
      </div>

      {(loading || authLoading) && <Loader2 className="w-5 h-5 animate-spin text-gray-400" />}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="rounded-lg border bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Usuario</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Zona</TableHead>
              <TableHead>Activo</TableHead>
              <TableHead>Último acceso</TableHead>
              <TableHead className="w-40" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.map((u) => {
              const isSelf = u.username === currentUser?.username;
              return (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">
                    {u.username}
                    {isSelf && <span className="ml-2 text-xs text-gray-400">(usted)</span>}
                  </TableCell>
                  <TableCell>
                    <RoleSelect
                      value={u.role}
                      disabled={isSelf}
                      onChange={(role) => handleRoleChange(u, role)}
                    />
                  </TableCell>
                  <TableCell>
                    <ZoneSelect
                      value={u.zone}
                      onChange={(zone) => handleZoneChange(u, zone)}
                    />
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={u.is_active}
                      disabled={isSelf}
                      onCheckedChange={(checked) => handleActiveChange(u, checked)}
                    />
                  </TableCell>
                  <TableCell className="text-xs text-gray-500">
                    {formatDateTime(u.last_login)}
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-xs"
                      onClick={() => openPasswordDialog(u)}
                    >
                      <KeyRound className="w-3.5 h-3.5" />
                      Contraseña
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
            {users.length === 0 && !loading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-gray-500 py-8">
                  Sin usuarios.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-gray-900">Historial</h2>
        <div className="rounded-lg border bg-white">
          <Table>
            <TableBody>
              {auditLog.map((entry) => (
                <TableRow key={entry.id} className="hover:bg-transparent">
                  <TableCell className="text-xs text-gray-500 whitespace-nowrap">
                    {formatDateTime(entry.created_at)}
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className="font-medium">{entry.actor_username}</span>{" "}
                    {AUDIT_ACTION_LABELS[entry.action]}{" "}
                    <span className="font-medium">{entry.target_username}</span>
                    {entry.detail && <span className="text-gray-500"> ({entry.detail})</span>}
                  </TableCell>
                </TableRow>
              ))}
              {auditLog.length === 0 && (
                <TableRow>
                  <TableCell colSpan={2} className="text-center text-sm text-gray-500 py-8">
                    Sin actividad todavía.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Crear usuario</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-username">Usuario</Label>
              <Input
                id="new-username"
                autoFocus
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-password">Contraseña</Label>
              <PasswordField id="new-password" value={newPassword} onChange={setNewPassword} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-role">Rol</Label>
              <RoleSelect id="new-role" value={newRole} onChange={setNewRole} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-zone">Zona (opcional)</Label>
              <ZoneSelect id="new-zone" value={newZone} onChange={setNewZone} />
            </div>
            {createError && <p className="text-sm text-red-600">{createError}</p>}
            <Button onClick={handleCreate} disabled={creating}>
              {creating ? "Creando..." : "Crear"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={passwordTarget !== null} onOpenChange={(open) => !open && setPasswordTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>
              Cambiar contraseña{passwordTarget && ` - ${passwordTarget.username}`}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="reset-password">Nueva contraseña</Label>
              <PasswordField id="reset-password" value={resetPassword} onChange={setResetPassword} />
            </div>
            {resetError && <p className="text-sm text-red-600">{resetError}</p>}
            <Button onClick={handleResetPassword} disabled={resetSubmitting}>
              {resetSubmitting ? "Guardando..." : "Guardar"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <AlertDialog open={deactivateTarget !== null} onOpenChange={(open) => !open && setDeactivateTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>¿Desactivar a {deactivateTarget?.username}?</AlertDialogTitle>
            <AlertDialogDescription>
              No podrá iniciar sesión hasta que se vuelva a activar su cuenta.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDeactivate}>Desactivar</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </main>
  );
}
