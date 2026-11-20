"use client";

import { usePathname, useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useSearchQuery } from "@/hooks/use-search-query";

export default function SearchBar() {
  const { query, setQuery } = useSearchQuery();
  const router = useRouter();
  const pathname = usePathname();
  // The catalog filters as you type; a product page searches the catalog on Enter.
  const onCatalog = pathname === "/catalogo";
  if (!onCatalog && !pathname.startsWith("/producto/")) return null;

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        if (!onCatalog) router.push("/catalogo");
      }}
      className="flex items-center bg-white rounded-lg px-3 py-1.5 w-full sm:w-auto sm:flex-1 sm:min-w-48 max-w-md order-last sm:order-none text-slate-500"
    >
      <Search className="w-4 h-4 mr-2 flex-shrink-0" />
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Buscar productos..."
        className="w-full bg-transparent text-sm text-slate-700 placeholder:text-slate-500 focus:outline-none"
      />
    </form>
  );
}
