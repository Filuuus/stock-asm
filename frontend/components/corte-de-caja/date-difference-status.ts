import type { DateDifferenceStatus } from "@/types/corte-de-caja";

// Labels and colors for the Comercial vs Contabilidad payment statuses - used
// by the Discrepancias tab and by the invoice detail.
export const STATUS_INFO: Record<
  DateDifferenceStatus,
  { label: string; description: string; badge: string; card: string }
> = {
  distinto_mes: {
    label: "Distinto mes",
    description:
      "Comercial y Contabilidad registran el pago en meses diferentes.",
    badge: "bg-red-50 text-red-700 border-red-200",
    card: "border-red-300 bg-red-50",
  },
  folio_equivocado: {
    label: "Folio equivocado",
    description:
      "La póliza parece citar otra factura: mismo monto y fecha, folio que difiere en un dígito.",
    badge: "bg-red-50 text-red-700 border-red-200",
    card: "border-red-300 bg-red-50",
  },
  monto_distinto: {
    label: "Monto distinto",
    description:
      "Parece el mismo pago, pero Comercial y la póliza tienen importes distintos.",
    badge: "bg-red-50 text-red-700 border-red-200",
    card: "border-red-300 bg-red-50",
  },
  solo_comercial: {
    label: "Solo en Comercial",
    description: "Pago en Comercial sin póliza en Contabilidad por ese monto.",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    card: "border-amber-300 bg-amber-50",
  },
  solo_contabilidad: {
    label: "Solo en Contabilidad",
    description: "Póliza sin pago aplicado en Comercial por ese monto.",
    badge: "bg-amber-50 text-amber-700 border-amber-200",
    card: "border-amber-300 bg-amber-50",
  },
  distinto_dia: {
    label: "Distinto día",
    description: "Mismo mes, distinto día.",
    badge: "bg-slate-50 text-slate-700 border-slate-200",
    card: "border-slate-300 bg-slate-50",
  },
  mismo_dia: {
    label: "Mismo día",
    description: "Ambas fechas coinciden.",
    badge: "bg-green-50 text-green-700 border-green-200",
    card: "border-green-300 bg-green-50",
  },
};
