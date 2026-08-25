import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

/**
 * Auth gate for the app - see proxy.ts for the actual route protection. Two ways in:
 *
 * - Google: real identity, the only role allowed to flip the voice-mode toggle to "real"
 *   (see components/voice-mode-toggle.tsx) since that spends real money on a real API key.
 * - Guest: a Credentials provider whose authorize() never actually checks anything - it just
 *   issues a session tagged role="guest". No password, no email, just a way in for a reviewer
 *   who doesn't want to use their Google account. Guests are mock-only.
 */
export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
    }),
    Credentials({
      id: "guest",
      name: "Guest",
      credentials: {},
      authorize: async () => ({ id: "guest", name: "Guest", email: null }),
    }),
  ],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    jwt({ token, account }) {
      if (account?.provider === "guest") {
        token.role = "guest";
      } else if (account) {
        token.role = "user";
      }
      return token;
    },
    session({ session, token }) {
      session.user.role = (token.role as "user" | "guest" | undefined) ?? "guest";
      return session;
    },
  },
});
