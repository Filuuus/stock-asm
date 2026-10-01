"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { Notice } from "@/components/notice";
import { HIDE_BELOW_SM } from "@/components/sortable-table";
import { CATEGORY_LABELS } from "@/components/catalog/CatalogFilters";
import { Availability, Price, productHref } from "@/components/catalog/ProductCard";
import { cn } from "@/lib/utils";
import { ProductDetail, RelatedPart } from "@/types/api";

const imageSrc = (images: { file: string; is_primary: boolean }[]) => {
  const img = images.find((i) => i.is_primary) ?? images[0];
  return img ? `/products/${img.file}` : "/placeholder.svg";
};

// One related part: our product (linked, with price and stock) when we sell
// it, otherwise GEA's description so the customer still knows what it is.
function PartCell({ part }: { part: RelatedPart }) {
  const ours = part.ours[0];
  if (!ours) {
    return (
      <div>
        <p className="text-gray-700">{part.desc}</p>
        <p className="text-xs text-gray-400">{part.code} · No está en nuestro catálogo</p>
      </div>
    );
  }
  return (
    <Link href={productHref(ours.CCODIGOPRODUCTO)} className="group flex items-center gap-3">
      <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded bg-gray-50">
        <Image src={imageSrc(ours.images)} alt="" fill sizes="48px" className="object-cover" />
      </div>
      <div className="min-w-0">
        <p className="font-medium text-gray-800 group-hover:text-blue-700">{ours.CNOMBREPRODUCTO}</p>
        <p className="text-xs text-gray-400">SKU: {ours.CCODIGOPRODUCTO}</p>
        <div className="flex flex-wrap items-baseline gap-x-3">
          <Price product={ours} className="!text-sm" />
          <Availability product={ours} />
        </div>
      </div>
    </Link>
  );
}

function PartsList({ title, parts }: { title: string; parts: RelatedPart[] }) {
  if (parts.length === 0) return null;
  // Products we sell first.
  const sorted = [...parts].sort((a, b) => Number(b.ours.length > 0) - Number(a.ours.length > 0));
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-semibold text-gray-900">{title}</h2>
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white text-sm">
        {sorted.map((p) => (
          <li key={p.code} className="px-4 py-3">
            <PartCell part={p} />
          </li>
        ))}
      </ul>
    </section>
  );
}

