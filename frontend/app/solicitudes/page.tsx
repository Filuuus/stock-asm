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
import { WhatsAppLink } from "@/components/whatsapp-link";
import { CLOSED_AS, type ClosedAs, QUOTE_STATUS as STATUS, type QuoteStatus, type Stage, waitingLabel } from "@/lib/quote-status";
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
  accepted: boolean; // the customer approved it, still open: a sale to close
  follow_up: "no_answer" | "expiring" | null; // sent, the customer hasn't approved it
  no_phone: boolean; // no number WhatsApp can reach
  expired: boolean;
  stage: Stage;
  closed_as: ClosedAs | null;
  from_staff: boolean; // made by staff (Servicios), not asked for from the catalog
  comparison: boolean;
  area: string | null;
  items: string[];
}

// Client requests are answered in hours; quotes staff made are followed up for days: two separate queues.
const ORIGINS = [
  { label: "De clientes", show: (r: RequestRow) => !r.from_staff },
  { label: "De staff", show: (r: RequestRow) => r.from_staff },
];

// By the next step; the first two oldest first (whoever has waited longest), the rest newest first.
const TABS: { label: string; stage?: Stage; oldestFirst?: boolean }[] = [
  { label: "Por cotizar", stage: "por_cotizar", oldestFirst: true },
  { label: "Por enviar", stage: "por_enviar", oldestFirst: true },
  { label: "Esperando", stage: "esperando" },
  { label: "Aprobadas", stage: "aprobada" },
  { label: "Cerradas", stage: "cerrada" },
  { label: "Todas" },
];

// The tab a queue opens on: its first with something in it.
const firstBusy = (rows: RequestRow[]) => Math.max(0, TABS.findIndex((t) => t.stage && rows.some((r) => r.stage === t.stage)));

const fold = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();

const Tag = ({ className, children }: { className: string; children: string }) => (
  <span className={cn("whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", className)}>{children}</span>
);

function Tags({ row: r }: { row: RequestRow }) {
  return (
    <div className="flex flex-wrap gap-1">
      {r.closed_as ? (
        <Tag className={CLOSED_AS[r.closed_as].className}>{CLOSED_AS[r.closed_as].label}</Tag>
      ) : (
        <Tag className={STATUS[r.status].className}>{STATUS[r.status].label}</Tag>
      )}
      {r.accepted && <Tag className="bg-green-600 text-white">Aprobada por el cliente</Tag>}
      {r.to_send && <Tag className="bg-amber-100 text-amber-800">Por enviar</Tag>}
      {r.no_phone && <Tag className="bg-red-100 text-red-800">Sin teléfono</Tag>}
      {r.follow_up === "no_answer" && <Tag className="bg-amber-100 text-amber-800">Sin respuesta</Tag>}
      {r.follow_up === "expiring" && <Tag className="bg-red-100 text-red-800">Vence pronto</Tag>}
      {r.attention === "stale" && <Tag className="bg-amber-100 text-amber-800">Sin seguimiento</Tag>}
      {r.expired && !r.closed_as && <Tag className="bg-gray-100 text-gray-600">Vencida</Tag>}
      {r.comparison && <Tag className="bg-slate-100 text-slate-700">Comparación</Tag>}
    </div>
  );
}

function WhatsApp({ row: r, onContact }: { row: RequestRow; onContact: (id: number) => void }) {
  if (r.no_phone) return null; // the "Sin teléfono" tag says it
  return (
    <WhatsAppLink phone={r.phone} onClick={() => onContact(r.id)} className="inline-flex items-center gap-1 text-sm text-green-700 hover:underline">
      <MessageCircle className="h-4 w-4" aria-hidden />
      <span className="whitespace-nowrap">{r.phone}</span>
    </WhatsAppLink>
  );
}

