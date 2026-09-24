// Same-hostname as the backend's dev server (see README) - SameSite=Lax
// session cookies are scoped by hostname, not port, so 127.0.0.1 and
// localhost would NOT share the login cookie even though they're both
// "localhost" to a human.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Wraps fetch for calls made from the browser (client components): always
// sends the session cookie, and attaches Django's CSRF header on mutating
// requests (GET doesn't need it - CSRF only guards unsafe methods).
export async function apiFetch(path: string, options: RequestInit = {}) {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (method !== "GET" && method !== "HEAD") {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
    if (options.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
  }

  return fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
}
