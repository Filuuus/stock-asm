"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Loader2 } from "lucide-react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { HIDE_BELOW_MD, HIDE_BELOW_SM } from "@/components/sortable-table";
import { MonthControl } from "@/components/date-controls";
import { formatMonth, isoToDate, monthToISO } from "@/lib/dates";
import { ZONE_LABELS, ZONE_ORDER } from "@/lib/zones";
import { cn, formatMoney } from "@/lib/utils";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import type { Zone } from "@/types/commissions";

interface MonthRow {
  month: string; // "YYYY-MM"
  ventas: number;
  devoluciones: number;
  costo: number;
  zonas: Record<Zone, number>;
}

interface SalesSummary {
  month: string;
  months: MonthRow[]; // January of last year through `month`
  brands: { brand: string; ytd: number; ytd_prev: number }[];
  cobrado: Partial<Record<Zone, number>>;
  cuentas_por_cobrar: { pendiente: number; dias_cobro: number | null };
}

const MONTH_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
// Categorical slots 1 and 2 of the dataviz palette (validated as a pair).
const COLOR_CURRENT = "#2a78d6";
const COLOR_PREVIOUS = "#eb6834";
const TOP_BRANDS = 8;

function lastCompleteMonth() {
  const d = new Date();
  return monthToISO(new Date(d.getFullYear(), d.getMonth() - 1, 1));
}

function sum(values: number[]) {
  return values.reduce((a, b) => a + b, 0);
}

// Relative change, or null when there's nothing to compare against.
function change(current: number, previous: number | undefined) {
  return previous ? (current - previous) / Math.abs(previous) : null;
}

function percent(value: number, digits = 1) {
  return `${(value * 100).toLocaleString("es-MX", { maximumFractionDigits: digits })}%`;
}

// "$4.2 M", "$850 k" - for axis ticks only; everything else is formatMoney.
function compactMoney(value: number) {
  return `$${value.toLocaleString("es-MX", { notation: "compact", maximumFractionDigits: 1 })}`;
}

function Delta({ value, label, unit = "%" }: { value: number | null; label: string; unit?: "%" | "pp" }) {
  if (value === null) return <p className="text-xs text-gray-400">sin dato {label}</p>;
  const up = value >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  const text =
    unit === "pp"
      ? `${up ? "+" : ""}${(value * 100).toLocaleString("es-MX", { maximumFractionDigits: 1 })} pts`
      : `${up ? "+" : ""}${percent(value)}`;
  return (
    <p className="flex items-center gap-1 text-xs text-gray-500">
      <span className={cn("inline-flex items-center font-medium", up ? "text-green-700" : "text-red-700")}>
        <Icon className="w-3.5 h-3.5" aria-hidden />
        {text}
      </span>
      {label}
    </p>
  );
}

function ChangeCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-gray-400">-</span>;
  return (
    <span className={cn("num", value >= 0 ? "text-green-700" : "text-red-700")}>
      {value >= 0 ? "+" : ""}
      {percent(value, 0)}
    </span>
  );
}

function Tile({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="p-4 space-y-1">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-lg sm:text-xl">{value}</CardTitle>
        {children}
      </CardHeader>
    </Card>
  );
}

