"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, Maximize2, Minus, Plus } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Notice } from "@/components/notice";
import AddToCart from "@/components/catalog/AddToCart";
import MatCalculator from "@/components/catalog/MatCalculator";
import { CATALOG_RESTORE_KEY, CATALOG_URL_KEY } from "@/components/catalog/CatalogView";
import { HIDE_BELOW_SM } from "@/components/sortable-table";
import { CATEGORY_LABELS, lineLabel } from "@/components/catalog/CatalogFilters";
import ProductCard, { Availability, Price } from "@/components/catalog/ProductCard";
import { apiFetch } from "@/lib/api";
import { cn, formatMoney, productHref } from "@/lib/utils";
import { formatDay } from "@/lib/dates";
import { Product, ProductDetail, ProductImage, RelatedPart, ServiceRule } from "@/types/api";

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
        <p className="text-xs text-gray-400">
          {/* The public gets no codes, nor the out-of-stock products we do sell. */}
          {part.code ? `${part.code} · No está en nuestro catálogo` : "Pregunta por disponibilidad"}
        </p>
      </div>
    );
  }
  return (
    <Link href={productHref(ours.key, ours.slug)} className="group flex items-center gap-3">
      <div className="relative h-12 w-12 shrink-0 overflow-hidden rounded bg-gray-50">
        <Image src={imageSrc(ours.images)} alt="" fill sizes="48px" className="object-cover" />
      </div>
      <div className="min-w-0">
        <p className="font-medium text-gray-800 group-hover:text-blue-700">{ours.CNOMBREPRODUCTO}</p>
        {ours.CCODIGOPRODUCTO && <p className="text-xs text-gray-400">SKU: {ours.CCODIGOPRODUCTO}</p>}
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
        {sorted.map((p, i) => (
          <li key={i} className="px-4 py-3">
            <PartCell part={p} />
          </li>
        ))}
      </ul>
    </section>
  );
}

// GEA's exploded drawing: the hotspot boxes are in the image's own pixels,
// so they're placed as percentages of its natural size once it loads.
type Hotspot = { pos: string; box: [number, number, number, number] };

