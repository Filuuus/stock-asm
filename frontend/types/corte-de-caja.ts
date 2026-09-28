import type { Zone } from "@/types/commissions";

export type PaymentMethod = "EFECTIVO" | "TERMINAL" | "CHEQUE" | "TRANSFERENCIA";

// How much to trust an unconfirmed suggested payment method: "alta" comes from
// the client's own confirmed history at the same bank, "media" from the
// client's history at any bank, "baja" only from the receiving bank (a person
// should choose).
export type SuggestionConfidence = "alta" | "media" | "baja";

export interface CorteDeCajaRow {
  invoice_id: number;
  event_date: string;
  folio: number;
  // "B 19758" - the tax series plus the bare folio, the way the accountant's
  // own sheet writes it. Prefer this over `folio` for display.
  folio_display: string;
  cliente: string;
  // The client's Contabilidad account (103-107-408), when resolvable - null
  // for the generic "Ventas Publico en General" account.
  cuenta: string | null;
  zone: Zone;
  due_date: string | null;
  category: string | null;
  amount: number;
  // true = a partial installment; the invoice isn't paid off yet.
  abono: boolean;
  excluded: boolean;
  // The real bank account that received the money (from the Contabilidad
  // ledger's own bank-debit line), when traceable - null for the handful
  // of ledger events that split across more than one account in the same
  // journal entry.
  bank: string | null;
  // payment_method is always the EFFECTIVE value - either a human-confirmed
  // tag, or (when unconfirmed) an auto-suggestion derived from `bank`
  // (bank known -> Transferencia, the dominant real case; the rare Caja
  // Chica case -> Efectivo). payment_method_confirmed tells you which.
  payment_method: PaymentMethod | "";
  payment_method_confirmed: boolean;
  suggestion_confidence: SuggestionConfidence | null;
  suggestion_reason: string;
  // Normalized bank key and bare client id - sent back with a confirmed tag so
  // the server can learn each client's habits.
  bank_code: string;
  client_id: number;
  reviewed: boolean;
  reviewed_by: string | null;
  note: string;
}

export interface UnclassifiedInfo {
  count: number;
  total_amount: number;
  note: string;
}

export interface SuggestionTier {
  count: number;
  total_amount: number;
}

export interface UnconfirmedInfo {
  count: number;
  total_amount: number;
  note: string;
}

// A payment Contpaqi Comercial records but Contabilidad has no poliza for.
// Listed for the accountant to fix in Contpaqi, never part of the corte:
// every date in the corte must be the Contabilidad date.
export interface SinPolizaRow {
  invoice_id: number;
  comercial_date: string;
  folio_display: string;
  cliente: string;
  zone: Zone;
  // A payment dated before its own invoice usually means a wrong reference.
  invoice_date: string;
  invoice_total: number;
  amount: number;
  referencia: string;
  // How many other invoices the same Comercial payment names - its amount is
  // the whole payment, not this invoice's share.
  shared_with: number;
}

export interface SinPolizaInfo {
  count: number;
  total_amount: number;
  rows: SinPolizaRow[];
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
  suggestions: Record<SuggestionConfidence, SuggestionTier>;
  unconfirmed: UnconfirmedInfo;
  sin_poliza: SinPolizaInfo;
}
