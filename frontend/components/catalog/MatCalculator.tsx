"use client";

import { useState } from "react";
import Link from "next/link";
import { useCart } from "@/hooks/use-cart";
import { matsForArea, NAILS_PER_MAT } from "@/lib/mats";
import { cn, formatMoney } from "@/lib/utils";
import { ProductImage } from "@/types/api";

type Item = { key: string; CNOMBREPRODUCTO: string; price: number | null; images: ProductImage[] };

const INPUT = "w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm";
const image = (p: Item) => (p.images.find((i) => i.is_primary) ?? p.images[0])?.file ?? null;

// On a 4 × 6 ft mat's page: how many mats (and nails) a job takes, added to the quote request together.
export default function MatCalculator({ mat, nail }: { mat: Item; nail: Item | null }) {
  const { add } = useCart();
  const [byArea, setByArea] = useState(false);
  const [beds, setBeds] = useState("");
  const [length, setLength] = useState("");
  const [width, setWidth] = useState("");
  const [added, setAdded] = useState(false);

  // One mat per bed.
  const mats = byArea ? matsForArea(Number(length), Number(width)) : Math.max(Math.floor(Number(beds)) || 0, 0);
  const nails = nail ? mats * NAILS_PER_MAT : 0;
  const total = (mat.price ?? 0) * mats + (nail?.price ?? 0) * nails;
  const edit = (set: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement>) => {
    set(e.target.value);
    setAdded(false);
  };
  const number = (label: string, value: string, set: (v: string) => void, decimal = false) => (
    <label className="block flex-1 text-xs text-gray-600">
      {label}
      <input
        type="number"
        min="0"
        step={decimal ? "0.1" : "1"}
        inputMode={decimal ? "decimal" : "numeric"}
        value={value}
        onChange={edit(set)}
        className={cn(INPUT, "mt-1")}
      />
    </label>
  );

  return (
    <section className="mt-6 max-w-sm rounded-lg border border-gray-200 bg-gray-50 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-semibold text-gray-900">¿Cuántos necesita?</h2>
        <button
          type="button"
          onClick={() => {
            setByArea(!byArea);
            setAdded(false);
          }}
          className="text-sm text-blue-600 hover:underline"
        >
          {byArea ? "Calcular por camas" : "Calcular por área"}
        </button>
      </div>
      <div className="mt-2 flex gap-2">
        {byArea ? (
          <>
            {number("Largo (m)", length, setLength, true)}
            {number("Ancho (m)", width, setWidth, true)}
          </>
        ) : (
          number("Camas (un tapete por cama)", beds, setBeds)
        )}
      </div>
      {mats > 0 && (
        <>
          <p className="mt-3 text-sm text-gray-700">
            {mats} tapetes{nail && ` + ${nails} clavos (${NAILS_PER_MAT} por tapete)`}:{" "}
            <span className="font-semibold text-gray-900">{formatMoney(total)}</span>
          </p>
          <p className="mt-1 text-xs text-gray-500">
            Estimado con IVA. El instalador confirma la cantidad; la instalación se cotiza aparte.
          </p>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                add({ key: mat.key, name: mat.CNOMBREPRODUCTO, image: image(mat) }, mats);
                if (nail) add({ key: nail.key, name: nail.CNOMBREPRODUCTO, image: image(nail) }, nails);
                setAdded(true);
              }}
              disabled={added}
              className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-60"
            >
              {added ? "Agregado" : "Agregar a mi solicitud"}
            </button>
            {added && (
              <Link href="/carrito" className="text-sm text-blue-600 hover:underline">
                Ver mi solicitud
              </Link>
            )}
          </div>
        </>
      )}
    </section>
  );
}
