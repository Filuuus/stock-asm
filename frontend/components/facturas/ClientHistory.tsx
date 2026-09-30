"use client";

import { useMemo, useState } from "react";
import { Check } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Notice } from "@/components/notice";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Field, Section, StatCard } from "@/components/facturas/InvoiceDetail";
import { HIDE_BELOW_LG, HIDE_BELOW_MD, HIDE_BELOW_SM, SortableHead, SortColumn, useSort, EmptyRow } from "@/components/sortable-table";
import { cn, formatMoney, plural } from "@/lib/utils";
import { formatDay } from "@/lib/dates";
import { zoneLabel } from "@/lib/zones";
import type { ClientHistory, ClientInvoice, ClientInvoiceStatus } from "@/types/facturas";

const STATUS_BADGE: Record<ClientInvoiceStatus, { label: string; className: string }> = {
  pagada: { label: "Pagada", className: "bg-green-50 text-green-700 border-green-200" },
  pendiente: { label: "Pendiente", className: "bg-amber-50 text-amber-700 border-amber-200" },
  vencida: { label: "Vencida", className: "bg-red-50 text-red-700 border-red-200" },
  cancelada: { label: "Cancelada", className: "bg-gray-50 text-gray-500 border-gray-200" },
};

type Filter = "todas" | "pendientes" | "vencidas" | "no_cuadran";

const FILTERS: { key: Filter; label: string; test: (r: ClientInvoice) => boolean }[] = [
  { key: "todas", label: "Todas", test: () => true },
  { key: "pendientes", label: "Pendientes", test: (r) => r.status === "pendiente" || r.status === "vencida" },
  { key: "vencidas", label: "Vencidas", test: (r) => r.status === "vencida" },
  { key: "no_cuadran", label: "No cuadran", test: (r) => !r.cuadra },
];

type SortKey =
  | "folio" | "fecha" | "vencimiento" | "total" | "pendiente" | "status" | "paid_date" | "days_late" | "cuadra";

// Most urgent first when sorting by status.
const STATUS_RANK: Record<ClientInvoiceStatus, number> = { vencida: 0, pendiente: 1, pagada: 2, cancelada: 3 };

const folioNumber = (r: ClientInvoice) => Number(r.folio_display.split(" ").pop());

const SORT_COLUMNS: Record<SortKey, SortColumn<ClientInvoice>> = {
  folio: { value: folioNumber, first: "desc" },
  fecha: { value: (r) => r.fecha, first: "desc" },
  vencimiento: { value: (r) => r.vencimiento, first: "desc" },
  total: { value: (r) => r.total, first: "desc" },
  pendiente: { value: (r) => r.pendiente, first: "desc" },
  status: { value: (r) => STATUS_RANK[r.status], first: "asc" },
  paid_date: { value: (r) => r.paid_date, first: "desc" },
  days_late: { value: (r) => r.days_late, first: "desc" },
  cuadra: { value: (r) => (r.cuadra ? 1 : 0), first: "asc" },
};

// Narrow screens keep folio, total and status; the row opens the full
// invoice for the rest.
const SORT_HEADERS: [SortKey, string, "right"?, string?][] = [
  ["folio", "Factura"],
  ["fecha", "Fecha", undefined, HIDE_BELOW_SM],
  ["vencimiento", "Vencimiento", undefined, HIDE_BELOW_MD],
  ["total", "Total", "right"],
  ["pendiente", "Pendiente", "right", HIDE_BELOW_SM],
  ["status", "Estado"],
  ["paid_date", "Pagada (póliza)", undefined, HIDE_BELOW_LG],
  ["days_late", "Atraso", "right", HIDE_BELOW_LG],
  ["cuadra", "Cuadre", undefined, HIDE_BELOW_LG],
];

const byNewest = (a: ClientInvoice, b: ClientInvoice) =>
  b.fecha.localeCompare(a.fecha) || folioNumber(b) - folioNumber(a);

