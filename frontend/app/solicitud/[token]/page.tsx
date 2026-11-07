import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Notice } from "@/components/notice";
import QuoteActions from "@/components/quote/QuoteActions";
import { API_URL } from "@/lib/api";
import { formatDay, formatMonth, todayISO } from "@/lib/dates";
import { formatMoney, plural, productHref } from "@/lib/utils";

// Personal links: keep them out of search engines.
export const metadata: Metadata = { title: "Mi solicitud | Agropecuaria Santa María", robots: { index: false, follow: false } };

interface LinkedQuote {
  number: number;
  token: string;
}

interface PublicRequest {
  number: number;
  status: "NEW" | "APPROVED" | "REJECTED";
  created_at: string;
  name: string;
  valid_until: string | null;
  total: number | null;
  subtotal?: number;
  discount: number; // percent
  discount_amount?: number;
  expired: boolean;
  accepted_at: string | null; // the customer approved it here
  can_modify: boolean;
  contact_phone: string | null;
  revision: LinkedQuote | null;
  revises: LinkedQuote | null;
  items: {
    key: string | null;
    linked: boolean;
    name: string;
    image: string | null;
    quantity: number;
    unit_price: number | null;
    subtotal: number | null;
    due: string | null; // a service quote's part: when it was due to be changed
  }[];
}

// Rentabilidad's print rules are landscape with a "Confidencial" footer; a quote goes to the customer.
const PRINT_PAGE = `@media print {
  @page {
    size: letter portrait;
    @bottom-left { content: "Agropecuaria Santa María"; }
  }
}`;

