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
  // Bare ERP client id - opens the client history (see ClientLink).
  client_id: number;
  cliente: string;
  zone: Zone;
  // A payment dated before its own invoice usually means a wrong reference.
  invoice_date: string;
  invoice_total: number;
  // What Comercial applied to this invoice (admAsocCargosAbonos).
  amount: number;
  // The Comercial payment document, series + folio (e.g. "BBV 19686").
  pago: string;
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

// "Diferencias de fecha" tab: each customer payment with its Contpaqi
// Comercial date next to its Contabilidad (poliza) date.
export type DateDifferenceStatus =
  | "distinto_mes"
  | "solo_comercial"
  | "solo_contabilidad"
  | "distinto_dia"
  | "mismo_dia";

export interface ComercialPayment {
  date: string;
  // When the payment was applied to the invoice - usually the same day.
  applied_date: string;
  amount: number;
  // The payment document as Comercial lists it ("BBV 19146").
  documento: string;
}

export interface ContabilidadPayment {
  date: string;
  amount: number;
  // "Ingresos 254" - poliza type and folio in Contabilidad.
  polizas: string[];
}

export interface DateDifferenceRow {
  invoice_id: number;
  folio_display: string;
  // Bare ERP client id - opens the client history (see ClientLink).
  client_id: number;
  cliente: string;
  zone: Zone;
  invoice_date: string;
  amount: number;
  status: DateDifferenceStatus;
  // Latest date on each side (a payment can be split in pieces on one side);
  // null when only the other system has the payment.
  comercial_date: string | null;
  contabilidad_date: string | null;
  days_difference: number | null;
  comercial: ComercialPayment[];
  contabilidad: ContabilidadPayment[];
}

export interface DateDifferencesSummary {
  date_from: string;
  date_to: string;
  rows: DateDifferenceRow[];
  totals: Record<DateDifferenceStatus, { count: number; total_amount: number }>;
}
