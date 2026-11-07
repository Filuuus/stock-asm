"use client";

import { usePathname } from "next/navigation";

// The site's header, except on /embed pages (shown inside Notion, which has its own frame around them).
export default function SiteHeader({ children }: { children: React.ReactNode }) {
  return usePathname().startsWith("/embed") ? null : children;
}
