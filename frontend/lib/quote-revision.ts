// The quote the cart is changing, set by Modificar on a customer's quote page.
export interface QuoteRevision {
  token: string;
  number: number;
}

const STORAGE_KEY = "quote-revision";

export function quoteRevision(): QuoteRevision | null {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
  } catch {
    return null;
  }
}

export function setQuoteRevision(revision: QuoteRevision | null) {
  try {
    if (revision) localStorage.setItem(STORAGE_KEY, JSON.stringify(revision));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // storage blocked: the cart sends a request of its own
  }
}
