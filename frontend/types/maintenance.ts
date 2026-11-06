// /api/servicios/plan/ (backend maintenance.services.build_plan)

export type PartStatus = "ok" | "overdue" | "stale" | "unknown" | "no_interval";
export type EventKind = "done" | "external" | "missed" | "due"; // external: changed by someone else

export interface ParlorPartRow {
  id: number; // the registry row, to fix its quantity or remove it
  parlor: number;
  client: string;
  code: string;
  quantity: number;
  group: string; // its category (Colectores, Pulsadores...)
  registered_as: string | null; // the calendar's code, when the client buys another model of the part
  last_change: string | null; // latest invoice of the part to that client
  last_invoice: number | null; // that invoice's ERP id, for the invoice dialog
  months: number | null;
  basis: "GEA" | "cliente" | "clientes" | "calendario" | null;
  due: string | null;
  status: PartStatus;
  // Agenda: done (with its invoice), external (its record, to undo it), missed, due.
  events: { date: string; kind: EventKind; invoice: number | null; external: number | null }[];
  per_year: number; // changes a year, last 3 years
  on_time: number | null; // share of the times it came due that it was changed that month
  score: number; // relevance: pesos a year weighted by on_time
  quote: { id: number; status: "cotizado" | "aprobado" | "enviado" } | null; // a service quote since its last change
}

export interface PlanParlor {
  id: number;
  client: string;
  label: string;
  client_id: number | null; // ERP id, for the client's invoice history
  name: string;
  sales_12m: number; // parlor service invoiced over the last 12 months (services.parlor_product + labor)
  attended: boolean; // our crew billed labor this year; the rest are prospects
  hours_per_day: number | null;
  parts: ParlorPartRow[];
}

export interface OrderLineProposal {
  code: string;
  services: number;
  buffer: number;
  stock: number;
  order: number;
}

export interface ServicePlan {
  categories: string[]; // part categories in display order
  names: Record<string, string>;
  keys: Record<string, string>; // catalog key (ERP product id) per part, for the product dialog
  stock: Record<string, number>; // general warehouse
  prices: Record<string, number>; // catalog list price, IVA included
  parlors: PlanParlor[];
  order: { day: string; lines: OrderLineProposal[] };
}
