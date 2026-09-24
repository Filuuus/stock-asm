export type Zone = "ZONA1" | "ZONA2" | "OFICINA" | "SERVICIOS" | "PUNTOVENTA";

export type Category = "R" | "R_NW" | "R_CHEM" | "R_FAN" | "B" | "S" | "ZERO";

export interface CommissionLine {
  invoice_id: number;
  folio: number;
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

export interface UnresolvedPaymentDate {
  count: number;
  total_amount: number;
  note: string;
}

export interface CreditNoted {
  count: number;
  total_amount: number;
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
