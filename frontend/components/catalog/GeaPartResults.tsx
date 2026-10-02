"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { productHref } from "@/components/catalog/ProductCard";

interface GeaPart {
  code: string;
  desc: string;
  appears_in: {
    pos: string;
    qty: number;
    has_drawing: boolean;
    parent: { CCODIGOPRODUCTO: string; CNOMBREPRODUCTO: string };
  }[];
}

const VISIBLE = 5;

// GEA parts we don't sell that match the search, each linked to the products
// of ours they're part of - opening the drawing with the part selected.
export default function GeaPartResults({ query }: { query: string }) {
  const [parts, setParts] = useState<GeaPart[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (query.replace(/\s/g, "").length < 3) return;
    const timer = setTimeout(async () => {
      try {
        const res = await apiFetch(
          `/api/gea-parts/?q=${encodeURIComponent(query)}`,
        );
        setParts(res.ok ? await res.json() : []);
        setExpanded(false);
      } catch {
        setParts([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  const shown = query.replace(/\s/g, "").length < 3 ? [] : parts;
  if (shown.length === 0) return null;
  return (
    // Folded to one line so the products stay first; opens on click.
    <details className="group mb-4 rounded-lg border border-gray-200 bg-white text-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-2.5 text-gray-700 [&::-webkit-details-marker]:hidden">
        <span>
          {shown.length === 1 ? "1 pieza GEA" : `${shown.length} piezas GEA`}{" "}
          que no están en el catálogo
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-gray-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="border-t border-gray-100 px-4 pb-3">
        <p className="mt-2 text-xs text-gray-500">
          Abre el equipo donde va la pieza para verla en su dibujo.
        </p>
        <ul className="divide-y divide-gray-100">
          {(expanded ? shown : shown.slice(0, VISIBLE)).map((part) => (
            <li key={part.code} className="py-2">
              <p className="text-gray-800">
                {part.desc}{" "}
                <span className="text-xs text-gray-400">{part.code}</span>
              </p>
              <ul className="mt-1 space-y-0.5">
                {part.appears_in.map((a) => (
                  <li key={a.parent.CCODIGOPRODUCTO} className="text-xs">
                    <Link
                      href={`${productHref(a.parent.CCODIGOPRODUCTO)}?pieza=${encodeURIComponent(part.code)}`}
                      className="text-blue-600 hover:underline"
                    >
                      {a.parent.CNOMBREPRODUCTO}
                    </Link>{" "}
                    <span className="text-gray-500">
                      · Posición {Number(a.pos)}
                    </span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
        {shown.length > VISIBLE && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="mt-2 text-sm text-blue-600 hover:underline"
          >
            {expanded ? "Ver menos" : `Ver más (${shown.length})`}
          </button>
        )}
      </div>
    </details>
  );
}
