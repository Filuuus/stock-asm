"use client";

import { useInvoiceDialog } from "@/components/facturas/invoice-dialog-context";

// An invoice number that opens the invoice dialog in place. Plain text for
// users who can't see invoice details.
export default function InvoiceLink({ invoiceId, label }: {
  invoiceId: number;
  label: string | number;
}) {
  const { canView, openInvoice } = useInvoiceDialog();
  if (!canView) return <>{label}</>;
  return (
    <button
      type="button"
      onClick={(e) => {
        // Rows that expand on click (Comisiones) shouldn't also toggle.
        e.stopPropagation();
        openInvoice(invoiceId);
      }}
      className="underline decoration-gray-300 underline-offset-2 hover:decoration-gray-700"
    >
      {label}
    </button>
  );
}
