"use client";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownRight, ArrowUpRight, ChevronRight, CircleAlert, CircleCheck, RefreshCw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { HIDE_BELOW_MD, HIDE_BELOW_SM } from "@/components/sortable-table";
import ClientLink from "@/components/facturas/ClientLink";
import { useInvoiceDialog } from "@/components/facturas/invoice-dialog-context";
import type { OverdueClient } from "@/components/analytics/OverdueClients";
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

// Brand sales: year to date and the month alone, each with last year's.
interface Brand {
  brand: string;
  ytd: number;
  ytd_prev: number;
  mes: number;
  mes_prev: number;
}

interface SalesSummary {
  month: string;
  // January of last year through the chart's end: the whole year, or up to
  // the last complete month - can run past `month`.
  months: MonthRow[];
  brands: Brand[];
  cobrado: Partial<Record<Zone, number>>;
  // Open invoices and notas de cargo today, however old, net of each client's
  // unapplied credits (leftover credit is saldo_a_favor); dias_cobro uses the
  // last 12 months only.
  cuentas_por_cobrar: {
    pendiente: number;
    dias_cobro: number | null;
    antiguedad: { bucket: string; pendiente: number; documentos: number }[];
    saldo_a_favor: number;
    clientes_vencidos: number;
    clientes: OverdueClient[]; // the top ones; the full list opens in the dialog
  };
  resultados: ResultsRow[]; // same months as `months`
  indicadores: IndicatorRow[]; // same months as `months`
  // The picked month's operating expenses per account, by category.
  gastos_cuentas: Record<string, AccountLine[]>;
  financieros_cuentas: AccountLine[]; // "Gastos financieros netos" per account; gains negative
}

// One ledger account in a month, with the same month last year (net debit).
interface AccountLine {
  cuenta: string;
  monto: number;
  anterior: number;
}

const MONTH_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
// Categorical slots 1 and 2 of the dataviz palette (validated as a pair).
const COLOR_CURRENT = "#2a78d6";
const COLOR_PREVIOUS = "#eb6834";
const TOP_BRANDS = 8;
type Unit = "%" | "x" | "dias" | "$";
// Rows of her INDICADORES sheet that we can compute, in her order. `note` is a
// caveat about our data, shown as a footnote - not a definition (the owner is
// an accountant).
const INDICATORS: { key: IndicatorKey; label: string; unit: Unit; group?: string; note?: string }[] = [
  { group: "Rentabilidad", key: "margen_bruto", label: "Margen bruto", unit: "%" },
  { key: "margen_operativo", label: "Margen operativo", unit: "%" },
  { key: "margen_neto", label: "Margen neto (antes de impuestos)", unit: "%" },
  { key: "gasto_operativo_ingresos", label: "Gasto operativo / ingresos", unit: "%" },
  { group: "Liquidez", key: "saldo_caja", label: "Caja y bancos al cierre", unit: "$" },
  { key: "razon_circulante", label: "Razón circulante", unit: "x" },
  { key: "prueba_acida", label: "Prueba ácida", unit: "x" },
  {
    group: "Ciclo de efectivo",
    key: "dias_cxc",
    label: "Días de cuentas por cobrar",
    unit: "dias",
    note:
      "Con los saldos de Contabilidad y las ventas del año; los días promedio de cobro de arriba usan " +
      "Comercial y los últimos 12 meses, por eso difieren.",
  },
  { key: "dias_inventario", label: "Días de inventario", unit: "dias" },
  {
    key: "dias_cxp",
    label: "Días de cuentas por pagar",
    unit: "dias",
    note:
      "Bajo por el anticipo a un proveedor extranjero, que hoy se resta de lo que se debe; pendiente de " +
      "revisar con Contabilidad. Afecta también el ciclo de efectivo.",
  },
  { key: "ciclo_efectivo", label: "Ciclo de conversión de efectivo", unit: "dias" },
  { group: "Endeudamiento y retorno", key: "endeudamiento", label: "Nivel de endeudamiento", unit: "%" },
  { key: "roa_ytd", label: "ROA acumulado", unit: "%" },
  { key: "roe_ytd", label: "ROE acumulado", unit: "%" },
  {
    group: "Punto de equilibrio",
    key: "pe_operativo_ytd",
    label: "Punto de equilibrio operativo (acum.)",
    unit: "$",
  },
  { key: "pe_financiero_ytd", label: "Punto de equilibrio financiero (acum.)", unit: "$" },
  { key: "cobertura_pef", label: "Cobertura del punto de equilibrio", unit: "x" },
];
// Footnote markers, in list order.
const NOTED = INDICATORS.filter((i) => i.note);
const noteMark = (key: IndicatorKey) => "*".repeat(NOTED.findIndex((i) => i.key === key) + 1);
// Targets from her model's "semáforo" - provisional, set for another organization.
const TARGETS: { key: IndicatorKey; goal: string; ok: (v: number) => boolean }[] = [
  { key: "margen_operativo", goal: "≥ 10%", ok: (v) => v >= 0.1 },
  { key: "razon_circulante", goal: "≥ 1.5x", ok: (v) => v >= 1.5 },
  { key: "ciclo_efectivo", goal: "≤ 30 días", ok: (v) => v <= 30 },
  { key: "cobertura_pef", goal: "≥ 1.0x", ok: (v) => v >= 1 },
]

// Shared look for every table here: tinted header with small caps labels,
// alternating row shading, row label in medium weight.
const TABLE_CLASS =
  "[&_thead_tr]:bg-slate-100 [&_thead_tr:hover]:bg-slate-100 [&_th]:h-9 [&_th]:text-[11px] [&_th]:font-semibold " +
  "[&_th]:whitespace-nowrap " +
  "[&_th]:uppercase [&_th]:tracking-wide [&_th]:text-slate-500 [&_tbody_tr]:bg-white " +
  "[&_tbody_tr:nth-child(even)]:bg-slate-50 [&_tbody_tr:hover]:bg-blue-50/60 [&_td:first-child]:font-medium " +
  "[&_td:first-child]:text-slate-800";

// Number-column widths for the tables whose rows expand ("table-fixed"): long
// account names wrap in the first column instead of resizing the table.
const COL_MONEY = "w-32 sm:w-40";
const COL_PERCENT = "w-[4.5rem] sm:w-24";
// The side-by-side cards (brands, aging, overdue clients) are under 480px wide
// between lg and ~1150px: fixed number columns, the name column truncates.
const COL_SIDE_MONEY = "w-[7.5rem]";
const COL_SHARE = "w-[8.5rem]"; // ShareBar is 7.5rem plus padding

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

