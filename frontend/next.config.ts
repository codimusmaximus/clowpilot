import type { NextConfig } from "next";

const apiBase =
  process.env.BACKEND_URL ??
  process.env.NEXT_PUBLIC_API_BASE ??
  "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/workspace/image",
        destination: `${apiBase}/api/workspace/image`,
      },
    ];
  },
};

export default nextConfig;
