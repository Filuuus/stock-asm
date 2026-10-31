"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { MessageCircle } from "lucide-react";
import { Notice } from "@/components/notice";
import { EmptyRow, HIDE_BELOW_SM } from "@/components/sortable-table";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { QUOTE_STATUS as STATUS, type QuoteStatus, waitingLabel, whatsappUrl } from "@/lib/quote-status";
import { cn } from "@/lib/utils";

interface RequestRow {
  id: number;
  status: QuoteStatus;
  created_at: string;
  name: string;
  company: string;
  phone: string;
  owner: string | null;
  attention: "amber" | "red" | "stale" | null;
  to_send: boolean;
  expired: boolean;
  comparison: boolean;
  area: string | null;
  items: string[];
}

const TABS: { label: string; show: (r: RequestRow) => boolean }[] = [
  { label: "Pendientes", show: (r) => r.status === "NEW" || r.status === "CONTACTED" || r.to_send },
  { label: "Aprobadas", show: (r) => r.status === "APPROVED" },
  { label: "Cerradas", show: (r) => r.status === "REJECTED" },
  { label: "Todas", show: () => true },
];

const fold = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

const Tag = ({ className, children }: { className: string; children: string }) => (
  <span className={cn("whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", className)}>{children}</span>
);

function Tags({ row: r }: { row: RequestRow }) {
  return (
    <div className="flex flex-wrap gap-1">
      <Tag className={STATUS[r.status].className}>{STATUS[r.status].label}</Tag>
      {r.to_send && <Tag className="bg-amber-100 text-amber-800">Por enviar</Tag>}
      {r.attention === "stale" && <Tag className="bg-amber-100 text-amber-800">Sin seguimiento</Tag>}
      {r.expired && <Tag className="bg-gray-100 text-gray-600">Vencida</Tag>}
      {r.comparison && <Tag className="bg-slate-100 text-slate-700">Comparación</Tag>}
    </div>
  );
}

function WhatsApp({ row: r, onContact }: { row: RequestRow; onContact: (id: number) => void }) {
  return (
    <a
      href={whatsappUrl(r.phone)}
      target="_blank"
      rel="noopener noreferrer"
      onClick={() => onContact(r.id)}
      className="inline-flex items-center gap-1 text-sm text-green-700 hover:underline"
    >
      <MessageCircle className="h-4 w-4" aria-hidden />
      <span className="whitespace-nowrap">{r.phone}</span>
    </a>
  );
}

// The office's work queue: quote requests from the public site, whoever has waited longest
// on top. Any staff member can pick one up; management approves.
export default function RequestsPage() {
  const { user, loading } = useAuth();
  const [rows, setRows] = useState<RequestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(0);
  const [query, setQuery] = useState("");

  const load = () =>
    apiFetch("/api/solicitudes/")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setRows)
      .catch(() => setError("No se pudieron cargar las solicitudes."));

  useEffect(() => {
    if (user) load();
  }, [user]);

  const shown = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    const found = (rows ?? []).filter((r) => {
      const text = fold(`${r.name} ${r.company} ${r.phone}`);
      return TABS[tab].show(r) && words.every((w) => text.includes(w));
    });
    return tab === 0 ? [...found].reverse() : found; // the server sends newest first
  }, [rows, tab, query]);

  if (!loading && !user) {
    return (
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
        <Notice tone="info" title="Inicia sesión para ver las solicitudes." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
      </main>
    );
  }

  // Opening WhatsApp marks it contacted and takes it, if it's still new.
  const contact = (id: number) => apiFetch(`/api/solicitudes/${id}/contactar/`, { method: "POST" }).then(load);

  return (
    <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Solicitudes</h1>
      <p className="mt-1 text-sm text-gray-500">Solicitudes de cotización enviadas desde el sitio.</p>
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1" role="tablist">
          {TABS.map((t, i) => (
            <button
              key={t.label}
              type="button"
              role="tab"
              aria-selected={tab === i}
              onClick={() => setTab(i)}
              className={cn("rounded-md px-3 py-1.5 text-sm font-medium", tab === i ? "bg-white text-gray-900 shadow-sm" : "text-gray-600 hover:text-gray-900")}
            >
              {t.label} ({(rows ?? []).filter(t.show).length})
            </button>
          ))}
        </div>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar por nombre, empresa o teléfono"
          aria-label="Buscar solicitudes"
          className="w-full sm:w-80"
        />
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Cliente</TableHead>
              <TableHead className={HIDE_BELOW_SM}>Espera</TableHead>
              <TableHead className={HIDE_BELOW_SM}>Responsable</TableHead>
              <TableHead className={HIDE_BELOW_SM}>Estado</TableHead>
              <TableHead className={cn(HIDE_BELOW_SM, "text-right")}>Contacto</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows === null ? (
              <EmptyRow colSpan={5}>Cargando…</EmptyRow>
            ) : shown.length === 0 ? (
              <EmptyRow colSpan={5}>{query ? "Sin resultados." : "No hay solicitudes aquí."}</EmptyRow>
            ) : (
              shown.map((r) => (
                <TableRow key={r.id} className={cn("align-top", r.attention === "red" && "bg-red-50/60", r.attention === "amber" && "bg-amber-50/60")}>
                  <TableCell className="whitespace-normal">
                    <Link href={`/solicitudes/${r.id}`} className="block">
                      <span className="font-medium text-gray-900 hover:text-blue-700">{r.name}</span>
                      <span className="ml-2 text-xs text-gray-400">#{r.id}</span>
                      {r.company && <span className="block text-xs text-gray-500">{r.company}</span>}
                      <span className="mt-0.5 block max-w-[calc(100vw-4rem)] truncate text-xs text-gray-500 sm:max-w-xl">
                        {r.items.join(", ")}
                        {r.area && ` · ${r.area}`}
                      </span>
                    </Link>
                    {/* Phones: the columns hidden there, under the name. */}
                    <div className="mt-2 sm:hidden">
                      <Tags row={r} />
                      <p className="mt-1 text-xs text-gray-500">
                        {waitingLabel(r.created_at)} · {r.owner ?? "Sin asignar"}
                      </p>
                      <WhatsApp row={r} onContact={contact} />
                    </div>
                  </TableCell>
                  <TableCell className={cn(HIDE_BELOW_SM, "whitespace-nowrap", r.attention === "red" && "font-medium text-red-700", r.attention === "amber" && "font-medium text-amber-700")}>
                    {waitingLabel(r.created_at)}
                  </TableCell>
                  <TableCell className={cn(HIDE_BELOW_SM, !r.owner && "text-gray-400")}>{r.owner ?? "Sin asignar"}</TableCell>
                  <TableCell className={HIDE_BELOW_SM}>
                    <Tags row={r} />
                  </TableCell>
                  <TableCell className={cn(HIDE_BELOW_SM, "text-right")}>
                    <WhatsApp row={r} onContact={contact} />
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
