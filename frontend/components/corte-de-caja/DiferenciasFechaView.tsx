"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { endOfMonth } from "date-fns";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import InvoiceLink from "@/components/facturas/InvoiceLink";
import ClientLink from "@/components/facturas/ClientLink";
import { MonthControl } from "@/components/date-controls";
import { currentMonthISO, dateToISO, formatDay, isoToDate } from "@/lib/dates";
import { STATUS_INFO } from "@/components/corte-de-caja/date-difference-status";
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import type {
  DateDifferenceRow,
  DateDifferenceStatus,
  DateDifferencesSummary,
} from "@/types/corte-de-caja";

const STATUS_ORDER = Object.keys(STATUS_INFO) as DateDifferenceStatus[];
const PROBLEM_STATUSES: DateDifferenceStatus[] = [
  "distinto_mes",
  "folio_equivocado",
  "monto_distinto",
  "solo_comercial",
  "solo_contabilidad",
];

function currency(value: number) {
  return value.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 2,
  });
}

function monthKey(iso: string | null) {
  return iso ? iso.slice(0, 7) : null;
}

export default function DiferenciasFechaView() {
  const [month, setMonth] = useState(currentMonthISO);
  const [data, setData] = useState<DateDifferencesSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<Set<DateDifferenceStatus>>(
    new Set(PROBLEM_STATUSES),
  );
  const [filter, setFilter] = useState("");
  const requestIdRef = useRef(0);

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    const from = `${month}-01`;
    const to = dateToISO(endOfMonth(isoToDate(month)));
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    apiFetch(
      `/api/corte-de-caja/diferencias-fecha/?date_from=${from}&date_to=${to}`,
      { cache: "no-store" },
    )
      .then(async (res) => {
        if (!res.ok) throw new Error(`El servidor respondió ${res.status}`);
        const json = await res.json();
        if (requestId === requestIdRef.current) setData(json);
      })
      .catch((err) => {
        if (requestId === requestIdRef.current) {
          setError(
            err instanceof Error
              ? err.message
              : "No se pudo cargar la información",
          );
        }
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setLoading(false);
      });
  }, [month]);

  const toggleStatus = (status: DateDifferenceStatus) => {
    setStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  };

  const rows = useMemo(() => {
    const term = filter.trim().toLowerCase();
    return (data?.rows ?? []).filter(
      (r) =>
        statuses.has(r.status) &&
        (!term ||
          r.cliente.toLowerCase().includes(term) ||
          r.folio_display.toLowerCase().includes(term) ||
          r.cited_folio_display?.toLowerCase().includes(term)),
    );
  }, [data, statuses, filter]);

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-gray-500">
        Cada pago de cliente en Contpaqi Comercial junto a su póliza en
        Contabilidad. Los pagos registrados en un mes en Comercial y en otro en
        Contabilidad se declaran en periodos distintos; también se marcan las
        pólizas con otro importe o que citan un folio equivocado. Corríjalos en
        Contpaqi. Un pago aparece en el mes de cualquiera de sus dos fechas.
      </p>

      <div className="flex items-center gap-2">
        <MonthControl month={month} onChange={setMonth} />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
            {STATUS_ORDER.map((status) => {
              const info = STATUS_INFO[status];
              const active = statuses.has(status);
              return (
                <button
                  key={status}
                  type="button"
                  onClick={() => toggleStatus(status)}
                  aria-pressed={active}
                  title={info.description}
                  className={cn(
                    "rounded-lg border p-4 text-left transition-colors",
                    active
                      ? info.card
                      : "border-gray-200 bg-white opacity-60 hover:opacity-100",
                  )}
                >
                  <p className="text-sm text-gray-600">{info.label}</p>
                  <p className="text-lg font-semibold text-gray-900">
                    {data.totals[status].count}
                  </p>
                  <p className="text-xs text-gray-500">
                    {currency(data.totals[status].total_amount)}
                  </p>
                </button>
              );
            })}
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-gray-900">
                Pagos ({rows.length})
              </h2>
              <Input
                placeholder="Buscar cliente o folio..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="max-w-xs"
              />
            </div>
            <div className="overflow-x-auto rounded-lg border bg-white">
              <Table className="min-w-[1000px]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="whitespace-nowrap">Estado</TableHead>
                    <TableHead className="whitespace-nowrap">Factura</TableHead>
                    <TableHead className="whitespace-nowrap">Cliente</TableHead>
                    <TableHead className="text-right whitespace-nowrap">Monto</TableHead>
                    <TableHead className="whitespace-nowrap">Comercial</TableHead>
                    <TableHead className="whitespace-nowrap">Contabilidad</TableHead>
                    <TableHead className="text-right whitespace-nowrap">Diferencia</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={7}
                        className="py-8 text-center text-sm text-gray-500"
                      >
                        Sin pagos con los filtros seleccionados en este mes.
                      </TableCell>
                    </TableRow>
                  ) : (
                    rows.map((row) => (
                      <DifferenceRow key={rowKey(row)} row={row} />
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function rowKey(row: DateDifferenceRow) {
  return [
    row.invoice_id,
    ...row.comercial.map((c) => `c${c.date}${c.documento}${c.amount}`),
    ...row.contabilidad.map((l) => `l${l.date}${l.polizas.join()}${l.amount}`),
  ].join("|");
}

function DifferenceRow({ row }: { row: DateDifferenceRow }) {
  const info = STATUS_INFO[row.status];
  const comercialMonth = monthKey(row.comercial_date);
  const monthMismatch = row.status === "distinto_mes";

  return (
    <TableRow className="align-top">
      <TableCell className="whitespace-nowrap">
        <Badge variant="outline" className={info.badge}>
          {info.label}
        </Badge>
      </TableCell>
      <TableCell className="font-mono text-xs whitespace-nowrap">
        <InvoiceLink invoiceId={row.invoice_id} label={row.folio_display} />
      </TableCell>
      <TableCell className="max-w-56 truncate" title={row.cliente}>
        <ClientLink clientId={row.client_id} label={row.cliente} />
      </TableCell>
      <TableCell className="text-right font-mono text-xs whitespace-nowrap">
        {currency(row.amount)}
      </TableCell>
      <TableCell className="text-xs">
        {row.comercial.length === 0 ? (
          <span className="text-gray-400">Sin pago aplicado</span>
        ) : (
          row.comercial.map((c) => (
            <div
              key={`${c.date}${c.documento}${c.amount}`}
              className="whitespace-nowrap"
            >
              <span
                className={cn("font-medium", monthMismatch && "text-red-700")}
              >
                {formatDay(c.date)}
              </span>
              <span className="ml-1 text-gray-500">{c.documento}</span>
              {row.comercial.length > 1 && (
                <span className="ml-1 text-gray-500">{currency(c.amount)}</span>
              )}
              {c.applied_date !== c.date && (
                <span className="block text-gray-400">
                  aplicado a la factura el {formatDay(c.applied_date)}
                </span>
              )}
            </div>
          ))
        )}
      </TableCell>
      <TableCell className="text-xs">
        {row.contabilidad.length === 0 ? (
          <span className="text-gray-400">Sin póliza</span>
        ) : (
          row.contabilidad.map((l) => (
            <div
              key={`${l.date}${l.polizas.join()}${l.amount}`}
              className="whitespace-nowrap"
            >
              <span
                className={cn(
                  "font-medium",
                  monthMismatch &&
                    monthKey(l.date) !== comercialMonth &&
                    "text-red-700",
                )}
              >
                {formatDay(l.date)}
              </span>
              <span className="ml-1 text-gray-500">
                Póliza {l.polizas.join(", ")}
              </span>
              {row.cited_invoice_id && row.cited_folio_display && (
                <span className="block text-red-700">
                  cita la factura{" "}
                  <InvoiceLink
                    invoiceId={row.cited_invoice_id}
                    label={row.cited_folio_display}
                  />
                </span>
              )}
              {row.contabilidad.length > 1 && (
                <span className="ml-1 text-gray-500">{currency(l.amount)}</span>
              )}
            </div>
          ))
        )}
      </TableCell>
      <TableCell className="text-right text-xs whitespace-nowrap">
        {row.days_difference === null
          ? "-"
          : row.days_difference === 0
            ? "0 días"
            : `${row.days_difference > 0 ? "+" : ""}${row.days_difference} ${Math.abs(row.days_difference) === 1 ? "día" : "días"}`}
      </TableCell>
    </TableRow>
  );
}
