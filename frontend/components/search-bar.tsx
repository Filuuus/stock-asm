"use client";

import { usePathname } from "next/navigation";
import { Search } from "lucide-react";
import { useSearchQuery } from "@/hooks/use-search-query";

export default function SearchBar() {
  const { query, setQuery } = useSearchQuery();
  // Only the catalog reads this query.
  if (usePathname() !== "/") return null;

  return (
    <div className="flex items-center bg-white rounded-lg px-3 py-1.5 w-full sm:w-auto sm:flex-1 sm:min-w-48 max-w-md order-last sm:order-none text-slate-500">
      <Search className="w-4 h-4 mr-2 flex-shrink-0" />
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Buscar productos..."
        className="w-full bg-transparent text-sm text-slate-700 placeholder:text-slate-500 focus:outline-none"
      />
    </div>
  );
}
