import type { NextConfig } from "next";

// En Docker: BACKEND_URL=http://backend:8000  |  En local: http://localhost:8000
const backend = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
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
