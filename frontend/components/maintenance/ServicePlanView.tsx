"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { Check, ChevronLeft, ChevronRight, Pencil, Printer } from "lucide-react";
import ProductDialog from "@/components/catalog/ProductDialog";
import ClientLink from "@/components/facturas/ClientLink";
import RequestsList from "@/components/quote/RequestsList";
import RequestDetail from "@/components/quote/RequestDetail";
import InvoiceLink from "@/components/facturas/InvoiceLink";
import { Notice } from "@/components/notice";
import { EmptyRow, HIDE_BELOW_MD, HIDE_BELOW_SM } from "@/components/sortable-table";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { WhatsAppLink } from "@/components/whatsapp-link";
import { formatDay, formatDayLong, formatMonth, isoToDate, todayISO } from "@/lib/dates";
import { cn, formatMoney, plural } from "@/lib/utils";
import type { EventKind, ParlorPartRow, PlanParlor, ServicePlan } from "@/types/maintenance";

// Service plan, on GEA's intervals. Agenda: management's calendar sheet, a row per client and a column per month;
// a client's name opens all its parts by category, the most relevant first, and a cell opens that month. Pedido:
// the next GEA order. Dates come from the invoices: an invoice for the parts is the record of the service.

const TABS = ["Agenda", "Pedido", "Solicitudes"] as const; // Solicitudes only when embedded
type Tab = (typeof TABS)[number];

const SOON_DAYS = 60;
const PROSPECT_OVERDUE_DAYS = 90; // a prospect's part overdue longer than this was likely changed elsewhere
const DAY_MS = 86_400_000;
const BASIS_LABEL: Record<string, string> = {
  GEA: "GEA",
  cliente: "su ritmo",
  clientes: "otros clientes",
  calendario: "calendario",
};
const MONTHS = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"];
// Short category names for the agenda's narrow month cells (the full names show on hover).
const SHORT: Record<string, string> = {
  Colectores: "Colect.",
  Pulsadores: "Puls.",
  "Vaso pesador": "Vaso",
  "Banco de válvulas": "Válv.",
  Retiradores: "Retir.",
  "Recibidor de leche": "Recib.",
  "Bomba de leche": "B. leche",
  "Trampa de líquidos": "Trampa",
  "Regulador de vacío": "Regul.",
  "Sistema de vacío": "Vacío",
  Enfriamiento: "Enfr.",
};
// What a cell shows: the plan's events, plus the next change of a part with an open quote (quoted: being priced or
// sent; accepted: the client approved it), so the agenda shows who was already offered the service.
type CellKind = EventKind | "quoted" | "accepted";
const KIND: Record<CellKind, { label: string; className: string }> = {
  missed: { label: "Vencido", className: "bg-red-100 text-red-800" },
  quoted: { label: "Cotizado", className: "bg-violet-200 text-violet-900" },
  accepted: { label: "Aprobado", className: "bg-green-600 text-white" },
  done: { label: "Realizado", className: "bg-sky-100 text-sky-800" },
  external: { label: "Externo", className: "bg-stone-200 text-stone-700" },
  due: { label: "Pendiente", className: "bg-green-100 text-green-800" },
};
const CELL_ORDER: CellKind[] = ["missed", "quoted", "accepted", "done", "external", "due"];
// Pending changes: what a crew sheet lists and a month's dialog can quote.
const PENDING: CellKind[] = ["missed", "quoted", "accepted", "due"];

const units = (n: number) => n.toLocaleString("es-MX", { maximumFractionDigits: 2 });
const fold = (text: string) => text.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
const clientName = (p: PlanParlor) => [p.name || p.client, p.label].filter(Boolean).join(" · ");
const isDated = (r: ParlorPartRow) => r.status === "ok" || r.status === "overdue";
// A part can be in two places of a parlor (the same hose on the claws and on the LECC): a row per place.
const placeKey = (r: ParlorPartRow) => `${r.code}|${r.group}`;

const Chip = ({ className, children, title }: { className: string; children: ReactNode; title?: string }) => (
  <span title={title} className={cn("whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium", className)}>
    {children}
  </span>
);

// A client's dated parts by category, most relevant first (services.relevance: pesos a year weighted by how often
// it's changed on time), each category's first date, and how many of its parts fall due with it (within SOON_DAYS
// of that date, so the same visit takes them).
interface Category {
  name: string;
  parts: ParlorPartRow[];
  first: string;
  together: number;
  score: number;
}

function categoriesOf(parlor: PlanParlor, order: string[]): Category[] {
  const byName = new Map<string, ParlorPartRow[]>();
  for (const r of parlor.parts.filter(isDated)) byName.set(r.group, [...(byName.get(r.group) ?? []), r]);
  const rank = (c: string) => (order.includes(c) ? order.indexOf(c) : order.length);
  return [...byName.entries()]
    .map(([name, parts]) => {
      const first = parts.map((r) => r.due!).sort()[0];
      const together = parts.filter((r) => isoToDate(r.due!).getTime() - isoToDate(first).getTime() <= SOON_DAYS * DAY_MS).length;
      const sorted = [...parts].sort((a, b) => b.score - a.score || a.due!.localeCompare(b.due!));
      return { name, parts: sorted, first, together, score: sorted[0].score };
    })
    .sort((a, b) => b.score - a.score || rank(a.name) - rank(b.name));
}

// Opens a quote request in a dialog over the page, from anywhere in it (QuoteChip).
const OpenRequest = createContext<(id: number) => void>(() => {});

// embedded: the Notion embed (/embed/servicios), where leaving the page isn't an option: Solicitudes is a tab here,
// with its requests opening in the same dialog as the agenda's quotes.
export default function ServicePlanView({ embedded = false }: { embedded?: boolean } = {}) {
  const { user, loading } = useAuth();
  const [plan, setPlan] = useState<ServicePlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Agenda");
  const [opened, setOpened] = useState<{ key: string; name: string } | null>(null);
  const [requestId, setRequestId] = useState<number | null>(null);
  const [requestChanges, setRequestChanges] = useState(0); // reloads the Solicitudes tab after its dialog closes
  const [today] = useState(() => new Date());
  // Prospects come without their parts until the prospects list is opened or searched: they're most of the data.
  const [withProspects, setWithProspects] = useState(false);

  // Again after a part's quantity is fixed or it's removed.
  const load = useCallback(
    () =>
      apiFetch(`/api/servicios/plan/${withProspects ? "?prospectos=1" : ""}`)
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then(setPlan)
        .catch(() => setError("No se pudo cargar el plan de servicios.")),
    [withProspects],
  );
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!loading && !user) {
    return (
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
        {embedded ? (
          <Notice tone="error" title="Este enlace no es válido o fue revocado." summary="Pide un enlace nuevo a quien administra el sitio." />
        ) : (
          <Notice tone="info" title="Inicia sesión para ver los servicios." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
        )}
      </main>
    );
  }

  // A part's name opens its product page in a dialog (parts not in the ERP stay plain text).
  const name = (code: string): ReactNode => {
    const label = plan?.names[code] ?? code;
    const key = plan?.keys[code];
    if (!key) return label;
    return (
      <button type="button" onClick={() => setOpened({ key, name: label })} className="text-left hover:text-blue-700 hover:underline">
        {label}
      </button>
    );
  };

  return (
    <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <h1 className="text-2xl font-semibold text-gray-900">Servicios</h1>
        <div className="flex gap-1 rounded-lg bg-gray-100 p-1" role="tablist">
          {TABS.filter((t) => embedded || t !== "Solicitudes").map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={tab === t}
              onClick={() => setTab(t)}
              className={cn("rounded-md px-3 py-1.5 text-sm font-medium", tab === t ? "bg-white text-gray-900 shadow-sm" : "text-gray-600 hover:text-gray-900")}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      <OpenRequest.Provider value={setRequestId}>
      <div className="mt-4">
        {tab === "Solicitudes" ? (
          <RequestsList onOpen={setRequestId} reloadKey={requestChanges} />
        ) : plan === null ? (
          <p className="text-sm text-gray-500">{error ? "" : "Cargando…"}</p>
        ) : tab === "Agenda" ? (
          <AgendaTab
            plan={plan}
            name={name}
            today={today}
            onChanged={load}
            onQuoted={(id) => (load(), setRequestId(id))}
            onShowProspects={() => setWithProspects(true)}
          />
        ) : (
          <OrderTab plan={plan} name={name} />
        )}
      </div>
      </OpenRequest.Provider>
      {opened && <ProductDialog productKey={opened.key} fallbackName={opened.name} onClose={() => setOpened(null)} />}
      {requestId !== null && (
        <Dialog
          open
          onOpenChange={(open) => {
            if (open) return;
            setRequestId(null);
            load(); // its status shows on the parts it quotes
            setRequestChanges((n) => n + 1);
          }}
        >
          <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] max-w-6xl overflow-y-auto">
            <DialogTitle className="sr-only">Solicitud #{requestId}</DialogTitle>
            <RequestDetail id={requestId} onOpenRequest={setRequestId} />
          </DialogContent>
        </Dialog>
      )}
    </main>
  );
}

