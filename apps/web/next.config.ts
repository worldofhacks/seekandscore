import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@seekandscore/ui", "@seekandscore/contracts"],
};

export default nextConfig;
