import type { Zone } from "@/types/commissions";

export type PaymentMethod = "EFECTIVO" | "TERMINAL" | "CHEQUE" | "TRANSFERENCIA";

export interface CorteDeCajaRow {
  invoice_id: number;
  event_date: string;
  folio: number;
  cliente: string;
  zone: Zone;
  due_date: string | null;
  category: string | null;
  amount: number;
  // null = amount came from the Comercial-side fallback (no per-invoice
  // split available), so whether it was a partial installment can't be
  // determined the way it can from the ledger.
  abono: boolean | null;
  source: "ledger" | "fallback";
  approximate: boolean;
  excluded: boolean;
  // The real bank account that received the money (from the Contabilidad
  // ledger's own bank-debit line), when traceable - null for fallback-
  // sourced events or a handful of ledger events that split across more
  // than one account in the same journal entry.
  bank: string | null;
  // payment_method is always the EFFECTIVE value - either a human-confirmed
  // tag, or (when unconfirmed) an auto-suggestion derived from `bank`
  // (bank known -> Transferencia, the dominant real case; the rare Caja
  // Chica case -> Efectivo). payment_method_confirmed tells you which.
  payment_method: PaymentMethod | "";
  payment_method_confirmed: boolean;
  reviewed: boolean;
  reviewed_by: string | null;
  note: string;
}

export interface UnclassifiedInfo {
  count: number;
  total_amount: number;
  note: string;
}

export interface UnconfirmedInfo {
  count: number;
  total_amount: number;
  note: string;
}

export interface ApproximateInfo {
  count: number;
  note: string;
}

export interface CorteDeCajaSummary {
  date_from: string;
  date_to: string;
  zone_totals: Partial<Record<Zone, number>>;
  method_totals: Partial<Record<PaymentMethod, number>>;
  cash_drawer_total: number;
  rows: CorteDeCajaRow[];
  unclassified: UnclassifiedInfo;
  unconfirmed: UnconfirmedInfo;
  approximate: ApproximateInfo;
}
