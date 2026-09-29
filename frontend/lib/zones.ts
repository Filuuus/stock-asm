import type { Zone } from "@/types/commissions";

// On-screen zone names. Just the zone - everyone knows which salesperson
// covers each route (user decision 2026-09-29); the .xlsx export keeps its
// own labels (CORTE_DE_CAJA_ZONE_LABELS) to mirror the accountant's sheet.
// Key order is the order zones are listed in, same as the export.
export const ZONE_LABELS: Record<Zone, string> = {
  ZONA1: "Zona 1",
  ZONA2: "Zona 2",
  OFICINA: "Oficina",
  SERVICIOS: "Servicios",
  PUNTOVENTA: "Punto de Venta",
};

export const ZONE_ORDER = Object.keys(ZONE_LABELS) as Zone[];

export function zoneLabel(zone: string | null | undefined) {
  if (!zone) return "-";
  return ZONE_LABELS[zone as Zone] ?? zone;
}
