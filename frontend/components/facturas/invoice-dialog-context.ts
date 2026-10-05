"use client";

import { createContext, useContext } from "react";

// Kept apart from InvoiceDialog so the links (InvoiceLink, ClientLink), which
// appear inside the dialog's own views, don't import the dialog itself.
export interface InvoiceDialogContextValue {
  // Whether the current user may see invoice and client details (the API is
  // limited to accounting and management - Comisiones is open to salespeople).
  canView: boolean;
  openInvoice: (invoiceId: number) => void;
  openClient: (clientId: number) => void;
  openOverdueClients: () => void; // management only (Ventas)
}

export const InvoiceDialogContext = createContext<InvoiceDialogContextValue | null>(null);

export function useInvoiceDialog() {
  const ctx = useContext(InvoiceDialogContext);
  if (!ctx) throw new Error("useInvoiceDialog must be used within InvoiceDialogProvider");
  return ctx;
}
