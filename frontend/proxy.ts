import { NextResponse } from "next/server";

import { auth } from "@/auth";

// Next.js 16 renamed middleware.ts to proxy.ts - same mechanism, new file name.
export default auth((req) => {
  const isLoginPage = req.nextUrl.pathname === "/login";

  if (!req.auth && !isLoginPage) {
    return NextResponse.redirect(new URL("/login", req.nextUrl.origin));
  }
  if (req.auth && isLoginPage) {
    return NextResponse.redirect(new URL("/", req.nextUrl.origin));
  }
});

export const config = {
  // Run on everything except static assets, image optimization, and the auth API routes
  // themselves (those must stay reachable to complete a login).
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico).*)"],
};
