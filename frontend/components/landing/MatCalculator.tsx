"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ShoppingCart } from "lucide-react";
import { useCart } from "@/hooks/use-cart";
import { matsForArea, NAILS_PER_MAT } from "@/lib/mats";
import { cn, formatMoney } from "@/lib/utils";
import { Product } from "@/types/api";

type Mode = "camas" | "area";

const INPUT = "w-full rounded-lg border border-gray-300 px-3 py-2 text-base";
const image = (p: Product) => (p.images.find((i) => i.is_primary) ?? p.images[0])?.file ?? null;

// Mats and nails for a job, priced from the public catalog, added to the quote request in one click.
export default function MatCalculator({ mats, nail }: { mats: Product[]; nail: Product | null }) {
  const { add } = useCart();
  const [mode, setMode] = useState<Mode>("camas");
  const [beds, setBeds] = useState("");
  const [length, setLength] = useState("");
  const [width, setWidth] = useState("");
  const [matKey, setMatKey] = useState(mats[0]?.key ?? "");
  const [added, setAdded] = useState(false);

  const mat = mats.find((m) => m.key === matKey);
  // One 4 × 6 ft mat per bed.
  const matCount = mode === "camas" ? Math.max(Math.floor(Number(beds)) || 0, 0) : matsForArea(Number(length), Number(width));
  const nailCount = nail ? matCount * NAILS_PER_MAT : 0;
  const total = (mat?.price ?? 0) * matCount + (nail?.price ?? 0) * nailCount;

  const addToRequest = () => {
    if (!mat || !matCount) return;
    add({ key: mat.key, name: mat.CNOMBREPRODUCTO, image: image(mat) }, matCount);
    if (nail) add({ key: nail.key, name: nail.CNOMBREPRODUCTO, image: image(nail) }, nailCount);
    setAdded(true);
  };
  const edit = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    set(e.target.value);
    setAdded(false);
  };

  if (!mats.length) return <p className="text-slate-600">Por ahora no hay tapetes con precio en el catálogo.</p>;

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div className="space-y-5 rounded-xl border border-gray-200 bg-white p-5">
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-100 p-1">
          {(
            [
              ["camas", "Camas o echaderos"],
              ["area", "Pasillos o áreas"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => {
                setMode(value);
                setAdded(false);
              }}
              className={cn(
                "rounded-md px-3 py-2 text-sm font-medium",
                mode === value ? "bg-white text-slate-900 shadow-sm" : "text-slate-600",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === "camas" ? (
          <label className="block">
            <span className="text-sm font-medium text-slate-700">¿Cuántas camas?</span>
            <input type="number" min="1" step="1" inputMode="numeric" value={beds} onChange={edit(setBeds)} className={cn(INPUT, "mt-1")} />
            <span className="mt-1 block text-xs text-slate-500">Un tapete de 4 × 6 pies (1.22 × 1.83 m) por cama.</span>
          </label>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Largo (m)</span>
              <input type="number" min="0" step="0.1" inputMode="decimal" value={length} onChange={edit(setLength)} className={cn(INPUT, "mt-1")} />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Ancho (m)</span>
              <input type="number" min="0" step="0.1" inputMode="decimal" value={width} onChange={edit(setWidth)} className={cn(INPUT, "mt-1")} />
            </label>
          </div>
        )}

        <label className="block">
          <span className="text-sm font-medium text-slate-700">Tapete</span>
          <select value={matKey} onChange={edit(setMatKey)} className={cn(INPUT, "mt-1 bg-white")}>
            {mats.map((m) => (
              <option key={m.key} value={m.key}>
                {m.CNOMBREPRODUCTO} · {formatMoney(m.price ?? 0)}
                {!m.in_stock && " · sobre pedido"}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex flex-col rounded-xl bg-slate-900 p-5 text-white">
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between gap-4">
            <dt className="text-slate-300">Tapetes</dt>
            <dd>{matCount}</dd>
          </div>
          {nail && (
            <div className="flex justify-between gap-4">
              <dt className="text-slate-300">Clavos ({NAILS_PER_MAT} por tapete)</dt>
              <dd>{nailCount}</dd>
            </div>
          )}
          <div className="flex justify-between gap-4 border-t border-slate-700 pt-2 text-lg font-bold">
            <dt>Total estimado</dt>
            <dd>{formatMoney(total)}</dd>
          </div>
        </dl>
        <p className="mt-2 text-xs text-slate-400">
          IVA incluido. Es un estimado: nuestro instalador confirma la cantidad al medir su establo. La instalación se
          cotiza aparte.
        </p>
        <button
          type="button"
          disabled={!matCount}
          onClick={addToRequest}
          className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-lg bg-emerald-500 px-5 py-3 font-semibold hover:bg-emerald-400 disabled:opacity-50 max-md:mt-5"
        >
          {added ? <Check className="h-5 w-5" /> : <ShoppingCart className="h-5 w-5" />}
          {added ? "Agregado a su solicitud" : "Agregar a mi solicitud"}
        </button>
        {added && (
          <Link href="/carrito" className="mt-3 text-center text-sm text-emerald-400 hover:underline">
            Ver mi solicitud y enviarla
          </Link>
        )}
      </div>
    </div>
  );
}
