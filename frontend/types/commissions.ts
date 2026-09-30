export type Zone = "ZONA1" | "ZONA2" | "OFICINA" | "SERVICIOS" | "PUNTOVENTA";

export type Category = "R" | "R_NW" | "R_CHEM" | "R_FAN" | "B" | "B_MIPRO" | "B_BOVI" | "S" | "ZERO";

export interface CommissionLine {
  invoice_id: number;
  folio: number;
  // Bare ERP client id - opens the client history (see ClientLink).
  client_id: number;
  cliente: string;
  zone: Zone;
  producto_codigo: string | null;
  producto_nombre: string;
  category: Category | null;
  rate_code: string | null;
  quantity: number | null;
  unit_amount: number | null;
  net_amount: number;
  rate: number | null;
  days_late: number;
  paid_date: string;
  due_date: string | null;
  commission: number;
  // Management-only manual correction flags (see InvoiceCommissionOverride) -
  // excluded rows are zeroed but stay visible; manual rows replace the
  // computed line with a flat management-entered amount.
  excluded?: boolean;
  manual?: boolean;
}

export interface InvoiceSearchResult {
  invoice_id: number;
  folio: number;
  cliente: string;
  fecha: string;
  total: number;
  zone: Zone | null;
}

// An invoice listed inside a Comisiones warning; `date` is when it was paid
// in Comercial (missing póliza) or when the credit note was applied.
export interface WarningInvoice {
  invoice_id: number;
  folio_display: string;
  client_id: number;
  cliente: string;
  zone: Zone;
  total: number;
  date: string;
}

// Paid in Comercial during the month, not yet registered in Contabilidad.
export interface UnresolvedPaymentDate {
  count: number;
  total_amount: number;
  rows: WarningInvoice[];
  note: string;
}

// Settled during the month only with credit notes or returns.
export interface CreditNoted {
  count: number;
  total_amount: number;
  rows: WarningInvoice[];
  note: string;
}

export interface CommissionsSummary {
  date_from: string;
  date_to: string;
  zone_totals: Partial<Record<Zone, number>>;
  lines: CommissionLine[];
  unresolved_payment_date: UnresolvedPaymentDate;
  credit_noted: CreditNoted;
}