// The customer's personal link: status while it's reviewed; once staff share the
// quote, the prices frozen then, and a button to approve it. Knowing the link is
// the only access, like a shared document - it isn't listed or guessable.
export default async function RequestPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const res = await fetch(`${API_URL}/api/solicitudes/publica/${encodeURIComponent(token)}/`, { cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`No se pudo cargar la solicitud (${res.status})`);
  const req: PublicRequest = await res.json();
  const approved = req.status === "APPROVED";
  const qty = (n: number) => Number(n).toLocaleString("es-MX", { maximumFractionDigits: 2 });
  const unpriced = req.items.filter((i) => i.subtotal === null).length;
  const today = todayISO();

  return (
    <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <style>{PRINT_PAGE}</style>
      <div className="mb-6 hidden items-center justify-between border-b border-gray-200 pb-4 print:flex">
        {/* A plain img: print shouldn't wait on the optimizer. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/logo.png" alt="Agropecuaria Santa María" className="h-14 w-auto" />
        <p className="text-right text-sm text-gray-600">
          Agropecuaria Santa María
          {req.contact_phone && <span className="block">Tel. {req.contact_phone}</span>}
        </p>
      </div>

      <h1 className="text-2xl font-semibold text-gray-900">{approved ? "Cotización" : "Solicitud"} #{req.number}</h1>
      <p className="mt-1 text-sm text-gray-500">
        {req.name} · {formatDay(req.created_at)}
      </p>
      {req.revises && (
        <p className="mt-1 text-sm text-gray-500 print:hidden">
          Cambios a la{" "}
          <Link href={`/solicitud/${req.revises.token}`} className="text-blue-600 hover:underline">
            solicitud #{req.revises.number}
          </Link>
        </p>
      )}

      <div className="mt-6 space-y-3 print:hidden">
        {req.status === "NEW" && (
          <Notice
            tone="info"
            title="Recibimos tu solicitud"
            summary={`Estamos revisando precios y existencias.${req.contact_phone ? "" : " Te contactaremos por WhatsApp."} Aquí verás los precios en cuanto esté lista.`}
          />
        )}
        {approved && !req.expired && !req.accepted_at && (
          <Notice
            tone="ok"
            title="Tu cotización está lista"
            summary={`Revisa los productos y precios; si estás de acuerdo, apruébala abajo.${req.valid_until ? ` Precios válidos hasta el ${formatDay(req.valid_until)}.` : ""}`}
          />
        )}
        {approved && req.accepted_at && (
          <Notice
            tone="ok"
            title={`Aprobaste esta cotización el ${formatDay(req.accepted_at)}`}
            summary="Te contactaremos para coordinar la entrega y la factura."
          />
        )}
        {req.expired && (
          <Notice
            tone="warning"
            title="Esta cotización venció"
            summary={`Sus precios fueron válidos hasta el ${formatDay(req.valid_until!)}. Solicita una actualización para confirmarlos.`}
          />
        )}
        {req.status === "REJECTED" && (
          <Notice
            tone="warning"
            title="Solicitud cerrada"
            summary={req.contact_phone ? "Si quieres retomarla, escríbenos." : "Si necesitas algo más, puedes enviar una nueva desde el catálogo."}
          />
        )}
        {req.revision && (
          <Notice
            tone="info"
            title="Tienes cambios en revisión"
            summary={
              <Link href={`/solicitud/${req.revision.token}`} className="text-blue-600 hover:underline">
                Ver solicitud #{req.revision.number}
              </Link>
            }
          />
        )}
      </div>

      <ul className="mt-6 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {req.items.map((item, i) => (
          <li key={i} className="flex items-center gap-3 p-3 sm:p-4">
            <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded bg-gray-50">
              <Image src={item.image ? `/products/${item.image}` : "/placeholder.svg"} alt="" fill sizes="56px" className="object-cover" />
            </div>
            <div className="min-w-0 flex-1">
              {item.linked && item.key ? (
                <Link href={productHref(item.key)} className="line-clamp-2 text-sm font-medium text-gray-800 hover:text-blue-700">
                  {item.name}
                </Link>
              ) : (
                <p className="line-clamp-2 text-sm font-medium text-gray-800">{item.name}</p>
              )}
              <p className="text-xs text-gray-400">
                {qty(item.quantity)} {Number(item.quantity) === 1 ? "pieza" : "piezas"}
                {approved && item.unit_price !== null && ` × ${formatMoney(item.unit_price)}`}
              </p>
              {item.due && (
                <p className={item.due < today ? "text-xs font-medium text-red-700" : "text-xs text-gray-600"}>
                  {item.due < today ? "Cambio pendiente desde" : "Cambio recomendado:"} {formatMonth(item.due.slice(0, 7))}
                </p>
              )}
            </div>
            {approved && (
              <span className="num shrink-0 text-sm font-medium text-gray-900">
                {item.subtotal !== null ? formatMoney(item.subtotal) : <span className="text-xs font-normal text-gray-500">Se cotiza aparte</span>}
              </span>
            )}
          </li>
        ))}
      </ul>

      {approved && Number(req.total) > 0 && (
        <p className="mt-4 text-right text-lg font-semibold text-gray-900">
          {Number(req.discount) > 0 && (
            <span className="block text-sm font-normal text-gray-600">
              Subtotal: <span className="num">{formatMoney(req.subtotal!)}</span>
              <br />
              Descuento {Number(req.discount)} %: <span className="num">−{formatMoney(req.discount_amount!)}</span>
            </span>
          )}
          Total: <span className="num">{formatMoney(req.total!)}</span>
          <span className="block text-xs font-normal text-gray-500">IVA incluido</span>
          {unpriced > 0 && (
            <span className="block text-xs font-normal text-gray-500">
              No incluye {plural(unpriced, "producto", "productos")} que se cotiza{unpriced > 1 && "n"} aparte
            </span>
          )}
        </p>
      )}

      <QuoteActions
        token={token}
        number={req.number}
        createdAt={req.created_at}
        items={req.items}
        approved={approved}
        expired={req.expired}
        accepted={Boolean(req.accepted_at)}
        canModify={req.can_modify}
        contactPhone={req.contact_phone}
      />

      {approved && (
        <div className="mt-8 hidden border-t border-gray-200 pt-3 text-xs text-gray-500 print:block">
          {req.valid_until && <p>{req.expired ? "Vencida el" : "Válida hasta el"} {formatDay(req.valid_until)}.</p>}
          <p>Precios con IVA incluido. Sujeto a disponibilidad. Este documento no es un comprobante fiscal.</p>
        </div>
      )}
    </main>
  );
}