function DrawingCanvas({
  img,
  hotspots,
  active,
  onSelect,
  idPrefix,
  className,
}: {
  img: string;
  hotspots: Hotspot[];
  active: string | null;
  onSelect: (pos: string) => void;
  idPrefix: string; // the page and the zoom view both render it - keep ids unique
  className?: string;
}) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  // Once the boxes exist, bring a pre-selected part into view.
  const [initial] = useState(active);
  useEffect(() => {
    if (size && initial) document.getElementById(`${idPrefix}-${initial}`)?.scrollIntoView({ block: "center", inline: "center" });
  }, [size, initial, idPrefix]);
  return (
    <div className={cn("relative", className)}>
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
            id={hotspots.findIndex((x) => x.pos === h.pos) === i ? `${idPrefix}-${h.pos}` : undefined}
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

const ZOOMS = [1, 1.5, 2, 3];

// The drawing on the page, plus "Ampliar": full screen, zoomable and scrollable
// for phones, numbers still clickable (picking one closes it and shows the row).
function Drawing(props: { img: string; hotspots: Hotspot[]; active: string | null; onSelect: (pos: string) => void }) {
  const [open, setOpen] = useState(false);
  const [zoom, setZoom] = useState(1);
  // A number picked in the zoom view is applied once the view has closed, so
  // the page can scroll to its row (an open dialog locks the page scroll).
  const picked = useRef<string | null>(null);
  return (
    <>
      <DrawingCanvas {...props} idPrefix="hs" className="mx-auto w-full max-w-xl" />
      <div className="mt-2 text-center">
        <button
          type="button"
          onClick={() => {
            setZoom(2);
            setOpen(true);
          }}
          className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          <Maximize2 className="h-4 w-4" />
          Ampliar dibujo
        </button>
      </div>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="flex h-[100dvh] max-w-none flex-col gap-0 p-0 sm:h-[90vh] sm:max-w-5xl"
          onCloseAutoFocus={(e) => {
            if (!picked.current) return;
            e.preventDefault(); // don't jump back to the "Ampliar" button
            const pos = picked.current;
            picked.current = null;
            // After the dialog releases the page's scroll lock, which would undo our scroll.
            setTimeout(() => props.onSelect(pos), 50);
          }}
        >
          <div className="flex items-center gap-2 border-b px-4 py-3 pr-12">
            <DialogTitle className="flex-1 text-base">Dibujo de despiece</DialogTitle>
            <button
              type="button"
              aria-label="Alejar"
              disabled={zoom === ZOOMS[0]}
              onClick={() => setZoom(ZOOMS[ZOOMS.indexOf(zoom) - 1])}
              className="rounded border px-2 py-1 disabled:opacity-40"
            >
              <Minus className="h-4 w-4" />
            </button>
            <span className="w-12 text-center text-sm text-gray-600">{zoom * 100}%</span>
            <button
              type="button"
              aria-label="Acercar"
              disabled={zoom === ZOOMS[ZOOMS.length - 1]}
              onClick={() => setZoom(ZOOMS[ZOOMS.indexOf(zoom) + 1])}
              className="rounded border px-2 py-1 disabled:opacity-40"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-auto bg-white">
            {/* Width grows with the zoom; the boxes are percentages, so they follow. */}
            <div style={{ width: `${zoom * 100}%` }}>
              <DrawingCanvas
                {...props}
                idPrefix="hs-zoom"
                className="w-full"
                onSelect={(pos) => {
                  picked.current = pos;
                  setOpen(false);
                }}
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

const PERIODS: Record<number, string> = { 0.25: "cada semana", 1: "cada mes", 12: "cada año" };
const period = (m: number) => PERIODS[m] ?? (m % 12 === 0 ? `cada ${m / 12} años` : `cada ${m} meses`);

// "Reemplazar cada 750 horas de trabajo o cada 6 meses"
function ruleText(r: ServiceRule) {
  const action = r.action.charAt(0).toUpperCase() + r.action.slice(1);
  const when = [r.hours && `cada ${r.hours.toLocaleString("es-MX")} horas de trabajo`, r.months && period(r.months)]
    .filter(Boolean)
    .join(" o ");
  return `${action} ${when}`;
}

function Service({ service }: { service: NonNullable<NonNullable<ProductDetail["gea"]>["service"]> }) {
  return (
    <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4 text-sm">
      <h2 className="font-semibold text-gray-900">Mantenimiento</h2>
      {service.rules.length > 0 ? (
        <ul className="mt-1 space-y-0.5 text-gray-700">
          {service.rules.map((r, i) => (
            <li key={i}>{ruleText(r)}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-gray-500">Depende del equipo donde se usa.</p>
      )}
      {service.rules.some((r) => r.hours && r.months) && (
        <p className="mt-1 text-xs text-gray-500">Lo que ocurra primero. Recomendación de GEA.</p>
      )}
      {service.in_assemblies.length > 0 && (
        <details className="group mt-3" open={service.rules.length === 0}>
          <summary className="cursor-pointer list-none text-blue-600 hover:underline [&::-webkit-details-marker]:hidden">
            En equipos específicos ({service.in_assemblies.length})
          </summary>
          <ul className="mt-2 space-y-1.5">
            {service.in_assemblies.map((a, i) => (
              <li key={`${a.code}-${i}`}>
                {a.ours[0] ? (
                  <Link href={productHref(a.ours[0].key, a.ours[0].slug)} className="text-gray-800 hover:text-blue-700">
                    {a.ours[0].CNOMBREPRODUCTO}
                  </Link>
                ) : (
                  <span className="text-gray-800">{a.desc}</span>
                )}
                <span className="block text-xs text-gray-500">{ruleText(a)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

const units = (n: number) => n.toLocaleString("es-MX", { maximumFractionDigits: 2 });

// Staff only: where the stock is (General, Matriz, the technicians' trucks...)
// and how the product moves.
function StaffBox({ staff }: { staff: NonNullable<ProductDetail["staff"]> }) {
  return (
    <div className="mt-6 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
      <h2 className="font-semibold text-gray-900">
        Para personal <span className="font-normal text-gray-500">· solo visible al iniciar sesión</span>
      </h2>
      <p className="mt-2 text-xs font-medium uppercase tracking-wide text-gray-500">Existencias por almacén</p>
      {staff.warehouses.length > 0 ? (
        <ul className="mt-1 space-y-0.5 text-gray-700">
          {staff.warehouses.map((w) => (
            <li key={w.name} className="flex justify-between gap-3">
              <span className="min-w-0 truncate">{w.name}</span>
              <span className={cn("num shrink-0", w.units < 0 && "text-red-600")}>{units(w.units)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-gray-500">Sin existencias en ningún almacén.</p>
      )}
      <p className="mt-3 text-gray-700">
        Vendidas en 12 meses: <span className="font-medium">{units(staff.sold_12m)}</span>
        {" · "}Última venta: <span className="font-medium">{staff.last_sale ? formatDay(staff.last_sale) : "nunca"}</span>
      </p>
    </div>
  );
}

// GEA's manuals are document numbers (to request the manual), one per language.
// Spanish and English first; the rest folded away.
function Manuals({ manuals }: { manuals: { code: string; lang: string }[] }) {
  const main = manuals
    .filter((m) => m.lang === "Español" || m.lang === "English")
    .sort((a, b) => Number(b.lang === "Español") - Number(a.lang === "Español"));
  const others = manuals.filter((m) => !main.includes(m));
  const item = (m: { code: string; lang: string }) => (
    <li key={`${m.code}-${m.lang}`}>
      {m.lang} <span className="text-gray-500">· {m.code}</span>
    </li>
  );
  return (
    <div className="mt-4 rounded-lg border border-gray-200 bg-white p-4 text-sm">
      <h2 className="font-semibold text-gray-900">Manuales</h2>
      <p className="text-xs text-gray-500">Número de documento GEA, para solicitar el manual.</p>
      {main.length > 0 && <ul className="mt-1 space-y-0.5 text-gray-700">{main.map(item)}</ul>}
      {others.length > 0 && (
        <details className="mt-2" open={main.length === 0}>
          <summary className="cursor-pointer list-none text-blue-600 hover:underline [&::-webkit-details-marker]:hidden">
            {main.length > 0 ? `Otros idiomas (${others.length})` : `Idiomas disponibles (${others.length})`}
          </summary>
          <ul className="mt-1 space-y-0.5 text-gray-700">{others.map(item)}</ul>
        </details>
      )}
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
          <li key={parent.key} className="px-4 py-3">
            <Link
              href={`${productHref(parent.key, parent.slug)}?pieza=${encodeURIComponent(product.key)}`}
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

// Catálogo › Bionat › Sustitutos de leche, each a link to the filtered catalog.
function Breadcrumb({ product }: { product: ProductDetail }) {
  const category = new URLSearchParams({ categoria: product.category });
  const crumbs = [{ href: `/catalogo?${category}`, label: CATEGORY_LABELS[product.category] ?? product.category }];
  if (product.line) {
    category.append("linea", product.line);
    crumbs.push({ href: `/catalogo?${category}`, label: lineLabel(product.line) });
  }
  return (
    <nav aria-label="Ruta" className="mb-4 -mt-2 flex flex-wrap items-center gap-1 text-sm text-gray-500">
      {crumbs.map((c, i) => (
        <span key={c.href} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3.5 w-3.5" />}
          <Link href={c.href} className="hover:text-blue-700 hover:underline">{c.label}</Link>
        </span>
      ))}
    </nav>
  );
}

// The main photo plus thumbnails to switch between them.
function Gallery({ images, alt }: { images: ProductImage[]; alt: string }) {
  const [index, setIndex] = useState(Math.max(images.findIndex((i) => i.is_primary), 0));
  const current = images[index];
  return (
    <div className="mx-auto w-full max-w-md">
      <div className="relative aspect-square overflow-hidden rounded-xl border border-gray-200 bg-white">
        <Image
          src={current ? `/products/${current.file}` : "/placeholder.svg"}
          alt={alt}
          fill
          sizes="(min-width: 768px) 50vw, 100vw"
          className="object-contain"
          priority
        />
      </div>
      {images.length > 1 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {images.map((img, i) => (
            <button
              key={img.id}
              type="button"
              onClick={() => setIndex(i)}
              aria-label={`Ver imagen ${i + 1}`}
              className={cn(
                "relative h-16 w-16 overflow-hidden rounded-lg border bg-white",
                i === index ? "border-blue-600 ring-1 ring-blue-600" : "border-gray-200 hover:border-gray-400",
              )}
            >
              <Image src={`/products/${img.file}`} alt="" fill sizes="64px" className="object-contain" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// The product's description; staff can write or edit it right here.
function Description({ product }: { product: ProductDetail }) {
  const [text, setText] = useState(product.description ?? "");
  const [draft, setDraft] = useState<string | null>(null); // null = not editing
  const [error, setError] = useState<string | null>(null);
  const isStaff = product.staff !== null;

  const save = async () => {
    setError(null);
    const res = await apiFetch(`/api/inventory/${product.key}/descripcion/`, {
      method: "PUT",
      body: JSON.stringify({ text: draft }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) return setError(data.error ?? "No se pudo guardar.");
    setText(data.description ?? "");
    setDraft(null);
  };

  if (!text && !isStaff) return null;
  return (
    <section className="mt-10 max-w-3xl">
      <h2 className="mb-3 text-lg font-semibold text-gray-900">Descripción</h2>
      {draft !== null ? (
        <>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={10}
            maxLength={4000}
            placeholder="Para qué sirve, características, presentación, uso recomendado…"
            className="w-full rounded-lg border border-gray-300 p-3 text-sm"
          />
          {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
          <div className="mt-2 flex gap-2">
            <button type="button" onClick={save} className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">
              Guardar
            </button>
            <button type="button" onClick={() => setDraft(null)} className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50">
              Cancelar
            </button>
          </div>
        </>
      ) : (
        <>
          {text ? (
            <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700">{text}</p>
          ) : (
            <p className="text-sm text-gray-400">Sin descripción.</p>
          )}
          {isStaff && (
            <button type="button" onClick={() => setDraft(text)} className="mt-2 text-xs text-blue-600 hover:underline">
              {text ? "Editar descripción" : "Agregar descripción"}
            </button>
          )}
        </>
      )}
    </section>
  );
}

// mat: set on full-size mat pages, with the nails to count alongside.
export default function ProductDetailView({
  product,
  highlight,
  mat,
}: {
  product: ProductDetail;
  highlight?: string;
  mat?: { nail: Product | null };
}) {
  const router = useRouter();
  const gea = product.gea;
  // Arriving from a part's "Aparece en" (our product's key) or the staff GEA
  // part search (a GEA code): start with that part selected.
  const highlightPos =
    highlight &&
    gea?.parts.find((p) => p.ours.some((o) => o.key === highlight) || (p.code && highlight.startsWith(p.code)))?.pos;
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
      <Link
        href="/catalogo"
        scroll={false}
        onClick={(e) => {
          // Back to the same filtered list and scroll position the user left.
          let url = "/catalogo";
          try {
            url = sessionStorage.getItem(CATALOG_URL_KEY) || "/catalogo";
            sessionStorage.setItem(CATALOG_RESTORE_KEY, "1");
          } catch {
            // storage blocked: plain link to the catalog
          }
          e.preventDefault();
          router.push(url, { scroll: false });
        }}
        className="mb-4 inline-flex items-center gap-1 text-sm text-blue-600 hover:underline"
      >
        <ChevronLeft className="h-4 w-4" />
        Catálogo
      </Link>
      <Breadcrumb product={product} />

      <div className="grid gap-6 md:grid-cols-2">
        <Gallery images={product.images} alt={product.CNOMBREPRODUCTO} />
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">{product.CNOMBREPRODUCTO}</h1>
          {product.CCODIGOPRODUCTO && <p className="mt-1 text-sm text-gray-400">SKU: {product.CCODIGOPRODUCTO}</p>}
          {gea && <p className="mt-4 text-gray-700">{gea.desc}</p>}
          <Price product={product} className="mt-4 block !text-3xl" />
          {product.price !== null && product.price > 0 && (
            <p className="mt-1 text-xs text-gray-500">
              IVA incluido
              {/* Staff also get the ERP's price before IVA. */}
              {product.staff && product.CPRECIO1 !== null && ` · Sin IVA: ${formatMoney(product.CPRECIO1)}`}
            </p>
          )}
          <Availability product={product} className="mt-2 text-sm" />
          <AddToCart product={product} withQuantity className="mt-4 max-w-sm" />
          {mat && <MatCalculator mat={product} nail={mat.nail} />}
          {product.staff && <StaffBox staff={product.staff} />}
          {gea?.service && <Service service={gea.service} />}
          {gea && gea.manuals.length > 0 && <Manuals manuals={gea.manuals} />}
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
                        <Link href={productHref(note.replacement_ours[0].key, note.replacement_ours[0].slug)} className="font-medium underline">
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

      <Description product={product} />

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
      {product.related.length > 0 && (
        <section className="mt-10">
          <h2 className="mb-3 text-lg font-semibold text-gray-900">Productos relacionados</h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4">
            {product.related.map((p) => (
              <ProductCard key={p.key} product={p} />
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
