import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Settings, ShoppingCart } from "lucide-react";
import { SearchQueryProvider } from "@/hooks/use-search-query";
import { AuthProvider } from "@/hooks/use-auth";
import SearchBar from "@/components/search-bar";
import HeaderNav from "@/components/header-nav";
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
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-screen flex flex-col bg-gray-50">
        <AuthProvider>
          <SearchQueryProvider>
            <header className="bg-slate-900 px-6 py-3 flex items-center justify-between text-white border-b border-slate-800">
              <div className="text-lg font-bold">Agropecuaria Santa María</div>
              <SearchBar />
              <div className="flex items-center space-x-4">
                <HeaderNav />
                <button aria-label="Configuración" className="p-2 hover:bg-slate-800 rounded-full">
                  <Settings className="w-5 h-5" />
                </button>
                <button aria-label="Carrito" className="p-2 hover:bg-slate-800 rounded-full">
                  <ShoppingCart className="w-5 h-5" />
                </button>
              </div>
            </header>
            <div className="flex-1 flex flex-col">{children}</div>
          </SearchQueryProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
