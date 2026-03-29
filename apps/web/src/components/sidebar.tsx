"use client";

import Link from "next/link";
import { useCallback, useSyncExternalStore } from "react";
import { usePathname } from "next/navigation";
import {
  Activity,
  ArrowLeftToLine,
  ArrowRightToLine,
  GitCompareArrows,
  Moon,
  Sun,
} from "lucide-react";
import { useTheme } from "./theme-provider";

const COLLAPSE_KEY = "leer-sidebar-collapsed";

const collapseListeners = new Set<() => void>();

function subscribeCollapse(cb: () => void) {
  collapseListeners.add(cb);
  return () => {
    collapseListeners.delete(cb);
  };
}

function getCollapseSnapshot() {
  return localStorage.getItem(COLLAPSE_KEY) === "true";
}

function setCollapsed(value: boolean) {
  localStorage.setItem(COLLAPSE_KEY, String(value));
  collapseListeners.forEach((l) => l());
}

export function Sidebar() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();
  const isRuns = pathname === "/" || pathname.startsWith("/runs");
  const isCompare = pathname.includes("/compare");

  const collapsed = useSyncExternalStore(
    subscribeCollapse,
    getCollapseSnapshot,
    () => false,
  );

  const toggleCollapse = useCallback(() => setCollapsed(!collapsed), [collapsed]);

  return (
    <aside
      className={`flex h-screen shrink-0 flex-col overflow-hidden border-r border-neutral-100 bg-white transition-[width] duration-200 ease-in-out ${
        collapsed ? "w-[52px]" : "w-52"
      }`}
    >
      {/* Header: logo + collapse toggle */}
      <div className="flex h-[53px] shrink-0 items-center border-b border-neutral-100 px-3">
        {!collapsed && (
          <div className="flex items-center gap-2 overflow-hidden pl-2">
            <Link
              href="/"
              className="whitespace-nowrap text-lg font-semibold tracking-tight text-neutral-900"
            >
              Leer
            </Link>
            <span className="shrink-0 rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] font-medium text-neutral-400">
              dev
            </span>
          </div>
        )}
        <button
          onClick={toggleCollapse}
          className={`flex shrink-0 items-center justify-center rounded-md p-1.5 text-neutral-400 transition-colors hover:bg-neutral-50 hover:text-neutral-600 ${
            collapsed ? "mx-auto" : "ml-auto"
          }`}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ArrowRightToLine size={14} /> : <ArrowLeftToLine size={14} />}
        </button>
      </div>

      {/* Project — expanded only */}
      <div
        className={`shrink-0 overflow-hidden border-b border-neutral-100 transition-[max-height,opacity,padding] duration-200 ease-in-out ${
          collapsed ? "max-h-0 opacity-0 py-0" : "max-h-20 opacity-100 py-3"
        }`}
      >
        <div className="px-5">
          <div className="text-[10px] font-medium uppercase tracking-wider text-neutral-400">
            Project
          </div>
          <div className="mt-0.5 truncate text-sm font-medium text-neutral-700">
            demo-project
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav
        className={`flex flex-col gap-0.5 py-3 ${collapsed ? "items-center px-1.5" : "px-3"}`}
      >
        <NavItem
          href="/"
          icon={Activity}
          label="Runs"
          active={isRuns && !isCompare}
          collapsed={collapsed}
        />
        <NavItem
          href="/"
          icon={GitCompareArrows}
          label="Compare"
          active={isCompare}
          collapsed={collapsed}
        />
      </nav>

      {/* Theme toggle */}
      <div
        className={`mt-auto shrink-0 border-t border-neutral-100 py-3 ${
          collapsed ? "px-1.5" : "px-3"
        }`}
      >
        <Tooltip label={theme === "dark" ? "Light mode" : "Dark mode"} enabled={collapsed}>
          <button
            onClick={toggle}
            className={`flex w-full items-center rounded-md py-1.5 text-neutral-500 transition-colors hover:bg-neutral-50 hover:text-neutral-700 ${
              collapsed ? "justify-center px-0" : "gap-2 px-3"
            }`}
          >
            {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            {!collapsed && (
              <span className="whitespace-nowrap text-[11px] font-medium">
                {theme === "dark" ? "Light mode" : "Dark mode"}
              </span>
            )}
          </button>
        </Tooltip>
      </div>
    </aside>
  );
}

/* ------------------------------------------------------------------ */

function NavItem({
  href,
  icon: Icon,
  label,
  active,
  collapsed,
}: {
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  label: string;
  active: boolean;
  collapsed: boolean;
}) {
  const colors = active
    ? "bg-neutral-100 text-neutral-900"
    : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-700";

  return (
    <Tooltip label={label} enabled={collapsed}>
      <Link
        href={href}
        className={`flex items-center rounded-md text-sm font-medium transition-colors ${colors} ${
          collapsed ? "justify-center p-2" : "gap-2.5 px-3 py-1.5"
        }`}
      >
        <Icon size={15} className="shrink-0" />
        {!collapsed && <span className="whitespace-nowrap">{label}</span>}
      </Link>
    </Tooltip>
  );
}

/* ------------------------------------------------------------------ */

function Tooltip({
  label,
  enabled,
  children,
}: {
  label: string;
  enabled: boolean;
  children: React.ReactNode;
}) {
  if (!enabled) return children;

  return (
    <div className="group/tip relative">
      {children}
      <div className="pointer-events-none absolute left-full top-1/2 z-50 ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-neutral-900 px-2.5 py-1 text-[11px] font-medium text-neutral-100 opacity-0 shadow-lg transition-opacity duration-150 group-hover/tip:opacity-100">
        {label}
      </div>
    </div>
  );
}
