"use client";

import { cn } from "@/lib/utils";
import { CalendarCheck, LayoutDashboard, LogOut, Mic, Send, TerminalSquare, Users } from "lucide-react";
import { signOut, useSession } from "next-auth/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { VoiceModeToggle } from "@/components/voice-mode-toggle";

const NAV_ITEMS = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/hiring-assistant", label: "Hiring Assistant", icon: Mic },
  { href: "/people-search", label: "People Search", icon: Users },
  { href: "/outreach", label: "Outreach", icon: Send },
  { href: "/attendance", label: "Attendance", icon: CalendarCheck },
] as const;

const DEV_NAV_ITEM = { href: "/call-console", label: "Call Console (dev)", icon: TerminalSquare } as const;

function NavLink({ href, label, icon: Icon }: { href: string; label: string; icon: typeof LayoutDashboard }) {
  const pathname = usePathname();
  const isActive = pathname === href;
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        isActive
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </Link>
  );
}

function UserFooter() {
  const { data: session } = useSession();
  if (!session) return null;

  const isGuest = session.user.role === "guest";
  const label = isGuest ? "Guest" : session.user.name || session.user.email || "Signed in";

  return (
    <div className="flex items-center gap-2 border-t px-3 py-3">
      {session.user.image ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={session.user.image} alt="" className="size-6 shrink-0 rounded-full" />
      ) : (
        <div className="flex size-6 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-[10px] font-medium">
          {isGuest ? "G" : label.slice(0, 1).toUpperCase()}
        </div>
      )}
      <span className="min-w-0 flex-1 truncate text-xs font-medium text-sidebar-foreground/80">{label}</span>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        title="Sign out"
        onClick={() => signOut({ redirectTo: "/login" })}
      >
        <LogOut className="size-3.5" />
      </Button>
    </div>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  if (pathname === "/login") return null;

  return (
    <aside className="flex h-full w-60 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="px-4 py-5">
        <span className="text-lg font-semibold tracking-tight">Hunar</span>
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-2">
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} {...item} />
        ))}
      </nav>
      <div className="border-t px-2 py-2">
        <p className="px-3 pb-1 text-xs font-medium uppercase tracking-wide text-sidebar-foreground/50">
          Developer
        </p>
        <NavLink {...DEV_NAV_ITEM} />
      </div>
      <div className="border-t px-2 py-3">
        <p className="px-3 pb-1.5 text-xs font-medium uppercase tracking-wide text-sidebar-foreground/50">
          Voice mode
        </p>
        <VoiceModeToggle />
      </div>
      <UserFooter />
    </aside>
  );
}