export default function SalesBIView() {
  const { loading: authLoading, isManagement } = useAuth();
  const [month, setMonth] = useState(lastCompleteMonth);
  const [data, setData] = useState<SalesSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isManagement) return;
    let cancelled = false;
    // Standard fetch-on-change; `cancelled` drops a stale month's response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    apiFetch(`/api/analytics/sales/?month=${month}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("No se pudieron cargar las ventas.");
        const json = await res.json();
        if (!cancelled) setData(json);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [month, isManagement]);

  const view = useMemo(() => {
    if (!data) return null;
    const year = Number(data.month.slice(0, 4));
    const m = Number(data.month.slice(5, 7));
    const byMonth = new Map(data.months.map((r) => [r.month, r]));
    const key = (y: number, mm: number) => `${y}-${String(mm).padStart(2, "0")}`;
    const cur = byMonth.get(data.month)!;
    const prev = byMonth.get(monthToISO(new Date(year, m - 2, 1)));
    const lastYear = byMonth.get(key(year - 1, m));
    const thisYearRows = data.months.filter((r) => r.month.startsWith(`${year}-`));
    const lastYearRows = data.months.filter((r) => r.month.startsWith(`${year - 1}-`));
    const lastYearToDate = lastYearRows.filter((r) => Number(r.month.slice(5)) <= m);
    const margin = (r?: MonthRow) => (r && r.ventas ? (r.ventas - r.costo) / r.ventas : null);
    const zoneYtd = (rows: MonthRow[], z: Zone) => sum(rows.map((r) => r.zonas[z] ?? 0));

    const brandTotal = sum(data.brands.map((b) => b.ytd));
    const top = data.brands.slice(0, TOP_BRANDS);
    const rest = data.brands.slice(TOP_BRANDS);
    const brands = rest.length
      ? [...top, { brand: "Otras", ytd: sum(rest.map((b) => b.ytd)), ytd_prev: sum(rest.map((b) => b.ytd_prev)) }]
      : top;

    return {
      year,
      cur,
      prev,
      lastYear,
      ytd: sum(thisYearRows.map((r) => r.ventas)),
      ytdPrev: sum(lastYearToDate.map((r) => r.ventas)),
      avgLastYear: sum(lastYearRows.map((r) => r.ventas)) / 12,
      margin: margin(cur),
      marginLastYear: margin(lastYear),
      cobrado: sum(Object.values(data.cobrado).map(Number)),
      chart: MONTH_ABBR.map((label, i) => ({
        label,
        actual: byMonth.get(key(year, i + 1))?.ventas ?? null,
        anterior: byMonth.get(key(year - 1, i + 1))?.ventas ?? null,
      })),
      zones: ZONE_ORDER.map((z) => ({
        zone: z,
        ventas: cur.zonas[z] ?? 0,
        lastYear: lastYear?.zonas[z],
        ytd: zoneYtd(thisYearRows, z),
        ytdPrev: zoneYtd(lastYearToDate, z),
        cobrado: data.cobrado[z] ?? 0,
      })),
      brands,
      brandTotal,
    };
  }, [data]);

  if (!authLoading && !isManagement) {
    return (
      <main className="max-w-7xl mx-auto w-full p-4 sm:p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">No tiene permiso para ver el análisis de ventas.</p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  const monthName = formatMonth(month);
  const monthShort = MONTH_ABBR[isoToDate(month).getMonth()].toLowerCase();

  return (
    <main className="max-w-7xl mx-auto w-full p-4 sm:p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">Ventas</h1>
        <p className="text-sm text-gray-500">
          Facturas del mes sin IVA, con devoluciones y notas de crédito ya descontadas. Mismas facturas y
          zonas que Comisiones y Corte de Caja.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <MonthControl month={month} onChange={setMonth} />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      {view && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            <Tile label={`Ventas de ${monthName}`} value={formatMoney(view.cur.ventas)}>
              <Delta value={change(view.cur.ventas, view.lastYear?.ventas)} label={`vs ${monthShort} ${view.year - 1}`} />
              <Delta value={change(view.cur.ventas, view.prev?.ventas)} label="vs mes anterior" />
              <Delta value={change(view.cur.ventas, view.avgLastYear)} label={`vs promedio mensual ${view.year - 1}`} />
            </Tile>
            <Tile label={`Acumulado ene-${monthShort} ${view.year}`} value={formatMoney(view.ytd)}>
              <Delta value={change(view.ytd, view.ytdPrev)} label={`vs ene-${monthShort} ${view.year - 1}`} />
            </Tile>
            <Tile label="Margen bruto del mes" value={view.margin === null ? "-" : percent(view.margin)}>
              <Delta
                value={view.margin !== null && view.marginLastYear !== null ? view.margin - view.marginLastYear : null}
                label={`vs ${monthShort} ${view.year - 1}`}
                unit="pp"
              />
              <p className="text-xs text-gray-400">aproximado, con el costo registrado en el ERP</p>
            </Tile>
            <Tile label={`Cobrado en ${monthName}`} value={formatMoney(view.cobrado)}>
              <p className="text-xs text-gray-400">con IVA, igual que Corte de Caja</p>
            </Tile>
            <Tile label="Por cobrar hoy" value={formatMoney(data!.cuentas_por_cobrar.pendiente)}>
              <p className="text-xs text-gray-500">
                {data!.cuentas_por_cobrar.dias_cobro ?? "-"} días promedio de cobro
              </p>
              <p className="text-xs text-gray-400">con IVA, facturas de los últimos 12 meses</p>
            </Tile>
            <Tile label="Devoluciones y notas de crédito" value={formatMoney(view.cur.devoluciones)}>
              <p className="text-xs text-gray-400">del mes, ya descontadas de las ventas</p>
            </Tile>
          </div>

          <Card>
            <CardHeader className="p-4 pb-0">
              <CardTitle className="text-base">Ventas por mes</CardTitle>
              <CardDescription>
                {view.year} contra {view.year - 1}, sin IVA
              </CardDescription>
            </CardHeader>
            <div className="h-72 p-2 sm:p-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={view.chart} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid vertical={false} stroke="#e5e7eb" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#6b7280" }} />
                  <YAxis
                    tickFormatter={compactMoney}
                    tickLine={false}
                    axisLine={false}
                    width={56}
                    tick={{ fontSize: 12, fill: "#6b7280" }}
                  />
                  <Tooltip
                    formatter={(value, name) => [formatMoney(Number(value)), name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  />
                  <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    name={String(view.year - 1)}
                    dataKey="anterior"
                    stroke={COLOR_PREVIOUS}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    isAnimationActive={false}
                  />
                  <Line
                    name={String(view.year)}
                    dataKey="actual"
                    stroke={COLOR_CURRENT}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={{ r: 5 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-base">Por zona</CardTitle>
                <CardDescription>
                  {monthName} contra {monthShort} {view.year - 1}
                </CardDescription>
              </CardHeader>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Zona</TableHead>
                    <TableHead className="text-right">Ventas</TableHead>
                    <TableHead className="text-right">Cambio</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM)}>Acumulado</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_MD)}>Cobrado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {view.zones.map((z) => (
                    <TableRow key={z.zone}>
                      <TableCell>{ZONE_LABELS[z.zone]}</TableCell>
                      <TableCell className="text-right num">{formatMoney(z.ventas)}</TableCell>
                      <TableCell className="text-right">
                        <ChangeCell value={change(z.ventas, z.lastYear)} />
                      </TableCell>
                      <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>{formatMoney(z.ytd)}</TableCell>
                      <TableCell className={cn("text-right num", HIDE_BELOW_MD)}>{formatMoney(z.cobrado)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>

            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-base">Por marca</CardTitle>
                <CardDescription>
                  Acumulado ene-{monthShort} {view.year} contra el mismo periodo de {view.year - 1}
                </CardDescription>
              </CardHeader>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Marca</TableHead>
                    <TableHead className="text-right">Ventas</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM)}>% del total</TableHead>
                    <TableHead className="text-right">Cambio</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {view.brands.map((b) => (
                    <TableRow key={b.brand}>
                      <TableCell className="max-w-[7rem] sm:max-w-[14rem] truncate" title={b.brand}>
                        {b.brand}
                      </TableCell>
                      <TableCell className="text-right num">{formatMoney(b.ytd)}</TableCell>
                      <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                        {view.brandTotal ? percent(b.ytd / view.brandTotal) : "-"}
                      </TableCell>
                      <TableCell className="text-right">
                        <ChangeCell value={change(b.ytd, b.ytd_prev)} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </div>
        </>
      )}
    </main>
  );
}
