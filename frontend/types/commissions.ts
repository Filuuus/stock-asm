export type Zone = "ZONA1" | "ZONA2" | "OFICINA" | "SERVICIOS" | "PUNTOVENTA";

export type Category = "R" | "B" | "S" | "ZERO";

export interface CommissionLine {
  invoice_id: number;
  folio: number;
  cliente: string;
  zone: Zone;
  producto_codigo: string;
  producto_nombre: string;
  category: Category;
  rate_code: string | null;
  quantity: number;
  unit_amount: number | null;
  net_amount: number;
  rate: number;
  days_late: number;
  paid_date: string;
  due_date: string | null;
  commission: number;
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
