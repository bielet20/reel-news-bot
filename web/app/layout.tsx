import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Reel News Bot",
  description: "Generador automático de shorts para Instagram, TikTok y YouTube",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // suppressHydrationWarning: extensiones del navegador (traductores, conversores
    // de moneda, gestores de contraseñas...) inyectan atributos en <html>/<body>
    // antes de que React hidrate — p.ej. data-smart-converter-loaded. Sin esto,
    // Next 16 lo marca como error de hidratación en consola. Solo silencia el
    // aviso para los atributos de ese elemento, no para su contenido.
    <html lang="es" className="h-full" suppressHydrationWarning>
      <body className="min-h-full flex flex-col" suppressHydrationWarning>
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
          <NavLink href="/settings">Settings</NavLink>
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