export function ClientHistoryView({ history, onOpenInvoice, onShowFull }: {
  history: ClientHistory;
  onOpenInvoice: (invoiceId: number) => void;
  onShowFull: () => void;
}) {
  const { client, summary } = history;
  const [filter, setFilter] = useState<Filter>("todas");
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    const test = FILTERS.find((f) => f.key === filter)!.test;
    const term = search.trim().toLowerCase();
    return history.invoices.filter(
      (r) => test(r) && (!term || r.folio_display.toLowerCase().includes(term)),
    );
  }, [history, filter, search]);
  const { sorted, sortKey, sortDir, toggle } = useSort(rows, SORT_COLUMNS, { key: "fecha", dir: "desc" }, byNewest);

  return (
    <div className="flex flex-col gap-8">
      <div className="rounded-lg border bg-white p-5 flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-2xl font-bold text-gray-900">{client.cliente}</span>
          {!client.activo && (
            <Badge variant="outline" className="bg-gray-50 text-gray-600 border-gray-200">Inactivo</Badge>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
          <Field label="Cuenta" value={client.codigo} />
          <Field label="RFC" value={client.rfc && <span className="whitespace-nowrap">{client.rfc}</span>} />
          <Field label="Zona" value={zoneLabel(client.zona)} />
          <Field label="Días de crédito" value={client.dias_credito ? `${client.dias_credito} días` : "Contado"} />
          <Field label="Límite de crédito" value={client.limite_credito > 0 ? formatMoney(client.limite_credito) : "Sin límite"} />
          <Field label="Cliente desde" value={formatDay(client.alta)} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Saldo pendiente"
          value={formatMoney(summary.saldo_pendiente)}
          sub={plural(summary.facturas_pendientes, "factura", "facturas")}
        />
        <StatCard
          label="Vencido"
          value={formatMoney(summary.vencido)}
          sub={plural(summary.facturas_vencidas, "factura vencida", "facturas vencidas")}
          tone={summary.vencido > 0 ? "bad" : undefined}
        />
        <StatCard
          label={summary.since ? "Facturado, últimos 12 meses" : "Facturado, todo el historial"}
          value={formatMoney(summary.facturado)}
          sub={plural(summary.facturas, "factura", "facturas")}
        />
        <StatCard
          label="Pagadas a tiempo"
          value={
            summary.pagadas_con_fecha
              ? `${summary.pagadas_a_tiempo} de ${summary.pagadas_con_fecha}`
              : "-"
          }
          sub={
            summary.promedio_dias_atraso !== null
              ? `Atraso promedio ${summary.promedio_dias_atraso} días (fecha de póliza vs vencimiento)`
              : undefined
          }
        />
      </div>

      {summary.no_cuadran > 0 && (
        <Notice
          tone="warning"
          title={`${plural(summary.no_cuadran, "factura no cuadra", "facturas no cuadran")} entre Comercial y Contabilidad`}
          summary="Abra cada una para ver qué corregir en Contpaqi."
          action={
            <Button size="sm" variant="outline" className="h-7 bg-white text-xs" onClick={() => setFilter("no_cuadran")}>
              Ver solo esas facturas
            </Button>
          }
        />
      )}

      <Section title="Facturas" count={rows.length}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Tabs value={filter} onValueChange={(v) => setFilter(v as Filter)} className="max-w-full overflow-x-auto">
            <TabsList>
              {FILTERS.map((f) => (
                <TabsTrigger key={f.key} value={f.key}>
                  {f.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Input
            placeholder="Buscar folio..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-white sm:w-48"
          />
        </div>
        <div className="overflow-x-auto rounded-lg border bg-white">
          <Table className="[&_td]:px-2 [&_th]:px-2 lg:[&_td]:px-3 lg:[&_th]:px-3">
            <TableHeader>
              <TableRow>
                {SORT_HEADERS.map(([key, label, align, className]) => (
                  <SortableHead
                    key={key}
                    label={label}
                    column={key}
                    sortKey={sortKey}
                    sortDir={sortDir}
                    onSort={toggle}
                    align={align}
                    className={className}
                  />
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 ? (
                <EmptyRow colSpan={9}>Sin facturas que mostrar.</EmptyRow>
              ) : (
                sorted.map((r) => <ClientInvoiceRow key={r.invoice_id} row={r} onOpen={onOpenInvoice} />)
              )}
            </TableBody>
          </Table>
        </div>
        {summary.since && (
          <p className="text-xs text-gray-500">
            Facturas desde el {formatDay(summary.since)}, más todas las que siguen pendientes.{" "}
            <button type="button" onClick={onShowFull} className="font-medium text-slate-700 underline">
              Ver todo el historial
            </button>
          </p>
        )}
      </Section>
    </div>
  );
}

function PaidCell({ row }: { row: ClientInvoice }) {
  if (row.paid_date) return <>{formatDay(row.paid_date)}</>;
  if (row.status !== "pagada") return <span className="text-gray-400">-</span>;
  if (row.comercial_cash < 1) return <span className="text-gray-500">Nota de crédito</span>;
  return <span className="text-amber-700">Sin póliza completa</span>;
}

function LateCell({ row }: { row: ClientInvoice }) {
  if (row.days_late === null) return <span className="text-gray-400">-</span>;
  if (row.days_late <= 0) {
    return <span className="text-green-700">{row.status === "vencida" ? "-" : "A tiempo"}</span>;
  }
  return (
    <span className="text-red-700">
      {row.days_late} {row.days_late === 1 ? "día" : "días"}
      {row.status === "vencida" && " (sigue)"}
    </span>
  );
}

function ClientInvoiceRow({ row, onOpen }: { row: ClientInvoice; onOpen: (id: number) => void }) {
  const badge = STATUS_BADGE[row.status];
  return (
    <TableRow
      onClick={() => onOpen(row.invoice_id)}
      className={cn("cursor-pointer hover:bg-slate-50", row.status === "cancelada" && "text-gray-400")}
    >
      <TableCell className="num underline decoration-gray-300 underline-offset-2">
        {row.folio_display}
      </TableCell>
      <TableCell className={cn("whitespace-nowrap", HIDE_BELOW_SM)}>{formatDay(row.fecha)}</TableCell>
      <TableCell className={cn("whitespace-nowrap", HIDE_BELOW_MD)}>{formatDay(row.vencimiento)}</TableCell>
      <TableCell className="text-right num">{formatMoney(row.total)}</TableCell>
      <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>{row.pendiente >= 1 ? formatMoney(row.pendiente) : "-"}</TableCell>
      <TableCell className="whitespace-nowrap">
        <Badge variant="outline" className={badge.className}>{badge.label}</Badge>
      </TableCell>
      <TableCell className={cn("whitespace-nowrap", HIDE_BELOW_LG)}><PaidCell row={row} /></TableCell>
      <TableCell className={cn("whitespace-nowrap text-right", HIDE_BELOW_LG)}><LateCell row={row} /></TableCell>
      <TableCell className={HIDE_BELOW_LG}>
        {row.cuadra ? (
          <Check className="w-4 h-4 text-green-600" />
        ) : (
          <span className="text-amber-700">No cuadra</span>
        )}
      </TableCell>
    </TableRow>
  );
}
