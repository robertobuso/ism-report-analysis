import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/providers/query-provider";
import { AuthProvider } from "@/providers/auth-provider";
import { Header } from "@/components/layout/header";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Portfolio Intelligence — Envoy Financial Intelligence Suite",
  description:
    "Persistent portfolio analytics workspace for the thoughtful investor",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} antialiased`}>
        <QueryProvider>
          <AuthProvider>
            <Header />
            <main className="min-h-[calc(100vh-73px)]">{children}</main>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
