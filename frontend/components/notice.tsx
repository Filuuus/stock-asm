"use client";

import { useState, type ReactNode } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, ChevronDown, Info } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

// The platform's one banner style. Always the same shape: what happened
// (title, with count and amount), one short line on what it means or what
// to do, an optional action, and the long explanation / invoice list folded
// behind "Ver detalle" so the page stays short, on phones especially.

export type NoticeTone = "error" | "warning" | "info" | "ok";

const TONES: Record<NoticeTone, { box: string; muted: string; icon: typeof Info }> = {
  error: { box: "border-red-200 bg-red-50 text-red-800", muted: "text-red-700", icon: AlertCircle },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-800", muted: "text-amber-700", icon: AlertTriangle },
  info: { box: "border-sky-200 bg-sky-50 text-sky-800", muted: "text-sky-700", icon: Info },
  ok: { box: "border-green-200 bg-green-50 text-green-800", muted: "text-green-700", icon: CheckCircle2 },
};

export function Notice({
  tone,
  title,
  summary,
  action,
  children,
}: {
  tone: NoticeTone;
  title?: ReactNode;
  summary?: ReactNode;
  action?: ReactNode;
  children?: ReactNode; // the folded detail
}) {
  const [open, setOpen] = useState(false);
  const { box, muted, icon: Icon } = TONES[tone];

  return (
    <Alert className={cn("flex items-start gap-3 px-4 py-3 text-sm", box)}>
      <Icon className="!static mt-0.5 h-4 w-4 shrink-0 !text-current" />
      <div className="flex min-w-0 flex-1 flex-col gap-1 !translate-y-0 !pl-0">
        {title && <AlertTitle className="mb-0 text-sm font-semibold leading-snug">{title}</AlertTitle>}
        {summary && <AlertDescription className={cn(title && muted)}>{summary}</AlertDescription>}
        {(children || action) && (
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
            {action}
            {children && (
              <button
                type="button"
                onClick={() => setOpen((o) => !o)}
                aria-expanded={open}
                className={cn("flex items-center gap-1 text-xs font-medium underline-offset-2 hover:underline", muted)}
              >
                {open ? "Ocultar detalle" : "Ver detalle"}
                <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
              </button>
            )}
          </div>
        )}
        {open && children && <div className={cn("mt-1 flex flex-col gap-2", muted)}>{children}</div>}
      </div>
    </Alert>
  );
}

// Invoices listed inside a notice: a compact table from sm up, one short
// block per invoice on phones. The first two columns head the phone block;
// the rest follow on one line with their labels.
export function NoticeList<T>({
  rows,
  rowKey,
  columns,
}: {
  rows: T[];
  rowKey: (row: T) => string | number;
  columns: { label: string; cell: (row: T) => ReactNode; align?: "right" }[];
}) {
  return (
    <>
      <table className="hidden text-xs sm:table">
        <thead className="text-left">
          <tr>
            {columns.map((c) => (
              <th key={c.label} className={cn("pb-1 pr-4 font-medium", c.align === "right" && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)}>
              {columns.map((c) => (
                <td
                  key={c.label}
                  className={cn("max-w-56 truncate py-0.5 pr-4 whitespace-nowrap", c.align === "right" && "text-right")}
                >
                  {c.cell(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="flex flex-col gap-2 text-xs sm:hidden">
        {rows.map((r) => (
          <li key={rowKey(r)} className="flex flex-col">
            <span className="flex min-w-0 items-baseline gap-2 font-medium">
              {columns[0].cell(r)}
              <span className="truncate">{columns[1].cell(r)}</span>
            </span>
            <span className="flex flex-wrap gap-x-2">
              {columns.slice(2).map((c) => (
                <span key={c.label}>
                  <span className="opacity-70">{c.label}:</span> {c.cell(r)}
                </span>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </>
  );
}
