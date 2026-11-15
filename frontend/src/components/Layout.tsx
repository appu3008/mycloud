import { NavLink, Outlet, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import logoUrl from "../assets/figma/logo-cloud.svg";
import iconSun from "../assets/figma/icon-sun.svg";
import iconMoon from "../assets/figma/icon-moon.svg";
import navOverview from "../assets/figma/nav-overview.svg";
import navMyFiles from "../assets/figma/nav-myfiles.svg";
import navRecent from "../assets/figma/nav-recent.svg";
import navFavorites from "../assets/figma/nav-favorites.svg";
import navShared from "../assets/figma/nav-shared.svg";
import navRecycle from "../assets/figma/nav-recycle.svg";
import navPhotos from "../assets/figma/nav-photos.svg";
import navVideos from "../assets/figma/nav-videos.svg";
import navDevices from "../assets/figma/nav-devices.svg";
import navActivity from "../assets/figma/nav-activity.svg";
import navMonitor from "../assets/figma/nav-monitor.svg";
import navSettings from "../assets/figma/nav-settings.svg";
import "../styles/layout.css";

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

const CLOUD_NAV: NavItem[] = [
  { to: "/", label: "Overview", icon: navOverview },
  { to: "/files", label: "My Files", icon: navMyFiles },
  { to: "/recent", label: "Recent Files", icon: navRecent },
  { to: "/favorites", label: "Favorites", icon: navFavorites },
  { to: "/shared", label: "Shared Files", icon: navShared },
  { to: "/recycle", label: "Recycle Bin", icon: navRecycle },
];
const MEDIA_NAV: NavItem[] = [
  { to: "/photos", label: "Photos", icon: navPhotos },
  { to: "/videos", label: "Videos", icon: navVideos },
];
const SYSTEM_NAV: NavItem[] = [
  { to: "/devices", label: "Devices", icon: navDevices },
  { to: "/activity", label: "Activity", icon: navActivity },
  { to: "/monitor", label: "Server Monitor", icon: navMonitor },
  { to: "/settings", label: "Settings", icon: navSettings },
];

function NavTabs({ items }: { items: NavItem[] }) {
  return (
    <>
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          className={({ isActive }) => `nav-tab${isActive ? " active" : ""}`}
        >
          <img src={item.icon} alt="" width={14} height={14} />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-cell">
          <img src={logoUrl} alt="" width={22} height={22} className="brand-mark" />
          <span className="brand-name">localcloud</span>
        </div>
        <div className="server-cell">
          <span className="mono-label">Your personal server</span>
          <span className="mono-label">Hosted on your laptop</span>
        </div>
        <div className="workspace-cell mono-label">Personal workspace</div>
        <div className="top-actions">
          <div className="theme-toggle" role="group" aria-label="Theme">
            <button
              className={`theme-opt${theme === "light" ? " active" : ""}`}
              onClick={() => theme !== "light" && toggle()}
            >
              <img src={iconSun} alt="" width={12} height={12} />
              <span>Light</span>
            </button>
            <button
              className={`theme-opt${theme === "dark" ? " active" : ""}`}
              onClick={() => theme !== "dark" && toggle()}
            >
              <img src={iconMoon} alt="" width={12} height={12} />
              <span>Dark</span>
            </button>
          </div>
          <span className="role-chip mono-label">{user?.role === "admin" ? "Administrator" : "Member"}</span>
          <button className="ghost-btn mono-label" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <nav className="nav-rows" aria-label="Primary">
        <div className="nav-row">
          <span className="nav-group mono-label">Cloud</span>
          <div className="nav-tabs">
            <NavTabs items={CLOUD_NAV} />
            <span className="nav-disabled mono-label" aria-hidden="true">
              Media
            </span>
            <NavTabs items={MEDIA_NAV} />
          </div>
        </div>
        <div className="nav-row">
          <span className="nav-group mono-label">System</span>
          <div className="nav-tabs">
            <NavTabs items={SYSTEM_NAV} />
          </div>
        </div>
      </nav>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

export function PageTitle({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <div className="page-title-row">
      <h1>{title}</h1>
      <div className="page-actions">{actions}</div>
    </div>
  );
}

export function PageTagline({ children }: { children: ReactNode }) {
  return <div className="page-tagline mono-label">{children}</div>;
}

/** Eyebrow row above the page title (small icon + mono label), per design. */
export function Eyebrow({ icon, children }: { icon?: string; children: ReactNode }) {
  return (
    <div className="page-eyebrow mono-label">
      {icon && <img src={icon} alt="" width={12} height={12} />}
      <span>{children}</span>
    </div>
  );
}
