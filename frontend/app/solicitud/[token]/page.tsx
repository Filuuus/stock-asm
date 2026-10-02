import Image from "next/image";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Notice } from "@/components/notice";
import { API_URL } from "@/lib/api";
import { formatDay } from "@/lib/dates";
import { formatMoney } from "@/lib/utils";

// Personal links: keep them out of search engines.
export const metadata: Metadata = { title: "Mi solicitud | Agropecuaria Santa María", robots: { index: false, follow: false } };

interface PublicRequest {
  number: number;
  status: "NEW" | "APPROVED" | "REJECTED";
  created_at: string;
  name: string;
  valid_until: string | null;
  total: number | null;
  items: { code: string; name: string; image: string | null; quantity: number; unit_price: number | null; subtotal: number | null }[];
}

// The customer's personal link: status while it's reviewed; once approved, the
// prices frozen at approval. Knowing the link is the only access, like a
// shared document - it isn't listed or guessable.
export default async function RequestPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const res = await fetch(`${API_URL}/api/solicitudes/publica/${encodeURIComponent(token)}/`, { cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`No se pudo cargar la solicitud (${res.status})`);
  const req: PublicRequest = await res.json();
  const approved = req.status === "APPROVED";
  const qty = (n: number) => Number(n).toLocaleString("es-MX", { maximumFractionDigits: 2 });

  return (
    <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Solicitud #{req.number}</h1>
      <p className="mt-1 text-sm text-gray-500">
        {req.name} · {formatDay(req.created_at)}
      </p>

      <div className="mt-6">
        {req.status === "NEW" && (
          <Notice
            tone="info"
            title="Recibimos tu solicitud"
            summary="Estamos revisando precios y existencias. Guarda esta página: aquí verás los precios en cuanto la aprobemos."
          />
        )}
        {approved && (
          <Notice
            tone="ok"
            title="Tu cotización está lista"
            summary={req.valid_until ? `Precios válidos hasta el ${formatDay(req.valid_until)}.` : undefined}
          />
        )}
        {req.status === "REJECTED" && (
          <Notice tone="warning" title="No pudimos atender esta solicitud" summary="Contáctanos para revisarla juntos." />
        )}
      </div>

      <ul className="mt-6 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {req.items.map((item) => (
          <li key={item.code} className="flex items-center gap-3 p-3 sm:p-4">
            <div className="relative h-14 w-14 shrink-0 overflow-hidden rounded bg-gray-50">
              <Image src={item.image ? `/products/${item.image}` : "/placeholder.svg"} alt="" fill sizes="56px" className="object-cover" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="line-clamp-2 text-sm font-medium text-gray-800">{item.name}</p>
              <p className="text-xs text-gray-400">
                SKU: {item.code} · {qty(item.quantity)} {Number(item.quantity) === 1 ? "pieza" : "piezas"}
                {approved && item.unit_price !== null && ` × ${formatMoney(item.unit_price)}`}
              </p>
            </div>
            {approved && (
              <span className="num shrink-0 text-sm font-medium text-gray-900">
                {item.subtotal !== null ? formatMoney(item.subtotal) : <span className="text-xs font-normal text-gray-500">Se cotiza aparte</span>}
              </span>
            )}
          </li>
        ))}
      </ul>

      {approved && req.total !== null && (
        <p className="mt-4 text-right text-lg font-semibold text-gray-900">
          Total: <span className="num">{formatMoney(req.total)}</span>
        </p>
      )}
    </main>
  );
}