// GEA's exploded drawing: the hotspot boxes are in the image's own pixels,
// so they're placed as percentages of its natural size once it loads.
function Drawing({
  img,
  hotspots,
  active,
  onSelect,
}: {
  img: string;
  hotspots: { pos: string; box: [number, number, number, number] }[];
  active: string | null;
  onSelect: (pos: string) => void;
}) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  // Once the boxes exist, bring a pre-selected part into view.
  const [initial] = useState(active);
  useEffect(() => {
    if (size && initial) document.getElementById(`hs-${initial}`)?.scrollIntoView({ block: "center" });
  }, [size, initial]);
  return (
    <div className="relative mx-auto w-full max-w-xl">
      {/* Plain img: the hotspots need the drawing's natural size, unresized. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={img}
        alt="Dibujo de despiece"
        className="w-full"
        // A cached drawing can finish loading before React attaches onLoad,
        // so also read its size when the element is attached.
        ref={(el) => {
          if (el?.complete && el.naturalWidth && !size) setSize({ w: el.naturalWidth, h: el.naturalHeight });
        }}
        onLoad={(e) => setSize({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
      />
      {size &&
        hotspots.map((h, i) => (
          <button
            key={`${h.pos}-${i}`}
            id={hotspots.findIndex((x) => x.pos === h.pos) === i ? `hs-${h.pos}` : undefined}
            type="button"
            onClick={() => onSelect(h.pos)}
            aria-label={`Posición ${Number(h.pos)}`}
            className={cn(
              "absolute rounded border-2 transition-colors",
              active === h.pos ? "border-blue-600 bg-blue-500/20" : "border-transparent hover:border-blue-400"
            )}
            style={{
              left: `${(h.box[0] / size.w) * 100}%`,
              top: `${(h.box[1] / size.h) * 100}%`,
              width: `${((h.box[2] - h.box[0]) / size.w) * 100}%`,
              height: `${((h.box[3] - h.box[1]) / size.h) * 100}%`,
            }}
          />
        ))}
    </div>
  );
}

// Where this part is used: each assembly opens on its drawing with the part selected.
function AppearsIn({ product }: { product: ProductDetail }) {
  if (product.appears_in.length === 0) return null;
  return (
    <section className="mt-8">
      <h2 className="mb-3 text-lg font-semibold text-gray-900">Aparece en</h2>
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white text-sm">
        {product.appears_in.map(({ parent, pos, qty, has_drawing }) => (
          <li key={parent.CCODIGOPRODUCTO} className="px-4 py-3">
            <Link
              href={`${productHref(parent.CCODIGOPRODUCTO)}?pieza=${encodeURIComponent(product.CCODIGOPRODUCTO)}`}
              className="group flex items-center gap-3"
            >
              <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded bg-gray-50">
                <Image src={imageSrc(parent.images)} alt="" fill sizes="48px" className="object-cover" />
              </div>
              <div className="min-w-0">
                <p className="font-medium text-gray-800 group-hover:text-blue-700">{parent.CNOMBREPRODUCTO}</p>
                <p className="text-xs text-gray-500">
                  {has_drawing ? `Posición ${Number(pos)} en el dibujo` : `Posición ${Number(pos)}`} · {qty}{" "}
                  {qty === 1 ? "pieza" : "piezas"}
                </p>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ProductDetailView({ product, highlight }: { product: ProductDetail; highlight?: string }) {
  const gea = product.gea;
  // Arriving from a part's "Aparece en": start with that part selected.
  const highlightPos =
    highlight &&
    gea?.parts.find((p) => p.ours.some((o) => o.CCODIGOPRODUCTO === highlight) || highlight.startsWith(p.code))?.pos;
  const [active, setActive] = useState<string | null>(highlightPos || null);
  // Without a drawing, bring the part's row into view instead (the drawing scrolls itself).
  useEffect(() => {
    if (highlightPos && !gea?.drawing) document.getElementById(`pos-${highlightPos}`)?.scrollIntoView({ block: "center" });
  }, [highlightPos, gea?.drawing]);
  const select = (pos: string) => {
    setActive(pos);
    document.getElementById(`pos-${pos}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  const note = gea?.note;
  const replacement = note?.replacement;

  return (
    <main className="mx-auto w-full max-w-7xl p-4 sm:p-6">
      <Link href="/" className="mb-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline">
        <ChevronLeft className="h-4 w-4" />
        Catálogo
      </Link>

      <div className="grid gap-6 md:grid-cols-2">
        <div className="relative mx-auto aspect-square w-full max-w-md overflow-hidden rounded-xl border border-gray-200 bg-white">
          <Image
            src={imageSrc(product.images)}
            alt={product.CNOMBREPRODUCTO}
            fill
            sizes="(min-width: 768px) 50vw, 100vw"
            className="object-contain"
            priority
          />
        </div>
        <div>
          <p className="text-sm text-gray-500">{CATEGORY_LABELS[product.category] ?? product.category}</p>
          <h1 className="mt-1 text-2xl font-semibold text-gray-900">{product.CNOMBREPRODUCTO}</h1>
          <p className="mt-1 text-sm text-gray-400">SKU: {product.CCODIGOPRODUCTO}</p>
          {gea && <p className="mt-4 text-gray-700">{gea.desc}</p>}
          <Price product={product} className="mt-4 block !text-3xl" />
          <Availability product={product} className="mt-2 text-sm" />
          {note && (
            <div className="mt-6">
              <Notice
                tone={note.not_orderable ? "warning" : "info"}
                title={note.not_orderable ? "GEA ya no surte esta pieza" : "Nota de GEA"}
                summary={
                  replacement ? (
                    <>
                      Reemplazo:{" "}
                      {note.replacement_ours[0] ? (
                        <Link href={productHref(note.replacement_ours[0].CCODIGOPRODUCTO)} className="font-medium underline">
                          {note.replacement_ours[0].CNOMBREPRODUCTO} ({replacement})
                        </Link>
                      ) : (
                        <span className="font-medium">{replacement}</span>
                      )}{" "}
                      · Solo visible para personal
                    </>
                  ) : (
                    "Solo visible para personal"
                  )
                }
              >
                {note.text}
              </Notice>
            </div>
          )}
        </div>
      </div>

      {gea?.drawing?.img && (
        <section className="mt-10">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Dibujo de despiece</h2>
          <p className="mb-3 text-sm text-gray-500">Toca un número en el dibujo para ver la pieza.</p>
          <Drawing img={gea.drawing.img} hotspots={gea.drawing.hotspots} active={active} onSelect={select} />
        </section>
      )}

      {gea && gea.parts.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Componentes</h2>
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500">
                <tr>
                  <th className={cn("w-px whitespace-nowrap px-4 py-2 font-medium", HIDE_BELOW_SM)}>Pos.</th>
                  <th className="w-px whitespace-nowrap px-3 py-2 font-medium sm:px-4">Cant.</th>
                  <th className="px-4 py-2 font-medium">Pieza</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {gea.parts.map((p, i) => (
                  <tr
                    key={`${p.pos}-${p.code}-${i}`}
                    id={i === gea.parts.findIndex((x) => x.pos === p.pos) ? `pos-${p.pos}` : undefined}
                    onClick={() => p.pos && setActive(p.pos)}
                    className={cn("align-top", active === p.pos && "bg-blue-50")}
                  >
                    <td className={cn("px-4 py-3 text-gray-500", HIDE_BELOW_SM)}>{Number(p.pos)}</td>
                    <td className="px-3 py-3 text-gray-500 sm:px-4">{p.qty}</td>
                    <td className="py-3 pr-3 sm:px-4">
                      <PartCell part={p} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <AppearsIn product={product} />
      {gea && <PartsList title="Refacciones" parts={gea.spare_parts} />}
      {gea && <PartsList title="Se usa en" parts={gea.used_in} />}
    </main>
  );
}
