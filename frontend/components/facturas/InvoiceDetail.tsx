"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { STATUS_INFO } from "@/components/corte-de-caja/date-difference-status";
import { cn, formatMoney } from "@/lib/utils";
import { Notice } from "@/components/notice";
import { formatDay } from "@/lib/dates";
import { zoneLabel } from "@/lib/zones";
import { apiFetch } from "@/lib/api";
import ClientLink from "@/components/facturas/ClientLink";
import InvoiceLink from "@/components/facturas/InvoiceLink";
import type {
  InvoiceDetail,
  InvoiceSearchResult,
  PaymentPair,
  Poliza,
} from "@/types/facturas";

// Everything about one invoice - shared by the Consulta de factura page and
// the invoice dialog any other screen opens (see InvoiceDialog).



export async function getJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path, { cache: "no-store" });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(json.error ?? `El servidor respondió ${res.status}`);
  return json as T;
}

function StatusBadges({ cancelada, pendiente, total, vencida }: {
  cancelada: boolean;
  pendiente: number;
  total: number;
  vencida?: boolean;
}) {
  if (cancelada) {
    return <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200">Cancelada</Badge>;
  }
  if (pendiente < 1) {
    return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">Pagada</Badge>;
  }
  return (
    <>
      <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200">
        {pendiente < total ? "Pago parcial" : "Sin pagar"}
      </Badge>
      {vencida && (
        <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200">Vencida</Badge>
      )}
    </>
  );
}

export function InvoiceList({ results, onSelect }: {
  results: InvoiceSearchResult[];
  onSelect: (id: number) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border bg-white">
      <Table className="min-w-[800px]">
        <TableHeader>
          <TableRow>
            <TableHead>Factura</TableHead>
            <TableHead>Fecha</TableHead>
            <TableHead>Cliente</TableHead>
            <TableHead>Zona</TableHead>
            <TableHead className="text-right">Total</TableHead>
            <TableHead className="text-right">Pendiente</TableHead>
            <TableHead>Estado</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map((r) => (
            <TableRow
              key={r.invoice_id}
              onClick={() => onSelect(r.invoice_id)}
              className="cursor-pointer hover:bg-slate-50"
            >
              <TableCell className="num">
                {r.folio_display}
              </TableCell>
              <TableCell className="whitespace-nowrap">{formatDay(r.fecha)}</TableCell>
              <TableCell className="max-w-72 truncate" title={r.cliente}>
                <ClientLink clientId={r.client_id} label={r.cliente} />
              </TableCell>
              <TableCell className="text-xs">{zoneLabel(r.zona)}</TableCell>
              <TableCell className="text-right num">{formatMoney(r.total)}</TableCell>
              <TableCell className="text-right num">{formatMoney(r.pendiente)}</TableCell>
              <TableCell className="whitespace-nowrap">
                <StatusBadges cancelada={r.cancelada} pendiente={r.pendiente} total={r.total} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function Section({ title, count, children }: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-gray-900">
        {title}
        {count !== undefined && <span className="ml-1 text-gray-400 font-normal">({count})</span>}
      </h2>
      {children}
    </section>
  );
}

export function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500">{label}</span>
      <span className="text-sm text-gray-900">{value || "-"}</span>
    </div>
  );
}

export function StatCard({ label, value, sub, tone }: {
  label: string;
  value: string;
  sub?: React.ReactNode;
  tone?: "ok" | "bad";
}) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-white p-4",
        tone === "bad" && "border-red-300 bg-red-50",
      )}
    >
      <p className="text-sm text-gray-600">{label}</p>
      <p className="text-lg font-semibold text-gray-900">{value}</p>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

