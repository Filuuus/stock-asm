"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ChevronLeft, Copy, ExternalLink, Link2, MessageCircle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Notice } from "@/components/notice";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { formatDay, todayISO } from "@/lib/dates";
import ProductDialog from "@/components/catalog/ProductDialog";
import AddProduct from "@/components/quote/AddProduct";
import { CLOSED_AS, QUOTE_STATUS, type ClosedAs, type QuoteStatus, type Stage } from "@/lib/quote-status";
import { WhatsAppLink } from "@/components/whatsapp-link";
import { cn, formatMoney } from "@/lib/utils";

interface QuoteItem {
  key: string | null;
  code: string;
  name: string;
  quantity: number;
  unit_price: number | null;
  typed_price?: string | number | null;
  catalog_price?: number | null;
  subtotal: number | null;
  stock: number | null;
  due: string | null; // a Servicios quote's part: when it was due when quoted
}

interface QuoteEvent {
  id: number;
  kind: "NOTE" | "ACTION";
  text: string;
  author: string | null;
  created_at: string;
  mine: boolean;
}

interface Detail {
  id: number;
  token: string;
  status: QuoteStatus;
  created_at: string;
  name: string;
  phone: string;
  company: string;
  note: string;
  decided_at: string | null;
  decided_by: string | null;
  valid_until: string | null;
  accepted_at: string | null; // the customer approved it from their link
  follow_up: "no_answer" | "expiring" | null; // sent, the customer hasn't approved it
  no_phone: boolean; // no number WhatsApp can reach
  subtotal: number;
  discount: number; // percent, on the whole request
  discount_amount: number;
  total: number;
  owner: string | null;
  mine: boolean;
  to_send: boolean;
  sent_at: string | null;
  from_staff: boolean;
  stage: Stage;
  closed_as: ClosedAs | null;
  expired: boolean;
  revises: number | null;
  revisions: number[];
  items: QuoteItem[];
  events: QuoteEvent[];
}

const units = (n: number | null) => (n === null ? "-" : Number(n).toLocaleString("es-MX", { maximumFractionDigits: 2 }));
const typed = (i: QuoteItem) => (i.typed_price ? String(Number(i.typed_price)) : "");
const moment = (iso: string) =>
  new Date(iso).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

