"use client";

import { Notice } from "@/components/notice";
import { FormEvent, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getJson, InvoiceDetailView, InvoiceList } from "@/components/facturas/InvoiceDetail";
import { useAuth } from "@/hooks/use-auth";
import type { InvoiceDetail, InvoiceSearchResult } from "@/types/facturas";

export default function FacturaView() {
  const { loading: authLoading, isAccounting, isManagement } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const selectedId = Number(searchParams.get("id")) || null;

  const [input, setInput] = useState(query);
  const [results, setResults] = useState<InvoiceSearchResult[] | null>(null);
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const navigate = (params: { q?: string; id?: number | null }) => {
    const next = new URLSearchParams();
    if (params.q) next.set("q", params.q);
    if (params.id) next.set("id", String(params.id));
    router.push(`${pathname}?${next.toString()}`);
  };

  // Keep the box in sync when the URL changes (back/forward, links).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setInput(query);
  }, [query]);

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    if (!query && !selectedId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResults(null);
      setDetail(null);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    const load = async () => {
      let found: InvoiceSearchResult[] | null = null;
      if (query) {
        found = (await getJson<{ results: InvoiceSearchResult[] }>(
          `/api/facturas/buscar/?q=${encodeURIComponent(query)}`,
        )).results;
      }
      let id = selectedId;
      // One invoice in the series the user typed (or one invoice at all):
      // open it directly, the others are listed under "Mismo folio".
      const matching = found?.filter((r) => r.series_match) ?? [];
      if (!id && matching.length === 1) id = matching[0].invoice_id;
      const invoice = id ? await getJson<InvoiceDetail>(`/api/facturas/${id}/`) : null;
      if (requestId !== requestIdRef.current) return;
      setResults(found);
      setDetail(invoice);
    };
    load()
      .catch((err) => {
        if (requestId === requestIdRef.current) {
          setError(err instanceof Error ? err.message : "No se pudo cargar la factura");
          setDetail(null);
        }
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setLoading(false);
      });
  }, [query, selectedId]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const q = input.trim();
    if (q) navigate({ q });
  };

  if (!authLoading && !(isAccounting || isManagement)) {
    return (
      <main className="max-w-7xl mx-auto w-full p-4 sm:p-6">
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white py-16 text-center">
          <p className="text-sm font-medium text-gray-700">
            No tiene permiso para consultar facturas.
          </p>
          <a href="/login" className="text-sm font-medium text-slate-900 underline">
            Iniciar sesión
          </a>
        </div>
      </main>
    );
  }

  const showResultsList = results && !detail && !loading;

  return (
    <main className="w-full max-w-7xl mx-auto p-4 sm:p-6 flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-gray-900">Facturas</h1>
        <p className="text-sm text-gray-500">
          Todo lo que Contpaqi sabe de un No. Factura: la factura y sus renglones, los pagos y notas
          de crédito aplicados en Comercial, las pólizas de Contabilidad que la citan, y lo que no
          cuadra entre ambos.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex items-center gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="No. Factura, ej. B 20016 o 20016"
          className="max-w-xs bg-white"
          autoFocus
        />
        <Button type="submit" disabled={!input.trim()}>
          <Search className="w-4 h-4" />
          Buscar
        </Button>
        {loading && <Loader2 className="w-4 h-4 animate-spin text-gray-400" />}
      </form>

      {error && <Notice tone="error" summary={error} />}

      {showResultsList && (
        <SearchResults
          results={results}
          onSelect={(id) => navigate({ q: query, id })}
        />
      )}

      {detail && (
        <InvoiceDetailView
          detail={detail}
          onSelect={(id) => navigate({ q: query, id })}
        />
      )}
    </main>
  );
}

function SearchResults({ results, onSelect }: {
  results: InvoiceSearchResult[];
  onSelect: (id: number) => void;
}) {
  if (results.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-white py-8 text-center text-sm text-gray-500">
        Sin facturas con ese folio.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-gray-600">
        Hay {results.length} facturas con ese folio. Elija una:
      </p>
      <InvoiceList results={results} onSelect={onSelect} />
    </div>
  );
}
