"use client";

import { Search } from "lucide-react";
import { useSearchQuery } from "@/hooks/use-search-query";

export default function SearchBar() {
  const { query, setQuery } = useSearchQuery();

  return (
    <div className="flex items-center bg-white rounded-lg px-3 py-1.5 w-1/3 max-w-md text-slate-500">
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