// Text color for an indicator value: by its target when it has one, otherwise
// red only when negative.
function indicatorTone(key: IndicatorKey, value: number | null | undefined) {
  if (typeof value !== "number") return "text-gray-400";
  const target = TARGETS.find((t) => t.key === key);
  if (target) return target.ok(value) ? "text-green-700" : "text-red-700";
  return value < 0 ? "text-red-700" : "";
}

// Categorical slots 1-8, in the order the backend lists the categories
// ("Otros" last). Validated as a set; labels/table carry the low-contrast ones.
const EXPENSE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];

// Top brands by the chosen period, the rest folded into "Otras".
function topBrands(brands: Brand[], period: "ytd" | "mes") {
  const prevKey = period === "ytd" ? "ytd_prev" : "mes_prev";
  const sorted = [...brands].sort((a, b) => b[period] - a[period]);
  const rest = sorted.slice(TOP_BRANDS);
  const rows = sorted.slice(0, TOP_BRANDS).map((b) => ({ brand: b.brand, value: b[period], prev: b[prevKey] }));
  if (rest.length)
    rows.push({
      brand: "Otras",
      value: sum(rest.map((b) => b[period])),
      prev: sum(rest.map((b) => b[prevKey])),
    });
  return { rows, total: sum(brands.map((b) => b[period])), prevTotal: sum(brands.map((b) => b[prevKey])) };
}

