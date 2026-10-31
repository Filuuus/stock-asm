"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { Check } from "lucide-react";
import { Profile } from "@/components/catalog/MatSpecBanner";
import { linePrice, lineAvailability, lineImage } from "@/components/catalog/LineCard";
import { Notice } from "@/components/notice";
import { parseDescription, specValue } from "@/lib/description";
import { matsForArea, matSheet, NAILS_PER_MAT } from "@/lib/mats";
import { cn, formatMoney, productHref } from "@/lib/utils";
import { ProductLine } from "@/types/api";

const MAX_COMPARED = 4;

// Where a customer will put it, read from each line's "Dónde se usa".
const AREAS = [
  { label: "Pasillos y corrales", match: /pasillos|corrales de espera|cruces|pasarelas|carriles|comederos/i },
  { label: "Sala de ordeño", match: /salas? de ordeño|rotativas|fosas/i },
  { label: "Camas", match: /camas|establos con amarre/i },
  { label: "Becerras", match: /becerras/i },
  { label: "Caballos", match: /caballerizas/i },
  { label: "Engorda con rejilla", match: /engorda/i },
  { label: "Mangas y manejo", match: /mangas|rampas|básculas/i },
];

const SPEC_ROWS = ["Espesor", "Espuma", "Cubierta", "Peso", "Superficie", "Parte inferior", "Se limpia con", "Vida útil", "Garantía"];

function compareRows(lines: ProductLine[]) {
  const data = lines.map((line) => ({ line, blocks: parseDescription(line.description), sheet: matSheet(line.description) }));
  const rows = SPEC_ROWS.map((label) => ({ label, values: data.map((d) => specValue(d.blocks, label)) }));
  return { data, rows: rows.filter((r) => r.values.some(Boolean)) };
}

// Standard 4 × 6 ft mats can be counted from a floor area; rolls and mattresses are measured for the job.
const isStandardMat = (size: string | null | undefined) => /4 × 6 pies|6 × 4 pies/.test(size ?? "");

