import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reel News Bot",
  description: "Generador automático de shorts para Instagram, TikTok y YouTube",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="h-full">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
