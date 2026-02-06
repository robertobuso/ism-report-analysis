"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Newspaper, PieChart, LayoutGrid, LogOut } from "lucide-react";
import { useAuth } from "@/providers/auth-provider";
import { EnvoyLogo } from "@/components/ui/orbital-logo";

const SUITE_URL = process.env.NEXT_PUBLIC_SUITE_URL || "http://localhost:5000";

const navItems = [
  { href: `${SUITE_URL}/suite`, label: "Suite Home", icon: LayoutGrid, external: true },
  { href: `${SUITE_URL}/dashboard`, label: "ISM Analysis", icon: BarChart3, external: true },
  { href: `${SUITE_URL}/news`, label: "News Analysis", icon: Newspaper, external: true },
  { href: "/", label: "Portfolio Intelligence", icon: PieChart, external: false },
];

export function Header() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <header className="bg-white px-6" style={{ boxShadow: "0 2px 10px rgba(0, 0, 0, 0.05)" }}>
      <div className="flex items-center justify-between py-4">
        <div className="flex items-center gap-8">
          {/* Brand - matches .ds-brand */}
          <Link
            href="/"
            className="flex items-center gap-2 text-primary font-bold no-underline hover:text-primary hover:no-underline"
            style={{ fontSize: "1.25rem" }}
          >
            <EnvoyLogo size={56} />
            Envoy LLC
          </Link>

          {/* Nav - matches .ds-nav */}
          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = !item.external && pathname === item.href;
              const Icon = item.icon;

              if (item.external) {
                return (
                  <a
                    key={item.href}
                    href={item.href}
                    className="flex items-center gap-1.5 px-3 py-2 font-medium text-foreground no-underline hover:text-primary hover:no-underline transition-colors rounded-button border-b-2 border-transparent"
                    style={{ fontSize: "0.875rem" }}
                  >
                    <Icon size={16} />
                    {item.label}
                  </a>
                );
              }

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-1.5 px-3 py-2 font-medium no-underline hover:no-underline transition-colors rounded-button border-b-2 ${
                    isActive
                      ? "text-primary border-primary"
                      : "text-foreground hover:text-primary border-transparent"
                  }`}
                  style={{ fontSize: "0.875rem" }}
                >
                  <Icon size={16} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {user && (
          <div className="flex items-center gap-4">
            <span className="text-sm text-muted hidden sm:block">{user.email}</span>
            <button
              onClick={logout}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-muted hover:text-foreground border border-gray-200 rounded-button transition-colors"
            >
              <LogOut size={16} />
              Logout
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
