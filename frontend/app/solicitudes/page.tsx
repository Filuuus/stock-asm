"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Notice } from "@/components/notice";
import { EmptyRow, HIDE_BELOW_SM } from "@/components/sortable-table";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import { QUOTE_STATUS as STATUS, type QuoteStatus } from "@/lib/quote-status";
import { cn } from "@/lib/utils";

interface RequestRow {
  id: number;
  status: QuoteStatus;
  created_at: string;
  name: string;
  company: string;
  items: number;
}

// Quote requests sent from the public cart (newest first). Any staff member
// can review them; management approves.
export default function RequestsPage() {
  const { user, loading } = useAuth();
  const [rows, setRows] = useState<RequestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch("/api/solicitudes/")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setRows)
      .catch(() => setError("No se pudieron cargar las solicitudes."));
  }, [user]);

  if (!loading && !user) {
    return (
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
        <Notice tone="info" title="Inicia sesión para ver las solicitudes." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Solicitudes</h1>
      <p className="mt-1 text-sm text-gray-500">Solicitudes de cotización enviadas desde el catálogo.</p>
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}
      <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>#</TableHead>
              <TableHead>Cliente</TableHead>
              <TableHead className={HIDE_BELOW_SM}>Fecha</TableHead>
              <TableHead className="text-right">Productos</TableHead>
              <TableHead>Estado</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows === null ? (
              <EmptyRow colSpan={5}>Cargando…</EmptyRow>
            ) : rows.length === 0 ? (
              <EmptyRow colSpan={5}>Aún no hay solicitudes.</EmptyRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id} className="cursor-pointer">
                  <TableCell>
                    <Link href={`/solicitudes/${r.id}`} className="text-blue-600 hover:underline">
                      {r.id}
                    </Link>
                  </TableCell>
                  <TableCell>
                    <Link href={`/solicitudes/${r.id}`} className="block">
                      <span className="font-medium text-gray-800">{r.name}</span>
                      {r.company && <span className="block text-xs text-gray-500">{r.company}</span>}
                    </Link>
                  </TableCell>
                  <TableCell className={HIDE_BELOW_SM}>{formatDay(r.created_at)}</TableCell>
                  <TableCell className="num">{r.items}</TableCell>
                  <TableCell>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUS[r.status].className)}>
                      {STATUS[r.status].label}
                    </span>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </main>
  );
}
