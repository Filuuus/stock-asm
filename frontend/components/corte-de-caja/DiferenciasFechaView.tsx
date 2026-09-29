"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { addMonths, endOfMonth, format, startOfMonth } from "date-fns";
import { es } from "date-fns/locale";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
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
import { cn } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import type {
  DateDifferenceRow,
  DateDifferenceStatus,
  DateDifferencesSummary,
} from "@/types/corte-de-caja";

const STATUS_INFO: Record<
  DateDifferenceStatus,
  { label: string; description: string; badge: string; card: string }
> = {
  distinto_mes: {
    label: "Distinto mes",
    description:
      "Comercial y Contabilidad registran el pago en meses diferentes.",
    badge: "bg-red-50 text-red-700 border-red-200",
    card: "border-red-300 bg-red-50",
  },
  solo_comercial: {
    label: "Solo en Comercial",
    description: "Pago en Comercial sin póliza en Contabilidad por ese monto.",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    card: "border-amber-300 bg-amber-50",
  },
  solo_contabilidad: {
    label: "Solo en Contabilidad",
    description: "Póliza sin pago aplicado en Comercial por ese monto.",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    card: "border-amber-300 bg-amber-50",
  },
  distinto_dia: {
    label: "Distinto día",
    description: "Mismo mes, distinto día.",
    badge: "bg-slate-50 text-slate-700 border-slate-200",
    card: "border-slate-300 bg-slate-50",
  },
  mismo_dia: {
    label: "Mismo día",
    description: "Ambas fechas coinciden.",
    badge: "bg-green-50 text-green-700 border-green-200",
    card: "border-green-300 bg-green-50",
  },
};

const STATUS_ORDER = Object.keys(STATUS_INFO) as DateDifferenceStatus[];
const PROBLEM_STATUSES: DateDifferenceStatus[] = [
  "distinto_mes",
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

// Built from parts, not parsed, for the same off-by-one-day reason as in
// CorteDeCajaView.
function isoToDate(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatDay(iso: string) {
  return format(isoToDate(iso), "d MMM yyyy", { locale: es });
}

function monthKey(iso: string | null) {
  return iso ? iso.slice(0, 7) : null;
}

export default function DiferenciasFechaView() {
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
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
    const from = format(month, "yyyy-MM-dd");
    const to = format(endOfMonth(month), "yyyy-MM-dd");
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
          r.folio_display.toLowerCase().includes(term)),
    );
  }, [data, statuses, filter]);

  const isCurrentMonth = startOfMonth(new Date()).getTime() === month.getTime();

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-gray-500">
        Cada pago de cliente con su fecha en Contpaqi Comercial junto a la fecha
        de su póliza en Contabilidad. Los pagos registrados en un mes en
        Comercial y en otro en Contabilidad se declaran en periodos distintos:
        corríjalos en Contpaqi. Un pago aparece en el mes de cualquiera de sus
        dos fechas.
      </p>

      <div className="flex items-center gap-2">
        <Button
          size="icon"
          variant="outline"
          onClick={() => setMonth((m) => addMonths(m, -1))}
          title="Mes anterior"
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <span className="w-40 text-center font-medium capitalize">
          {format(month, "MMMM yyyy", { locale: es })}
        </span>
        <Button
          size="icon"
          variant="outline"
          onClick={() => setMonth((m) => addMonths(m, 1))}
          disabled={isCurrentMonth}
          title="Mes siguiente"
        >
          <ChevronRight className="w-4 h-4" />
        </Button>
        {loading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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
        {row.folio_display}
      </TableCell>
      <TableCell className="max-w-56 truncate" title={row.cliente}>
        {row.cliente}
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
