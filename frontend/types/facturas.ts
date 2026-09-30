import type { Zone } from "@/types/commissions";
import type { DateDifferenceStatus } from "@/types/corte-de-caja";

export interface InvoiceSearchResult {
  invoice_id: number;
  folio_display: string;
  // false when the user typed a series and this invoice is in another one.
  series_match: boolean;
  fecha: string;
  client_id: number;
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
  client_id: number;
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

export interface PaymentPair {
  status: DateDifferenceStatus;
  comercial: {
    date: string;
    applied_date: string;
    amount: number;
    documento: string;
  }[];
  contabilidad: { date: string; amount: number; polizas: string[] }[];
  // folio_equivocado only: the other side, on the look-alike invoice.
  cited: {
    invoice_id: number;
    folio_display: string;
    documento: string;
    date: string;
    amount: number;
  } | null;
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

export type ClientInvoiceStatus = "pagada" | "pendiente" | "vencida" | "cancelada";

export interface ClientInvoice {
  invoice_id: number;
  folio_display: string;
  fecha: string;
  vencimiento: string | null;
  zona: Zone | string | null;
  total: number;
  pendiente: number;
  comercial_cash: number;
  comercial_credit: number;
  contabilidad_cash: number;
  // The day the payment polizas covered the part paid with money - the
  // Contabilidad date, as in the corte and commissions. Null when unpaid,
  // settled only by credit notes, or the polizas never cover it.
  paid_date: string | null;
  // Paid: paid_date - vencimiento. Overdue: days past due so far.
  days_late: number | null;
  status: ClientInvoiceStatus;
  // Comercial's money and the counted polizas agree (the invoice detail's
  // "Cuadre"; the detail also checks each payment's date and amount).
  cuadra: boolean;
}

export interface ClientHistory {
  client: {
    client_id: number;
    // Same as the client's account in Contabilidad (103-104-977).
    codigo: string;
    cliente: string;
    rfc: string;
    zona: Zone | string | null;
    dias_credito: number | null;
    limite_credito: number;
    alta: string | null;
    activo: boolean;
  };
  summary: {
    // Start of the recent period; null when the full history was asked for.
    since: string | null;
    facturado: number;
    facturas: number;
    // All open invoices, however old.
    saldo_pendiente: number;
    facturas_pendientes: number;
    vencido: number;
    facturas_vencidas: number;
    pagadas_con_fecha: number;
    pagadas_a_tiempo: number;
    promedio_dias_atraso: number | null;
    no_cuadran: number;
  };
  invoices: ClientInvoice[];
  full: boolean;
}
