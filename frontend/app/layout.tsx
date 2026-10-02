import type { Metadata } from "next";
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
              <header className="bg-slate-900 px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-white border-b border-slate-800">
                <Link href="/" className="text-lg font-bold whitespace-nowrap">
                  Agropecuaria Santa María
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