// A due date: red when past, green (the agenda's "por realizar") within SOON_DAYS.
function DueDate({ due, today, className }: { due: string; today: Date; className?: string }) {
  const days = (isoToDate(due).getTime() - today.getTime()) / DAY_MS;
  return (
    <span className={cn("whitespace-nowrap", days < 0 ? "font-medium text-red-700" : days <= SOON_DAYS && "font-medium text-green-700", className)}>
      {formatDay(due)}
    </span>
  );
}

// A part's open service quote, linking to its request.
// cotizado: being priced; aprobado: shared on the client's link; aceptado: the client approved it.
const QUOTE_LABEL = { cotizado: "Cotizando", aprobado: "Cotizado", enviado: "Enviado", aceptado: "Aprobado" };
function QuoteChip({ quote }: { quote: ParlorPartRow["quote"] }) {
  const open = useContext(OpenRequest);
  if (!quote) return null;
  return (
    <button
      type="button"
      onClick={() => open(quote.id)}
      className={cn(
        "whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium hover:underline",
        quote.status === "aceptado" ? "bg-green-600 text-white" : "bg-violet-100 text-violet-800", // as the agenda's cells
      )}
    >
      {QUOTE_LABEL[quote.status]} #{quote.id}
    </button>
  );
}

// A part's quantity, fixable in place (the calendars' are often estimates: hoses by the meter).
function PartQuantity({ row, onChanged }: { row: ParlorPartRow; onChanged: () => void }) {
  const [value, setValue] = useState<string | null>(null);
  const [error, setError] = useState(false);
  if (value === null) {
    return (
      <span className="inline-flex items-center gap-1 whitespace-nowrap">
        {units(row.quantity)}
        <button type="button" aria-label={`Corregir cantidad de ${row.code}`} onClick={() => setValue(String(row.quantity))}>
          <Pencil className="h-3 w-3 text-gray-400 hover:text-blue-700" />
        </button>
      </span>
    );
  }
  const save = async () => {
    const r = await apiFetch(`/api/servicios/piezas/${row.id}/`, { method: "PATCH", body: JSON.stringify({ quantity: Number(value) }) });
    if (!r.ok) return setError(true);
    setValue(null);
    onChanged();
  };
  return (
    <form
      className="inline-flex items-center gap-1"
      onSubmit={(e) => {
        e.preventDefault();
        save();
      }}
    >
      <Input
        type="number"
        min={1}
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && (e.stopPropagation(), setValue(null))}
        aria-label={`Cantidad de ${row.code}`}
        className={cn("h-7 w-20 text-right", error && "border-red-500")}
      />
      <button type="submit" aria-label="Guardar cantidad">
        <Check className="h-4 w-4 text-green-700" />
      </button>
    </form>
  );
}

// Parts picked in a client's or a month's dialog, for the selection bar's actions (by place: a part can be in two
// places of a parlor).
function useSelection(initial: ParlorPartRow[] = []) {
  const [keys, setKeys] = useState(() => new Set(initial.map(placeKey)));
  const set = (rows: ParlorPartRow[], on: boolean) =>
    setKeys((prev) => {
      const next = new Set(prev);
      for (const r of rows) {
        if (on) next.add(placeKey(r));
        else next.delete(placeKey(r));
      }
      return next;
    });
  return { keys, has: (r: ParlorPartRow) => keys.has(placeKey(r)), set, clear: () => setKeys(new Set()) };
}
type Selection = ReturnType<typeof useSelection>;

function SelectBox({ rows, selection, label }: { rows: ParlorPartRow[]; selection: Selection; label: string }) {
  const on = rows.filter(selection.has).length;
  return (
    <Checkbox
      aria-label={label}
      checked={on === 0 ? false : on === rows.length ? true : "indeterminate"}
      onCheckedChange={(v) => selection.set(rows, v === true)}
      onClick={(e) => e.stopPropagation()} // inside a category's summary: don't fold it
    />
  );
}

// What can be done to the selected parts: quote them, note that someone else changed them (another dealer, the
// client's own crew: no invoice of ours shows it, but it restarts their interval so the client can be offered the
// next change in time), or remove them as not in the parlor. Shown only while something is selected.
function SelectionBar({
  parts,
  onQuote,
  onChanged,
  onClear,
}: {
  parts: ParlorPartRow[];
  onQuote: (parts: ParlorPartRow[]) => void;
  onChanged: () => void;
  onClear: () => void;
}) {
  const [day, setDay] = useState<string | null>(null); // the "Lo cambió otro" form
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (parts.length === 0) return null;
  const done = () => {
    setDay(null);
    setNote("");
    setError(null);
    onClear();
    onChanged();
  };
  const external = async () => {
    const r = await apiFetch("/api/servicios/externos/", { method: "POST", body: JSON.stringify({ parts: parts.map((p) => p.id), day, note }) });
    if (!r.ok) return setError((await r.json().catch(() => ({}))).error ?? "No se pudo guardar.");
    done();
  };
  const remove = async () => {
    if (!window.confirm(`¿Quitar ${plural(parts.length, "pieza", "piezas")} de este cliente? La sala no las tiene.`)) return;
    const results = await Promise.all(parts.map((p) => apiFetch(`/api/servicios/piezas/${p.id}/`, { method: "DELETE" })));
    if (results.some((r) => !r.ok)) setError("No se pudieron quitar todas.");
    done();
  };
  return (
    <div className="sticky -bottom-6 -mx-6 -mb-6 mt-2 border-t border-gray-200 bg-white px-6 py-3 shadow-[0_-4px_8px_-6px_rgba(0,0,0,0.15)]">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium text-gray-900">{plural(parts.length, "pieza seleccionada", "piezas seleccionadas")}</span>
        <Button size="sm" onClick={() => onQuote(parts)}>Cotizar</Button>
        <Button size="sm" variant="outline" onClick={() => setDay(day === null ? todayISO() : null)}>Lo cambió otro</Button>
        <Button size="sm" variant="outline" className="text-red-700 hover:text-red-800" onClick={remove}>No aplica</Button>
        <button type="button" className="ml-auto text-xs text-gray-500 hover:underline" onClick={onClear}>Quitar selección</button>
      </div>
      {day !== null && (
        <form
          className="mt-2 flex flex-wrap items-center gap-2 rounded-md bg-stone-100 p-2 text-xs"
          onSubmit={(e) => {
            e.preventDefault();
            external();
          }}
        >
          <span className="text-stone-700">Cambiadas por otro el</span>
          <Input type="date" value={day} max={todayISO()} onChange={(e) => setDay(e.target.value)} aria-label="Fecha del cambio" className="h-7 w-36" />
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Quién lo hizo (opcional)" aria-label="Nota" className="h-7 w-48" />
          <Button type="submit" size="sm" className="h-7">Guardar</Button>
        </form>
      )}
      {error && <p className="mt-1 text-xs text-red-700">{error}</p>}
    </div>
  );
}

