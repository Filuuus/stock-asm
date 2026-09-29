"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ExternalLink, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getJson, InvoiceDetailView } from "@/components/facturas/InvoiceDetail";
import { useAuth } from "@/hooks/use-auth";
import type { InvoiceDetail } from "@/types/facturas";

interface InvoiceDialogContextValue {
  // Whether the current user may see invoice details (the API is limited to
  // accounting and management - Comisiones is open to salespeople too).
  canView: boolean;
  openInvoice: (invoiceId: number) => void;
}

const InvoiceDialogContext = createContext<InvoiceDialogContextValue | null>(null);

// One dialog for the whole app: any screen that shows an invoice number opens
// it through useInvoiceDialog() (see InvoiceLink) instead of navigating away.
export function InvoiceDialogProvider({ children }: { children: ReactNode }) {
  const { isAccounting, isManagement } = useAuth();
  const [invoiceId, setInvoiceId] = useState<number | null>(null);
  const openInvoice = useCallback((id: number) => setInvoiceId(id), []);

  return (
    <InvoiceDialogContext.Provider value={{ canView: isAccounting || isManagement, openInvoice }}>
      {children}
      <InvoiceDialog
        invoiceId={invoiceId}
        onSelect={setInvoiceId}
        onClose={() => setInvoiceId(null)}
      />
    </InvoiceDialogContext.Provider>
  );
}

export function useInvoiceDialog() {
  const ctx = useContext(InvoiceDialogContext);
  if (!ctx) throw new Error("useInvoiceDialog must be used within InvoiceDialogProvider");
  return ctx;
}

function InvoiceDialog({ invoiceId, onSelect, onClose }: {
  invoiceId: number | null;
  onSelect: (id: number) => void;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<InvoiceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (invoiceId === null) return;
    const requestId = ++requestIdRef.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    setError(null);
    getJson<InvoiceDetail>(`/api/facturas/${invoiceId}/`)
      .then((json) => {
        if (requestId === requestIdRef.current) setDetail(json);
      })
      .catch((err) => {
        if (requestId === requestIdRef.current) {
          setError(err instanceof Error ? err.message : "No se pudo cargar la factura");
          setDetail(null);
        }
      })
      .finally(() => {
        if (requestId === requestIdRef.current) setLoading(false);
      });
  }, [invoiceId]);

  // Only show the detail that belongs to the invoice asked for - never the
  // previous one while the next is loading.
  const shown = detail && detail.invoice.invoice_id === invoiceId ? detail : null;

  return (
    <Dialog open={invoiceId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-6xl w-[calc(100%-2rem)] max-h-[90vh] overflow-y-auto bg-gray-50 grid-cols-[minmax(0,1fr)]">
        <DialogHeader className="pr-8">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <DialogTitle>Consulta de factura</DialogTitle>
            {shown && (
              <Link
                href={`/facturas?q=${encodeURIComponent(shown.invoice.folio_display)}&id=${shown.invoice.invoice_id}`}
                onClick={onClose}
                className="flex items-center gap-1 text-sm font-medium text-slate-700 hover:text-slate-900"
              >
                Abrir como página
                <ExternalLink className="w-3.5 h-3.5" />
              </Link>
            )}
          </div>
          <DialogDescription>
            Datos en vivo de Contpaqi Comercial y Contabilidad.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {loading && !shown && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            Cargando factura...
          </div>
        )}
        {shown && <InvoiceDetailView detail={shown} onSelect={onSelect} />}
      </DialogContent>
    </Dialog>
  );
}
