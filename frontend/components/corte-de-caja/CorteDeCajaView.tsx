"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { addDays, format, isSameDay } from "date-fns";
import { es } from "date-fns/locale";
import type { DateRange } from "react-day-picker";
import {
  AlertTriangle,
  Ban,
  Calendar as CalendarIcon,
  Check,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  Info,
  Loader2,
  Pencil,
  RotateCcw,
  X,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { useAuth } from "@/hooks/use-auth";
import { Zone } from "@/types/commissions";
import { CorteDeCajaRow, CorteDeCajaSummary, PaymentMethod } from "@/types/corte-de-caja";

// Deliberately not date-fns's parseISO here - for a plain "YYYY-MM-DD"
// calendar date (no time/timezone meaning at all) it's safer to build the
// Date from its parts directly than to trust a library's date-only parsing
// behavior, which has actually changed between date-fns major versions and
// caused a real off-by-one-day display bug here (a date stored as the 24th
// rendering as "23 sep").
function isoToDate(iso: string) {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function dateToISO(date: Date) {
  return format(date, "yyyy-MM-dd");
}

function formatShort(iso: string) {
  return format(isoToDate(iso), "d MMM yyyy", { locale: es });
}

// A single trigger that opens a range-capable calendar (pick one day, or
// drag/click a start and end) - replaces two separate <input type="date">
// fields, which needed two round trips to change one day.
function DateRangeControl({
  dateFrom,
  dateTo,
  onChange,
}: {
  dateFrom: string;
  dateTo: string;
  onChange: (from: string, to: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<DateRange | undefined>({
    from: isoToDate(dateFrom),
    to: isoToDate(dateTo),
  });

  const handleOpenChange = (next: boolean) => {
    if (next) {
      setPending({ from: isoToDate(dateFrom), to: isoToDate(dateTo) });
    }
    setOpen(next);
  };

  const applyPreset = (from: Date, to: Date) => {
    onChange(dateToISO(from), dateToISO(to));
    setOpen(false);
  };

  const handleApply = () => {
    if (!pending?.from) return;
    applyPreset(pending.from, pending.to ?? pending.from);
  };

  const label = isSameDay(isoToDate(dateFrom), isoToDate(dateTo))
    ? formatShort(dateFrom)
    : `${formatShort(dateFrom)} – ${formatShort(dateTo)}`;

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-56 justify-start gap-2 font-normal">
          <CalendarIcon className="w-4 h-4 text-gray-400" />
          {label}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-3" align="start">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={() => applyPreset(new Date(), new Date())}>
              Hoy
            </Button>
            <Button size="sm" variant="outline" onClick={() => applyPreset(addDays(new Date(), -1), addDays(new Date(), -1))}>
              Ayer
            </Button>
          </div>
          <Calendar
            mode="range"
            selected={pending}
            onSelect={setPending}
            defaultMonth={pending?.to ?? pending?.from}
            numberOfMonths={2}
            locale={es}
          />
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500">
              {pending?.from ? formatShort(dateToISO(pending.from)) : "Seleccione una fecha"}
              {pending?.to && !isSameDay(pending.from!, pending.to) ? ` – ${formatShort(dateToISO(pending.to))}` : ""}
            </p>
            <Button size="sm" onClick={handleApply} disabled={!pending?.from}>
              Aplicar
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

const ZONE_LABELS: Record<Zone, string> = {
  ZONA1: "Zona 1 (Juan Jose Franco)",
  ZONA2: "Zona 2 (Jesus Mendez)",
  OFICINA: "Oficina",
  SERVICIOS: "Servicios",
  PUNTOVENTA: "Punto de Venta",
};

const CATEGORY_LABELS: Record<string, string> = {
  R: "Refacciones",
  R_NW: "Refacciones (Tapetes y pernos)",
  R_CHEM: "Refacciones (Químicos)",
  R_FAN: "Refacciones (Ventiladores)",
  B: "Bionat",
  S: "Servicios",
};

const METHOD_LABELS: Record<PaymentMethod, string> = {
  EFECTIVO: "Efectivo",
  TERMINAL: "Terminal",
  CHEQUE: "Cheque",
  TRANSFERENCIA: "Transferencia",
};

function currency(value: number) {
  return value.toLocaleString("es-MX", {
    style: "currency",
    currency: "MXN",
    maximumFractionDigits: 2,
  });
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function CorteDeCajaView() {
  const { loading: authLoading, isAccounting, isManagement } = useAuth();
  const canUse = isAccounting || isManagement;

  const [dateFrom, setDateFrom] = useState(todayISO());
  const [dateTo, setDateTo] = useState(todayISO());
  const [data, setData] = useState<CorteDeCajaSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null);

  const [editingRow, setEditingRow] = useState<CorteDeCajaRow | null>(null);
  const [editNote, setEditNote] = useState("");
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const requestIdRef = useRef(0);

  const fetchSummary = async (from: string, to: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(from) || !/^\d{4}-\d{2}-\d{2}$/.test(to)) return;

    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/corte-de-caja/summary/?date_from=${from}&date_to=${to}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error(`El servidor respondió ${res.status}`);
      const json = await res.json();
      if (requestId !== requestIdRef.current) return;
      setData(json);
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : "No se pudo cargar la información");
    } finally {
      if (requestId === requestIdRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!canUse) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSummary(dateFrom, dateTo);
    // Intentionally run once auth resolves - handleDateChange covers refetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canUse]);

  const handleDateChange = (from: string, to: string) => {
    setDateFrom(from);
    setDateTo(to);
    fetchSummary(from, to);
  };

  // Shifts the whole [dateFrom, dateTo] window by one day, preserving its
  // span - so this also works sensibly when a multi-day range is selected,
  // not just a single day.
  const handleShiftDays = (delta: number) => {
    const from = dateToISO(addDays(isoToDate(dateFrom), delta));
    const to = dateToISO(addDays(isoToDate(dateTo), delta));
    handleDateChange(from, to);
  };

  const handleZoneClick = (zone: Zone) => {
    setSelectedZone((prev) => (prev === zone ? null : zone));
  };

  const patchAdjustment = async (row: CorteDeCajaRow, body: Record<string, unknown>) => {
    const res = await apiFetch("/api/corte-de-caja/adjustments/", {
      method: "POST",
      body: JSON.stringify({ invoice_id: row.invoice_id, event_date: row.event_date, ...body }),
    });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error ?? "No se pudo guardar el ajuste.");
    return json;
  };

  const handleMethodChange = async (row: CorteDeCajaRow, method: string) => {
    try {
      await patchAdjustment(row, { payment_method: method });
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la forma de pago.");
    }
  };

  const handleToggleReviewed = async (row: CorteDeCajaRow) => {
    try {
      await patchAdjustment(row, { reviewed: !row.reviewed });
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la factura.");
    }
  };

  const handleToggleExclude = async (row: CorteDeCajaRow) => {
    try {
      await patchAdjustment(row, { excluded: !row.excluded });
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo actualizar la factura.");
    }
  };

  const openEditDialog = (row: CorteDeCajaRow) => {
    setEditingRow(row);
    setEditNote(row.note);
    setEditError(null);
  };

  const handleSubmitEdit = async () => {
    if (!editingRow) return;
    setEditSubmitting(true);
    setEditError(null);
    try {
      await patchAdjustment(editingRow, { note: editNote });
      setEditingRow(null);
      fetchSummary(dateFrom, dateTo);
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "No se pudo guardar el ajuste.");
    } finally {
      setEditSubmitting(false);
    }
  };

  const rows = useMemo(() => {
    if (!data) return [];
    let filtered = data.rows;
    if (selectedZone) filtered = filtered.filter((r) => r.zone === selectedZone);
    const q = filter.trim().toLowerCase();
    if (!q) return filtered;
    return filtered.filter((r) => `${r.cliente} ${r.folio}`.toLowerCase().includes(q));
  }, [data, filter, selectedZone]);

  if (!authLoading && !canUse) {
    return (
      <main className="max-w-7xl mx-auto w-full p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">
            {authLoading ? "" : "No tiene permiso para ver el Corte de Caja."}
          </p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="w-full p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">Corte de Caja</h1>
        <p className="text-sm text-gray-500">
          Cobranza diaria calculada automáticamente desde el ERP - un renglón por cada
          pago identificado (incluye abonos parciales). La forma de pago se sugiere según
          el banco que recibió el dinero - confirme o corrija cada una.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="icon"
          variant="outline"
          onClick={() => handleShiftDays(-1)}
          title="Día anterior"
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>
        <DateRangeControl dateFrom={dateFrom} dateTo={dateTo} onChange={handleDateChange} />
        <Button
          size="icon"
          variant="outline"
          onClick={() => handleShiftDays(1)}
          title="Día siguiente"
        >
          <ChevronRight className="w-4 h-4" />
        </Button>
        {(loading || authLoading) && (
          <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
        )}
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {data && !error && (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Card className="border-slate-900">
              <CardHeader className="p-4">
                <CardDescription>TOTAL CORTE</CardDescription>
                <CardTitle className="text-xl">{currency(data.cash_drawer_total)}</CardTitle>
                <p className="text-xs text-gray-400">efectivo + terminal + cheque</p>
              </CardHeader>
            </Card>
            {(["EFECTIVO", "TERMINAL", "CHEQUE", "TRANSFERENCIA"] as PaymentMethod[]).map((method) => (
              <Card key={method}>
                <CardHeader className="p-4">
                  <CardDescription>{METHOD_LABELS[method]}</CardDescription>
                  <CardTitle className="text-xl">{currency(data.method_totals[method] ?? 0)}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {(Object.keys(ZONE_LABELS) as Zone[]).map((zone) => (
              <Card
                key={zone}
                onClick={() => handleZoneClick(zone)}
                className={cn(
                  "cursor-pointer transition-colors hover:border-gray-400",
                  selectedZone === zone && "border-slate-900 ring-1 ring-slate-900",
                )}
              >
                <CardHeader className="p-4">
                  <CardDescription>{ZONE_LABELS[zone]}</CardDescription>
                  <CardTitle className="text-lg">{currency(data.zone_totals[zone] ?? 0)}</CardTitle>
                </CardHeader>
              </Card>
            ))}
          </div>

          {data.unclassified.count > 0 && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">
                  {data.unclassified.count} pagos sin forma de pago asignada (
                  {currency(data.unclassified.total_amount)})
                </p>
                <p className="text-amber-700">{data.unclassified.note}</p>
              </div>
            </div>
          )}

          {data.unconfirmed.count > 0 && (
            <div className="flex items-start gap-3 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
              <Info className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">
                  {data.unconfirmed.count} pagos con forma de pago sugerida sin confirmar (
                  {currency(data.unconfirmed.total_amount)})
                </p>
                <p className="text-sky-700">{data.unconfirmed.note}</p>
              </div>
            </div>
          )}

          {data.approximate.count > 0 && (
            <div className="flex items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <Info className="w-5 h-5 shrink-0 mt-0.5" />
              <div>
                <p className="font-medium">{data.approximate.count} pagos con monto aproximado</p>
                <p className="text-slate-600">{data.approximate.note}</p>
              </div>
            </div>
          )}

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold text-gray-900">Pagos ({rows.length})</h2>
                {selectedZone && (
                  <button
                    onClick={() => setSelectedZone(null)}
                    className="flex items-center gap-1 rounded-full bg-slate-900 px-2.5 py-1 text-xs font-medium text-white hover:bg-slate-700"
                  >
                    {ZONE_LABELS[selectedZone]}
                    <X className="w-3 h-3" />
                  </button>
                )}
              </div>
              <Input
                placeholder="Buscar cliente o folio..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-72"
              />
            </div>

            <div className="rounded-lg border bg-white overflow-x-auto">
              <Table className="min-w-[1550px]">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead className="whitespace-nowrap">Fecha</TableHead>
                    <TableHead className="whitespace-nowrap">Folio</TableHead>
                    <TableHead className="whitespace-nowrap">Cliente</TableHead>
                    <TableHead className="whitespace-nowrap">Zona</TableHead>
                    <TableHead className="whitespace-nowrap">Categoría</TableHead>
                    <TableHead className="whitespace-nowrap text-right">Monto</TableHead>
                    <TableHead className="whitespace-nowrap">Tipo</TableHead>
                    <TableHead className="whitespace-nowrap">Banco</TableHead>
                    <TableHead className="whitespace-nowrap">Forma de pago</TableHead>
                    <TableHead className="whitespace-nowrap w-40">Nota</TableHead>
                    <TableHead className="w-24" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow
                      key={`${row.invoice_id}-${row.event_date}`}
                      className={cn(row.excluded && "opacity-50")}
                    >
                      <TableCell>
                        <Checkbox
                          checked={row.reviewed}
                          onCheckedChange={() => handleToggleReviewed(row)}
                          title={row.reviewed ? `Revisado por ${row.reviewed_by ?? "?"}` : "Marcar como revisado"}
                        />
                      </TableCell>
                      <TableCell className="text-xs text-gray-600 whitespace-nowrap">{row.event_date}</TableCell>
                      <TableCell className={cn("font-mono text-xs whitespace-nowrap", row.excluded && "line-through")}>
                        {row.folio}
                      </TableCell>
                      <TableCell className={cn("max-w-48 truncate", row.excluded && "line-through")}>
                        {row.cliente}
                      </TableCell>
                      <TableCell className="text-xs text-gray-600 whitespace-nowrap">
                        {ZONE_LABELS[row.zone] ?? row.zone}
                      </TableCell>
                      <TableCell className="text-xs text-gray-600 whitespace-nowrap">
                        {row.category ? (CATEGORY_LABELS[row.category] ?? row.category) : "-"}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs whitespace-nowrap">
                        {currency(row.amount)}
                        {row.approximate && (
                          <HelpCircle
                            className="inline w-3 h-3 ml-1 text-amber-500"
                            aria-label="Monto aproximado, revisar"
                          />
                        )}
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {row.abono === null ? (
                          <span className="text-xs text-gray-400">?</span>
                        ) : row.abono ? (
                          <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                            Abono
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                            Completo
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-gray-600 max-w-32 truncate" title={row.bank ?? undefined}>
                        {row.bank ?? "-"}
                      </TableCell>
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center gap-1">
                          <select
                            value={row.payment_method}
                            onChange={(e) => handleMethodChange(row, e.target.value)}
                            className={cn(
                              "h-8 rounded-md border px-2 text-xs",
                              row.payment_method_confirmed
                                ? "border-input bg-background"
                                : "border-sky-300 bg-sky-50",
                            )}
                            title={
                              row.payment_method && !row.payment_method_confirmed
                                ? "Sugerido automáticamente según el banco - sin confirmar"
                                : undefined
                            }
                          >
                            <option value="">Sin clasificar</option>
                            {(Object.keys(METHOD_LABELS) as PaymentMethod[]).map((m) => (
                              <option key={m} value={m}>
                                {METHOD_LABELS[m]}
                              </option>
                            ))}
                          </select>
                          {row.payment_method && !row.payment_method_confirmed && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="px-1.5 h-8"
                              title="Confirmar sugerencia"
                              onClick={() => handleMethodChange(row, row.payment_method)}
                            >
                              <Check className="w-3.5 h-3.5 text-sky-600" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="max-w-40 truncate text-xs text-gray-600">{row.note}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <Button size="sm" variant="ghost" className="px-2" onClick={() => openEditDialog(row)}>
                            <Pencil className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="px-2"
                            onClick={() => handleToggleExclude(row)}
                            title={row.excluded ? "Restaurar pago" : "Excluir pago"}
                          >
                            {row.excluded ? <RotateCcw className="w-3.5 h-3.5" /> : <Ban className="w-3.5 h-3.5" />}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {rows.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={12} className="text-center text-sm text-gray-500 py-8">
                        Sin resultados para este período.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}

      <Dialog open={editingRow !== null} onOpenChange={(open) => !open && setEditingRow(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              Nota - factura {editingRow?.folio} ({editingRow?.event_date}) - {editingRow?.cliente}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="edit-note">Observaciones</Label>
              <Textarea id="edit-note" value={editNote} onChange={(e) => setEditNote(e.target.value)} rows={3} />
            </div>
            {editError && <p className="text-sm text-red-600">{editError}</p>}
            <Button onClick={handleSubmitEdit} disabled={editSubmitting}>
              {editSubmitting ? "Guardando..." : "Guardar"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
