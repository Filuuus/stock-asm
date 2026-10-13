"use client";

import { useEffect, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Camera, Loader2, X } from "lucide-react";
import { Notice } from "@/components/notice";
import { productHref } from "@/lib/utils";
import { normalize } from "@/components/catalog/CatalogFilters";
import { useAuth } from "@/hooks/use-auth";
import { apiFetch } from "@/lib/api";
import { cn, plural } from "@/lib/utils";
import { Product, ProductImage } from "@/types/api";

const PAGE = 40;

// Staff page for photographing products from a phone: products without a
// photo first, in stock first, best sellers first.
export default function PhotosView() {
  const { user, loading } = useAuth();
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [all, setAll] = useState(false); // also products that already have photos
  const [shown, setShown] = useState(PAGE);
  // Products photographed in this visit stay in the list, so the result shows.
  const [touched, setTouched] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!user) return;
    apiFetch("/api/inventory/")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setProducts)
      .catch(() => setError("No se pudo cargar el catálogo."));
  }, [user]);

  const list = useMemo(() => {
    if (!products) return [];
    const q = normalize(query.trim());
    return products
      .filter((p) => all || p.images.length === 0 || touched.has(p.key))
      .filter((p) => !q || normalize(`${p.CNOMBREPRODUCTO} ${p.CCODIGOPRODUCTO ?? ""}`).includes(q))
      .sort(
        (a, b) =>
          Number(b.in_stock) - Number(a.in_stock) ||
          (a.sold_rank ?? Infinity) - (b.sold_rank ?? Infinity) ||
          a.CNOMBREPRODUCTO.localeCompare(b.CNOMBREPRODUCTO),
      );
  }, [products, query, all, touched]);

  const setImages = (key: string, images: ProductImage[]) => {
    setTouched((t) => new Set(t).add(key));
    setProducts((ps) => ps && ps.map((p) => (p.key === key ? { ...p, images } : p)));
  };

  if (!loading && !user) {
    return (
      <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
        <Notice tone="info" title="Inicia sesión para subir fotos." action={<Link href="/login" className="underline">Iniciar sesión</Link>} />
      </main>
    );
  }

  const missingInStock = products?.filter((p) => p.in_stock && p.images.length === 0).length;

  return (
    <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Fotos de productos</h1>
      <p className="mt-1 text-sm text-gray-500">
        {missingInStock === undefined
          ? "Cargando…"
          : `${plural(missingInStock, "producto", "productos")} en existencia sin foto. Toma la foto con el producto sobre un fondo claro.`}
      </p>
      {error && <div className="mt-4"><Notice tone="error" title={error} /></div>}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setShown(PAGE);
          }}
          placeholder="Buscar por nombre o código"
          className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm sm:w-auto sm:min-w-0 sm:flex-1"
        />
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
          Incluir los que ya tienen foto
        </label>
      </div>

      <ul className="mt-4 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
        {list.slice(0, shown).map((p) => (
          <PhotoRow key={p.key} product={p} onChange={(images) => setImages(p.key, images)} />
        ))}
        {products && list.length === 0 && <li className="p-4 text-sm text-gray-500">No hay productos con ese filtro.</li>}
      </ul>
      {list.length > shown && (
        <button
          type="button"
          onClick={() => setShown((n) => n + PAGE)}
          className="mt-4 w-full rounded-lg border border-gray-300 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Ver más ({list.length - shown})
        </button>
      )}
    </main>
  );
}

function PhotoRow({ product, onChange }: { product: Product; onChange: (images: ProductImage[]) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const upload = async (file: File) => {
    setBusy(true);
    setError(null);
    const body = new FormData();
    body.append("foto", file);
    try {
      const res = await apiFetch(`/api/inventory/${product.key}/fotos/`, { method: "POST", body });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "No se pudo subir la foto.");
      onChange([...product.images, data]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo subir la foto.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (img: ProductImage) => {
    if (!confirm("¿Quitar esta foto del catálogo?")) return;
    const res = await apiFetch(`/api/inventory/${product.key}/fotos/${img.id}/`, { method: "DELETE" });
    if (!res.ok) return setError("No se pudo quitar la foto.");
    const rest = product.images.filter((i) => i.id !== img.id);
    // The server promotes the next photo to primary; mirror it.
    onChange(img.is_primary && rest[0] ? [{ ...rest[0], is_primary: true }, ...rest.slice(1)] : rest);
  };

  return (
    <li className="p-3 sm:p-4">
      <div className="flex items-center gap-3">
        <div className="min-w-0 flex-1">
          <Link href={productHref(product.key, product.slug)} className="line-clamp-2 text-sm font-medium text-gray-800 hover:text-blue-700">
            {product.CNOMBREPRODUCTO}
          </Link>
          <p className={cn("text-xs", product.in_stock ? "text-green-700" : "text-gray-400")}>
            {product.CCODIGOPRODUCTO} · {product.in_stock
              ? `${(product.stock ?? 0).toLocaleString("es-MX", { maximumFractionDigits: 2 })} en almacén`
              : "Sin existencia"}
          </p>
        </div>
        {/* No `capture`: phones offer both the camera and the gallery. */}
        <label
          className={cn(
            "inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700",
            busy && "pointer-events-none opacity-60",
          )}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Camera className="h-4 w-4" />}
          Foto
          <input
            type="file"
            accept="image/*"
            className="sr-only"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = ""; // the same file can be picked again
              if (file) upload(file);
            }}
          />
        </label>
      </div>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      {product.images.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {product.images.map((img) => (
            <div key={img.id} className="relative h-20 w-20 overflow-hidden rounded border border-gray-200 bg-gray-50">
              <Image src={`/products/${img.file}`} alt="" fill sizes="80px" className="object-cover" />
              <button
                type="button"
                onClick={() => remove(img)}
                aria-label="Quitar foto"
                className="absolute right-0.5 top-0.5 rounded-full bg-white/90 p-0.5 text-gray-600 hover:text-red-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </li>
  );
}
