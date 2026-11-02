"use client";

import { use, useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ChevronLeft, Copy, MessageCircle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Notice } from "@/components/notice";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import { QUOTE_STATUS, type QuoteStatus, whatsappUrl } from "@/lib/quote-status";
import { cn, formatMoney, productHref } from "@/lib/utils";

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
  total: number;
  owner: string | null;
  mine: boolean;
  to_send: boolean;
  expired: boolean;
  items: QuoteItem[];
  events: QuoteEvent[];
}

const units = (n: number | null) => (n === null ? "-" : Number(n).toLocaleString("es-MX", { maximumFractionDigits: 2 }));
const typed = (i: QuoteItem) => (i.typed_price ? String(Number(i.typed_price)) : "");
const moment = (iso: string) =>
  new Date(iso).toLocaleString("es-MX", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });

// One request: the customer, what they asked for and everyone's notes. While it's open staff
// adjust quantities and prices; management approves, which freezes the prices, and the
// customer's link then shows them.
export default function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, loading, isManagement } = useAuth();
  const [req, setReq] = useState<Detail | null>(null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [validDays, setValidDays] = useState("15");
  const [note, setNote] = useState("");
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

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

  if (!loading && !user) {
    return (
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
        <Notice tone="info" title="Inicia sesión para ver esta solicitud." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
      </main>
    );
  }
  if (!req) {
    return (
      <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
        {error ? <Notice tone="error" title={error} /> : <p className="text-sm text-gray-500">Cargando…</p>}
      </main>
    );
  }

  const isOpen = req.status === "NEW" || req.status === "CONTACTED";
  const edited = req.items.some((i) => quantities[i.code] !== String(Number(i.quantity)) || (prices[i.code] ?? "") !== typed(i));
  const link = typeof window === "undefined" ? "" : `${process.env.NEXT_PUBLIC_SITE_URL ?? window.location.origin}/solicitud/${req.token}`;
  const message = `Hola ${req.name}, tu cotización de Agropecuaria Santa María está lista: ${link}`;

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
    <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <Link href="/solicitudes" className="mb-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <ChevronLeft className="h-4 w-4" />
        Solicitudes
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-900">Solicitud #{req.id}</h1>
        <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-medium", QUOTE_STATUS[req.status].className)}>
          {QUOTE_STATUS[req.status].label}
        </span>
        {req.to_send && <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-sm font-medium text-amber-800">Por enviar</span>}
        {req.expired && <span className="rounded-full bg-gray-100 px-2.5 py-0.5 text-sm font-medium text-gray-600">Vencida</span>}
      </div>

      {/* The next step for this stage, always on top. */}
      <div className="mt-4 flex flex-wrap items-end gap-2 rounded-lg border border-gray-200 bg-white p-3">
        {isOpen && (
          <Button asChild>
            <a href={whatsappUrl(req.phone)} target="_blank" rel="noopener noreferrer" onClick={() => act("contactar")}>
              <MessageCircle className="mr-1.5 h-4 w-4" />
              WhatsApp
            </a>
          </Button>
        )}
        {req.status === "NEW" && <Button variant="outline" disabled={busy} onClick={() => act("contactar")}>Marcar contactada</Button>}
        {req.status === "CONTACTED" && <Button variant="outline" disabled={busy} onClick={() => act("deshacer-contacto")}>Deshacer contacto</Button>}
        {req.status === "APPROVED" && (
          <>
            <Button asChild>
              <a href={whatsappUrl(req.phone, message)} target="_blank" rel="noopener noreferrer" onClick={() => act("enviada")}>
                <MessageCircle className="mr-1.5 h-4 w-4" />
                Enviar por WhatsApp
              </a>
            </Button>
            <Button
              variant="outline"
              onClick={async () => {
                await navigator.clipboard.writeText(link);
                setCopied(true);
              }}
            >
              <Copy className="mr-1.5 h-4 w-4" />
              {copied ? "Enlace copiado" : "Copiar enlace"}
            </Button>
            {req.to_send && <Button variant="outline" disabled={busy} onClick={() => act("enviada")}>Marcar enviada</Button>}
            {isManagement && <Button variant="outline" disabled={busy} onClick={() => act("reabrir")}>Reabrir</Button>}
          </>
        )}
        {req.status !== "REJECTED" && (
          <>
            {req.mine ? (
              <Button variant="outline" disabled={busy} onClick={() => act("soltar")}>Soltar</Button>
            ) : (
              <Button variant="outline" disabled={busy} onClick={() => act("tomar")}>Tomar</Button>
            )}
            <Button variant="outline" disabled={busy} onClick={() => setClosing(!closing)}>Cerrar</Button>
          </>
        )}
        {isOpen && (isManagement ? (
          <div className="ml-auto flex items-end gap-2">
            <label className="text-xs text-gray-600">
              Vigencia (días)
              <Input type="number" min="1" max="365" value={validDays} onChange={(e) => setValidDays(e.target.value)} className="mt-1 w-20" />
            </label>
            <Button disabled={busy || edited} onClick={() => act("aprobar", { valid_days: Number(validDays) })}>Aprobar</Button>
          </div>
        ) : (
          <p className="ml-auto self-center text-sm text-gray-500">Solo gerencia puede aprobar.</p>
        ))}
        {closing && (
          <form onSubmit={close} className="flex w-full gap-2">
            <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="¿Por qué se cierra?" aria-label="Motivo de cierre" />
            <Button type="submit" disabled={busy || !reason.trim()}>Cerrar solicitud</Button>
          </form>
        )}
      </div>
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <div className="grid gap-2 rounded-lg border border-gray-200 bg-white p-4 text-sm sm:grid-cols-2">
            <p><span className="text-gray-500">Cliente:</span> {req.name}{req.company && ` · ${req.company}`}</p>
            <p><span className="text-gray-500">Teléfono:</span> <a href={`tel:${req.phone}`} className="text-blue-600 hover:underline">{req.phone}</a></p>
            <p><span className="text-gray-500">Recibida:</span> {formatDay(req.created_at)}</p>
            <p><span className="text-gray-500">Responsable:</span> {req.owner ?? <span className="text-gray-400">Sin asignar</span>}</p>
            {req.valid_until && <p><span className="text-gray-500">Vigencia:</span> {formatDay(req.valid_until)}</p>}
            {req.note && <p className="sm:col-span-2"><span className="text-gray-500">Nota del cliente:</span> {req.note}</p>}
          </div>

          <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className="min-w-44 px-4 py-2 font-medium">Producto</th>
                  <th className="px-4 py-2 font-medium">Cantidad</th>
                  <th className="hidden whitespace-nowrap px-4 py-2 text-right font-medium sm:table-cell">Existencia</th>
                  <th className="px-4 py-2 text-right font-medium">Precio</th>
                  <th className="px-4 py-2 text-right font-medium">Importe</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {req.items.map((i) => (
                  <tr key={i.code} className="align-top">
                    <td className="px-4 py-3">
                      {i.key ? (
                        <Link href={productHref(i.key)} className="font-medium text-gray-800 hover:text-blue-700">{i.name}</Link>
                      ) : (
                        <span className="font-medium text-gray-800">{i.name}</span>
                      )}
                      <p className="text-xs text-gray-400">SKU: {i.code}</p>
                    </td>
                    <td className="px-4 py-3">
                      {isOpen ? (
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
                      )}
                    </td>
                    <td className={cn("hidden px-4 py-3 text-right sm:table-cell", i.stock !== null && i.stock <= 0 && "text-red-600")}>
                      {units(i.stock)}
                    </td>
                    <td className="num px-4 py-3 text-right">
                      {isOpen ? (
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          inputMode="decimal"
                          value={prices[i.code] ?? ""}
                          placeholder={i.catalog_price ? String(i.catalog_price) : "Sin precio"}
                          onChange={(e) => setPrices((p) => ({ ...p, [i.code]: e.target.value }))}
                          aria-label={`Precio de ${i.name}`}
                          className="ml-auto w-28 text-right"
                        />
                      ) : i.unit_price !== null ? (
                        formatMoney(i.unit_price)
                      ) : (
                        <span className="text-gray-400">Sin precio</span>
                      )}
                    </td>
                    <td className="num px-4 py-3 text-right">{i.subtotal !== null ? formatMoney(i.subtotal) : "-"}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-gray-200">
                  <td colSpan={5} className="px-4 py-3 text-right font-semibold text-gray-900">
                    Total: <span className="num">{formatMoney(req.total)}</span>{" "}
                    <span className="text-xs font-normal text-gray-500">IVA incluido</span>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
          {isOpen && (
            <>
              <p className="mt-2 text-xs text-gray-500">
                Escribe el precio con IVA para poner o cambiar el de un producto; en blanco usa el del catálogo. Los precios se congelan al aprobar. Cantidad 0 quita el producto. &quot;Sin precio&quot; aparece al cliente como &quot;Se cotiza aparte&quot;.
              </p>
              {edited && (
                <div className="mt-3 flex items-center gap-3">
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() =>
                      send(`/api/solicitudes/${id}/`, "PUT", {
                        items: Object.entries(quantities).map(([code, quantity]) => ({
                          code,
                          quantity: Number(quantity) || 0,
                          unit_price: prices[code] ?? "",
                        })),
                      })
                    }
                  >
                    Guardar cambios
                  </Button>
                  <p className="text-xs text-gray-500">Guarda los cambios antes de aprobar.</p>
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
                  {e.author ?? "Alguien"} {e.text} · {moment(e.created_at)}
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
    </main>
  );
}
