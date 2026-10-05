"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHeader, TableRow } from "@/components/ui/table";
import ClientLink from "@/components/facturas/ClientLink";
import { EmptyRow, HIDE_BELOW_LG, HIDE_BELOW_SM, SortableHead, SortColumn, SortDir, useSort } from "@/components/sortable-table";
import { cn, formatMoney } from "@/lib/utils";

// Same labels as the backend's AGING_BUCKETS, past due only.
const OVERDUE_BUCKETS = ["1-30 días", "31-60 días", "61-90 días", "Más de 90 días"] as const;

export interface OverdueClient {
  client_id: number;
  cliente: string;
  pendiente: number;
  vencido: number;
  dias_vencido: number;
  documentos_vencidos: number;
  por_antiguedad: Record<string, number>;
}

export interface OverdueClientsList {
  clientes: OverdueClient[];
  pendiente: number;
  saldo_a_favor: number;
}

// Columns come in as the screen widens: the age split from lg (a landscape
// tablet), the count from xl. Fixed widths ("table-fixed") with the client
// column taking what's left and truncating, so it fits at every width.
const HIDE_BELOW_XL = "hidden xl:table-cell";
const COL_MONEY = "w-28";

type SortKey = "cliente" | "vencido" | (typeof OVERDUE_BUCKETS)[number] | "documentos" | "dias" | "pendiente";

const SORT_COLUMNS: Record<SortKey, SortColumn<OverdueClient>> = {
  cliente: { value: (c) => c.cliente, first: "asc" },
  vencido: { value: (c) => c.vencido, first: "desc" },
  ...(Object.fromEntries(
    OVERDUE_BUCKETS.map((b) => [b, { value: (c: OverdueClient) => c.por_antiguedad[b] || null, first: "desc" }]),
  ) as Record<(typeof OVERDUE_BUCKETS)[number], SortColumn<OverdueClient>>),
  documentos: { value: (c) => c.documentos_vencidos, first: "desc" },
  dias: { value: (c) => c.dias_vencido, first: "desc" },
  pendiente: { value: (c) => c.pendiente, first: "desc" },
};

const SORT_HEADERS: [SortKey, ReactNode, "left" | "right", string?][] = [
  ["cliente", "Cliente", "left"],
  ["vencido", "Vencido", "right", COL_MONEY],
  // "días" is in the description; the short labels let the table fit a tablet.
  ...OVERDUE_BUCKETS.map((b): [SortKey, ReactNode, "right", string] => [b, b.replace(" días", ""), "right", cn(HIDE_BELOW_LG, COL_MONEY)]),
  ["documentos", "Documentos", "right", cn(HIDE_BELOW_XL, "w-28")],
  [
    "dias",
    <>
      <span className="xl:hidden">Días</span>
      <span className="hidden xl:inline">Días de atraso</span>
    </>,
    "right",
    "w-20 xl:w-32",
  ],
  ["pendiente", "Saldo total", "right", cn(HIDE_BELOW_SM, COL_MONEY)],
];

const byName = (a: OverdueClient, b: OverdueClient) => a.cliente.localeCompare(b.cliente, "es");

// Survives going into a client's history and back ("Volver" remounts this view).
let lastSort: { key: SortKey; dir: SortDir } = { key: "vencido", dir: "desc" };

function sum(values: number[]) {
  return values.reduce((a, b) => a + b, 0);
}

export function OverdueClientsView({ list }: { list: OverdueClientsList }) {
  const [search, setSearch] = useState("");
  const query = search.trim().toLowerCase();
  const rows = query ? list.clientes.filter((c) => c.cliente.toLowerCase().includes(query)) : list.clientes;
  const { sorted, sortKey, sortDir, toggle } = useSort(rows, SORT_COLUMNS, lastSort, byName);
  useEffect(() => {
    lastSort = { key: sortKey, dir: sortDir };
  }, [sortKey, sortDir]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-gray-600">
          {list.clientes.length} clientes con facturas vencidas, con IVA y menos sus saldos a favor; saldo por días de
          vencido. Haga clic en una columna para ordenar.
        </p>
        <Input
          placeholder="Buscar cliente..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-white sm:w-56"
        />
      </div>
      <div className="overflow-x-auto rounded-lg border bg-white">
        <Table className="table-fixed [&_td]:px-2 [&_th]:px-2">
          <TableHeader>
            <TableRow>
              {SORT_HEADERS.map(([key, label, align, className]) => (
                <SortableHead
                  key={key}
                  label={label}
                  column={key}
                  sortKey={sortKey}
                  sortDir={sortDir}
                  onSort={toggle}
                  align={align}
                  className={className}
                />
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 ? (
              <EmptyRow colSpan={SORT_HEADERS.length}>Ningún cliente coincide con la búsqueda.</EmptyRow>
            ) : (
              <>
                {sorted.map((c) => (
                  <TableRow key={c.client_id}>
                    <TableCell className="truncate" title={c.cliente}>
                      <ClientLink clientId={c.client_id} label={c.cliente} />
                    </TableCell>
                    <TableCell className="text-right num">{formatMoney(c.vencido)}</TableCell>
                    {OVERDUE_BUCKETS.map((b) => (
                      <TableCell key={b} className={cn("text-right num", HIDE_BELOW_LG)}>
                        {c.por_antiguedad[b] ? formatMoney(c.por_antiguedad[b]) : "-"}
                      </TableCell>
                    ))}
                    <TableCell className={cn("text-right num", HIDE_BELOW_XL)}>{c.documentos_vencidos}</TableCell>
                    <TableCell className={cn("text-right num", c.dias_vencido > 90 && "text-red-700")}>
                      {c.dias_vencido}
                    </TableCell>
                    <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>{formatMoney(c.pendiente)}</TableCell>
                  </TableRow>
                ))}
                <TableRow className="!bg-slate-100 font-semibold">
                  <TableCell>Total{query && " (filtrados)"}</TableCell>
                  <TableCell className="text-right num">{formatMoney(sum(rows.map((c) => c.vencido)))}</TableCell>
                  {OVERDUE_BUCKETS.map((b) => (
                    <TableCell key={b} className={cn("text-right num", HIDE_BELOW_LG)}>
                      {formatMoney(sum(rows.map((c) => c.por_antiguedad[b] || 0)))}
                    </TableCell>
                  ))}
                  <TableCell className={cn("text-right num", HIDE_BELOW_XL)}>
                    {sum(rows.map((c) => c.documentos_vencidos))}
                  </TableCell>
                  <TableCell />
                  <TableCell className={cn("text-right num", HIDE_BELOW_SM)}>
                    {formatMoney(sum(rows.map((c) => c.pendiente)))}
                  </TableCell>
                </TableRow>
              </>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
