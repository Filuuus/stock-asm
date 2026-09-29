"use client";

import { useInvoiceDialog } from "@/components/facturas/invoice-dialog-context";

// A client name that opens the client's invoice history in the dialog.
// Plain text for users who can't see it.
export default function ClientLink({ clientId, label }: {
  clientId: number | null | undefined;
  label: string;
}) {
  const { canView, openClient } = useInvoiceDialog();
  if (!canView || !clientId) return <>{label}</>;
  return (
    <button
      type="button"
      onClick={(e) => {
        // Rows that expand on click (Comisiones) shouldn't also toggle.
        e.stopPropagation();
        openClient(clientId);
      }}
      className="max-w-full truncate text-left underline decoration-gray-300 underline-offset-2 hover:decoration-gray-700"
    >
      {label}
    </button>
  );
}