export default function MatCompareView({ lines, nailPrice }: { lines: ProductLine[]; nailPrice: number | null }) {
  const [length, setLength] = useState("");
  const [width, setWidth] = useState("");
  const [area, setArea] = useState<string | null>(null);
  const shown = useMemo(() => {
    const match = AREAS.find((a) => a.label === area)?.match;
    return match ? lines.filter((l) => match.test(l.uses)) : lines;
  }, [area, lines]);
  const [picked, setPicked] = useState(() => lines.slice(0, 3).map((l) => l.line));
  const compared = picked.flatMap((name) => lines.filter((l) => l.line === name));
  const { data, rows } = compareRows(compared);
  const mats = matsForArea(Number(length), Number(width));

  const chooseArea = (label: string | null) => {
    const next = label === area ? null : label;
    setArea(next);
    const match = AREAS.find((a) => a.label === next)?.match;
    setPicked((match ? lines.filter((l) => match.test(l.uses)) : lines).slice(0, 3).map((l) => l.line));
  };
  const toggle = (name: string) =>
    setPicked((now) => (now.includes(name) ? now.filter((n) => n !== name) : now.length < MAX_COMPARED ? [...now, name] : now));

  return (
    <main className="mx-auto max-w-7xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900 sm:text-3xl">Compara tapetes y colchones</h1>
      <p className="mt-2 max-w-2xl text-gray-600">
        Elige dónde lo vas a usar y compara hasta {MAX_COMPARED} productos. Si tienes dudas, en la oficina tenemos muestras para que los veas.
      </p>

      <h2 className="mt-6 text-sm font-semibold text-gray-900">¿Dónde lo vas a usar?</h2>
      <div className="mt-2 flex flex-wrap gap-2">
        {AREAS.map((a) => (
          <button
            key={a.label}
            type="button"
            aria-pressed={area === a.label}
            onClick={() => chooseArea(a.label)}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-sm",
              area === a.label ? "border-slate-900 bg-slate-900 text-white" : "border-gray-300 bg-white text-gray-700 hover:border-gray-400",
            )}
          >
            {a.label}
          </button>
        ))}
      </div>

      <h2 className="mt-6 text-sm font-semibold text-gray-900">Elige qué comparar ({compared.length} de {MAX_COMPARED})</h2>
      <div className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {shown.map((line) => {
          const on = picked.includes(line.line);
          const full = !on && picked.length >= MAX_COMPARED;
          return (
            <button
              key={line.line}
              type="button"
              aria-pressed={on}
              disabled={full}
              onClick={() => toggle(line.line)}
              className={cn(
                "relative rounded-xl border bg-white p-2 text-left text-sm font-medium text-gray-900",
                on ? "border-blue-600 ring-1 ring-blue-600" : "border-gray-200 hover:border-gray-400",
                full && "cursor-not-allowed opacity-50",
              )}
            >
              <span className="relative block aspect-square overflow-hidden rounded-lg bg-gray-50">
                <Image src={lineImage(line)} alt="" fill sizes="(min-width: 1024px) 15vw, 45vw" className="object-cover" />
              </span>
              <span className="mt-2 block">{line.line}</span>
              {on && (
                <span className="absolute right-3 top-3 rounded-full bg-blue-600 p-1 text-white">
                  <Check className="h-3.5 w-3.5" aria-hidden />
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="mt-6 max-w-xl rounded-xl border border-gray-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-gray-900">¿Qué área vas a cubrir?</h2>
        <p className="text-xs text-gray-500">Mídela y compara cuántos tapetes necesitas y cuánto costarían.</p>
        <div className="mt-3 grid grid-cols-2 gap-3">
          {[{ label: "Largo (m)", value: length, set: setLength }, { label: "Ancho (m)", value: width, set: setWidth }].map((f) => (
            <label key={f.label} className="text-xs text-gray-600">
              {f.label}
              <input
                type="number"
                min="0"
                step="0.1"
                inputMode="decimal"
                value={f.value}
                onChange={(e) => f.set(e.target.value)}
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm"
              />
            </label>
          ))}
        </div>
      </div>

      {compared.length === 0 ? (
        <div className="mt-8">
          <Notice tone="info" title="Elige al menos un producto para compararlo." />
        </div>
      ) : (
        <div className="mt-8 overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="w-full min-w-[40rem] table-fixed text-sm">
            <thead>
              <tr className="border-b border-gray-200 align-top">
                <th scope="col" className="w-32 p-3 text-left font-medium text-gray-500 sm:w-40">
                  <span className="sr-only">Característica</span>
                </th>
                {data.map(({ line }) => (
                  <th key={line.line} scope="col" className="p-3 text-left">
                    <span className="relative mb-2 block aspect-square max-w-48 overflow-hidden rounded-lg bg-gray-50">
                      <Image src={lineImage(line)} alt="" fill sizes="25vw" className="object-cover" />
                    </span>
                    <span className="text-base font-semibold text-gray-900">{line.line}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="[&_td]:p-3 [&_td]:align-top [&_td]:text-gray-700 [&_th]:p-3 [&_th]:align-top [&_th]:font-medium [&_th]:text-gray-900 [&_tr]:border-b [&_tr]:border-gray-100 [&_tr:last-child]:border-0">
              <tr>
                <th scope="row" className="text-left">Precio</th>
                {data.map(({ line }) => <td key={line.line} className="font-semibold">{linePrice(line)}</td>)}
              </tr>
              {mats > 0 && (
                <>
                  <tr className="bg-blue-50/60">
                    <th scope="row" className="text-left">Tapetes para tu área</th>
                    {data.map(({ line, sheet }) => (
                      <td key={line.line}>{isStandardMat(sheet?.size) ? mats.toLocaleString("es-MX") : "Según medida"}</td>
                    ))}
                  </tr>
                  <tr className="bg-blue-50/60">
                    <th scope="row" className="text-left">Costo estimado</th>
                    {data.map(({ line, sheet }) => (
                      <td key={line.line} className="font-semibold">
                        {isStandardMat(sheet?.size) && line.mat_price
                          ? `Desde ${formatMoney(mats * (line.mat_price + NAILS_PER_MAT * (nailPrice ?? 0)))}`
                          : "Se cotiza"}
                      </td>
                    ))}
                  </tr>
                </>
              )}
              <tr>
                <th scope="row" className="text-left">Disponibilidad</th>
                {data.map(({ line }) => (
                  <td key={line.line} className={line.in_stock ? "!text-green-700" : "!text-amber-700"}>{lineAvailability(line)}</td>
                ))}
              </tr>
              <tr>
                <th scope="row" className="text-left">Corte</th>
                {data.map(({ line, sheet }) => (
                  <td key={line.line}>
                    {sheet && sheet.layers.length > 0 ? (
                      <Profile layers={sheet.layers} top={sheet.top} bottom={sheet.bottom} width={136} />
                    ) : (
                      "—"
                    )}
                  </td>
                ))}
              </tr>
              {rows.map((r) => (
                <tr key={r.label}>
                  <th scope="row" className="text-left">{r.label}</th>
                  {r.values.map((value, i) => <td key={i} className="first-letter:uppercase">{value ?? "—"}</td>)}
                </tr>
              ))}
              <tr>
                <th scope="row" className="text-left">Medida</th>
                {data.map(({ line, sheet }) => <td key={line.line}>{sheet?.size ?? "—"}</td>)}
              </tr>
              <tr>
                <th scope="row" className="text-left">Adecuado para</th>
                {data.map(({ line, sheet }) => <td key={line.line}>{sheet?.uses.join(", ") || "—"}</td>)}
              </tr>
              <tr>
                <th scope="row"><span className="sr-only">Enlace</span></th>
                {data.map(({ line }) => (
                  <td key={line.line}>
                    <Link href={productHref(line.key, line.slug)} className="inline-flex rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium !text-white hover:bg-blue-700">
                      Ver producto
                    </Link>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-gray-500">
        El diseño puede variar respecto a las imágenes.
        {mats > 0 && ` Estimado con IVA para tapetes de 4 × 6 pies${nailPrice ? `, con ${NAILS_PER_MAT} clavos por tapete` : ""}; no incluye instalación ni envío. El precio final puede cambiar según el interlock y se confirma en la cotización.`}
      </p>
    </main>
  );
}