export function InvoiceDetailView({ detail, onSelect }: {
  detail: InvoiceDetail;
  onSelect: (id: number) => void;
}) {
  const { invoice, balance, flags } = detail;
  const credits = detail.applications.filter((a) => a.doc_type !== 9);
  const cashMismatch = Math.abs(balance.comercial_cash - balance.contabilidad_cash) > 1;
  const paymentPolizas = detail.polizas.filter((p) => p.is_payment);
  const otherPolizas = detail.polizas.filter((p) => !p.is_payment);

  return (
    <div className="flex flex-col gap-8">
      {/* Header */}
      <div className="rounded-lg border bg-white p-5 flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-2xl font-bold font-mono text-gray-900">{invoice.folio_display}</span>
          <StatusBadges
            cancelada={invoice.cancelada}
            pendiente={invoice.pendiente}
            total={invoice.total}
            vencida={invoice.vencida}
          />
        </div>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Field label="Cliente" value={<ClientLink clientId={invoice.client_id} label={invoice.cliente} />} />
          <Field label="RFC" value={invoice.rfc} />
          <Field label="Zona" value={zoneLabel(invoice.zona)} />
          <Field label="Capturó" value={invoice.usuario} />
          <Field label="Fecha" value={formatDay(invoice.fecha)} />
          <Field label="Vencimiento" value={formatDay(invoice.vencimiento)} />
          <Field label="Referencia" value={invoice.referencia} />
          <Field label="Observaciones" value={invoice.observaciones} />
        </div>
      </div>

      {/* What to fix */}
      {flags.length === 0 ? (
        <Notice
          tone="ok"
          summary="Comercial y Contabilidad cuadran: cada pago tiene su póliza, con la misma fecha e importe."
        />
      ) : (
        <Section title="Revisar en Contpaqi" count={flags.length}>
          <div className="flex flex-col gap-2">
            {flags.map((flag, i) => (
              <Notice key={i} tone={flag.level} summary={flag.text} />
            ))}
          </div>
        </Section>
      )}

      {/* Balance */}
      <Section title="Cuadre">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard label="Total factura" value={formatMoney(balance.total)} />
          <StatCard
            label="Pagado según Comercial"
            value={formatMoney(balance.pagado_comercial)}
            sub={
              <>
                Pagos del cliente {formatMoney(balance.comercial_cash)}
                {balance.comercial_credit > 0 && (
                  <> · Notas de crédito y devoluciones {formatMoney(balance.comercial_credit)}</>
                )}
                {balance.comercial_other > 0 && <> · Otros {formatMoney(balance.comercial_other)}</>}
              </>
            }
          />
          <StatCard
            label="Cobrado según Contabilidad"
            value={formatMoney(balance.contabilidad_cash)}
            sub={`${balance.polizas_de_cobro} ${balance.polizas_de_cobro === 1 ? "póliza" : "pólizas"} de cobro`}
            tone={cashMismatch && !invoice.cancelada ? "bad" : undefined}
          />
          <StatCard label="Pendiente" value={formatMoney(balance.pendiente)} />
        </div>
      </Section>

      {/* Payments: Comercial vs Contabilidad */}
      <Section title="Pagos: Comercial y Contabilidad" count={detail.payments.length}>
        {detail.payments.length === 0 ? (
          <p className="text-sm text-gray-500">Ningún pago del cliente registrado.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border bg-white">
            <Table className="min-w-[800px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Estado</TableHead>
                  <TableHead>Comercial</TableHead>
                  <TableHead>Contabilidad</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.payments.map((pair, i) => (
                  <PaymentPairRow key={i} pair={pair} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>

      {(credits.length > 0 || detail.unapplied_returns.length > 0) && (
        <Section title="Notas de crédito y devoluciones" count={credits.length + detail.unapplied_returns.length}>
          <div className="overflow-x-auto rounded-lg border bg-white">
            <Table className="min-w-[700px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Documento</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead className="text-right">Aplicado a esta factura</TableHead>
                  <TableHead className="text-right">Total del documento</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {credits.map((a) => (
                  <TableRow key={`a${a.documento_id}`}>
                    <TableCell className="whitespace-nowrap">
                      {a.tipo} <span className="num text-gray-500">{a.documento}</span>
                      {a.cancelado && <span className="ml-1 text-xs text-red-700">(cancelado)</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{formatDay(a.fecha)}</TableCell>
                    <TableCell className="text-right num">{formatMoney(a.amount)}</TableCell>
                    <TableCell className="text-right num">{formatMoney(a.documento_total)}</TableCell>
                  </TableRow>
                ))}
                {detail.unapplied_returns.map((r) => (
                  <TableRow key={`r${r.documento_id}`}>
                    <TableCell className="whitespace-nowrap">
                      {r.tipo} <span className="num text-gray-500">{r.documento}</span>
                      {r.cancelado && <span className="ml-1 text-xs text-red-700">(cancelado)</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">{formatDay(r.fecha)}</TableCell>
                    <TableCell className="text-right text-xs text-amber-700">No aplicada</TableCell>
                    <TableCell className="text-right num">{formatMoney(r.total)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      )}

      {detail.referencing_payments.length > 0 && (
        <Section title="Pagos que mencionan este folio, aplicados a otra factura" count={detail.referencing_payments.length}>
          <div className="overflow-x-auto rounded-lg border bg-white">
            <Table className="min-w-[700px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Pago</TableHead>
                  <TableHead>Fecha</TableHead>
                  <TableHead className="text-right">Importe</TableHead>
                  <TableHead>Referencia</TableHead>
                  <TableHead>Aplicado a</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {detail.referencing_payments.map((p) => (
                  <TableRow key={p.documento_id}>
                    <TableCell className="num">{p.documento}</TableCell>
                    <TableCell className="whitespace-nowrap">{formatDay(p.fecha)}</TableCell>
                    <TableCell className="text-right num">{formatMoney(p.total)}</TableCell>
                    <TableCell className="text-xs">{p.referencia}</TableCell>
                    <TableCell className="num">
                      {p.applied_to.length ? p.applied_to.join(", ") : "Ninguna factura"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      )}

      <Section title="Pólizas de cobro que citan la factura" count={paymentPolizas.length}>
        {paymentPolizas.length === 0 ? (
          <p className="text-sm text-gray-500">Ninguna póliza de cobro cita esta factura.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {paymentPolizas.map((p) => <PolizaCard key={p.poliza_id} poliza={p} />)}
          </div>
        )}
      </Section>

      <Section title="Renglones" count={detail.lines.length}>
        <div className="overflow-x-auto rounded-lg border bg-white">
          <Table className="min-w-[900px]">
            <TableHeader>
              <TableRow>
                <TableHead>Código</TableHead>
                <TableHead>Producto</TableHead>
                <TableHead className="text-right">Cantidad</TableHead>
                <TableHead className="text-right">Precio</TableHead>
                <TableHead className="text-right">Descuento</TableHead>
                <TableHead className="text-right">IVA</TableHead>
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {detail.lines.map((l) => (
                <TableRow key={l.numero}>
                  <TableCell className="num">{l.codigo}</TableCell>
                  <TableCell className="max-w-96 truncate" title={l.producto}>{l.producto}</TableCell>
                  <TableCell className="text-right num">{l.cantidad.toLocaleString("es-MX")}</TableCell>
                  <TableCell className="text-right num">{formatMoney(l.precio)}</TableCell>
                  <TableCell className="text-right num">{l.descuento ? formatMoney(l.descuento) : "-"}</TableCell>
                  <TableCell className="text-right num">{formatMoney(l.iva)}</TableCell>
                  <TableCell className="text-right num">{formatMoney(l.total)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>

      {otherPolizas.length > 0 && (
        <Section title="Otras pólizas que citan la factura" count={otherPolizas.length}>
          <p className="-mt-2 text-sm text-gray-500">
            Ventas del día, cancelaciones, devoluciones... No cuentan como cobro.
          </p>
          <div className="flex flex-col gap-2">
            {otherPolizas.map((p) => <PolizaCard key={p.poliza_id} poliza={p} />)}
          </div>
        </Section>
      )}

      {detail.same_folio.length > 0 && (
        <Section title="Otras facturas con el mismo folio" count={detail.same_folio.length}>
          <InvoiceList results={detail.same_folio} onSelect={onSelect} />
        </Section>
      )}
    </div>
  );
}

function PaymentPairRow({ pair }: { pair: PaymentPair }) {
  const info = STATUS_INFO[pair.status];
  const highlight = pair.status === "distinto_mes" || pair.status === "monto_distinto";
  return (
    <TableRow className="align-top">
      <TableCell className="whitespace-nowrap">
        <Badge variant="outline" className={info.badge} title={info.description}>
          {info.label}
        </Badge>
      </TableCell>
      <TableCell className="text-xs">
        {pair.comercial.length === 0 ? (
          <>
            <span className="text-gray-400">Sin pago aplicado</span>
            {pair.cited && <CitedElsewhere cited={pair.cited} verb="aplicado a" />}
          </>
        ) : (
          pair.comercial.map((c, i) => (
            <div key={i} className="whitespace-nowrap">
              <span className={cn("font-medium", highlight && "text-red-700")}>{formatDay(c.date)}</span>
              <span className="ml-1 text-gray-500">{c.documento}</span>
              <span className="ml-2 num">{formatMoney(c.amount)}</span>
              {c.applied_date !== c.date && (
                <span className="block text-gray-400">aplicado a la factura el {formatDay(c.applied_date)}</span>
              )}
            </div>
          ))
        )}
      </TableCell>
      <TableCell className="text-xs">
        {pair.contabilidad.length === 0 ? (
          <>
            <span className="text-gray-400">Sin póliza</span>
            {pair.cited && <CitedElsewhere cited={pair.cited} verb="cita" />}
          </>
        ) : (
          pair.contabilidad.map((l, i) => (
            <div key={i} className="whitespace-nowrap">
              <span className={cn("font-medium", highlight && "text-red-700")}>{formatDay(l.date)}</span>
              <span className="ml-1 text-gray-500">Póliza {l.polizas.join(", ")}</span>
              <span className="ml-2 num">{formatMoney(l.amount)}</span>
            </div>
          ))
        )}
      </TableCell>
    </TableRow>
  );
}

// folio_equivocado: the matching payment or poliza sits on a look-alike folio.
function CitedElsewhere({ cited, verb }: { cited: NonNullable<PaymentPair["cited"]>; verb: string }) {
  return (
    <span className="block whitespace-nowrap text-red-700">
      {formatDay(cited.date)} {cited.documento} {verb}{" "}
      <InvoiceLink invoiceId={cited.invoice_id} label={cited.folio_display} />
    </span>
  );
}

// A payment poliza covering several invoices has one client line per
// invoice; by default only this invoice's lines and the bank line are shown.
function PolizaCard({ poliza }: { poliza: Poliza }) {
  const [open, setOpen] = useState(false);
  const [allLines, setAllLines] = useState(false);
  const relevant = poliza.lines.filter((l) => l.cites_invoice || l.is_bank);
  const lines = allLines ? poliza.lines : relevant;
  const hidden = poliza.lines.length - relevant.length;

  return (
    <div className={cn("rounded-lg border bg-white", !poliza.counted && poliza.is_payment && "border-dashed")}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-left text-sm hover:bg-slate-50"
      >
        {open ? <ChevronDown className="w-4 h-4 text-gray-400" /> : <ChevronRight className="w-4 h-4 text-gray-400" />}
        <span className="font-medium text-gray-900">{poliza.label}</span>
        <span className="text-gray-600">{formatDay(poliza.fecha)}</span>
        <span className="text-gray-500 truncate max-w-72" title={poliza.concepto}>{poliza.concepto}</span>
        {poliza.bank && <span className="text-xs text-gray-500">{poliza.bank}</span>}
        {poliza.is_payment && (
          <span className="ml-auto num">{formatMoney(poliza.amount)}</span>
        )}
        {poliza.is_payment && !poliza.counted && (
          <span className="basis-full pl-8 text-xs text-amber-700">No se cuenta: {poliza.not_counted_reason}</span>
        )}
      </button>
      {open && (
        <div className="border-t px-4 py-3 flex flex-col gap-2">
          <div className="overflow-x-auto">
            <Table className="min-w-[800px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Cuenta</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead className="text-right">Importe</TableHead>
                  <TableHead>Referencia</TableHead>
                  <TableHead>Concepto</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lines.map((l) => (
                  <TableRow key={l.numero} className={cn(l.cites_invoice && "bg-sky-50/60")}>
                    <TableCell className="text-xs">
                      <span className="font-mono text-gray-500">{l.codigo}</span> {l.cuenta}
                    </TableCell>
                    <TableCell className="text-xs">{l.tipo}</TableCell>
                    <TableCell className="text-right num">{formatMoney(l.importe)}</TableCell>
                    <TableCell className="num">{l.referencia}</TableCell>
                    <TableCell className="text-xs max-w-72 truncate" title={l.concepto}>{l.concepto}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {hidden > 0 && (
            <button
              type="button"
              onClick={() => setAllLines((a) => !a)}
              className="self-start text-xs font-medium text-slate-700 underline"
            >
              {allLines ? "Ver solo las líneas de esta factura" : `Ver todas las líneas de la póliza (${hidden} más)`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
