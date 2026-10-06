"use client";

import { Notice } from "@/components/notice";
import { ReactNode, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, ExternalLink, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { getJson, InvoiceDetailView } from "@/components/facturas/InvoiceDetail";
import { ClientHistoryView } from "@/components/facturas/ClientHistory";
import { InvoiceDialogContext } from "@/components/facturas/invoice-dialog-context";
import { OverdueClientsView, type OverdueClientsList } from "@/components/analytics/OverdueClients";
import { useAuth } from "@/hooks/use-auth";
import type { ClientHistory, InvoiceDetail } from "@/types/facturas";

type View =
  | { kind: "invoice"; id: number }
  | { kind: "client"; id: number; full: boolean }
  | { kind: "overdue" };

function viewPath(view: View) {
  if (view.kind === "overdue") return "/api/analytics/overdue-clients/";
  return view.kind === "invoice"
    ? `/api/facturas/${view.id}/`
    : `/api/facturas/clientes/${view.id}/${view.full ? "?completo=1" : ""}`;
}

function sameView(a: View | undefined, b: View) {
  return !!a && viewPath(a) === viewPath(b);
}

const TITLES: Record<View["kind"], string> = {
  invoice: "Factura",
  client: "Historial del cliente",
  overdue: "Clientes con saldo vencido",
};

// One dialog for the whole app: any screen that shows an invoice number or a
// client name opens it through useInvoiceDialog() (see InvoiceLink and
// ClientLink) instead of navigating away. Views stack, so going from a
// client to one of its invoices can come back with "Volver".
export function InvoiceDialogProvider({ children }: { children: ReactNode }) {
  const { isAccounting, isManagement } = useAuth();
  const [stack, setStack] = useState<View[]>([]);
  const push = useCallback(
    (view: View) => setStack((s) => (sameView(s[s.length - 1], view) ? s : [...s, view])),
    [],
  );
  const openInvoice = useCallback((id: number) => push({ kind: "invoice", id }), [push]);
  const openClient = useCallback((id: number) => push({ kind: "client", id, full: false }), [push]);
  const openOverdueClients = useCallback(() => push({ kind: "overdue" }), [push]);

  return (
    <InvoiceDialogContext.Provider
      value={{ canView: isAccounting || isManagement, openInvoice, openClient, openOverdueClients }}
    >
      {children}
      <DetailDialog
        view={stack[stack.length - 1] ?? null}
        canGoBack={stack.length > 1}
        onBack={() => setStack((s) => s.slice(0, -1))}
        onReplace={(view) => setStack((s) => [...s.slice(0, -1), view])}
        onClose={() => setStack([])}
        openInvoice={openInvoice}
      />
    </InvoiceDialogContext.Provider>
  );
}

function DetailDialog({ view, canGoBack, onBack, onReplace, onClose, openInvoice }: {
  view: View | null;
  canGoBack: boolean;
  onBack: () => void;
  onReplace: (view: View) => void;
  onClose: () => void;
  openInvoice: (id: number) => void;
}) {
  // Loaded views are kept for this dialog session, so "Volver" is instant.
  // ERP data changes during the day, so the cache is dropped on close.
  const [cache, setCache] = useState<Record<string, InvoiceDetail | ClientHistory | OverdueClientsList>>({});
  const [loadingPath, setLoadingPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const path = view ? viewPath(view) : null;
  const data = path ? cache[path] : undefined;

  const close = () => {
    setCache({});
    onClose();
  };

  useEffect(() => {
    if (!path || data) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoadingPath(path);
    setError(null);
    getJson<InvoiceDetail | ClientHistory | OverdueClientsList>(path)
      .then((json) => {
        if (!cancelled) setCache((c) => ({ ...c, [path]: json }));
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "No se pudo cargar la información");
      })
      .finally(() => {
        if (!cancelled) setLoadingPath(null);
      });
    return () => {
      cancelled = true;
    };
  }, [path, data]);

  const invoice = view?.kind === "invoice" ? (data as InvoiceDetail | undefined) : undefined;
  const client = view?.kind === "client" ? (data as ClientHistory | undefined) : undefined;
  const overdue = view?.kind === "overdue" ? (data as OverdueClientsList | undefined) : undefined;

  return (
    <Dialog open={view !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="max-w-6xl w-[calc(100%-2rem)] max-h-[90vh] overflow-y-auto bg-gray-50 grid-cols-[minmax(0,1fr)]">
        <DialogHeader className="pr-8 text-left">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {canGoBack && (
                <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2">
                  <ChevronLeft className="w-4 h-4" />
                  Volver
                </Button>
              )}
              <DialogTitle>
                {view ? TITLES[view.kind] : ""}
              </DialogTitle>
            </div>
            {invoice && (
              <Link
                href={`/facturas?q=${encodeURIComponent(invoice.invoice.folio_display)}&id=${invoice.invoice.invoice_id}`}
                onClick={close}
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

        {error && !data && <Notice tone="error" summary={error} />}
        {!data && loadingPath === path && (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            Cargando...
          </div>
        )}
        {overdue && <OverdueClientsView list={overdue} />}
        {invoice && <InvoiceDetailView detail={invoice} onSelect={openInvoice} />}
        {client && view?.kind === "client" && (
          <ClientHistoryView
            history={client}
            onOpenInvoice={openInvoice}
            onShowFull={() => onReplace({ ...view, full: true })}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
