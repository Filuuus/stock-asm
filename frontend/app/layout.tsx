import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import { SearchQueryProvider } from "@/hooks/use-search-query";
import { AuthProvider } from "@/hooks/use-auth";
import { CartProvider } from "@/hooks/use-cart";
import SearchBar from "@/components/search-bar";
import HeaderNav from "@/components/header-nav";
import { InvoiceDialogProvider } from "@/components/facturas/InvoiceDialog";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  // Absolute URLs for link previews and the sitemap; set it to the real domain on the server.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "Agropecuaria Santa María",
  description: "Catálogo de Productos",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-screen flex flex-col bg-gray-50">
        <AuthProvider>
          <CartProvider>
            <SearchQueryProvider>
              <header className="print:hidden bg-slate-900 px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-white border-b border-slate-800">
                {/* White backing: the logo's black "AGROPECUARIA" disappears on the dark header. */}
                <Link href="/" className="flex-shrink-0 rounded-md bg-white px-2 py-1">
                  <Image src="/logo.png" alt="Agropecuaria Santa María" width={1500} height={601} priority className="h-10 w-auto" />
                </Link>
                <SearchBar />
                <HeaderNav />
              </header>
              <InvoiceDialogProvider>
                <div className="flex-1 flex flex-col">{children}</div>
              </InvoiceDialogProvider>
            </SearchQueryProvider>
          </CartProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
