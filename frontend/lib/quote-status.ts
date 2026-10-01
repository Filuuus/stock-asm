// Quote request statuses as shown to staff (Solicitudes list and detail).
export type QuoteStatus = "NEW" | "APPROVED" | "REJECTED";

export const QUOTE_STATUS: Record<QuoteStatus, { label: string; className: string }> = {
  NEW: { label: "Nueva", className: "bg-blue-50 text-blue-700" },
  APPROVED: { label: "Aprobada", className: "bg-green-50 text-green-700" },
  REJECTED: { label: "Rechazada", className: "bg-gray-100 text-gray-600" },
};
