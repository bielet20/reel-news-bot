import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reel News Bot",
  description: "Generador automático de shorts para Instagram, TikTok y YouTube",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="h-full">
      <body className="min-h-full flex flex-col">
        <nav style={{
          background: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          padding: "0 16px",
          display: "flex",
          alignItems: "center",
          gap: 4,
          height: 48,
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}>
          <Link href="/" style={{
            fontSize: 14,
            fontWeight: 700,
            color: "var(--accent)",
            textDecoration: "none",
            marginRight: 12,
          }}>
            🎬 Reel News Bot
          </Link>
          <NavLink href="/">Generar</NavLink>
          <NavLink href="/montaje">Montaje</NavLink>
          <NavLink href="/canales">Canales</NavLink>
          <NavLink href="/library">Biblioteca</NavLink>
          <NavLink href="/music">Música</NavLink>
        </nav>
        {children}
      </body>
    </html>
  );
}

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link href={href} style={{
      fontSize: 13,
      color: "var(--muted)",
      textDecoration: "none",
      padding: "6px 10px",
      borderRadius: 7,
    }}>
      {children}
    </Link>
  );
}
