import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  webpack: (config) => {
    // Silence optional peer dep warnings from @magic-sdk/admin
    config.resolve.fallback = {
      ...config.resolve.fallback,
      encoding: false,
      bufferutil: false,
      "utf-8-validate": false,
    };
    return config;
  },
};

export default nextConfig;
