"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { ArrowDownRight, ArrowUpRight, CircleAlert, CircleCheck, Loader2 } from "lucide-react";
import {
  Bar,
  BarChart,
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

// Operating results from Contabilidad, by posting month.
interface ResultsRow {
  month: string;
  ingresos: number;
  costo: number;
  financieros: number;
  utilidad_operativa: number;
  gastos: Record<string, number>; // category -> amount
}

// Her financial model's INDICADORES, per month. Absent when not posted yet.
type IndicatorKey =
  | "margen_bruto" | "margen_operativo" | "margen_neto" | "gasto_operativo_ingresos" | "saldo_caja"
  | "razon_circulante" | "prueba_acida" | "dias_cxc" | "dias_inventario" | "dias_cxp" | "ciclo_efectivo"
  | "endeudamiento" | "roa_ytd" | "roe_ytd" | "pe_operativo_ytd" | "pe_financiero_ytd" | "cobertura_pef";
type IndicatorRow = { month: string; posted: boolean } & Partial<Record<IndicatorKey, number | null>>;

interface SalesSummary {
  month: string;
  months: MonthRow[]; // January of last year through `month`
  brands: { brand: string; ytd: number; ytd_prev: number }[];
  cobrado: Partial<Record<Zone, number>>;
  cuentas_por_cobrar: { pendiente: number; dias_cobro: number | null };
  resultados: ResultsRow[]; // same months as `months`
  indicadores: IndicatorRow[]; // same months as `months`
}

const MONTH_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
// Categorical slots 1 and 2 of the dataviz palette (validated as a pair).
const COLOR_CURRENT = "#2a78d6";
const COLOR_PREVIOUS = "#eb6834";
const TOP_BRANDS = 8;
type Unit = "%" | "x" | "dias" | "$";
// Rows of her INDICADORES sheet that we can compute, in her order.
const INDICATORS: { key: IndicatorKey; label: string; unit: Unit; group?: string }[] = [
  { group: "Rentabilidad", key: "margen_bruto", label: "Margen bruto", unit: "%" },
  { key: "margen_operativo", label: "Margen operativo", unit: "%" },
  { key: "margen_neto", label: "Margen neto (antes de impuestos)", unit: "%" },
  { key: "gasto_operativo_ingresos", label: "Gasto operativo / ingresos", unit: "%" },
  { group: "Liquidez", key: "saldo_caja", label: "Caja y bancos al cierre", unit: "$" },
  { key: "razon_circulante", label: "Razón circulante", unit: "x" },
  { key: "prueba_acida", label: "Prueba ácida", unit: "x" },
  { group: "Ciclo de efectivo", key: "dias_cxc", label: "Días de cuentas por cobrar", unit: "dias" },
  { key: "dias_inventario", label: "Días de inventario", unit: "dias" },
  { key: "dias_cxp", label: "Días de cuentas por pagar", unit: "dias" },
  { key: "ciclo_efectivo", label: "Ciclo de conversión de efectivo", unit: "dias" },
  { group: "Endeudamiento y retorno", key: "endeudamiento", label: "Nivel de endeudamiento", unit: "%" },
  { key: "roa_ytd", label: "ROA acumulado", unit: "%" },
  { key: "roe_ytd", label: "ROE acumulado", unit: "%" },
  { group: "Punto de equilibrio", key: "pe_operativo_ytd", label: "Punto de equilibrio operativo (acum.)", unit: "$" },
  { key: "pe_financiero_ytd", label: "Punto de equilibrio financiero (acum.)", unit: "$" },
  { key: "cobertura_pef", label: "Cobertura del punto de equilibrio", unit: "x" },
];
// Targets from her model's "semáforo" - provisional, set for another organization.
const TARGETS: { key: IndicatorKey; label: string; goal: string; ok: (v: number) => boolean; reading: [string, string] }[] = [
  {
    key: "margen_operativo", label: "Margen operativo", goal: "≥ 10%", ok: (v) => v >= 0.1,
    reading: ["La operación cubre su estructura de gastos.", "La operación no deja suficiente margen sobre sus gastos."],
  },
  {
    key: "razon_circulante", label: "Razón circulante", goal: "≥ 1.5x", ok: (v) => v >= 1.5,
    reading: ["Hay holgura para cubrir las obligaciones de corto plazo.", "Poca holgura para cubrir obligaciones de corto plazo."],
  },
  {
    key: "ciclo_efectivo", label: "Ciclo de efectivo", goal: "≤ 30 días", ok: (v) => v <= 30,
    reading: ["El efectivo se recupera rápido.", "El efectivo tarda en regresar (inventario + cobranza - pagos)."],
  },
  {
    key: "cobertura_pef", label: "Cobertura del punto de equilibrio", goal: "≥ 1.0x", ok: (v) => v >= 1,
    reading: ["Los ingresos del año superan el punto de equilibrio.", "Los ingresos del año no alcanzan el punto de equilibrio."],
  },
];

// Shared look for every table here: tinted header with small caps labels,
// alternating row shading, row label in medium weight.
const TABLE_CLASS =
  "[&_thead_tr]:bg-slate-100 [&_thead_tr:hover]:bg-slate-100 [&_th]:h-9 [&_th]:text-[11px] [&_th]:font-semibold " +
  "[&_th]:uppercase [&_th]:tracking-wide [&_th]:text-slate-500 [&_tbody_tr]:bg-white " +
  "[&_tbody_tr:nth-child(even)]:bg-slate-50 [&_tbody_tr:hover]:bg-blue-50/60 [&_td:first-child]:font-medium " +
  "[&_td:first-child]:text-slate-800";

function SectionHeading({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-l-4 border-slate-900 pl-3">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      <p className="text-sm text-gray-500">{children}</p>
    </div>
  );
}

function formatIndicator(value: number | null | undefined, unit: Unit) {
  if (value === null || value === undefined) return "-";
  if (unit === "%") return percent(value);
  if (unit === "x") return `${value.toLocaleString("es-MX", { maximumFractionDigits: 2 })}x`;
  if (unit === "dias") return value.toLocaleString("es-MX", { maximumFractionDigits: 0 });
  return compactMoney(value);
}

// Text color for a matrix cell: targeted indicators by their target (the
// semáforo above carries the icon + label), other money/percent values red
// when negative.
function indicatorTone(key: IndicatorKey, value: number | null | undefined) {
  if (typeof value !== "number") return "text-gray-400";
  const target = TARGETS.find((t) => t.key === key);
  if (target) return target.ok(value) ? "text-green-700" : "text-red-700";
  return value < 0 ? "text-red-700" : "";
}

// Categorical slots 1-5, in the order the backend lists the categories.
const EXPENSE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"];

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
    const results = new Map(data.resultados.map((r) => [r.month, r]));
    const res = results.get(data.month)!;
    const resLastYear = results.get(key(year - 1, m));
    const expenses = (r?: ResultsRow) => (r ? sum(Object.values(r.gastos)) : 0);
    const opMargin = (r?: ResultsRow) => (r && r.ingresos ? r.utilidad_operativa / r.ingresos : null);
    const categories = Object.keys(res.gastos);
    const indicators = new Map(data.indicadores.map((r) => [r.month, r]));
    const lastYearIndicators = data.indicadores.filter((r) => r.month.startsWith(`${year - 1}-`) && r.posted);
    // Her "PROM. 2025" column: plain average of last year's posted months.
    const indicatorAverage = (k: IndicatorKey) => {
      const values = lastYearIndicators.map((r) => r[k]).filter((v): v is number => typeof v === "number");
      return values.length ? sum(values) / values.length : null;
    };
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
      res,
      resLastYear,
      // Until the accountant posts the month's cost of sales, its result is meaningless.
      resPosted: res.costo > 0,
      opMargin: opMargin(res),
      opMarginLastYear: opMargin(resLastYear),
      expenses: expenses(res),
      expensesLastYear: expenses(resLastYear),
      categories,
      indicator: indicators.get(data.month),
      indicatorMonths: MONTH_ABBR.slice(0, m).map((label, i) => ({ label, row: indicators.get(key(year, i + 1)) })),
      indicatorAverage,
      expenseChart: MONTH_ABBR.slice(0, m).map((label, i) => {
        const r = results.get(key(year, i + 1));
        return { label, ...(r && r.costo > 0 ? r.gastos : {}) };
      }),
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
              <Table className={TABLE_CLASS}>
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
              <Table className={TABLE_CLASS}>
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
                        {view.brandTotal ? (
                          <span className="flex items-center justify-end gap-2">
                            <span className="h-1.5 w-16 rounded-full bg-slate-200" aria-hidden>
                              <span
                                className="block h-full rounded-full"
                                style={{ width: `${(b.ytd / view.brandTotal) * 100}%`, background: COLOR_CURRENT }}
                              />
                            </span>
                            {percent(b.ytd / view.brandTotal)}
                          </span>
                        ) : (
                          "-"
                        )}
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

          <SectionHeading title="Resultados">
              Según Contabilidad: cada mes cuenta lo que el contador registró en ese mes, por eso los ingresos
              pueden no coincidir con las ventas facturadas. Gastos agrupados por el nombre de la cuenta.
            </SectionHeading>

          {!view.resPosted ? (
            <p className="rounded-xl border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-600">
              Contabilidad todavía no registra el costo de ventas de {monthName}; los resultados aparecen
              cuando el contador cierre el mes.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                <Tile label={`Utilidad operativa de ${monthName}`} value={formatMoney(view.res.utilidad_operativa)}>
                  <Delta
                    value={change(view.res.utilidad_operativa, view.resLastYear?.utilidad_operativa)}
                    label={`vs ${monthShort} ${view.year - 1}`}
                  />
                  <p className="text-xs text-gray-400">ingresos - costo - gastos de operación</p>
                </Tile>
                <Tile label="Margen operativo" value={view.opMargin === null ? "-" : percent(view.opMargin)}>
                  <Delta
                    value={
                      view.opMargin !== null && view.opMarginLastYear !== null
                        ? view.opMargin - view.opMarginLastYear
                        : null
                    }
                    label={`vs ${monthShort} ${view.year - 1}`}
                    unit="pp"
                  />
                </Tile>
                <Tile label="Gastos de operación" value={formatMoney(view.expenses)}>
                  <Delta value={change(view.expenses, view.expensesLastYear)} label={`vs ${monthShort} ${view.year - 1}`} />
                  <p className="text-xs text-gray-400">
                    {view.res.ingresos ? percent(view.expenses / view.res.ingresos) : "-"} de los ingresos
                  </p>
                </Tile>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <Card>
                  <CardHeader className="p-4 pb-0">
                    <CardTitle className="text-base">Gastos de operación por mes</CardTitle>
                    <CardDescription>{view.year}, por categoría</CardDescription>
                  </CardHeader>
                  <div className="h-72 p-2 sm:p-4">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={view.expenseChart} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
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
                          cursor={{ fill: "#f3f4f6" }}
                        />
                        <Legend iconType="square" itemSorter={null} wrapperStyle={{ fontSize: 12 }} />
                        {view.categories.map((c, i) => (
                          <Bar
                            key={c}
                            dataKey={c}
                            stackId="gastos"
                            fill={EXPENSE_COLORS[i]}
                            stroke="#fff"
                            strokeWidth={1}
                            isAnimationActive={false}
                          />
                        ))}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </Card>

                <Card>
                  <CardHeader className="p-4 pb-2">
                    <CardTitle className="text-base">Gastos de {monthName}</CardTitle>
                    <CardDescription>
                      Contra {monthShort} {view.year - 1}
                    </CardDescription>
                  </CardHeader>
                  <Table className={TABLE_CLASS}>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Categoría</TableHead>
                        <TableHead className="text-right">Monto</TableHead>
                        <TableHead className={cn("text-right", HIDE_BELOW_SM)}>% ingresos</TableHead>
                        <TableHead className="text-right">Cambio</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {view.categories.map((c, i) => (
                        <TableRow key={c}>
                          <TableCell>
                            <span className="flex items-center gap-2">
                              <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: EXPENSE_COLORS[i] }} />
                              {c}
                            </span>
                          </TableCell>
                          <TableCell className="text-right num">{formatMoney(view.res.gastos[c])}</TableCell>
                          <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                            {view.res.ingresos ? percent(view.res.gastos[c] / view.res.ingresos) : "-"}
                          </TableCell>
                          <TableCell className="text-right">
                            <ChangeCell value={change(view.res.gastos[c], view.resLastYear?.gastos[c])} />
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </Card>
              </div>

              <SectionHeading title="Indicadores">
                  Mismas fórmulas que el modelo financiero mensual, con los saldos de Contabilidad al cierre de cada
                  mes. Las metas del semáforo son provisionales: vienen de ese modelo, hecho para otra organización.
                </SectionHeading>

              <Card>
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-base">Semáforo de {monthName}</CardTitle>
                </CardHeader>
                <Table className={TABLE_CLASS}>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Indicador</TableHead>
                      <TableHead className="text-right">Actual</TableHead>
                      <TableHead className={cn("text-right", HIDE_BELOW_SM)}>Meta</TableHead>
                      <TableHead>Estatus</TableHead>
                      <TableHead className={HIDE_BELOW_MD}>Lectura</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {TARGETS.map((t) => {
                      const value = view.indicator?.[t.key];
                      const unit = INDICATORS.find((i) => i.key === t.key)!.unit;
                      const ok = typeof value === "number" ? t.ok(value) : null;
                      return (
                        <TableRow key={t.key}>
                          <TableCell>{t.label}</TableCell>
                          <TableCell className="text-right num">
                            {formatIndicator(value, unit)}
                            {unit === "dias" && typeof value === "number" ? " días" : ""}
                          </TableCell>
                          <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>{t.goal}</TableCell>
                          <TableCell>
                            {ok === null ? (
                              "-"
                            ) : (
                              <span
                                className={cn(
                                  "inline-flex items-center gap-1 text-sm font-medium whitespace-nowrap",
                                  ok ? "text-green-700" : "text-red-700",
                                )}
                              >
                                {ok ? <CircleCheck className="w-4 h-4" aria-hidden /> : <CircleAlert className="w-4 h-4" aria-hidden />}
                                {ok ? "Cumple" : "No cumple"}
                              </span>
                            )}
                          </TableCell>
                          <TableCell className={cn("text-sm text-gray-500", HIDE_BELOW_MD)}>
                            {ok === null ? "" : t.reading[ok ? 0 : 1]}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </Card>

              <Card>
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-base">Indicadores por mes</CardTitle>
                  <CardDescription>
                    {view.year} y promedio mensual de {view.year - 1}; días = saldo al cierre entre el flujo diario
                    acumulado del año
                  </CardDescription>
                </CardHeader>
                <Table className={TABLE_CLASS}>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 bg-inherit min-w-[11rem]">Indicador</TableHead>
                      <TableHead className="text-right whitespace-nowrap">Prom. {view.year - 1}</TableHead>
                      {view.indicatorMonths.map((mm, i) => (
                        <TableHead
                          key={mm.label}
                          className={cn("text-right", i === view.indicatorMonths.length - 1 && "bg-blue-100 text-blue-800")}
                        >
                          {mm.label}
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {INDICATORS.map((ind) => (
                      <Fragment key={ind.key}>
                        {ind.group && (
                          // Group label row: ! overrides the table's row and first-column styles.
                          <tr className="border-b !bg-slate-200">
                            <td
                              colSpan={view.indicatorMonths.length + 2}
                              className="sticky left-0 px-4 py-1.5 text-[11px] !font-semibold uppercase tracking-wide !text-slate-600"
                            >
                              {ind.group}
                            </td>
                          </tr>
                        )}
                        <TableRow>
                          <TableCell className="sticky left-0 bg-inherit">{ind.label}</TableCell>
                          <TableCell className="text-right num text-gray-500">
                            {formatIndicator(view.indicatorAverage(ind.key), ind.unit)}
                          </TableCell>
                          {view.indicatorMonths.map((mm, i) => {
                            const value = mm.row?.[ind.key];
                            return (
                              <TableCell
                                key={mm.label}
                                className={cn(
                                  "text-right num",
                                  indicatorTone(ind.key, value),
                                  i === view.indicatorMonths.length - 1 && "bg-blue-50 font-semibold",
                                )}
                              >
                                {formatIndicator(value, ind.unit)}
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      </Fragment>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </>
          )}
        </>
      )}
    </main>
  );
}
