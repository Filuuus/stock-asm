"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Copy, MessageCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Notice } from "@/components/notice";
import { productHref } from "@/components/catalog/ProductCard";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import { QUOTE_STATUS, type QuoteStatus } from "@/lib/quote-status";
import { cn, formatMoney } from "@/lib/utils";

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
  items: { code: string; name: string; quantity: number; unit_price: number | null; subtotal: number | null; stock: number | null }[];
}

const units = (n: number | null) => (n === null ? "-" : Number(n).toLocaleString("es-MX", { maximumFractionDigits: 2 }));

// WhatsApp wants the number with country code: a 10-digit Mexican number gets 52.
function whatsappNumber(phone: string) {
  const digits = phone.replace(/\D/g, "");
  return digits.length === 10 ? `52${digits}` : digits;
}

// One request: staff adjust quantities while it's new; management approves
// (freezing today's prices, valid N days) or rejects. Once approved, the
// customer's link shows the prices - share it from here.
export default function RequestDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { user, loading, isManagement } = useAuth();
  const [req, setReq] = useState<Detail | null>(null);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [validDays, setValidDays] = useState("15");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const show = useCallback((data: Detail) => {
    setReq(data);
    setQuantities(Object.fromEntries(data.items.map((i) => [i.code, String(Number(i.quantity))])));
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
      if (!res.ok) setError(data.error ?? "No se pudo guardar.");
      else show(data);
    } finally {
      setBusy(false);
    }
  };

  if (!loading && !user) {
    return (
      <main className="mx-auto w-full max-w-5xl p-4 sm:p-6">
        <Notice tone="info" title="Inicia sesión para ver esta solicitud." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
      </main>
    );
  }
  if (!req) {
    return (
      <main className="mx-auto w-full max-w-5xl p-4 sm:p-6">
        {error ? <Notice tone="error" title={error} /> : <p className="text-sm text-gray-500">Cargando…</p>}
      </main>
    );
  }

  const isNew = req.status === "NEW";
  const edited = req.items.some((i) => quantities[i.code] !== String(Number(i.quantity)));
  const link = typeof window === "undefined" ? "" : `${window.location.origin}/solicitud/${req.token}`;
  const message = `Hola ${req.name}, tu cotización de Agropecuaria Santa María está lista: ${link}`;

  return (
    <main className="mx-auto w-full max-w-5xl p-4 sm:p-6">
      <Link href="/solicitudes" className="mb-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <ChevronLeft className="h-4 w-4" />
        Solicitudes
      </Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold text-gray-900">Solicitud #{req.id}</h1>
        <span className={cn("rounded-full px-2.5 py-0.5 text-sm font-medium", QUOTE_STATUS[req.status].className)}>
          {QUOTE_STATUS[req.status].label}
        </span>
      </div>

      <div className="mt-4 grid gap-1 rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700 sm:grid-cols-2">
        <p><span className="text-gray-500">Cliente:</span> {req.name}{req.company && ` · ${req.company}`}</p>
        <p>
          <span className="text-gray-500">Teléfono:</span>{" "}
          <a href={`tel:${req.phone}`} className="text-blue-600 hover:underline">{req.phone}</a>
        </p>
        <p><span className="text-gray-500">Recibida:</span> {formatDay(req.created_at)}</p>
        {req.decided_at && (
          <p>
            <span className="text-gray-500">{req.status === "APPROVED" ? "Aprobada" : "Rechazada"}:</span>{" "}
            {formatDay(req.decided_at)}{req.decided_by && ` por ${req.decided_by}`}
            {req.valid_until && ` · válida hasta ${formatDay(req.valid_until)}`}
          </p>
        )}
        {req.note && <p className="sm:col-span-2"><span className="text-gray-500">Nota:</span> {req.note}</p>}
      </div>

      <div className="mt-6 overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs text-gray-500">
            <tr>
              <th className="px-4 py-2 font-medium">Producto</th>
              <th className="px-4 py-2 font-medium">Cantidad</th>
              <th className="hidden px-4 py-2 text-right font-medium sm:table-cell">Existencia</th>
              <th className="px-4 py-2 text-right font-medium">Precio</th>
              <th className="px-4 py-2 text-right font-medium">Importe</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {req.items.map((i) => (
              <tr key={i.code} className="align-top">
                <td className="px-4 py-3">
                  <Link href={productHref(i.code)} className="font-medium text-gray-800 hover:text-blue-700">{i.name}</Link>
                  <p className="text-xs text-gray-400">SKU: {i.code}</p>
                </td>
                <td className="px-4 py-3">
                  {isNew ? (
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
                <td className="num px-4 py-3 text-right">{i.unit_price !== null ? formatMoney(i.unit_price) : <span className="text-xs text-gray-500">Sin precio</span>}</td>
                <td className="num px-4 py-3 text-right">{i.subtotal !== null ? formatMoney(i.subtotal) : "-"}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-gray-200">
              <td colSpan={5} className="px-4 py-3 text-right font-semibold text-gray-900">
                Total: <span className="num">{formatMoney(req.total)}</span>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
      {isNew && (
        <p className="mt-2 text-xs text-gray-500">
          Precios actuales del catálogo; se congelan al aprobar. Cantidad 0 quita el producto. &quot;Sin precio&quot; aparece al cliente como &quot;Se cotiza aparte&quot;.
        </p>
      )}

      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      {isNew && (
        <div className="mt-6 flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4">
          {edited && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                send(`/api/solicitudes/${req.id}/`, "PUT", {
                  items: Object.entries(quantities).map(([code, quantity]) => ({ code, quantity: Number(quantity) || 0 })),
                })
              }
            >
              Guardar cantidades
            </Button>
          )}
          {isManagement ? (
            <>
              <label className="text-sm text-gray-700">
                Vigencia (días)
                <Input type="number" min="1" max="365" value={validDays} onChange={(e) => setValidDays(e.target.value)} className="mt-1 w-24" />
              </label>
              <Button disabled={busy || edited} onClick={() => send(`/api/solicitudes/${req.id}/aprobar/`, "POST", { valid_days: Number(validDays) })}>
                Aprobar
              </Button>
              <Button variant="outline" disabled={busy || edited} onClick={() => send(`/api/solicitudes/${req.id}/rechazar/`, "POST")}>
                Rechazar
              </Button>
              {edited && <p className="w-full text-xs text-gray-500">Guarda las cantidades antes de aprobar.</p>}
            </>
          ) : (
            <p className="text-sm text-gray-500">Solo gerencia puede aprobar o rechazar.</p>
          )}
        </div>
      )}

      {req.status === "APPROVED" && (
        <div className="mt-6 rounded-lg border border-green-200 bg-green-50 p-4">
          <p className="text-sm font-medium text-green-800">Comparte la cotización con el cliente</p>
          <p className="mt-1 break-all text-xs text-green-700">{link}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button asChild>
              <a href={`https://wa.me/${whatsappNumber(req.phone)}?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">
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
          </div>
        </div>
      )}
    </main>
  );
}
