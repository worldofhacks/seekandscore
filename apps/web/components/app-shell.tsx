import type { PropsWithChildren, ReactNode } from "react";

import { Badge } from "@seekandscore/ui";

import {
  DealIcon,
  GridIcon,
  LockIcon,
  MapIcon,
  PulseIcon,
  QueueIcon,
} from "@/components/icons";

interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  count?: string;
  active?: boolean;
  locked?: boolean;
}

const navItems: NavItem[] = [
  { label: "Overview", href: "#overview", icon: <GridIcon />, active: true },
  { label: "Research queue", href: "#candidate-queue", icon: <QueueIcon />, count: "12" },
  { label: "Map", href: "#candidate-queue", icon: <MapIcon /> },
  { label: "Deals", href: "#candidate-queue", icon: <DealIcon />, count: "4" },
  { label: "Outreach", href: "#outreach-panel", icon: <LockIcon />, locked: true },
  { label: "Source health", href: "#source-health", icon: <PulseIcon /> },
];

function BrandMark() {
  return (
    <span aria-hidden="true" className="brand-mark">
      <span />
      <span />
      <span />
    </span>
  );
}

export function AppShell({ children }: PropsWithChildren) {
  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <BrandMark />
          <div>
            <strong>Seek and Score</strong>
            <span>Property intelligence</span>
          </div>
        </div>

        <div className="sidebar-region" aria-label="Active region">
          <span className="sidebar-region__eyebrow">Active region</span>
          <strong>Central Texas</strong>
          <span>3 counties · shadow mode</span>
        </div>

        <nav aria-label="Primary navigation" className="sidebar-nav">
          <p className="sidebar-nav__label">Workspace</p>
          <ul>
            {navItems.map((item) => (
              <li key={item.label}>
                <a
                  aria-current={item.active ? "page" : undefined}
                  className={`sidebar-nav__item${item.active ? " is-active" : ""}`}
                  href={item.href}
                >
                  <span className="sidebar-nav__icon">{item.icon}</span>
                  <span>{item.label}</span>
                  {item.count ? <span className="sidebar-nav__count">{item.count}</span> : null}
                  {item.locked ? <LockIcon className="sidebar-nav__lock" height="14" width="14" /> : null}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footer__row">
            <span className="status-indicator" />
            <span>Workspace healthy</span>
          </div>
          <Badge tone="outline">Synthetic preview</Badge>
          <p>No production data or outreach is active.</p>
        </div>
      </aside>

      <div className="app-workspace">
        <header className="mobile-header">
          <div className="sidebar-brand">
            <BrandMark />
            <strong>Seek and Score</strong>
          </div>
          <Badge tone="outline">Central Texas</Badge>
        </header>
        {children}
      </div>
    </div>
  );
}
