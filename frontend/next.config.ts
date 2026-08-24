import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // "standalone" output is only for the self-hosted Docker build (see
  // frontend/Dockerfile) - it's not needed on Vercel, and actually breaks
  // routing there (every route 404s) since Vercel's build has its own
  // tracing/bundling that conflicts with a standalone server build. Vercel
  // sets VERCEL=1 during its builds, so key off that instead of hardcoding.
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  // Pin the workspace root to this directory: the parent directory (the
  // user's home dir) happens to contain an unrelated package-lock.json,
  // which otherwise confuses Turbopack's root inference.
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
