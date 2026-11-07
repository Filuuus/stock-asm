// Quote request statuses as shown to staff (Solicitudes list and detail).
export type QuoteStatus = "NEW" | "CONTACTED" | "APPROVED" | "REJECTED";

export const QUOTE_STATUS: Record<QuoteStatus, { label: string; className: string }> = {
  NEW: { label: "Nueva", className: "bg-blue-50 text-blue-700" },
  CONTACTED: { label: "Contactada", className: "bg-violet-50 text-violet-700" },
  APPROVED: { label: "Cotizada", className: "bg-green-50 text-green-700" }, // prices shared on the client's link
  REJECTED: { label: "Cerrada", className: "bg-gray-100 text-gray-600" },
};

// Where a request is in its life, as the Solicitudes tabs group them (the server decides: catalog/quotes.py _stage).
export type Stage = "por_cotizar" | "por_enviar" | "esperando" | "aprobada" | "cerrada";
export type ClosedAs = "vendida" | "vencida" | "cerrada";

export const CLOSED_AS: Record<ClosedAs, { label: string; className: string }> = {
  vendida: { label: "Vendida", className: "bg-green-100 text-green-800" },
  vencida: { label: "Vencida", className: "bg-gray-100 text-gray-600" },
  cerrada: { label: "Cerrada", className: "bg-gray-100 text-gray-600" },
};

// WhatsApp wants the number with country code: a 10-digit Mexican number gets 52. On a computer, straight to
// WhatsApp Web: wa.me first shows a "start chat" page whose button opens the regular WhatsApp app, not a Business
// account signed in on the web. Phones and tablets keep wa.me, which opens the installed app (Business too).
// Checked at click time, so links rendered on the server never differ from the browser's.
export function whatsappUrl(phone: string, text?: string) {
  const digits = phone.replace(/\D/g, "");
  const number = digits.length === 10 ? `52${digits}` : digits;
  const query = text ? `text=${encodeURIComponent(text)}` : "";
  if (isComputer()) return `https://web.whatsapp.com/send?${number ? `phone=${number}&` : ""}${query}`;
  return `https://wa.me/${number}${query ? `?${query}` : ""}`;
}

// iPads report a Mac user agent; touch points give them away.
function isComputer() {
  if (typeof navigator === "undefined") return false;
  return !/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) && navigator.maxTouchPoints <= 1;
}

// "hoy", "hace 1 día", "hace 3 días".
export function waitingLabel(iso: string, now = new Date()) {
  const days = Math.floor((now.getTime() - new Date(iso).getTime()) / 86400000);
  return days <= 0 ? "hoy" : `hace ${days} ${days === 1 ? "día" : "días"}`;
}
