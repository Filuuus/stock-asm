"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import { TableHead } from "@/components/ui/table";
import { cn } from "@/lib/utils";

// Click-to-sort table headers, like a spreadsheet: click a column to sort by
// it, click it again to reverse. Each column says which way its first click
// goes - "largest first" for amounts, days and dates, A-Z for text.

export type SortDir = "asc" | "desc";
type SortValue = string | number | null | undefined;

export interface SortColumn<T> {
  value: (row: T) => SortValue;
  first: SortDir;
}

const collator = new Intl.Collator("es", { sensitivity: "base", numeric: true });

function compareValues(a: SortValue, b: SortValue) {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return collator.compare(String(a), String(b));
}

export function useSort<T, K extends string>(
  rows: T[],
  columns: Record<K, SortColumn<T>>,
  initial: { key: NoInfer<K>; dir: SortDir },
  // Keeps equal rows in a stable, meaningful order (e.g. by folio).
  tieBreak?: (a: T, b: T) => number,
) {
  const [sort, setSort] = useState<{ key: K; dir: SortDir }>(initial);

  const sorted = useMemo(() => {
    const column = columns[sort.key];
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const va = column.value(a);
      const vb = column.value(b);
      const aEmpty = va === null || va === undefined || va === "";
      const bEmpty = vb === null || vb === undefined || vb === "";
      // Empty values always go last, whichever the direction.
      if (aEmpty !== bEmpty) return aEmpty ? 1 : -1;
      const result = aEmpty ? 0 : sign * compareValues(va, vb);
      return result || (tieBreak ? tieBreak(a, b) : 0);
    });
  }, [rows, columns, sort, tieBreak]);

  const toggle = (key: K) =>
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: columns[key].first },
    );

  return { sorted, sortKey: sort.key, sortDir: sort.dir, toggle };
}

export function SortableHead<K extends string>({
  label,
  column,
  sortKey,
  sortDir,
  onSort,
  align = "left",
  className,
}: {
  label: string;
  column: K;
  sortKey: K;
  sortDir: SortDir;
  onSort: (key: K) => void;
  align?: "left" | "right";
  className?: string;
}) {
  const active = sortKey === column;
  const Icon = !active ? ArrowUpDown : sortDir === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
      className={cn(align === "right" && "text-right", className)}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={cn(
          "group inline-flex items-center gap-1 whitespace-nowrap hover:text-gray-900",
          align === "right" && "flex-row-reverse",
          active && "text-gray-900",
        )}
      >
        {label}
        <Icon
          className={cn(
            "h-3.5 w-3.5 shrink-0",
            active ? "opacity-100" : "opacity-0 group-hover:opacity-40 group-focus-visible:opacity-40",
          )}
        />
      </button>
    </TableHead>
  );
}

// Secondary columns drop out on narrow screens so the key ones (folio,
// client, amount) fit without sideways scrolling. Apply the same constant to
// a column's header and its cells.
export const HIDE_BELOW_SM = "hidden sm:table-cell";
export const HIDE_BELOW_MD = "hidden md:table-cell";
export const HIDE_BELOW_LG = "hidden lg:table-cell";
