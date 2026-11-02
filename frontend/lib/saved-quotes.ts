// Quotes opened on this device, so a customer can get back to them without an account.
// A list by date and number only: the status is on the quote's own page.
export interface SavedQuote {
  token: string;
  number: number;
  created_at: string;
  products: number;
}

const STORAGE_KEY = "my-quotes";
const EMPTY: SavedQuote[] = [];
const listeners = new Set<() => void>();
let cached: { raw: string | null; quotes: SavedQuote[] } = { raw: null, quotes: EMPTY };

export function savedQuotes(): SavedQuote[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch {
    // private mode / blocked storage: nothing saved
  }
  if (raw !== cached.raw) {
    try {
      cached = { raw, quotes: raw ? JSON.parse(raw) : EMPTY };
    } catch {
      cached = { raw, quotes: EMPTY };
    }
  }
  return cached.quotes;
}

export function rememberQuote(quote: SavedQuote) {
  try {
    const others = savedQuotes().filter((q) => q.token !== quote.token);
    localStorage.setItem(STORAGE_KEY, JSON.stringify([quote, ...others].sort((a, b) => b.number - a.number)));
  } catch {
    return;
  }
  listeners.forEach((l) => l());
}

export function subscribeSavedQuotes(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export const noSavedQuotes = () => EMPTY;
