// Quote request statuses as shown to staff (Solicitudes list and detail).
export type QuoteStatus = "NEW" | "CONTACTED" | "APPROVED" | "REJECTED";

export const QUOTE_STATUS: Record<QuoteStatus, { label: string; className: string }> = {
  NEW: { label: "Nueva", className: "bg-blue-50 text-blue-700" },
  CONTACTED: { label: "Contactada", className: "bg-violet-50 text-violet-700" },
  APPROVED: { label: "Aprobada", className: "bg-green-50 text-green-700" },
  REJECTED: { label: "Cerrada", className: "bg-gray-100 text-gray-600" },
};

// WhatsApp wants the number with country code: a 10-digit Mexican number gets 52.
export function whatsappUrl(phone: string, text?: string) {
  const digits = phone.replace(/\D/g, "");
  const number = digits.length === 10 ? `52${digits}` : digits;
  return `https://wa.me/${number}${text ? `?text=${encodeURIComponent(text)}` : ""}`;
}

// "hoy", "hace 1 día", "hace 3 días".
export function waitingLabel(iso: string, now = new Date()) {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86400000);
  return days <= 0 ? "hoy" : `hace ${days} ${days === 1 ? "día" : "días"}`;
}
