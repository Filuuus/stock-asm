import type { Zone } from "@/types/commissions";
import type { DateDifferenceStatus } from "@/types/corte-de-caja";

export interface InvoiceSearchResult {
  invoice_id: number;
  folio_display: string;
  // false when the user typed a series and this invoice is in another one.
  series_match: boolean;
  fecha: string;
  cliente: string;
  zona: Zone | string | null;
  total: number;
  pendiente: number;
  cancelada: boolean;
}

export interface InvoiceHeader {
  invoice_id: number;
  folio_display: string;
  serie: string;
  folio: number;
  fecha: string;
  vencimiento: string | null;
  cliente: string;
  rfc: string;
  zona: Zone | string | null;
  agente: string;
  total: number;
  pendiente: number;
  cancelada: boolean;
  vencida: boolean;
  usuario: string;
  referencia: string;
  observaciones: string;
}

export interface InvoiceLine {
  numero: number;
  codigo: string;
  producto: string;
  cantidad: number;
  precio: number;
  descuento: number;
  neto: number;
  iva: number;
  total: number;
}

export interface InvoiceBalance {
  total: number;
  pendiente: number;
  pagado_comercial: number;
  // Applied in Comercial by customer payments / by credit notes and returns /
  // by any other document type.
  comercial_cash: number;
  comercial_credit: number;
  comercial_other: number;
  // Sum of the payment polizas that count for this invoice.
  contabilidad_cash: number;
  polizas_de_cobro: number;
  ok: boolean;
}

export type FlagLevel = "error" | "warning" | "info";

export interface InvoiceFlag {
  level: FlagLevel;
  text: string;
}

// "monto_distinto": a Comercial payment and a poliza a few days apart whose
// amounts differ slightly - most likely the same payment typed differently.
export type PaymentPairStatus = DateDifferenceStatus | "monto_distinto";

export interface PaymentPair {
  status: PaymentPairStatus;
  comercial: {
    date: string;
    applied_date: string;
    amount: number;
    documento: string;
  }[];
  contabilidad: { date: string; amount: number; polizas: string[] }[];
}

export interface InvoiceApplication {
  documento_id: number;
  doc_type: number;
  tipo: string;
  documento: string;
  fecha: string;
  applied_date: string;
  amount: number;
  documento_total: number;
  cancelado: boolean;
  referencia: string;
  usuario: string;
}

export interface UnappliedReturn {
  documento_id: number;
  tipo: string;
  documento: string;
  fecha: string;
  total: number;
  cancelado: boolean;
}

export interface ReferencingPayment {
  documento_id: number;
  tipo: string;
  documento: string;
  fecha: string;
  total: number;
  referencia: string;
  cancelado: boolean;
  // Invoices Comercial applied this payment to instead ("F 20734").
  applied_to: string[];
}

export interface PolizaLine {
  numero: number;
  codigo: string;
  cuenta: string;
  tipo: "Cargo" | "Abono";
  importe: number;
  referencia: string;
  concepto: string;
  cites_invoice: boolean;
  // The line debiting the bank/cash account the money landed in.
  is_bank: boolean;
}

export interface Poliza {
  poliza_id: number;
  label: string;
  fecha: string;
  concepto: string;
  is_payment: boolean;
  // Net of the lines citing this invoice (abonos add, cargos subtract).
  amount: number;
  names_client: boolean;
  bank: string | null;
  counted: boolean;
  not_counted_reason: string;
  lines: PolizaLine[];
}

export interface InvoiceDetail {
  invoice: InvoiceHeader;
  lines: InvoiceLine[];
  balance: InvoiceBalance;
  flags: InvoiceFlag[];
  payments: PaymentPair[];
  applications: InvoiceApplication[];
  unapplied_returns: UnappliedReturn[];
  referencing_payments: ReferencingPayment[];
  polizas: Poliza[];
  same_folio: InvoiceSearchResult[];
}