// The office's work queues: requests from the public site and quotes staff made (Servicios), each by its next step.
// Any staff member can pick one up and send it.
export default function RequestsPage() {
  const { user, loading } = useAuth();
  const [rows, setRows] = useState<RequestRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [origin, setOrigin] = useState(0);
  const [tab, setTab] = useState<number | null>(null); // null: the queue's first tab with something in it
  const [query, setQuery] = useState("");

  const load = () =>
    apiFetch("/api/solicitudes/")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setRows)
      .catch(() => setError("No se pudieron cargar las solicitudes."));

  useEffect(() => {
    if (user) load();
  }, [user]);

  const queue = useMemo(() => (rows ?? []).filter(ORIGINS[origin].show), [rows, origin]);
  const current = tab ?? firstBusy(queue);
  const inTab = (r: RequestRow, i: number) => !TABS[i].stage || r.stage === TABS[i].stage;
  const shown = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    const found = queue.filter((r) => inTab(r, current) && words.every((w) => fold(`${r.name} ${r.company} ${r.phone}`).includes(w)));
    return TABS[current].oldestFirst ? [...found].reverse() : found; // the server sends newest first
  }, [queue, current, query]);
  // What needs someone in a queue: everything not waiting on the customer or closed.
  const waiting = (show: (r: RequestRow) => boolean) =>
    (rows ?? []).filter((r) => show(r) && (r.stage === "por_cotizar" || r.stage === "por_enviar" || r.stage === "aprobada" || !!r.follow_up)).length;

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
      <p className="mt-1 text-sm text-gray-500">Solicitudes del sitio y cotizaciones hechas desde Servicios.</p>
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      <div className="mt-6 flex gap-6 border-b border-gray-200" role="tablist" aria-label="Origen">
        {ORIGINS.map((o, i) => {
          const count = waiting(o.show);
          return (
            <button
              key={o.label}
              type="button"
              role="tab"
              aria-selected={origin === i}
              onClick={() => {
                setOrigin(i);
                setTab(null);
              }}
              className={cn(
                "-mb-px flex items-center gap-2 border-b-2 pb-2 text-base font-medium",
                origin === i ? "border-gray-900 text-gray-900" : "border-transparent text-gray-500 hover:text-gray-800",
              )}
            >
              {o.label}
              {count > 0 && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">{count}</span>}
            </button>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1" role="tablist" aria-label="Etapa">
          {TABS.map((t, i) => {
            const count = queue.filter((r) => inTab(r, i)).length;
            return (
              <button
                key={t.label}
                type="button"
                role="tab"
                aria-selected={current === i}
                onClick={() => setTab(i)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm font-medium",
                  current === i ? "bg-white text-gray-900 shadow-sm" : count ? "text-gray-600 hover:text-gray-900" : "text-gray-400",
                )}
              >
                {t.label} ({count})
              </button>
            );
          })}
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
              <TableHead className={cn(HIDE_BELOW_SM, "whitespace-nowrap")}>Espera</TableHead>
              <TableHead className={cn(HIDE_BELOW_SM, "whitespace-nowrap")}>Responsable</TableHead>
              <TableHead className={cn(HIDE_BELOW_SM, "whitespace-nowrap")}>Estado</TableHead>
              <TableHead className={cn(HIDE_BELOW_SM, "whitespace-nowrap text-right")}>Contacto</TableHead>
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
                  <TableCell className="w-full max-w-0 whitespace-normal">
                    <Link href={`/solicitudes/${r.id}`} className="block">
                      <span className="font-medium text-gray-900 hover:text-blue-700">{r.name}</span>
                      <span className="ml-2 text-xs text-gray-400">#{r.id}</span>
                      {r.company && <span className="block text-xs text-gray-500">{r.company}</span>}
                      <span className="mt-0.5 block truncate text-xs text-gray-500">
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
                  <TableCell className={cn(HIDE_BELOW_SM, "whitespace-nowrap", !r.owner && "text-gray-400")}>{r.owner ?? "Sin asignar"}</TableCell>
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
