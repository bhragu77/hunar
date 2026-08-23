import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin the workspace root to this directory: the parent directory (the
  // user's home dir) happens to contain an unrelated package-lock.json,
  // which otherwise confuses Turbopack's root inference.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