// A client's categories (each opening to its parts) and, folded, its parts without recent history.
function ClientDetail({
  categories,
  undated,
  name,
  today,
  onChanged,
  selection,
}: {
  categories: Category[];
  undated: ParlorPartRow[];
  name: (code: string) => ReactNode;
  today: Date;
  onChanged: () => void;
  selection: Selection;
}) {
  return (
    <>
    {categories.length === 0 && <p className="px-4 py-3 text-sm text-gray-500">Ninguna pieza con fecha.</p>}
    {categories.map((c) => (
      <details key={c.name} className="group/cat border-b border-gray-100 last:border-b-0">
        <summary className="grid cursor-pointer list-none grid-cols-[1rem_1rem_minmax(0,1fr)_auto] items-center gap-x-3 px-4 py-2.5 hover:bg-gray-50 sm:grid-cols-[1rem_1rem_minmax(0,1fr)_8rem_9rem]">
          <ChevronRight className="h-4 w-4 text-gray-400 transition-transform group-open/cat:rotate-90" />
          <SelectBox rows={c.parts} selection={selection} label={`Seleccionar ${c.name}`} />
          <span className="font-medium text-gray-900">{c.name}</span>
          <DueDate due={c.first} today={today} />
          <span className="hidden text-right text-sm text-gray-500 sm:block">
            {c.together} de {plural(c.parts.length, "pieza", "piezas")}
          </span>
        </summary>
        <div className="bg-gray-50/60 pb-2 pl-2 pr-2 sm:pl-8 sm:pr-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-8"><span className="sr-only">Seleccionar</span></TableHead>
                <TableHead>Pieza</TableHead>
                <TableHead className={cn(HIDE_BELOW_SM, "text-right")}>Cant.</TableHead>
                <TableHead className={HIDE_BELOW_MD}>Última factura</TableHead>
                <TableHead className={HIDE_BELOW_SM}>Próximo cambio</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {c.parts.map((r) => (
                <TableRow key={placeKey(r)} className="align-top">
                  <TableCell className="pr-0">
                    <SelectBox rows={[r]} selection={selection} label={`Seleccionar ${r.code}`} />
                  </TableCell>
                  <TableCell className="whitespace-normal">
                    <span className="text-gray-900">{name(r.code)}</span> <QuoteChip quote={r.quote} />
                    <span className="block text-xs text-gray-400">
                      {r.code} · {r.per_year ? `${units(r.per_year)} ${r.per_year === 1 ? "cambio" : "cambios"} al año` : "sin cambios en 3 años"}
                      {r.on_time !== null && ` · ${Math.round(r.on_time * 100)} % a tiempo`}
                    </span>
                    {r.registered_as && (
                      <span className="block text-xs text-gray-400">en el calendario: {r.registered_as} (compra este modelo)</span>
                    )}
                    {/* Phones: the next change under the name instead of in its column. */}
                    <span className="mt-1 block text-xs sm:hidden">
                      Próximo cambio: <DueDate due={r.due!} today={today} />
                    </span>
                  </TableCell>
                  <TableCell className={cn(HIDE_BELOW_SM, "text-right tabular-nums")}>
                    <PartQuantity row={r} onChanged={onChanged} />
                  </TableCell>
                  <TableCell className={HIDE_BELOW_MD}>
                    {r.last_invoice ? <InvoiceLink invoiceId={r.last_invoice} label={formatDay(r.last_change)} /> : formatDay(r.last_change)}
                  </TableCell>
                  <TableCell className={HIDE_BELOW_SM}>
                    <DueDate due={r.due!} today={today} />
                    <span className="block text-xs text-gray-400">
                      cada {units(r.months!)} meses ({BASIS_LABEL[r.basis ?? ""] ?? r.basis})
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </details>
    ))}
    {undated.length > 0 && (
      <details className="border-t border-gray-200">
        <summary className="flex cursor-pointer items-center gap-3 px-4 py-2 text-sm text-gray-500">
          <SelectBox rows={undated} selection={selection} label="Seleccionar las piezas sin historial" />
          Sin historial reciente ({undated.length})
        </summary>
        <p className="px-4 pb-2 text-xs text-gray-500">
          Piezas del calendario que no se le han facturado a este cliente en los últimos 2 años, o nunca: quizá
          las compra en otro lado o no las tiene. Toman fecha en cuanto se facturen.
        </p>
        <ul className="px-4 pb-3 text-sm">
          {undated.map((r) => (
            <li key={placeKey(r)} className="flex flex-wrap items-center gap-x-2 py-0.5 text-gray-600">
              <SelectBox rows={[r]} selection={selection} label={`Seleccionar ${r.code}`} />
              <span>{name(r.code)}</span>
              <span className="text-xs text-gray-400">
                {r.code} · {r.group}
                {r.last_change && (
                  <>
                    {" · última factura "}
                    {r.last_invoice ? <InvoiceLink invoiceId={r.last_invoice} label={formatDay(r.last_change)} /> : formatDay(r.last_change)}
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
      </details>
    )}
    </>
  );
}

// A client's overdue categories, those due within SOON_DAYS, and its next date after today.
function summaryOf(categories: Category[], today: Date) {
  const soon = today.getTime() + SOON_DAYS * DAY_MS;
  return {
    overdue: categories.filter((c) => isoToDate(c.first) < today),
    coming: categories.filter((c) => isoToDate(c.first) >= today && isoToDate(c.first).getTime() <= soon),
    next: categories.map((c) => c.first).filter((d) => isoToDate(d) >= today).sort()[0] ?? null,
  };
}

// The client's phone for WhatsApp: Contpaqi's is often missing or a landline, so staff type it here (kept locally,
// and filled into the client's open quotes from Servicios that had none).
function ClientPhone({ parlor, onChanged }: { parlor: PlanParlor; onChanged: () => void }) {
  const [value, setValue] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const valid = parlor.phone.replace(/\D/g, "").length >= 10;
  if (value === null) {
    return (
      <span className="flex items-center gap-1.5">
        {valid ? (
          <WhatsAppLink phone={parlor.phone} className="text-blue-600 hover:underline">
            {parlor.phone}
          </WhatsAppLink>
        ) : (
          <Chip className="bg-amber-100 text-amber-800">{parlor.phone ? `Teléfono incompleto: ${parlor.phone}` : "Sin teléfono"}</Chip>
        )}
        <button type="button" onClick={() => setValue(parlor.phone)} className="text-gray-400 hover:text-blue-700" aria-label="Cambiar teléfono">
          <Pencil className="h-3.5 w-3.5" />
        </button>
      </span>
    );
  }
  const save = async (e: FormEvent) => {
    e.preventDefault();
    const res = await apiFetch(`/api/servicios/clientes/${encodeURIComponent(parlor.client)}/telefono/`, {
      method: "PUT",
      body: JSON.stringify({ phone: value }),
    });
    if (!res.ok) {
      setError((await res.json().catch(() => ({}))).error ?? "No se pudo guardar.");
      return;
    }
    setValue(null);
    setError(null);
    onChanged();
  };
  return (
    <form onSubmit={save} className="flex items-center gap-1.5">
      <Input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="Celular, 10 dígitos" className="h-8 w-40" aria-label="Teléfono" />
      <Button type="submit" size="sm">Guardar</Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => (setValue(null), setError(null))}>Cancelar</Button>
      {error && <span className="text-xs text-red-700">{error}</span>}
    </form>
  );
}

// A prospect someone reached out to, so two people don't call the same farm (quoting them marks it too).
function ProspectContact({ parlor, onChanged }: { parlor: PlanParlor; onChanged: () => void }) {
  const toggle = async () => {
    if ((await apiFetch(`/api/servicios/salas/${parlor.id}/contactado/`, { method: parlor.contacted_at ? "DELETE" : "POST" })).ok) {
      onChanged();
    }
  };
  return parlor.contacted_at ? (
    <span className="flex items-center gap-1.5">
      <Chip className="bg-violet-100 text-violet-800">
        Contactado {new Date(parlor.contacted_at).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}
        {parlor.contacted_by && ` · ${parlor.contacted_by}`}
      </Chip>
      <button type="button" onClick={toggle} className="text-xs text-gray-400 hover:text-red-700 hover:underline">Deshacer</button>
    </span>
  ) : (
    <Button size="sm" variant="outline" onClick={toggle}>Marcar contactado</Button>
  );
}

// Everything about one client: what's overdue or coming, then its categories and parts, most relevant first.
function ClientDialog({
  parlor,
  plan,
  name,
  today,
  onClose,
  onQuote,
  onChanged,
}: {
  parlor: PlanParlor;
  plan: ServicePlan;
  name: (code: string) => ReactNode;
  today: Date;
  onClose: () => void;
  onQuote: (parts?: ParlorPartRow[]) => void;
  onChanged: () => void;
}) {
  const categories = categoriesOf(parlor, plan.categories);
  const { overdue, coming, next } = summaryOf(categories, today);
  const selection = useSelection();
  const selected = parlor.parts.filter(selection.has); // the plan as reloaded: removed parts drop out
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] max-w-4xl overflow-y-auto">
        <DialogHeader className="text-left">
          <DialogTitle>
            <ClientLink clientId={parlor.client_id} label={clientName(parlor)} />
          </DialogTitle>
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <span className="text-xs text-gray-400">{parlor.client}</span>
            {overdue.map((c) => (
              <Chip key={c.name} className="bg-red-100 text-red-800" title={`Vencida desde ${formatDay(c.first)}`}>{c.name}</Chip>
            ))}
            {coming.map((c) => (
              <Chip key={c.name} className="bg-green-100 text-green-800" title={`Vence ${formatDay(c.first)}`}>{c.name}</Chip>
            ))}
            {next && <span className="text-gray-500">Siguiente: {formatDay(next)}</span>}
            <Button size="sm" className="ml-auto" onClick={() => onQuote()}>
              Cotizar servicio
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-gray-600">
            <ClientPhone parlor={parlor} onChanged={onChanged} />
            {!parlor.attended && <ProspectContact parlor={parlor} onChanged={onChanged} />}
          </div>
        </DialogHeader>
        <div className="rounded-lg border border-gray-200">
          <ClientDetail
            categories={categories}
            undated={parlor.parts.filter((r) => !isDated(r))}
            name={name}
            today={today}
            onChanged={onChanged}
            selection={selection}
          />
        </div>
        <SelectionBar parts={selected} onQuote={onQuote} onChanged={onChanged} onClear={selection.clear} />
      </DialogContent>
    </Dialog>
  );
}

// The quote picker's sections, most urgent first, in the agenda's colors (red: venció, green: por realizar); the
// ones not due yet start folded.
const URGENCY = {
  overdue: { name: "Vencidas", border: "border-red-400", text: "text-red-700", open: true },
  soon: { name: `Próximas (${SOON_DAYS} días)`, border: "border-green-500", text: "text-green-700", open: true },
  later: { name: "Más adelante", border: "border-slate-300", text: "text-slate-600", open: false },
  undated: { name: "Sin historial reciente", border: "border-gray-200", text: "text-gray-500", open: false },
};

// Picks the parts for a client's service quote (overdue and due within SOON_DAYS come checked; quantities can
// change) and sends them to Solicitudes as a request, where prices, approval and the client's link follow.
function QuoteDialog({
  parlor,
  plan,
  name,
  today,
  onClose,
  onCreated,
  preselect,
}: {
  parlor: PlanParlor;
  plan: ServicePlan;
  name: (code: string) => ReactNode;
  today: Date;
  onClose: () => void;
  onCreated: (id: number) => void;
  preselect?: ParlorPartRow[]; // opened from an agenda month: exactly these parts
}) {
  const soon = today.getTime() + SOON_DAYS * DAY_MS;
  // Opened from the agenda: the month's parts; else what's overdue or due soon, not already on an open quote.
  const [initial] = useState(() =>
    Object.fromEntries(
      (preselect ?? parlor.parts.filter((r) => isDated(r) && !r.quote && isoToDate(r.due!).getTime() <= soon))
        .filter((r) => plan.keys[r.code])
        .map((r) => [placeKey(r), String(r.quantity)]),
    ),
  );
  const [picked, setPicked] = useState<Record<string, string>>(initial);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // By urgency, each part labeled with its category; within a section, soonest first.
  const due = (r: ParlorPartRow) => isoToDate(r.due!).getTime();
  const byDue = (a: ParlorPartRow, b: ParlorPartRow) => due(a) - due(b) || a.group.localeCompare(b.group, "es");
  const dated = parlor.parts.filter(isDated);
  const groups = [
    { ...URGENCY.overdue, parts: dated.filter((r) => due(r) < today.getTime()).sort(byDue) },
    { ...URGENCY.soon, parts: dated.filter((r) => due(r) >= today.getTime() && due(r) <= soon).sort(byDue) },
    { ...URGENCY.later, parts: dated.filter((r) => due(r) > soon).sort(byDue) },
    { ...URGENCY.undated, parts: parlor.parts.filter((r) => !isDated(r)).sort((a, b) => a.group.localeCompare(b.group, "es")) },
  ].filter((g) => g.parts.length);
  const toggle = (rows: ParlorPartRow[], on: boolean) =>
    setPicked((p) => {
      const next = { ...p };
      for (const r of rows.filter((r) => plan.keys[r.code])) {
        if (on) next[placeKey(r)] ??= String(r.quantity);
        else delete next[placeKey(r)];
      }
      return next;
    });
  const chosen = Object.entries(picked).filter(([, q]) => Number(q) > 0);
  const codeOf = (place: string) => place.split("|")[0];
  const priced = chosen.filter(([place]) => plan.prices[codeOf(place)]);
  const total = priced.reduce((sum, [place, q]) => sum + plan.prices[codeOf(place)] * Number(q), 0);

  const send = async () => {
    setSending(true);
    setError(null);
    const r = await apiFetch(`/api/servicios/salas/${parlor.id}/cotizar/`, {
      method: "POST",
      body: JSON.stringify({
        items: chosen.map(([place, q]) => {
          const [code, group] = place.split("|");
          // When it was due: the quote shows it to staff and the client.
          const due = parlor.parts.find((r) => placeKey(r) === place)?.due ?? null;
          return { key: plan.keys[code], quantity: Number(q), code, group, due };
        }),
      }),
    }).catch(() => null);
    const body = r ? await r.json().catch(() => ({})) : {};
    if (r?.ok) return onCreated(body.id);
    setError(body.error ?? "No se pudo crear la solicitud.");
    setSending(false);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] max-w-3xl overflow-y-auto">
        <DialogHeader className="text-left">
          <DialogTitle>Cotizar servicio · {clientName(parlor)}</DialogTitle>
          <p className="text-sm text-gray-500">
            Marca las piezas que entran en la propuesta. Se crea una solicitud en Solicitudes para ponerle precios y
            enviarla al cliente.
          </p>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {groups.map((g) => {
            const all = g.parts.filter((r) => plan.keys[r.code]).every((r) => placeKey(r) in picked);
            return (
            <details key={g.name} open={g.open || g.parts.some((r) => placeKey(r) in initial)} className={cn("group/sec rounded-lg border-l-4 py-1 pl-3", g.border)}>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2">
                <span className={cn("flex items-center gap-1 text-xs font-semibold uppercase tracking-wide", g.text)}>
                  <ChevronRight className="h-4 w-4 transition-transform group-open/sec:rotate-90" />
                  {g.name} ({g.parts.length})
                  {g.parts.some((r) => placeKey(r) in picked) &&
                    ` · ${plural(g.parts.filter((r) => placeKey(r) in picked).length, "marcada", "marcadas")}`}
                </span>
                <button
                  type="button"
                  className="text-xs text-blue-600 hover:underline"
                  onClick={(e) => {
                    e.preventDefault(); // a click in the summary would also fold the section
                    toggle(g.parts, !all);
                  }}
                >
                  {all ? "Quitar todas" : "Marcar todas"}
                </button>
              </summary>
              <ul className="mt-1 flex flex-col">
                {g.parts.map((r) => {
                  const place = placeKey(r);
                  const on = place in picked;
                  const quotable = Boolean(plan.keys[r.code]);
                  return (
                    <li key={place} className="flex items-center gap-3 border-b border-gray-100 py-1.5 text-sm last:border-b-0">
                      <Checkbox
                        id={`q-${place}`}
                        checked={on}
                        disabled={!quotable}
                        onCheckedChange={(v) =>
                          setPicked((p) => {
                            const next = { ...p };
                            if (v) next[place] = String(r.quantity);
                            else delete next[place];
                            return next;
                          })
                        }
                      />
                      <label htmlFor={`q-${place}`} className={cn("min-w-0 flex-1", !quotable && "text-gray-400")}>
                        {name(r.code)} <QuoteChip quote={r.quote} />
                        <span className="block text-xs text-gray-400">
                          <span className="mr-1 rounded bg-gray-100 px-1.5 py-px text-gray-600">{r.group}</span>
                          {r.code}
                          {isDated(r) && (
                            <span className={cn("font-medium", g.text)}>
                              {" · "}
                              {isoToDate(r.due!) < today ? "venció" : "vence"} {formatDay(r.due)}
                            </span>
                          )}
                          {!quotable && " · no está en Contpaqi"}
                        </span>
                        {quotable && (
                          <span className="block text-xs text-gray-500">
                            {plan.prices[r.code] ? formatMoney(plan.prices[r.code]) : "sin precio"}
                            {" · "}
                            <span className={cn((plan.stock[r.code] ?? 0) < Number(picked[place] || r.quantity) && "font-medium text-red-700")}>
                              existencia {units(plan.stock[r.code] ?? 0)}
                            </span>
                          </span>
                        )}
                      </label>
                      <Input
                        type="number"
                        min={0}
                        step="any"
                        aria-label={`Cantidad de ${r.code} (${r.group})`}
                        value={picked[place] ?? ""}
                        disabled={!on}
                        onChange={(e) => setPicked((p) => ({ ...p, [place]: e.target.value }))}
                        className="h-8 w-20 text-right"
                      />
                    </li>
                  );
                })}
              </ul>
            </details>
            );
          })}
        </div>
        {error && <Notice tone="error" title={error} />}
        <div className="flex flex-wrap items-center justify-end gap-2">
          <span className="mr-auto text-sm text-gray-600">
            Precio de lista: <span className="font-semibold tabular-nums">{formatMoney(total)}</span>
            {priced.length < chosen.length && ` (${chosen.length - priced.length} sin precio)`}
          </span>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={send} disabled={sending || chosen.length === 0}>
            {sending ? "Creando…" : `Crear solicitud (${plural(chosen.length, "pieza", "piezas")})`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// The agenda's client order. Purchases: everything invoiced over the last 12 months (the clients differ hugely).
const overdueCount = (p: PlanParlor) => p.parts.filter((r) => r.status === "overdue").length;
const nextDue = (p: PlanParlor) => p.parts.filter(isDated).map((r) => r.due!).sort()[0] ?? "9999";
const SORTS = {
  ventas: { label: "Ordenar: compras de servicio (12 meses)", compare: (a: PlanParlor, b: PlanParlor) => b.sales_12m - a.sales_12m },
  vencidas: { label: "Ordenar: piezas vencidas", compare: (a: PlanParlor, b: PlanParlor) => overdueCount(b) - overdueCount(a) },
  proximo: { label: "Ordenar: próximo cambio", compare: (a: PlanParlor, b: PlanParlor) => nextDue(a).localeCompare(nextDue(b)) },
  nombre: { label: "Ordenar: nombre", compare: () => 0 },
};
type SortKey = keyof typeof SORTS;
const compactMoney = (n: number) =>
  n.toLocaleString("es-MX", { style: "currency", currency: "MXN", notation: "compact", maximumFractionDigits: 1 });

// Management's calendar sheet: a row per client, a column per month of the year, each cell the categories done
// (invoiced), missed or due that month. "Atrasado" (current year only) holds what came due before January and
// is still undone. A cell opens that month for that client in a dialog, with the client's full detail below.
type CellPart = { row: ParlorPartRow; date: string; invoice?: number | null; external?: number | null };
type Cell = Partial<Record<CellKind, Record<string, CellPart[]>>>; // kind -> category -> parts

function AgendaTab({
  plan,
  name,
  today,
  onChanged,
  onQuoted,
  onShowProspects,
}: {
  plan: ServicePlan;
  name: (code: string) => ReactNode;
  today: Date;
  onChanged: () => void;
  onQuoted: (id: number) => void;
  onShowProspects: () => void;
}) {
  const [year, setYear] = useState(today.getFullYear());
  const [query, setQuery] = useState("");
  const [only, setOnly] = useState(""); // one category, or all
  const [sort, setSort] = useState<SortKey>("ventas");
  const [approvedOnly, setApprovedOnly] = useState(false); // only clients with a quote they approved, not invoiced
  const [printMonth, setPrintMonth] = useState(today.getMonth() + 1);
  const [month, setMonth] = useState<{ parlor: PlanParlor; month: number; cell: Cell } | null>(null);
  // By id, so an open dialog shows the plan as reloaded after an edit.
  const [clientId, setClientId] = useState<number | null>(null);
  // The quote picker: for which client, and the parts picked in a dialog (else its default).
  const [quotingFor, setQuotingFor] = useState<{ id: number; parts?: ParlorPartRow[] } | null>(null);
  const client = plan.parlors.find((p) => p.id === clientId) ?? null;
  const quoting = plan.parlors.find((p) => p.id === quotingFor?.id) ?? null;
  const current = year === today.getFullYear();
  const rows = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return plan.parlors
      .filter((p) => words.every((w) => fold(`${clientName(p)} ${p.client}`).includes(w)))
      .filter((p) => !approvedOnly || p.accepted_quotes.length > 0)
      .sort((a, b) => SORTS[sort].compare(a, b) || clientName(a).localeCompare(clientName(b), "es"))
      .map((p) => {
        const cells: Record<number, Cell> = {}; // month 1-12; 0 = Atrasado
        const add = (month: number, kind: CellKind, row: ParlorPartRow, date: string, invoice?: number | null, external?: number | null) => {
          const byCat = ((cells[month] ??= {})[kind] ??= {});
          (byCat[row.group] ??= []).push({ row, date, invoice, external });
        };
        const parts = p.parts.filter((r) => isDated(r) && (!only || r.group === only));
        for (const r of parts) {
          // A part's open quote covers its next change: the first one missed or due after its last change.
          const quoted: CellKind | null = r.quote ? (r.quote.status === "aceptado" ? "accepted" : "quoted") : null;
          const next = r.events.find((e) => (e.kind === "missed" || e.kind === "due") && (!r.last_change || e.date > r.last_change));
          for (const e of r.events) {
            // A due date that was missed but replaced later only clutters the sheet: the change shows on its own.
            // (The events keep it for the on-time share, services.relevance.)
            if (e.kind === "missed" && r.events.some((d) => (d.kind === "done" || d.kind === "external") && d.date > e.date)) continue;
            const [y, m] = e.date.split("-").map(Number);
            if (y === year) add(m, quoted && e === next ? quoted : e.kind, r, e.date, e.invoice, e.external);
          }
          if (current && r.status === "overdue" && Number(r.due!.slice(0, 4)) < year) add(0, quoted ?? "missed", r, r.due!);
        }
        // With one category, only the clients that have it this year. A folded prospect (sent without its parts)
        // counts if it has any dated part.
        const active = p.folded ? p.next_due !== null : only ? Object.keys(cells).length > 0 : parts.length > 0;
        return { parlor: p, cells, active };
      })
      .filter((r) => r.active || query);
  }, [plan, query, year, current, only, sort, approvedOnly]);
  // Sales waiting: quotes clients approved that nobody has invoiced yet.
  const approvedCount = plan.parlors.reduce((n, p) => n + p.accepted_quotes.length, 0);
  // Clients our crew served this year; the rest (calendar clients we didn't serve, parts buyers who install them
  // themselves) are prospects, folded under the table so they don't bury the clients.
  // Filtered to approved quotes: prospects too, in the one table.
  const clients = approvedOnly ? rows : rows.filter((r) => r.parlor.attended);
  // The ones worth calling first: a part overdue lately or due soon, by date; then the rest, by date.
  const worthCalling = (p: PlanParlor) => {
    if (!p.next_due) return false;
    const days = (isoToDate(p.next_due).getTime() - today.getTime()) / DAY_MS;
    return days >= -PROSPECT_OVERDUE_DAYS && days <= SOON_DAYS;
  };
  const prospects = rows
    .filter((r) => !r.parlor.attended)
    .sort((a, b) => Number(worthCalling(b.parlor)) - Number(worthCalling(a.parlor)) || (a.parlor.next_due ?? "9").localeCompare(b.parlor.next_due ?? "9"));
  const callable = prospects.filter((r) => worthCalling(r.parlor)).length;
  // Categories any client has, in the page's order.
  const categories = useMemo(() => {
    const present = new Set(plan.parlors.flatMap((p) => p.parts.filter(isDated).map((r) => r.group)));
    return [...plan.categories.filter((c) => present.has(c)), ...[...present].filter((c) => !plan.categories.includes(c)).sort()];
  }, [plan]);
  const months = current ? [0, ...MONTHS.map((_, i) => i + 1)] : MONTHS.map((_, i) => i + 1);
  const thisMonth = today.getMonth() + 1;
  const table = (list: typeof rows) => (
      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white print:hidden">
        <table className="w-full min-w-[48rem] sm:min-w-[56rem] table-fixed border-collapse text-xs">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500">
              <th className="sticky left-0 w-32 bg-white px-3 py-2 text-left font-medium sm:w-44">Cliente</th>
              {months.map((m) => (
                <th
                  key={m}
                  className={cn("px-1 py-2 text-center font-medium", m === 0 && "w-16", current && m === thisMonth && "bg-blue-50 text-blue-800")}
                >
                  {m === 0 ? "Atrasado" : MONTHS[m - 1]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list.map(({ parlor: p, cells }) => (
              <tr key={p.id} className="border-b border-gray-100 last:border-b-0">
                <td className="sticky left-0 bg-white px-3 py-1.5" title={clientName(p)}>
                  <button
                    type="button"
                    onClick={() => setClientId(p.id)}
                    className="block max-w-full truncate text-left font-medium text-gray-900 hover:text-blue-700 hover:underline"
                  >
                    {clientName(p)}
                  </button>
                  <span className="block text-[11px] text-gray-400" title="Facturado en los últimos 12 meses en refacciones y servicio de la sala de ordeña (sin higiene, ventiladores, alimento ni otras líneas)">
                    {p.sales_12m ? `${compactMoney(p.sales_12m)} al año` : "sin servicio en 12 meses"}
                  </span>
                  {!p.attended && p.next_due && (
                    <span className={cn("block text-[11px]", worthCalling(p) ? "font-medium text-green-700" : "text-gray-400")}>
                      Próxima pieza: {formatDay(p.next_due)}
                    </span>
                  )}
                  {!p.attended && p.contacted_at && (
                    <span className="block text-[11px] text-violet-700">
                      Contactado {new Date(p.contacted_at).toLocaleDateString("es-MX", { day: "numeric", month: "short" })}
                    </span>
                  )}
                </td>
                {months.map((m) => {
                  const cell = cells[m];
                  return (
                    <td key={m} className={cn("px-1 py-1 align-top", current && m === thisMonth && "bg-blue-50/40")}>
                      {cell && (
                        <button
                          type="button"
                          onClick={() => setMonth({ parlor: p, month: m, cell })}
                          aria-label={`${clientName(p)}, ${m === 0 ? "atrasado" : MONTHS[m - 1]}`}
                          className="flex w-full flex-col gap-0.5 rounded hover:ring-2 hover:ring-blue-300"
                        >
                          {CELL_ORDER.map((k) => {
                            const byCat = cell[k];
                            if (!byCat) return null;
                            const cats = Object.keys(byCat);
                            return (
                              <span key={k} className={cn("truncate rounded px-1 py-0.5 text-center font-medium", KIND[k].className)}>
                                {SHORT[cats[0]] ?? cats[0]}
                                {cats.length > 1 && ` +${cats.length - 1}`}
                              </span>
                            );
                          })}
                        </button>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
  );

  return (
    <section className="flex flex-col gap-3">
      <MonthSheet rows={clients} year={year} month={printMonth} today={today} plan={plan} only={only} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 print:hidden">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="sm" aria-label="Año anterior" onClick={() => setYear((y) => y - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="w-14 text-center font-semibold tabular-nums">{year}</span>
          <Button variant="outline" size="sm" aria-label="Año siguiente" onClick={() => setYear((y) => y + 1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <Input
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            onShowProspects(); // a match may be a prospect
          }}
          placeholder="Buscar cliente o número"
          aria-label="Buscar cliente"
          className="w-full sm:w-64"
        />
        <select
          value={only}
          onChange={(e) => setOnly(e.target.value)}
          aria-label="Categoría"
          className="h-9 rounded-md border border-input bg-white px-2 text-sm"
        >
          <option value="">Todas las categorías</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          aria-label="Ordenar clientes"
          className="h-9 rounded-md border border-input bg-white px-2 text-sm"
        >
          {(Object.keys(SORTS) as SortKey[]).map((k) => (
            <option key={k} value={k}>{SORTS[k].label}</option>
          ))}
        </select>
        <span className="flex items-center gap-1">
          <select
            value={printMonth}
            onChange={(e) => setPrintMonth(Number(e.target.value))}
            aria-label="Mes a imprimir"
            className="h-9 rounded-md border border-input bg-white px-2 text-sm"
          >
            {MONTHS.map((m, i) => (
              <option key={m} value={i + 1}>{m} {year}</option>
            ))}
          </select>
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Printer className="h-4 w-4" />
            Imprimir mes
          </Button>
        </span>
        <span className="flex flex-wrap gap-1.5 text-xs">
          {CELL_ORDER.map((k) => (
            <Chip key={k} className={KIND[k].className}>{KIND[k].label}</Chip>
          ))}
        </span>
      </div>

      {approvedCount > 0 && (
        <button
          type="button"
          onClick={() => {
            if (!approvedOnly) onShowProspects(); // a prospect's approved parts come with its parts
            setApprovedOnly(!approvedOnly);
          }}
          className={cn(
            "self-start rounded-full px-3 py-1 text-sm font-medium print:hidden",
            approvedOnly ? "bg-gray-100 text-gray-700 hover:bg-gray-200" : "bg-green-600 text-white hover:bg-green-700",
          )}
        >
          {approvedOnly ? "Mostrar todos los clientes" : `${plural(approvedCount, "cotización aprobada", "cotizaciones aprobadas")} por facturar`}
        </button>
      )}
      {table(clients)}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500 print:hidden">
        <p>Haz clic en un cliente para ver todas sus piezas, o en una casilla para ver ese mes.</p>
      </div>
      {prospects.length > 0 && !approvedOnly && (
        // Open while searching, so a match among the prospects shows.
        <details
          key={query ? "search" : "folded"}
          open={!!query}
          onToggle={(e) => e.currentTarget.open && onShowProspects()}
          className="group print:hidden"
        >
          <summary className="cursor-pointer select-none text-sm font-medium text-gray-700">
            Prospectos ({prospects.length})
            {callable > 0 && (
              <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800">
                {plural(callable, "con pieza por cambiar", "con piezas por cambiar")} pronto
              </span>
            )}
            <span className="ml-2 text-xs font-normal text-gray-500">
              sin mano de obra nuestra en {today.getFullYear()}: compran refacciones o los atendimos antes
            </span>
          </summary>
          <div className="mt-2">{table(prospects)}</div>
        </details>
      )}

      {month && (
        <MonthDialog
          {...month}
          year={year}
          plan={plan}
          name={name}
          onClose={() => setMonth(null)}
          onChanged={onChanged}
          onQuote={(parts) => {
            setQuotingFor({ id: month.parlor.id, parts });
            setMonth(null);
          }}
          onClient={() => {
            setClientId(month.parlor.id);
            setMonth(null);
          }}
        />
      )}
      {client && (
        <ClientDialog
          parlor={client}
          plan={plan}
          name={name}
          today={today}
          onClose={() => setClientId(null)}
          onQuote={(parts) => {
            setQuotingFor({ id: client.id, parts });
            setClientId(null);
          }}
          onChanged={onChanged}
        />
      )}
      {quoting && (
        <QuoteDialog
          parlor={quoting}
          plan={plan}
          name={name}
          today={today}
          preselect={quotingFor?.parts}
          onClose={() => setQuotingFor(null)}
          onCreated={(id) => {
            setQuotingFor(null);
            onQuoted(id);
          }}
        />
      )}
    </section>
  );
}

// The crew's sheet for one month, printed (or saved as PDF) from the agenda: each client with something due or
// missed that month (plus what's overdue from before, for the current month), its parts and a box to tick.
function MonthSheet({
  rows,
  year,
  month,
  today,
  plan,
  only,
}: {
  rows: { parlor: PlanParlor; cells: Record<number, Cell> }[];
  year: number;
  month: number;
  today: Date;
  plan: ServicePlan;
  only: string;
}) {
  const withOverdue = year === today.getFullYear() && month === today.getMonth() + 1;
  const clients = rows
    .map(({ parlor, cells }) => {
      const parts = new Map<string, CellPart & { late: boolean }>();
      const take = (cell: Cell | undefined, late: boolean) =>
        PENDING.forEach((k) =>
          Object.values(cell?.[k] ?? {}).flat().forEach((c) => parts.set(placeKey(c.row), { ...c, late: late || k === "missed" || (k !== "due" && c.date < todayISO()) })),
        );
      if (withOverdue) take(cells[0], true);
      take(cells[month], false);
      return { parlor, parts: [...parts.values()].sort((a, b) => a.row.group.localeCompare(b.row.group, "es") || a.date.localeCompare(b.date)) };
    })
    .filter((c) => c.parts.length);
  return (
    <div className="hidden print:block">
      <h2 className="text-lg font-semibold">
        Servicios · <span className="capitalize">{formatMonth(`${year}-${String(month).padStart(2, "0")}`)}</span>
        {only && ` · ${only}`}
      </h2>
      <p className="mb-3 text-xs text-gray-500">
        {plural(clients.length, "cliente", "clientes")} · impreso el {formatDay(todayISO())}
      </p>
      {clients.length === 0 && <p className="text-sm">Nada vence este mes.</p>}
      {clients.map(({ parlor, parts }) => (
        <section key={parlor.id} className="pdf-keep mb-3">
          <p className="border-b border-gray-400 text-sm font-semibold">
            {clientName(parlor)} <span className="font-normal text-gray-500">{parlor.client}</span>
          </p>
          <table className="w-full text-xs">
            <tbody>
              {parts.map(({ row, date, late }) => (
                <tr key={placeKey(row)} className="border-b border-gray-200">
                  <td className="w-5 py-0.5">☐</td>
                  <td className="w-28 text-gray-500">{row.group}</td>
                  <td>{plan.names[row.code] ?? row.code} <span className="text-gray-500">{row.code}</span></td>
                  <td className="w-12 text-right tabular-nums">{units(row.quantity)}</td>
                  <td className="w-28 text-right">{late ? `venció ${formatDay(date)}` : formatDay(date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}

// One agenda cell: what was done, missed or due that month for that client, then the client's full detail.
function MonthDialog({
  parlor,
  month,
  cell,
  year,
  plan,
  name,
  onClose,
  onClient,
  onChanged,
  onQuote,
}: {
  parlor: PlanParlor;
  month: number;
  cell: Cell;
  year: number;
  plan: ServicePlan;
  name: (code: string) => ReactNode;
  onClose: () => void;
  onClient: () => void;
  onChanged: () => void;
  onQuote: (parts: ParlorPartRow[]) => void;
}) {
  // What's overdue or coming this month and not quoted yet starts selected: quoting it, or noting someone else did
  // it, is one click.
  const cellParts = (kinds: CellKind[]) => [
    ...new Map(kinds.flatMap((k) => Object.values(cell[k] ?? {}).flat()).map((c) => [placeKey(c.row), c.row])).values(),
  ];
  const selection = useSelection(cellParts(["missed", "due"]));
  const selected = cellParts(CELL_ORDER).filter(selection.has);
  // Categories and parts in the client's order of relevance, as in its full detail.
  const order = categoriesOf(parlor, plan.categories).map((c) => c.name);
  const rank = (c: string) => (order.includes(c) ? order.indexOf(c) : order.length);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] w-[calc(100%-2rem)] max-w-3xl overflow-y-auto">
        <DialogHeader className="text-left">
          <DialogTitle>
            <ClientLink clientId={parlor.client_id} label={clientName(parlor)} />
          </DialogTitle>
          <p className="text-sm text-gray-500">
            {month === 0 ? `Atrasado: venció antes de ${year}` : <span className="capitalize">{formatMonth(`${year}-${String(month).padStart(2, "0")}`)}</span>}
          </p>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {CELL_ORDER.map((k) => {
            const byCat = cell[k];
            if (!byCat) return null;
            return (
              <section key={k}>
                <div className="flex items-center gap-2">
                  <SelectBox rows={cellParts([k])} selection={selection} label={`Seleccionar: ${KIND[k].label}`} />
                  <Chip className={KIND[k].className}>{KIND[k].label}</Chip>
                </div>
                <div className="mt-2 flex flex-col gap-2">
                  {Object.keys(byCat)
                    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
                    .map((c) => (
                      <div key={c}>
                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{c}</p>
                        <ul className="mt-1 flex flex-col gap-1 text-sm">
                          {[...byCat[c]].sort((a, b) => b.row.score - a.row.score).map(({ row, date, invoice, external }) => (
                            <li key={`${row.code}-${date}`} className="flex flex-wrap items-center justify-between gap-x-3">
                              <span className="flex items-center gap-2">
                                <SelectBox rows={[row]} selection={selection} label={`Seleccionar ${row.code}`} />
                                <span>
                                {name(row.code)} <QuoteChip quote={row.quote} />
                                <span className="ml-2 text-xs text-gray-400">
                                  cant. {units(row.quantity)} · {row.code}
                                </span>
                                </span>
                              </span>
                              <span className="text-gray-600">
                                {invoice ? <InvoiceLink invoiceId={invoice} label={formatDay(date)} /> : formatDay(date)}
                                {external && (
                                  <button
                                    type="button"
                                    className="ml-2 text-xs text-gray-400 hover:text-red-700 hover:underline"
                                    onClick={async () => {
                                      if (!window.confirm("¿Quitar este cambio hecho por otro?")) return;
                                      if ((await apiFetch(`/api/servicios/externos/${external}/`, { method: "DELETE" })).ok) {
                                        onChanged();
                                        onClose(); // the month as shown no longer holds
                                      }
                                    }}
                                  >
                                    Deshacer
                                  </button>
                                )}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                </div>
              </section>
            );
          })}

          <Button variant="outline" className="self-start" onClick={onClient}>
            Ver todas las piezas del cliente
          </Button>
        </div>
        <SelectionBar
          parts={selected}
          onQuote={onQuote}
          onChanged={() => {
            onChanged();
            onClose(); // the month as shown no longer holds
          }}
          onClear={selection.clear}
        />
      </DialogContent>
    </Dialog>
  );
}

// The next GEA order, to copy into the order: what falls due before the following order lands, plus two months of
// counter sales, minus general-warehouse stock.
function OrderTab({ plan, name }: { plan: ServicePlan; name: (code: string) => ReactNode }) {
  const lines = useMemo(() => [...plan.order.lines].sort((a, b) => b.order - a.order), [plan]);
  return (
    <section>
      <h2 className="text-lg font-semibold text-gray-900">Pedido del {formatDayLong(plan.order.day)}</h2>
      <p className="mt-1 max-w-3xl text-sm text-gray-500">
        GEA recibe el pedido el primer miércoles del mes (por confirmar). Cubre lo que vence antes de que llegue el
        siguiente pedido, más dos meses de venta de mostrador, menos la existencia del almacén general.
      </p>
      <div className="mt-3 overflow-hidden rounded-lg border border-gray-200 bg-white">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pieza</TableHead>
              <TableHead className={cn(HIDE_BELOW_SM, "text-right")}>Para servicios</TableHead>
              <TableHead className={cn(HIDE_BELOW_MD, "text-right")}>Extra mostrador</TableHead>
              <TableHead className={cn(HIDE_BELOW_SM, "text-right whitespace-nowrap")}>Existencia</TableHead>
              <TableHead className="whitespace-nowrap text-right">Pedir</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {lines.length === 0 ? (
              <EmptyRow colSpan={5}>No hace falta pedir nada.</EmptyRow>
            ) : (
              lines.map((l) => (
                <TableRow key={l.code}>
                  <TableCell className="whitespace-normal">
                    <span className="font-medium text-gray-900">{name(l.code)}</span>
                    <span className="block text-xs text-gray-500">{l.code}</span>
                    <span className="block text-xs text-gray-500 sm:hidden">
                      Servicios {units(l.services)} · existencia {units(l.stock)}
                    </span>
                  </TableCell>
                  <TableCell className={cn(HIDE_BELOW_SM, "text-right tabular-nums")}>{units(l.services)}</TableCell>
                  <TableCell className={cn(HIDE_BELOW_MD, "text-right tabular-nums")}>{units(l.buffer)}</TableCell>
                  <TableCell className={cn(HIDE_BELOW_SM, "text-right tabular-nums", l.stock <= 0 && "text-red-700")}>{units(l.stock)}</TableCell>
                  <TableCell className="whitespace-nowrap text-right font-semibold tabular-nums">{units(l.order)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
