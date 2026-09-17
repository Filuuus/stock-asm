"use client";

import { createContext, useContext, useState, ReactNode } from "react";

interface SearchQueryContextValue {
  query: string;
  setQuery: (query: string) => void;
}

const SearchQueryContext = createContext<SearchQueryContextValue | null>(null);

export function SearchQueryProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  return (
    <SearchQueryContext.Provider value={{ query, setQuery }}>
      {children}
    </SearchQueryContext.Provider>
  );
}

export function useSearchQuery() {
  const context = useContext(SearchQueryContext);
  if (!context) {
    throw new Error("useSearchQuery must be used within a SearchQueryProvider");
  }
  return context;
}