// Card header with tabs: title and tabs share a row, the description gets
// its own line so it isn't squeezed next to the tabs on a phone.
function TabbedHeader({
  title,
  description,
  tabs,
  value,
  onChange,
}: {
  title: string;
  description: string;
  tabs: [string, string][]; // [value, label]
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <CardHeader className="p-4 pb-2 space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <CardTitle className="text-base">{title}</CardTitle>
        <Tabs value={value} onValueChange={onChange}>
          <TabsList className="h-8">
            {tabs.map(([v, label]) => (
              <TabsTrigger key={v} value={v} className="text-xs">
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      <CardDescription>{description}</CardDescription>
    </CardHeader>
  );
}

// One month's expenses as a single bar split by category, largest first.
// Each slice opens its category's accounts in the table below (its legend).
function ExpenseSplit({
  parts,
  total,
  selected,
  onSelect,
}: {
  parts: { category: string; value: number; color: string }[];
  total: number;
  selected: string | null;
  onSelect: (category: string) => void;
}) {
  return (
    <div className="flex h-12 w-full gap-0.5 overflow-hidden rounded-md">
      {parts
        .filter((p) => p.value > 0)
        .map((p) => {
          const label = `${p.category}: ${formatMoney(p.value)} (${total ? percent(p.value / total, 0) : "-"})`;
          return (
            <button
              key={p.category}
              type="button"
              className={cn("h-full transition-opacity", selected && selected !== p.category && "opacity-30")}
              style={{ flexGrow: p.value, flexBasis: 0, background: p.color }}
              title={label}
              aria-label={label}
              onClick={() => onSelect(p.category)}
            />
          );
        })}
    </div>
  );
}

// The month's income statement, top to bottom: each line's sign and whether
// it's a subtotal. Costs come back positive from the backend.
function incomeStatement(r: ResultsRow) {
  const expenses = sum(Object.values(r.gastos));
  const gross = r.ingresos - r.costo;
  return [
    { label: "Ingresos", value: r.ingresos },
    { label: "Costo de ventas", value: -r.costo, cost: true },
    { label: "Utilidad bruta", value: gross, total: true },
    { label: "Gastos de operación", value: -expenses, cost: true },
    { label: "Utilidad operativa", value: r.utilidad_operativa, total: true },
    { label: "Gastos financieros netos", value: -r.financieros, cost: true, expandable: true },
    { label: "Utilidad antes de impuestos", value: r.utilidad_operativa - r.financieros, total: true },
  ];
}

// The income statement as a horizontal waterfall: each line a row whose bar
// floats where it sits between zero and the month's income - costs bite off
// the running total, subtotals stand from zero. Amount, % of income and the
// change vs the same month last year sit beside each bar; the financial line
// opens its accounts.
function IncomeWaterfall({
  res,
  resLastYear,
  accounts,
  prevLabel,
}: {
  res: ResultsRow;
  resLastYear?: ResultsRow;
  accounts: AccountLine[];
  prevLabel: string;
}) {
  const [open, setOpen] = useState(false);
  const lines = incomeStatement(res);
  const prevLines = resLastYear ? incomeStatement(resLastYear) : null;
  // Each line's [from, to] on the axis: subtotals from zero, the rest from the
  // running total of the lines above them.
  const spans = lines.map((line, i) => {
    const from = line.total ? 0 : sum(lines.slice(0, i).filter((l) => !l.total).map((l) => l.value));
    const to = line.total ? line.value : from + line.value;
    return [Math.min(from, to), Math.max(from, to)];
  });
  const lo = Math.min(0, ...spans.map(([a]) => a));
  const hi = Math.max(...spans.map(([, b]) => b));
  const at = (v: number) => `${((v - lo) / (hi - lo || 1)) * 100}%`;
  const share = (v: number) => (res.ingresos ? percent(v / res.ingresos) : "-");
  // Label | bar | amount | % | change on wide screens; on phones the bar drops under label + amount.
  const ROW = "grid grid-cols-[1fr_auto] sm:grid-cols-[12.5rem_1fr_8.5rem_5.5rem_5rem] items-center gap-x-3";

  return (
    <div className="px-4 pb-4">
      <div className={cn(ROW, "hidden sm:grid pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500")}>
        <span />
        <span />
        <span className="text-right">Monto</span>
        <span className="text-right whitespace-nowrap">% ingresos</span>
        <span className="text-right whitespace-nowrap">vs {prevLabel}</span>
      </div>
      {lines.map((line, i) => {
        const [a, b] = spans[i];
        const prev = prevLines?.[i].value;
        const negative = line.total && line.value < 0;
        return (
          <Fragment key={line.label}>
            <div className={cn(ROW, "gap-y-1.5 py-2", line.total && "border-t border-slate-200")}>
              <div className={cn("text-sm", line.total ? "font-semibold text-gray-900" : "text-gray-600")}>
                {line.expandable ? (
                  <button
                    type="button"
                    className="-ml-1 flex items-center gap-1 text-left"
                    aria-expanded={open}
                    onClick={() => setOpen((o) => !o)}
                  >
                    <ChevronRight
                      className={cn("w-4 h-4 shrink-0 text-gray-400 transition-transform", open && "rotate-90")}
                      aria-hidden
                    />
                    {line.label}
                  </button>
                ) : (
                  line.label
                )}
              </div>
              <div
                className={cn(
                  "text-right num text-sm sm:col-start-3 sm:row-start-1",
                  line.total ? "font-semibold" : "text-gray-600",
                  negative && "text-red-700",
                )}
              >
                {formatMoney(line.value)}
                <span className="sm:hidden font-normal text-gray-500"> · {share(line.value)}</span>
              </div>
              <div
                className="relative col-span-2 h-3 rounded-sm bg-slate-100 sm:col-span-1 sm:col-start-2 sm:row-start-1 sm:h-4"
                title={`${line.label}: ${formatMoney(line.value)} (${share(line.value)})`}
              >
                <div
                  className="absolute inset-y-0 rounded-sm"
                  style={{
                    left: at(a),
                    width: `max(2px, calc(${at(b)} - ${at(a)}))`,
                    background: negative ? "#e34948" : line.total ? COLOR_CURRENT : i === 0 ? "#334155" : "#94a3b8",
                  }}
                />
              </div>
              <div className="hidden sm:block text-right num text-sm text-gray-600">{share(line.value)}</div>
              <div className="hidden sm:block text-right text-sm">
                {/* Costs: how much bigger they got (red when up). Subtotals: signed,
                    so a loss turning into a profit reads as an improvement. */}
                <ChangeCell
                  value={
                    line.cost
                      ? change(Math.abs(line.value), prev === undefined ? undefined : Math.abs(prev))
                      : change(line.value, prev)
                  }
                  inverse={line.cost}
                />
              </div>
            </div>
            {line.expandable && open && (
              <div className="mb-1 rounded-md bg-slate-50 py-1">
                {accounts
                  .filter((acc) => acc.monto || acc.anterior)
                  .map((acc) => (
                    // As they hit the result: costs negative, gains positive. Nothing this
                    // month only matters next to last year's amount, hidden on phones.
                    <div
                      key={acc.cuenta}
                      className={cn(
                        "grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_8.5rem_5.5rem_5rem] gap-x-3 py-1 text-xs",
                        !acc.monto && "hidden sm:grid",
                      )}
                    >
                      <span className="pl-7 text-gray-500">{acc.cuenta}</span>
                      <span className="text-right num text-gray-600">{formatMoney(0 - acc.monto || 0)}</span>
                      <span className="hidden sm:block text-right num text-gray-500">{share(0 - acc.monto || 0)}</span>
                      <span className="hidden sm:block text-right">
                        <ChangeCell
                          value={change(Math.abs(acc.monto), Math.abs(acc.anterior))}
                          inverse={(acc.monto || acc.anterior) > 0}
                        />
                      </span>
                    </div>
                  ))}
              </div>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

// One indicator's trend this year: a line through the months so far (gaps
// where Contabilidad hasn't closed), last year's monthly average dashed, and
// a dot on the picked month (the last one).
function Sparkline({ values, reference }: { values: (number | null)[]; reference: number | null }) {
  const known = values.filter((v): v is number => v !== null);
  if (!known.length) return <div className="h-7" />;
  const all = reference === null ? known : [...known, reference];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const x = (i: number) => (values.length === 1 ? 50 : (i / (values.length - 1)) * 100);
  const y = (v: number) => (hi === lo ? 50 : 10 + (1 - (v - lo) / (hi - lo)) * 80); // % of the height
  const path = values
    .map((v, i) => (v === null ? "" : `${i > 0 && values[i - 1] !== null ? "L" : "M"}${x(i)},${y(v)}`))
    .join("");
  const last = values[values.length - 1];
  return (
    <div className="relative h-7">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible">
        {reference !== null && (
          <line
            x1={0}
            x2={100}
            y1={y(reference)}
            y2={y(reference)}
            stroke="#94a3b8"
            strokeWidth={1}
            strokeDasharray="3 3"
            vectorEffect="non-scaling-stroke"
          />
        )}
        <path d={path} fill="none" stroke={COLOR_CURRENT} strokeWidth={2} vectorEffect="non-scaling-stroke" />
      </svg>
      {last !== null && (
        // A dot drawn in HTML so it stays round while the line stretches.
        <span
          className="absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
          style={{ left: `${x(values.length - 1)}%`, top: `${y(last)}%`, background: COLOR_CURRENT }}
        />
      )}
    </div>
  );
}

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

// `inverse` is for costs and returns: the number keeps its sign, but going up is red.
function Delta({
  value,
  label,
  unit = "%",
  inverse = false,
}: {
  value: number | null;
  label: string;
  unit?: "%" | "pp";
  inverse?: boolean;
}) {
  if (value === null) return <p className="text-xs text-gray-400">sin dato {label}</p>;
  const up = value >= 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  const text =
    unit === "pp"
      ? `${up ? "+" : ""}${(value * 100).toLocaleString("es-MX", { maximumFractionDigits: 1 })} pts`
      : `${up ? "+" : ""}${percent(value)}`;
  return (
    <p className="flex flex-wrap items-center gap-x-1 text-xs text-gray-500">
      <span className={cn("inline-flex items-center whitespace-nowrap font-medium", up !== inverse ? "text-green-700" : "text-red-700")}>
        <Icon className="w-3.5 h-3.5" aria-hidden />
        {text}
      </span>
      {label}
    </p>
  );
}

// A share of the total as a small bar plus the percentage. Fixed track and
// number widths, so every row's bar starts and ends at the same place.
function ShareBar({ value, total }: { value: number; total: number }) {
  if (!total) return <>-</>;
  return (
    <span className="flex items-center justify-end gap-2">
      <span className="h-1.5 w-16 shrink-0 rounded-full bg-slate-200" aria-hidden>
        <span
          className="block h-full rounded-full"
          style={{ width: `${Math.max(0, value / total) * 100}%`, background: COLOR_CURRENT }}
        />
      </span>
      <span className="w-12 shrink-0 text-right">{percent(value / total)}</span>
    </span>
  );
}

// `inverse` is for costs: the number keeps its sign, but going up is red.
function ChangeCell({ value, inverse = false }: { value: number | null; inverse?: boolean }) {
  if (value === null) return <span className="text-gray-400">-</span>;
  return (
    <span className={cn("num", value >= 0 !== inverse ? "text-green-700" : "text-red-700")}>
      {value >= 0 ? "+" : ""}
      {percent(value, 0)}
    </span>
  );
}

function Tile({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader className="p-3 sm:p-4 space-y-1">
        <CardDescription className="text-xs sm:text-sm">{label}</CardDescription>
        <CardTitle className="text-base sm:text-xl">{value}</CardTitle>
        {children}
      </CardHeader>
    </Card>
  );
}

export default function SalesBIView() {
  const { loading: authLoading, isManagement } = useAuth();
  const { openOverdueClients } = useInvoiceDialog();
  const [month, setMonth] = useState(lastCompleteMonth);
  const [data, setData] = useState<SalesSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The server caches each month for 10 minutes; "Actualizar" bumps `reload`
  // and flags that one fetch to skip the cache.
  const [reload, setReload] = useState(0);
  const forceRefresh = useRef(false);
  const [brandPeriod, setBrandPeriod] = useState<"ytd" | "mes">("mes");
  const [zonePeriod, setZonePeriod] = useState<"ytd" | "mes">("mes");
  const [expensePeriod, setExpensePeriod] = useState<"anual" | "mes">("anual");
  // Expense category whose accounts are listed; kept across months to compare.
  const [openCategory, setOpenCategory] = useState<string | null>(null);
  const toggleCategory = (c: string) => setOpenCategory((open) => (open === c ? null : c));
  const [openIndicator, setOpenIndicator] = useState<IndicatorKey | null>(null);
  // When the indicator table is wider than the screen, start it at the picked
  // month (its last column) rather than at January.
  const indicatorTable = useRef<HTMLTableElement>(null);
  useEffect(() => {
    const wrapper = indicatorTable.current?.parentElement;
    if (wrapper) wrapper.scrollLeft = wrapper.scrollWidth;
  }, [data]);

  useEffect(() => {
    if (!isManagement) return;
    const refresh = forceRefresh.current ? "&refresh=1" : "";
    forceRefresh.current = false;
    let cancelled = false;
    // Standard fetch-on-change; `cancelled` drops a stale month's response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    apiFetch(`/api/analytics/sales/?month=${month}${refresh}`)
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
  }, [month, isManagement, reload]);

  const view = useMemo(() => {
    if (!data) return null;
    const year = Number(data.month.slice(0, 4));
    const m = Number(data.month.slice(5, 7));
    const byMonth = new Map(data.months.map((r) => [r.month, r]));
    const key = (y: number, mm: number) => `${y}-${String(mm).padStart(2, "0")}`;
    const cur = byMonth.get(data.month)!;
    const prev = byMonth.get(monthToISO(new Date(year, m - 2, 1)));
    const lastYear = byMonth.get(key(year - 1, m));
    const thisYearRows = data.months.filter((r) => r.month.startsWith(`${year}-`) && r.month <= data.month);
    const lastYearRows = data.months.filter((r) => r.month.startsWith(`${year - 1}-`));
    const lastYearToDate = lastYearRows.filter((r) => Number(r.month.slice(5)) <= m);
    const margin = (r?: MonthRow) => (r && r.ventas ? (r.ventas - r.costo) / r.ventas : null);
    const results = new Map(data.resultados.map((r) => [r.month, r]));
    const res = results.get(data.month)!;
    const resLastYear = results.get(key(year - 1, m));
    const expenses = (r?: ResultsRow) => (r ? sum(Object.values(r.gastos)) : 0);
    const categories = Object.keys(res.gastos);
    const indicators = new Map(data.indicadores.map((r) => [r.month, r]));
    const lastYearIndicators = data.indicadores.filter((r) => r.month.startsWith(`${year - 1}-`) && r.posted);
    // Her "PROM. 2025" column: plain average of last year's posted months.
    const indicatorAverage = (k: IndicatorKey) => {
      const values = lastYearIndicators.map((r) => r[k]).filter((v): v is number => typeof v === "number");
      return values.length ? sum(values) / values.length : null;
    };
    const zoneYtd = (rows: MonthRow[], z: Zone) => sum(rows.map((r) => r.zonas[z] ?? 0));

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
      })),
      brands: topBrands(data.brands, brandPeriod),
      res,
      resLastYear,
      // Until the accountant posts the month's cost of sales, its result is meaningless.
      resPosted: res.costo > 0,
      expenses: expenses(res),
      categories,
      // The picked month alone, largest first; colors stay with the category.
      expenseMonth: categories
        .map((c, i) => ({
          category: c,
          value: res.gastos[c],
          color: EXPENSE_COLORS[i],
        }))
        .sort((a, b) => b.value - a.value),
      indicator: indicators.get(data.month),
      indicatorMonths: MONTH_ABBR.slice(0, m).map((label, i) => ({
        label,
        row: indicators.get(key(year, i + 1)),
      })),
      indicatorAverage,
      // Whole range like the sales chart; months not closed yet stay empty.
      expenseChart: MONTH_ABBR.map((label, i) => {
        const r = results.get(key(year, i + 1));
        return { label, ...(r && r.costo > 0 ? r.gastos : {}) };
      }),
    };
  }, [data, brandPeriod]);

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

  // Chart click on column i: open that month of the year shown, if it has sales.
  const openMonth = (i: number) => {
    if (view && Number.isInteger(i) && view.chart[i]?.actual !== null) {
      setMonth(`${view.year}-${String(i + 1).padStart(2, "0")}`);
    }
  };

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

      <div className="flex items-center gap-2 sm:gap-3">
        <MonthControl month={month} onChange={setMonth} />
        <Button
          size="sm"
          variant="outline"
          className="h-9 sm:h-8"
          disabled={loading}
          title="Actualizar con los datos más recientes del ERP"
          aria-label="Actualizar"
          onClick={() => {
            forceRefresh.current = true;
            setReload((n) => n + 1);
          }}
        >
          <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} aria-hidden />
          <span className="hidden sm:inline">Actualizar</span>
        </Button>
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      {view && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            <Tile label={`Ventas de ${monthName}`} value={formatMoney(view.cur.ventas)}>
              <Delta value={change(view.cur.ventas, view.lastYear?.ventas)} label={`vs ${monthShort} ${view.year - 1}`} />
              <Delta value={change(view.cur.ventas, view.prev?.ventas)} label="vs mes anterior" />
              <Delta value={change(view.cur.ventas, view.avgLastYear)} label={`vs promedio mensual ${view.year - 1}`} />
            </Tile>
            <Tile label={`Acumulado ene-${monthShort} ${view.year}`} value={formatMoney(view.ytd)}>
              <Delta value={change(view.ytd, view.ytdPrev)} label={`vs ene-${monthShort} ${view.year - 1}`} />
            </Tile>
            <Tile label="Margen bruto del mes (costo del ERP)" value={view.margin === null ? "-" : percent(view.margin)}>
              <Delta
                value={view.margin !== null && view.marginLastYear !== null ? view.margin - view.marginLastYear : null}
                label={`vs ${monthShort} ${view.year - 1}`}
                unit="pp"
              />
              <p className="text-xs text-gray-400">
                por fecha de factura; el de Contabilidad, cuando cierra el mes, está en Resultados
              </p>
            </Tile>
            <Tile label={`Cobrado en ${monthName}`} value={formatMoney(view.cobrado)}>
              <p className="text-xs text-gray-400">con IVA, igual que Corte de Caja</p>
            </Tile>
            <Tile label="Por cobrar hoy" value={formatMoney(data!.cuentas_por_cobrar.pendiente)}>
              <p className="text-xs text-gray-500">
                {data!.cuentas_por_cobrar.dias_cobro ?? "-"} días promedio de cobro (últimos 12 meses)
              </p>
              <p className="text-xs text-gray-400">con IVA, todas las facturas abiertas, menos saldos a favor</p>
            </Tile>
            <Tile label="Devoluciones y notas de crédito" value={formatMoney(view.cur.devoluciones)}>
              <Delta
                value={change(view.cur.devoluciones, view.lastYear?.devoluciones)}
                label={`vs ${monthShort} ${view.year - 1}`}
                inverse
              />
              <p className="text-xs text-gray-500">
                {view.cur.ventas ? percent(view.cur.devoluciones / (view.cur.ventas + view.cur.devoluciones)) : "-"} de
                lo facturado en el mes
              </p>
              <p className="text-xs text-gray-400">ya descontadas de las ventas</p>
            </Tile>
          </div>

          <Card>
            <CardHeader className="p-4 pb-0">
              <CardTitle className="text-base">Ventas por mes</CardTitle>
              <CardDescription>
                {view.year} contra {view.year - 1}, sin IVA. Haga clic en un mes para verlo.
              </CardDescription>
            </CardHeader>
            <div className="h-72 p-2 sm:p-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={view.chart}
                  margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                  // Mouse clicks focus parts of the chart; keep the ring for keyboard users only.
                  className="cursor-pointer [&_:focus:not(:focus-visible)]:outline-none"
                  // Anywhere in a month's column opens that month of the year shown;
                  // last year's dot (below) opens last year's instead.
                  onClick={(e) => openMonth(Number(e.activeIndex))}
                >
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
                  <ReferenceLine
                    x={MONTH_ABBR[Number(data!.month.slice(5)) - 1]}
                    stroke="#94a3b8"
                    strokeDasharray="4 4"
                  />
                  <Line
                    name={String(view.year - 1)}
                    dataKey="anterior"
                    stroke={COLOR_PREVIOUS}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    activeDot={(p) => (
                      <g
                        onClick={(e) => {
                          e.stopPropagation();
                          setMonth(`${view.year - 1}-${String(p.index + 1).padStart(2, "0")}`);
                        }}
                      >
                        <circle cx={p.cx} cy={p.cy} r={12} fill="transparent" />
                        <circle cx={p.cx} cy={p.cy} r={5} fill={COLOR_PREVIOUS} stroke="#fff" strokeWidth={2} />
                      </g>
                    )}
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
              <TabbedHeader
                title="Por zona"
                description={
                  zonePeriod === "ytd"
                    ? `Acumulado ene-${monthShort} ${view.year} contra el mismo periodo de ${view.year - 1}`
                    : `${monthName} contra ${monthShort} ${view.year - 1}`
                }
                tabs={[
                  ["ytd", "Acumulado"],
                  ["mes", "Mensual"],
                ]}
                value={zonePeriod}
                onChange={(v) => setZonePeriod(v as "ytd" | "mes")}
              />
              <Table className={TABLE_CLASS}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Zona</TableHead>
                    <TableHead className="text-right">Ventas</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM)}>% del total</TableHead>
                    <TableHead className="text-right">Cambio</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(() => {
                    const rows = view.zones.map((z) => ({
                      key: z.zone,
                      label: ZONE_LABELS[z.zone],
                      value: zonePeriod === "ytd" ? z.ytd : z.ventas,
                      prev: zonePeriod === "ytd" ? z.ytdPrev : z.lastYear,
                    }));
                    // Totals from the rows themselves, so the column always adds up.
                    const total = sum(rows.map((r) => r.value));
                    const prevTotal = rows.some((r) => r.prev !== undefined) ? sum(rows.map((r) => r.prev ?? 0)) : undefined;
                    return [...rows, { key: "total", label: "Total", value: total, prev: prevTotal }].map((r) => (
                      // ! overrides the table's zebra: the total row stands out.
                      <TableRow key={r.key} className={cn(r.key === "total" && "!bg-slate-100 font-semibold")}>
                        <TableCell>{r.label}</TableCell>
                        <TableCell className="text-right num">{formatMoney(r.value)}</TableCell>
                        <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                          <ShareBar value={r.value} total={total} />
                        </TableCell>
                        <TableCell className="text-right">
                          <ChangeCell value={change(r.value, r.prev)} />
                        </TableCell>
                      </TableRow>
                    ));
                  })()}
                </TableBody>
              </Table>
            </Card>

            <Card>
              <TabbedHeader
                title="Por marca"
                description={
                  brandPeriod === "ytd"
                    ? `Acumulado ene-${monthShort} ${view.year} contra el mismo periodo de ${view.year - 1}`
                    : `${monthName} contra ${monthShort} ${view.year - 1}`
                }
                tabs={[
                  ["ytd", "Acumulado"],
                  ["mes", "Mensual"],
                ]}
                value={brandPeriod}
                onChange={(v) => setBrandPeriod(v as "ytd" | "mes")}
              />
              <Table className={cn(TABLE_CLASS, "table-fixed")}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Marca</TableHead>
                    <TableHead className={cn("text-right", COL_SIDE_MONEY)}>Ventas</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM, COL_SHARE)}>% del total</TableHead>
                    <TableHead className="text-right w-24">Cambio</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {view.brands.rows.map((b) => (
                    <TableRow key={b.brand}>
                      <TableCell className="truncate" title={b.brand}>
                        {b.brand}
                      </TableCell>
                      <TableCell className="text-right num">{formatMoney(b.value)}</TableCell>
                      <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                        <ShareBar value={b.value} total={view.brands.total} />
                      </TableCell>
                      <TableCell className="text-right">
                        <ChangeCell value={change(b.value, b.prev)} />
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow className="!bg-slate-100 font-semibold">
                    <TableCell>Total</TableCell>
                    <TableCell className="text-right num">{formatMoney(view.brands.total)}</TableCell>
                    <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                      <ShareBar value={view.brands.total} total={view.brands.total} />
                    </TableCell>
                    <TableCell className="text-right">
                      <ChangeCell value={change(view.brands.total, view.brands.prevTotal)} />
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </Card>
          </div>

          <SectionHeading title="Cuentas por cobrar">
            Facturas abiertas hoy según Comercial, con IVA, por días de vencidas, menos los pagos, notas de crédito y
            devoluciones de cada cliente que no se han aplicado a una factura. No depende del mes elegido.
          </SectionHeading>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="text-base">Antigüedad</CardTitle>
                <CardDescription>
                  Saldo por días desde el vencimiento.
                  {data!.cuentas_por_cobrar.saldo_a_favor > 0 &&
                    ` Saldos a favor de clientes sin facturas que cubrir: ${formatMoney(
                      data!.cuentas_por_cobrar.saldo_a_favor,
                    )}, no restados.`}
                </CardDescription>
              </CardHeader>
              <Table className={cn(TABLE_CLASS, "table-fixed")}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Vencimiento</TableHead>
                    <TableHead className={cn("text-right", COL_SIDE_MONEY)}>Por cobrar</TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM, COL_SHARE)}>% del total</TableHead>
                    <TableHead className="text-right w-28">Documentos</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(() => {
                    const { antiguedad, pendiente } = data!.cuentas_por_cobrar;
                    const rows = [
                      ...antiguedad,
                      { bucket: "Total", pendiente, documentos: sum(antiguedad.map((b) => b.documentos)) },
                    ];
                    return rows.map((b) => (
                      <TableRow key={b.bucket} className={cn(b.bucket === "Total" && "!bg-slate-100 font-semibold")}>
                        <TableCell>{b.bucket}</TableCell>
                        <TableCell className="text-right num">{formatMoney(b.pendiente)}</TableCell>
                        <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                          <ShareBar value={b.pendiente} total={pendiente} />
                        </TableCell>
                        <TableCell className="text-right num">{b.documentos}</TableCell>
                      </TableRow>
                    ));
                  })()}
                </TableBody>
              </Table>
            </Card>

            <Card>
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-base">Clientes con más saldo vencido</CardTitle>
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={openOverdueClients}>
                    Ver los {data!.cuentas_por_cobrar.clientes_vencidos}
                  </Button>
                </div>
                <CardDescription>
                  {data!.cuentas_por_cobrar.clientes.length} de {data!.cuentas_por_cobrar.clientes_vencidos} clientes
                  con facturas vencidas. Haga clic en un cliente para ver sus facturas.
                </CardDescription>
              </CardHeader>
              <Table className={cn(TABLE_CLASS, "table-fixed")}>
                <TableHeader>
                  <TableRow>
                    <TableHead>Cliente</TableHead>
                    <TableHead className={cn("text-right", COL_SIDE_MONEY)}>Vencido</TableHead>
                    <TableHead className="text-right w-20 xl:w-32">
                      <span className="xl:hidden">Días</span>
                      <span className="hidden xl:inline">Días de atraso</span>
                    </TableHead>
                    <TableHead className={cn("text-right", HIDE_BELOW_SM, COL_SIDE_MONEY)}>Saldo total</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data!.cuentas_por_cobrar.clientes.map((c) => (
                    <TableRow key={c.client_id}>
                      <TableCell className="truncate" title={c.cliente}>
                        <ClientLink clientId={c.client_id} label={c.cliente} />
                      </TableCell>
                      <TableCell className="text-right num">{formatMoney(c.vencido)}</TableCell>
                      <TableCell className={cn("text-right num", c.dias_vencido > 90 && "text-red-700")}>
                        {c.dias_vencido}
                      </TableCell>
                      <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>{formatMoney(c.pendiente)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </div>

          <SectionHeading title="Resultados">
              Según Contabilidad: cada mes cuenta lo que el contador registró en ese mes, por eso los ingresos
              pueden no coincidir con las ventas facturadas. Gastos agrupados por tipo de cuenta.
            </SectionHeading>

          {!view.resPosted && (
            <p className="rounded-xl border border-dashed border-gray-300 bg-white p-6 text-center text-sm text-gray-600">
              Contabilidad todavía no registra el costo de ventas de {monthName}; los resultados aparecen cuando el
              contador cierre el mes.
            </p>
          )}

          {view.resPosted && (
            <Card>
              <CardHeader className="p-4 pb-3">
                <CardTitle className="text-base">Estado de resultados de {monthName}</CardTitle>
                <CardDescription>
                  Cada barra parte del ingreso del mes: los costos lo van reduciendo y las utilidades muestran lo que
                  queda.
                </CardDescription>
              </CardHeader>
              <IncomeWaterfall
                res={view.res}
                resLastYear={view.resLastYear}
                accounts={data!.financieros_cuentas}
                prevLabel={`${monthShort} ${view.year - 1}`}
              />
            </Card>
          )}

          <Card>
            <TabbedHeader
              title="Gastos de operación"
              description={
                expensePeriod === "anual"
                  ? `${view.year} por mes. Haga clic en una barra para ver ese mes y esa categoría.`
                  : `${monthName}. Haga clic en un color o en una categoría para ver sus cuentas.`
              }
              tabs={[
                ["anual", "Anual"],
                ["mes", "Mensual"],
              ]}
              value={expensePeriod}
              onChange={(v) => setExpensePeriod(v as "anual" | "mes")}
            />
            {expensePeriod === "anual" ? (
              <div className="h-64 sm:h-80 px-1 sm:px-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={view.expenseChart}
                    margin={{ top: 8, right: 8, bottom: 0, left: 0 }}
                    // Mouse clicks focus parts of the chart; keep the ring for keyboard users only.
                    className="[&_:focus:not(:focus-visible)]:outline-none"
                  >
                    <CartesianGrid vertical={false} stroke="#e5e7eb" />
                    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: "#6b7280" }} />
                    <YAxis
                      tickFormatter={compactMoney}
                      tickLine={false}
                      axisLine={false}
                      width={52}
                      tick={{ fontSize: 12, fill: "#6b7280" }}
                    />
                    <Tooltip
                      formatter={(value, name) => [formatMoney(Number(value)), name]}
                      contentStyle={{ fontSize: 12, borderRadius: 8 }}
                      cursor={{ fill: "#f3f4f6" }}
                    />
                    <ReferenceLine
                      x={MONTH_ABBR[Number(data!.month.slice(5)) - 1]}
                      stroke="#94a3b8"
                      strokeDasharray="4 4"
                    />
                    {view.categories.map((c, i) => (
                      <Bar
                        key={c}
                        dataKey={c}
                        stackId="gastos"
                        fill={EXPENSE_COLORS[i]}
                        stroke="#fff"
                        strokeWidth={1}
                        isAnimationActive={false}
                        className="cursor-pointer"
                        onClick={(bar) => {
                          openMonth(MONTH_ABBR.indexOf(bar.payload?.label));
                          setOpenCategory(c);
                        }}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : view.resPosted ? (
              <div className="px-4 pt-2 pb-4">
                <ExpenseSplit
                  parts={view.expenseMonth}
                  total={view.expenses}
                  selected={openCategory}
                  onSelect={toggleCategory}
                />
              </div>
            ) : (
              <p className="px-4 py-10 text-center text-sm text-gray-500">
                {monthName} todavía no está cerrado en Contabilidad.
              </p>
            )}

            {view.resPosted ? (
              // The month's table doubles as the charts' legend; a row opens its accounts.
              <div className="border-t">
                <p className="px-4 pt-3 pb-2 text-sm font-medium text-gray-900">
                  Gastos de {monthName}{" "}
                  <span className="font-normal text-gray-500">
                    contra {monthShort} {view.year - 1}
                  </span>
                </p>
                <Table className={cn(TABLE_CLASS, "table-fixed")}>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Categoría</TableHead>
                      <TableHead className={cn("text-right", COL_MONEY)}>Monto</TableHead>
                      <TableHead className={cn("text-right", COL_PERCENT)}>% gasto</TableHead>
                      <TableHead className={cn("text-right w-28", HIDE_BELOW_MD)}>% ingresos</TableHead>
                      <TableHead className={cn("text-right w-24", HIDE_BELOW_SM)}>Cambio</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {view.categories.map((c, i) => {
                      const open = openCategory === c;
                      const accounts = data!.gastos_cuentas[c] ?? [];
                      return (
                        <Fragment key={c}>
                          <TableRow className="cursor-pointer" onClick={() => toggleCategory(c)}>
                            <TableCell>
                              <button type="button" className="flex items-center gap-2 text-left" aria-expanded={open}>
                                <ChevronRight
                                  className={cn("w-4 h-4 shrink-0 text-gray-400 transition-transform", open && "rotate-90")}
                                  aria-hidden
                                />
                                <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: EXPENSE_COLORS[i] }} />
                                {c}
                              </button>
                            </TableCell>
                            <TableCell className="text-right num">{formatMoney(view.res.gastos[c])}</TableCell>
                            <TableCell className="text-right num">
                              {view.expenses ? percent(view.res.gastos[c] / view.expenses, 0) : "-"}
                            </TableCell>
                            <TableCell className={cn("text-right num", HIDE_BELOW_MD)}>
                              {view.res.ingresos ? percent(view.res.gastos[c] / view.res.ingresos) : "-"}
                            </TableCell>
                            <TableCell className={cn("text-right", HIDE_BELOW_SM)}>
                              <ChangeCell value={change(view.res.gastos[c], view.resLastYear?.gastos[c])} inverse />
                            </TableCell>
                          </TableRow>
                          {open &&
                            accounts.map((a) => (
                              // ! overrides the table's zebra and first-column styles for detail rows.
                              // Accounts with nothing this month only matter next to last year's
                              // amount, which phones don't show.
                              <TableRow
                                key={a.cuenta}
                                className={cn("!bg-white text-xs sm:text-sm [&_td]:py-2", !a.monto && "hidden sm:table-row")}
                              >
                                <TableCell className="pl-6 sm:pl-16 !font-normal !text-gray-600">{a.cuenta}</TableCell>
                                <TableCell className="text-right num text-gray-700">{formatMoney(a.monto)}</TableCell>
                                <TableCell className="text-right num text-gray-500">
                                  {view.expenses ? percent(a.monto / view.expenses, 1) : "-"}
                                </TableCell>
                                <TableCell className={cn("text-right num text-gray-500", HIDE_BELOW_MD)}>
                                  {view.res.ingresos ? percent(a.monto / view.res.ingresos) : "-"}
                                </TableCell>
                                <TableCell className={cn("text-right", HIDE_BELOW_SM)}>
                                  <ChangeCell value={change(a.monto, a.anterior)} inverse />
                                </TableCell>
                              </TableRow>
                            ))}
                        </Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <ul className="flex flex-wrap gap-x-4 gap-y-1.5 px-4 pt-2 pb-4 text-xs text-gray-600">
                {view.categories.map((c, i) => (
                  <li key={c} className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: EXPENSE_COLORS[i] }} />
                    {c}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {view.resPosted && (
            <>
              <SectionHeading title="Indicadores">
                Mismas fórmulas que el modelo financiero mensual, con los saldos de Contabilidad al cierre de cada mes.
                Las metas son provisionales: vienen de ese modelo, hecho para otra organización.
              </SectionHeading>

              {/* Phones: one row per indicator with its trend; tapping shows every month. */}
              <Card className="sm:hidden">
                <div className="px-4 py-2">
                  <div className="hidden sm:grid grid-cols-[15rem_1fr_7rem_10rem] gap-x-4 pt-1 pb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    <span>Indicador</span>
                    <span>Tendencia {view.year}</span>
                    <span className="text-right">{MONTH_ABBR[Number(data!.month.slice(5)) - 1]}</span>
                    <span className="text-right">Referencia</span>
                  </div>
                  {INDICATORS.map((ind) => {
                    const value = view.indicator?.[ind.key];
                    const target = TARGETS.find((t) => t.key === ind.key);
                    const ok = target && typeof value === "number" ? target.ok(value) : null;
                    const average = view.indicatorAverage(ind.key);
                    const series = view.indicatorMonths.map((mm) => mm.row?.[ind.key] ?? null);
                    const open = openIndicator === ind.key;
                    const show = (v: number | null | undefined) =>
                      formatIndicator(v, ind.unit) + (ind.unit === "dias" && typeof v === "number" ? " días" : "");
                    return (
                      <Fragment key={ind.key}>
                        {ind.group && (
                          <p className="mt-3 border-b border-slate-200 pb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                            {ind.group}
                          </p>
                        )}
                        <div
                          className="grid cursor-pointer grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 border-b border-slate-100 py-2 sm:grid-cols-[15rem_1fr_7rem_10rem]"
                          onClick={() => setOpenIndicator(open ? null : ind.key)}
                        >
                          <button type="button" className="flex items-center gap-1 text-left text-sm text-gray-800" aria-expanded={open}>
                            <ChevronRight
                              className={cn("w-4 h-4 shrink-0 text-gray-400 transition-transform", open && "rotate-90")}
                              aria-hidden
                            />
                            {ind.label}
                          </button>
                          <span
                            className={cn(
                              "flex items-center justify-end gap-1 text-sm num font-semibold sm:col-start-3 sm:row-start-1",
                              indicatorTone(ind.key, value),
                            )}
                          >
                            {ok !== null &&
                              (ok ? (
                                <CircleCheck className="w-4 h-4" aria-label="Cumple la meta" />
                              ) : (
                                <CircleAlert className="w-4 h-4" aria-label="No cumple la meta" />
                              ))}
                            {show(value)}
                          </span>
                          <div className="col-span-2 pl-5 sm:col-span-1 sm:col-start-2 sm:row-start-1 sm:pl-0">
                            <Sparkline values={series} reference={average} />
                          </div>
                          <span className="hidden sm:block text-right text-xs leading-tight text-gray-500">
                            <span className="whitespace-nowrap">
                              prom. {view.year - 1}: <span className="num">{show(average)}</span>
                            </span>
                            {target && (
                              <>
                                <br />
                                meta {target.goal}
                              </>
                            )}
                          </span>
                        </div>
                        {open && (
                          <div className="space-y-2 border-b border-slate-100 bg-slate-50 px-5 py-3 text-sm">
                            <p className="text-xs text-gray-500">
                              Promedio mensual {view.year - 1}: <span className="num">{show(average)}</span>
                              {target && ` · meta ${target.goal}`}
                            </p>
                            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                              {view.indicatorMonths.map((mm, i) => (
                                <li
                                  key={mm.label}
                                  className={cn(
                                    "num",
                                    i === view.indicatorMonths.length - 1 ? "font-semibold text-gray-900" : "text-gray-600",
                                  )}
                                >
                                  <span className="text-gray-400">{mm.label}</span> {show(mm.row?.[ind.key])}
                                </li>
                              ))}
                            </ul>
                            {ind.note && <p className="text-xs text-gray-500">{ind.note}</p>}
                          </div>
                        )}
                      </Fragment>
                    );
                  })}
                </div>
              </Card>

              {/* Tablet and desktop: the full table, as in her model, with the targets in it. */}
              <Card className="hidden sm:block">
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-base">Indicadores por mes</CardTitle>
                  <CardDescription>
                    {view.year} y promedio mensual de {view.year - 1}; días = saldo al cierre entre el flujo diario
                    acumulado del año
                  </CardDescription>
                </CardHeader>
                <Table className={TABLE_CLASS} ref={indicatorTable}>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 bg-inherit min-w-[11rem]">Indicador</TableHead>
                      <TableHead className="text-right">Meta</TableHead>
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
                    {INDICATORS.map((ind) => {
                      const target = TARGETS.find((t) => t.key === ind.key);
                      return (
                        <Fragment key={ind.key}>
                          {ind.group && (
                            // Group label row: ! overrides the table's row and first-column styles.
                            // The label sits in the first (pinned) cell alone - a cell spanning the
                            // whole row can't stay pinned when the table scrolls sideways.
                            <tr className="border-b !bg-slate-200">
                              <td className="sticky left-0 bg-slate-200 px-4 py-1.5 text-[11px] !font-semibold uppercase tracking-wide whitespace-nowrap !text-slate-600">
                                {ind.group}
                              </td>
                              <td colSpan={view.indicatorMonths.length + 2} />
                            </tr>
                          )}
                          <TableRow>
                            <TableCell className="sticky left-0 bg-inherit">
                              {ind.label}
                              {ind.note && <span className="text-gray-400">{noteMark(ind.key)}</span>}
                            </TableCell>
                            <TableCell className="text-right num whitespace-nowrap text-gray-500">{target?.goal}</TableCell>
                            <TableCell className="text-right num text-gray-500">
                              {formatIndicator(view.indicatorAverage(ind.key), ind.unit)}
                            </TableCell>
                            {view.indicatorMonths.map((mm, i) => {
                              const value = mm.row?.[ind.key];
                              const picked = i === view.indicatorMonths.length - 1;
                              // The semáforo: the picked month's value carries the target's icon.
                              const ok = picked && target && typeof value === "number" ? target.ok(value) : null;
                              return (
                                <TableCell
                                  key={mm.label}
                                  className={cn(
                                    "text-right num",
                                    indicatorTone(ind.key, value),
                                    picked && "bg-blue-50 font-semibold",
                                  )}
                                >
                                  <span className="inline-flex items-center justify-end gap-1 whitespace-nowrap">
                                    {ok !== null &&
                                      (ok ? (
                                        <CircleCheck className="w-4 h-4" aria-label="Cumple la meta" />
                                      ) : (
                                        <CircleAlert className="w-4 h-4" aria-label="No cumple la meta" />
                                      ))}
                                    {formatIndicator(value, ind.unit)}
                                  </span>
                                </TableCell>
                              );
                            })}
                          </TableRow>
                        </Fragment>
                      );
                    })}
                  </TableBody>
                </Table>
                <div className="space-y-1 px-4 py-3 text-xs text-gray-500">
                  {NOTED.map((ind) => (
                    <p key={ind.key}>
                      {noteMark(ind.key)} {ind.label}: {ind.note}
                    </p>
                  ))}
                </div>
              </Card>
            </>
          )}
        </>
      )}
    </main>
  );
}
