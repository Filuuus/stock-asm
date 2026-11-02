"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { formatDay } from "@/lib/dates";
import { noSavedQuotes, savedQuotes, subscribeSavedQuotes } from "@/lib/saved-quotes";
import { plural } from "@/lib/utils";

// Customers have no accounts: this is whatever was opened on this device.
export default function MyRequestsView() {
  const quotes = useSyncExternalStore(subscribeSavedQuotes, savedQuotes, noSavedQuotes);

  return (
    <main className="mx-auto w-full max-w-3xl p-4 sm:p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Mis solicitudes</h1>
      <p className="mt-1 text-sm text-gray-500">Las que abriste en este dispositivo. Entra a una para ver cómo va.</p>
      {quotes.length === 0 ? (
        <div className="mt-6 rounded-lg border border-dashed border-gray-300 bg-white py-10 text-center">
          <p className="text-sm text-gray-500">Aún no hay solicitudes en este dispositivo.</p>
          <p className="mt-1 text-sm text-gray-500">Si ya enviaste una, abre el enlace que te compartimos.</p>
          <Link href="/catalogo" className="mt-2 inline-block text-sm text-blue-600 hover:underline">
            Ir al catálogo
          </Link>
        </div>
      ) : (
        <ul className="mt-6 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
          {quotes.map((q) => (
            <li key={q.token}>
              <Link href={`/solicitud/${q.token}`} className="flex items-center gap-3 p-3 hover:bg-gray-50 sm:p-4">
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-gray-800">Solicitud #{q.number}</span>
                  <span className="block text-xs text-gray-500">
                    {formatDay(q.created_at)} · {plural(q.products, "producto", "productos")}
                  </span>
                </span>
                <ChevronRight className="h-4 w-4 shrink-0 text-gray-400" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
