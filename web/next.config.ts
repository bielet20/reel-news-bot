import type { NextConfig } from "next";

// En Docker: BACKEND_URL=http://backend:8000  |  En local: http://localhost:8000
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  // Next 16 bloquea por defecto las peticiones cross-origin a los recursos de
  // dev (_next/*, webpack-hmr) si el host no es "localhost". Abrir la app en
  // http://127.0.0.1:3000 dejaba la página sin hidratar (renderiza pero los
  // clics no hacen nada). Permitimos también 127.0.0.1 y la IP de la LAN.
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [
      { source: "/api/:path*",           destination: `${backend}/api/:path*` },
      { source: "/videos/:path*",        destination: `${backend}/videos/:path*` },
      { source: "/library-files/:path*", destination: `${backend}/library-files/:path*` },
      { source: "/music-files/:path*",   destination: `${backend}/music-files/:path*` },
    ];
  },
};

export default nextConfig;