// One request: the customer, what they asked for and everyone's notes. While it's open staff
// adjust products, quantities and prices, then share it, which freezes the prices and shows them on the
// customer's link, where the customer approves it. Its own page (/solicitudes/<id>), or a dialog over another page
// (Servicios): onOpenRequest then shows a linked request in place instead of navigating.
export default function RequestDetail({ id, onOpenRequest }: { id: string | number; onOpenRequest?: (id: number) => void }) {
  const embedded = Boolean(onOpenRequest);
  const Shell = embedded ? "div" : "main";
  const shell = embedded ? "" : "mx-auto w-full max-w-7xl p-4 sm:p-6";
  const [opened, setOpened] = useState<{ key: string; name: string } | null>(null);
  const requestLink = (other: number, label: string) =>
    onOpenRequest ? (
      <button key={other} type="button" onClick={() => onOpenRequest(other)} className="text-sm text-blue-600 hover:underline">
        {label}
      </button>
    ) : (
      <Link key={other} href={`/solicitudes/${other}`} className="text-sm text-blue-600 hover:underline">
        {label}
      </Link>
    );
  const { user, loading } = useAuth();
  const [req, setReq] = useState<Detail | null>(null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [validDays, setValidDays] = useState("15");
  const [note, setNote] = useState("");
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"mensaje" | "enlace" | null>(null); // for two seconds after copying
  // The phone being fixed (a request made from Servicios takes Contpaqi's, which can be missing or a landline).
  const [phone, setPhone] = useState<string | null>(null);
  const [discount, setDiscount] = useState<string | null>(null); // being typed

  const show = useCallback((data: Detail) => {
    setReq(data);
    setQuantities(Object.fromEntries(data.items.map((i) => [i.code, String(Number(i.quantity))])));
    setPrices(Object.fromEntries(data.items.map((i) => [i.code, typed(i)])));
  }, []);

  useEffect(() => {
    if (!user) return;
    apiFetch(`/api/solicitudes/${id}/`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(show)
      .catch(() => setError("No se pudo cargar la solicitud."));
  }, [user, id, show]);

  const send = async (path: string, method: string, body?: object) => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(path, { method, body: body ? JSON.stringify(body) : undefined });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error ?? "No se pudo guardar.");
        return false;
      }
      show(data);
      return true;
    } finally {
      setBusy(false);
    }
  };
  const act = (action: string, body?: object) => send(`/api/solicitudes/${id}/${action}/`, "POST", body);
  // Any unsaved quantities and prices go along, because saving reloads the table.
  const saveItems = (change: Record<string, string> = {}) =>
    send(`/api/solicitudes/${id}/`, "PUT", {
      items: Object.entries({ ...quantities, ...change }).map(([code, quantity]) => ({
        code,
        quantity: Number(quantity) || 0,
        unit_price: prices[code] ?? "",
      })),
    });

  if (!loading && !user) {
    return (
      <Shell className={shell}>
        <Notice tone="info" title="Inicia sesión para ver esta solicitud." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
      </Shell>
    );
  }
  if (!req) {
    return (
      <Shell className={shell}>
        {error ? <Notice tone="error" title={error} /> : <p className="text-sm text-gray-500">Cargando…</p>}
      </Shell>
    );
  }

  const isOpen = req.status === "NEW" || req.status === "CONTACTED";
  const edited = req.items.some((i) => quantities[i.code] !== String(Number(i.quantity)) || (prices[i.code] ?? "") !== typed(i));
  const link = typeof window === "undefined" ? "" : `${process.env.NEXT_PUBLIC_SITE_URL ?? window.location.origin}/solicitud/${req.token}`;
  // A client who asked gets their quote; one staff prepared is a first contact, so it says who we are and why.
  const message = !req.from_staff
    ? `Hola ${req.name}, tu cotización de Agropecuaria Santa María está lista. Ahí puedes revisarla y aprobarla: ${link}`
    : req.items.some((i) => i.due)
      ? `Hola ${req.name}, le saluda Agropecuaria Santa María. Revisando el historial de mantenimiento de su sala de ordeña, vimos que ya le toca el cambio de algunas piezas. Le preparamos una cotización sin compromiso; puede revisarla y, si está de acuerdo, aprobarla aquí: ${link}`
      : `Hola ${req.name}, le saluda Agropecuaria Santa María. Le preparamos una cotización sin compromiso; puede revisarla y, si está de acuerdo, aprobarla aquí: ${link}`;

  // A row's quantity and price: inputs while open, text after (in their columns, or under the name on phones).
  const quantity = (i: QuoteItem) =>
    isOpen ? (
      <Input
        type="number"
        min="0"
        inputMode="decimal"
        value={quantities[i.code] ?? ""}
        onChange={(e) => setQuantities((q) => ({ ...q, [i.code]: e.target.value }))}
        aria-label={`Cantidad de ${i.name}`}
        className="w-20"
      />
    ) : (
      units(i.quantity)
    );
  const price = (i: QuoteItem) =>
    isOpen ? (
      <Input
        type="number"
        min="0"
        step="0.01"
        inputMode="decimal"
        value={prices[i.code] ?? ""}
        placeholder={i.catalog_price ? String(i.catalog_price) : "Sin precio"}
        onChange={(e) => setPrices((p) => ({ ...p, [i.code]: e.target.value }))}
        aria-label={`Precio de ${i.name}`}
        className="w-28 text-right sm:ml-auto"
      />
    ) : i.unit_price !== null ? (
      formatMoney(i.unit_price)
    ) : (
      <span className="text-gray-400">Sin precio</span>
    );
  // Sending is for an open quote, or a shared one the client hasn't approved yet.
  const canSend = isOpen || (req.status === "APPROVED" && !req.accepted_at);
  const copy = async (text: string, what: "mensaje" | "enlace") => {
    await navigator.clipboard.writeText(text);
    setCopied(what);
    setTimeout(() => setCopied(null), 2000);
  };
  // Shares it if it's still open and marks it sent (once): the message is already on its way.
  const sendQuote = () => (isOpen || !req.sent_at ? act("enviar", { valid_days: Number(validDays) }) : Promise.resolve(true));
  const addNote = async (e: FormEvent) => {
    e.preventDefault();
    if (await act("nota", { text: note })) setNote("");
  };
  const close = async (e: FormEvent) => {
    e.preventDefault();
    if (await act("cerrar", { reason })) {
      setClosing(false);
      setReason("");
    }
  };

  return (
    <Shell className={shell}>
      {!embedded && (
        <Link href="/solicitudes" className="mb-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
          <ChevronLeft className="h-4 w-4" />
          Solicitudes
        </Link>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-900">Solicitud #{req.id}</h1>
        <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-medium", QUOTE_STATUS[req.status].className)}>
          {QUOTE_STATUS[req.status].label}
        </span>
        {req.accepted_at && (
          <span className="rounded-full bg-green-600 px-2.5 py-0.5 text-sm font-medium text-white">Aprobada por el cliente</span>
        )}
        {req.follow_up === "no_answer" && (
          <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm font-medium text-amber-800">Sin respuesta</span>
        )}
        {req.follow_up === "expiring" && (
          <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-sm font-medium text-red-800">Vence pronto</span>
        )}
        {req.to_send && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm font-medium text-amber-800">Por enviar</span>}
        {req.expired && !req.closed_as && <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-sm font-medium text-gray-600">Vencida</span>}
        {req.closed_as && <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-medium", CLOSED_AS[req.closed_as].className)}>{CLOSED_AS[req.closed_as].label}</span>}
        {req.revises && requestLink(req.revises, `Cambios a la solicitud #${req.revises}`)}
        {req.revisions.map((other) => requestLink(other, `Cambios en la solicitud #${other}`))}
      </div>

      {/* The next step for this stage, always on top. */}
      <div className="mt-4 space-y-3 rounded-lg border border-gray-200 bg-white p-3">
        {/* The quote: one step to send it (shares it if it's still open, so prices freeze, and marks it sent),
            and the client's link to copy or open. */}
        <div className="flex flex-wrap items-end gap-2">
          {canSend && isOpen && (
            <label className="text-xs text-gray-600">
              Vigencia (días)
              <Input type="number" min="1" max="365" value={validDays} onChange={(e) => setValidDays(e.target.value)} className="mt-1 w-20" />
            </label>
          )}
          {canSend && (
            <>
              <Button asChild>
                <WhatsAppLink
                  phone={req.phone}
                  text={message}
                  disabled={busy || edited || req.no_phone}
                  title={req.no_phone ? "Escribe el teléfono del cliente primero" : isOpen ? "Congela los precios, la marca como enviada y abre el chat con el enlace" : undefined}
                  onClick={sendQuote}
                >
                  <MessageCircle className="mr-1.5 h-4 w-4" />
                  {req.sent_at ? "Reenviar por WhatsApp" : "Enviar por WhatsApp"}
                </WhatsAppLink>
              </Button>
              <Button
                variant="outline"
                disabled={busy || edited}
                onClick={async () => {
                  await copy(message, "mensaje");
                  await sendQuote();
                }}
              >
                <Copy className="mr-1.5 h-4 w-4" />
                {copied === "mensaje" ? "Mensaje copiado" : "Copiar mensaje"}
              </Button>
            </>
          )}
          <Button variant="outline" onClick={() => copy(link, "enlace")}>
            <Link2 className="mr-1.5 h-4 w-4" />
            {copied === "enlace" ? "Enlace copiado" : "Copiar enlace"}
          </Button>
          <Button variant="outline" asChild>
            <a href={link} target="_blank" rel="noopener noreferrer" title="La página que ve el cliente">
              <ExternalLink className="mr-1.5 h-4 w-4" />
              Ver cotización
            </a>
          </Button>
        </div>
        {/* The request: who has it, and closing or reopening it. */}
        <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
          {isOpen && (
            <Button asChild variant="outline" size="sm">
              <WhatsAppLink phone={req.phone} disabled={req.no_phone} onClick={() => act("contactar")}>
                <MessageCircle className="mr-1.5 h-4 w-4" />
                Escribir
              </WhatsAppLink>
            </Button>
          )}
          {req.status === "NEW" && <Button variant="outline" size="sm" disabled={busy} onClick={() => act("contactar")}>Marcar contactada</Button>}
          {req.status === "CONTACTED" && <Button variant="outline" size="sm" disabled={busy} onClick={() => act("deshacer-contacto")}>Deshacer contacto</Button>}
          {req.status === "APPROVED" && (
            <Button variant={req.accepted_at ? "default" : "outline"} size="sm" disabled={busy} onClick={() => act("vendida")}>
              Marcar como vendida
            </Button>
          )}
          {(req.status === "APPROVED" || req.status === "REJECTED") && (
            <Button variant="outline" size="sm" disabled={busy} onClick={() => act("reabrir")}>Reabrir</Button>
          )}
          {req.status !== "REJECTED" && (
            <>
              {req.mine ? (
                <Button variant="outline" size="sm" disabled={busy} onClick={() => act("soltar")}>Soltar</Button>
              ) : (
                <Button variant="outline" size="sm" disabled={busy} onClick={() => act("tomar")}>Tomar</Button>
              )}
              <Button variant="outline" size="sm" disabled={busy} onClick={() => setClosing(!closing)}>Cerrar</Button>
            </>
          )}
        </div>
        {closing && (
          <form onSubmit={close} className="flex w-full gap-2">
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="¿Por qué se cierra?" aria-label="Motivo de cierre" />
            <Button type="submit" disabled={busy || !reason.trim()}>Cerrar solicitud</Button>
          </form>
        )}
      </div>
      {req.no_phone && (
        <div className="mt-4">
          <Notice
            tone="warning"
            title="Sin teléfono para WhatsApp"
            summary="Escribe el celular del cliente en Teléfono (Cambiar) para poder enviarle la cotización. Si viene de Servicios, queda guardado para sus siguientes cotizaciones."
          />
        </div>
      )}
      {req.follow_up && (
        <div className="mt-4">
          <Notice
            tone="warning"
            title={req.follow_up === "expiring" ? `Vence el ${formatDay(req.valid_until!)} y el cliente no la ha aprobado` : "El cliente no ha respondido"}
            summary="Escríbele por WhatsApp para darle seguimiento; si ya no le interesa, cierra la solicitud con el motivo."
          />
        </div>
      )}
      {req.accepted_at && req.status === "APPROVED" && (
        <div className="mt-4">
          <Notice
            tone="ok"
            title={`El cliente aprobó la cotización el ${moment(req.accepted_at)}`}
            summary="Coordina la entrega por WhatsApp, factura en Contpaqi y márcala como vendida."
          />
        </div>
      )}
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <div className="grid gap-2 rounded-lg border border-gray-200 bg-white p-4 text-sm sm:grid-cols-2">
            <p><span className="text-gray-500">Cliente:</span> {req.name}{req.company && ` · ${req.company}`}</p>
            {phone === null ? (
              <p>
                <span className="text-gray-500">Teléfono:</span>{" "}
                {req.phone ? (
                  <a href={`tel:${req.phone}`} className="text-blue-600 hover:underline">{req.phone}</a>
                ) : (
                  <span className="text-red-700">sin teléfono</span>
                )}{" "}
                <button type="button" className="text-xs text-gray-500 hover:underline" onClick={() => setPhone(req.phone)}>
                  Cambiar
                </button>
              </p>
            ) : (
              <form
                className="flex items-center gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await act("telefono", { phone })) setPhone(null);
                }}
              >
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} aria-label="Teléfono" className="h-8 w-40" autoFocus />
                <Button type="submit" size="sm" disabled={busy}>Guardar</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setPhone(null)}>Cancelar</Button>
              </form>
            )}
            <p><span className="text-gray-500">Recibida:</span> {formatDay(req.created_at)}</p>
            <p><span className="text-gray-500">Responsable:</span> {req.owner ?? <span className="text-gray-400">Sin asignar</span>}</p>
            {req.valid_until && <p><span className="text-gray-500">Vigencia:</span> {formatDay(req.valid_until)}</p>}
            {req.note && <p className="sm:col-span-2"><span className="text-gray-500">Nota del cliente:</span> {req.note}</p>}
          </div>

          <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="px-3 py-2 font-medium sm:min-w-44 sm:px-4">Producto</th>
                  <th className="hidden px-4 py-2 font-medium sm:table-cell">Cantidad</th>
                  <th className="hidden whitespace-nowrap px-4 py-2 text-right font-medium sm:table-cell">Existencia</th>
                  <th className="hidden px-4 py-2 text-right font-medium sm:table-cell">Precio</th>
                  <th className="hidden px-4 py-2 text-right font-medium sm:table-cell">Importe</th>
                  {isOpen && <th className="w-10 px-2 py-2"><span className="sr-only">Quitar</span></th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {req.items.map((i) => (
                  <tr key={i.code} className="align-top">
                    <td className="px-3 py-3 sm:px-4">
                      {i.key ? (
                        <button
                          type="button"
                          onClick={() => setOpened({ key: i.key!, name: i.name })}
                          className="text-left font-medium text-gray-800 hover:text-blue-700 hover:underline"
                        >
                          {i.name}
                        </button>
                      ) : (
                        <span className="font-medium text-gray-800">{i.name}</span>
                      )}
                      <p className="text-xs text-gray-400">SKU: {i.code}</p>
                      {i.due && <DueLine due={i.due} />}
                      {/* Phones: quantity, price and amount under the name instead of in their columns. */}
                      <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 sm:hidden">
                        {quantity(i)}
                        <span className="text-gray-400">×</span>
                        {price(i)}
                        <span className="num ml-auto font-medium text-gray-900">{i.subtotal !== null ? formatMoney(i.subtotal) : "-"}</span>
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 sm:table-cell">
                      {quantity(i)}
                    </td>
                    <td className={cn("hidden px-4 py-3 text-right sm:table-cell", i.stock !== null && i.stock <= 0 && "text-red-600")}>
                      {units(i.stock)}
                    </td>
                    <td className="num hidden px-4 py-3 text-right sm:table-cell">
                      {price(i)}
                    </td>
                    <td className="num hidden px-4 py-3 text-right sm:table-cell">{i.subtotal !== null ? formatMoney(i.subtotal) : "-"}</td>
                    {isOpen && (
                      <td className="px-2 py-3">
                        <button
                          type="button"
                          disabled={busy || req.items.length === 1}
                          onClick={() => saveItems({ [i.code]: "0" })}
                          aria-label={`Quitar ${i.name}`}
                          title={req.items.length === 1 ? "La solicitud debe conservar al menos un producto" : "Quitar"}
                          className="rounded p-2 text-gray-400 hover:bg-gray-100 hover:text-red-600 disabled:opacity-40"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-gray-200">
                  <td colSpan={isOpen ? 6 : 5} className="px-4 py-3 text-right text-gray-900">
                    {Number(req.discount) > 0 && (
                      <p className="text-sm text-gray-600">
                        Subtotal: <span className="num">{formatMoney(req.subtotal)}</span>
                        <br />
                        Descuento {Number(req.discount)} %: <span className="num">−{formatMoney(req.discount_amount)}</span>
                      </p>
                    )}
                    {isOpen && (
                      <form
                        className="my-1 inline-flex items-center gap-2 text-sm"
                        onSubmit={async (e) => {
                          e.preventDefault();
                          if (await act("descuento", { discount: Number(discount ?? req.discount) || 0 })) setDiscount(null);
                        }}
                      >
                        <label htmlFor="quote-discount" className="text-gray-600">Descuento (%)</label>
                        <Input
                          id="quote-discount"
                          type="number"
                          min="0"
                          max="99"
                          step="0.5"
                          value={discount ?? String(Number(req.discount))}
                          onChange={(e) => setDiscount(e.target.value)}
                          className="h-8 w-20 text-right"
                        />
                        {discount !== null && <Button type="submit" size="sm" variant="outline" disabled={busy}>Aplicar</Button>}
                      </form>
                    )}
                    <p className="font-semibold">
                      Total: <span className="num">{formatMoney(req.total)}</span>{" "}
                      <span className="text-xs font-normal text-gray-500">IVA incluido</span>
                    </p>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          {isOpen && (
            <>
              <AddProduct exclude={req.items.map((i) => i.code)} disabled={busy} onAdd={(code) => saveItems({ [code]: "1" })} />
              <p className="mt-2 text-xs text-gray-500">
                Escribe el precio con IVA para poner o cambiar el de un producto; en blanco usa el del catálogo. Los precios se congelan al compartir la cotización. &quot;Sin precio&quot; aparece al cliente como &quot;Se cotiza aparte&quot;.
              </p>
              {edited && (
                <div className="mt-3 flex items-center gap-3">
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      saveItems()
                    }
                  >
                    Guardar cambios
                  </Button>
                  <p className="text-xs text-gray-500">Guarda los cambios antes de compartir.</p>
                </div>
              )}
            </>
          )}
        </div>

        <section className="flex flex-col rounded-lg border border-gray-200 bg-white p-4 lg:max-h-[42rem]">
          <h2 className="font-semibold text-gray-900">Seguimiento</h2>
          <p className="text-xs text-gray-500">Solo lo ve el personal.</p>
          <ol className="mt-3 flex-1 space-y-3 overflow-y-auto">
            {req.events.length === 0 && <li className="text-sm text-gray-400">Aún no hay movimientos.</li>}
            {req.events.map((e) =>
              e.kind === "NOTE" ? (
                <li key={e.id} className="rounded-lg bg-slate-50 p-2.5 text-sm">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-medium text-gray-900">{e.author ?? "Usuario eliminado"}</span>
                    <span className="flex items-center gap-1 text-xs text-gray-400">
                      {moment(e.created_at)}
                      {e.mine && (
                        <button
                          type="button"
                          aria-label="Borrar nota"
                          onClick={() => send(`/api/solicitudes/${id}/notas/${e.id}/`, "DELETE")}
                          className="rounded p-0.5 hover:bg-gray-200 hover:text-red-600"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </span>
                  </div>
                  <p className="mt-0.5 whitespace-pre-line text-gray-700">{e.text}</p>
                </li>
              ) : (
                <li key={e.id} className="px-2.5 text-xs text-gray-500">
                  {e.author ?? "El cliente"} {e.text} · {moment(e.created_at)}
                </li>
              ),
            )}
          </ol>
          <form onSubmit={addNote} className="mt-3 border-t border-gray-100 pt-3">
            <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder="Escribe una nota…" aria-label="Nueva nota" />
            <Button type="submit" size="sm" disabled={busy || !note.trim()} className="mt-2">Agregar nota</Button>
          </form>
        </section>
      </div>
      {opened && <ProductDialog productKey={opened.key} fallbackName={opened.name} onClose={() => setOpened(null)} />}
    </Shell>
  );
}

// A Servicios quote's part: overdue (red) or when it's due, compared with today.
function DueLine({ due }: { due: string }) {
  const past = due < todayISO();
  return <p className={cn("text-xs", past ? "font-medium text-red-700" : "text-green-700")}>{past ? "Vencido" : "Toca"} {formatDay(due)}</p>;
}
