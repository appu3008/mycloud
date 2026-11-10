import { NavLink, Outlet, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import "../styles/layout.css";

const NAV_SECTIONS: { header: string; links: { to: string; label: string }[] }[] = [
  {
    header: "Cloud",
    links: [
      { to: "/", label: "Overview" },
      { to: "/files", label: "My Files" },
      { to: "/recent", label: "Recent Files" },
      { to: "/favorites", label: "Favorites" },
      { to: "/shared", label: "Shared Files" },
      { to: "/recycle", label: "Recycle Bin" },
    ],
  },
  {
    header: "Media",
    links: [
      { to: "/photos", label: "Photos" },
      { to: "/videos", label: "Videos" },
    ],
  },
  {
    header: "System",
    links: [
      { to: "/devices", label: "Devices" },
      { to: "/activity", label: "Activity" },
      { to: "/monitor", label: "Server Monitor" },
      { to: "/settings", label: "Settings" },
    ],
  },
];

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
      <aside className="sidebar">
        <div className="brand-row">
          <span className="brand">MyCloud</span>
          <button className="ghost-btn icon-btn" onClick={toggle} title="Toggle theme">
            {theme === "dark" ? "☀" : "☾"}
          </button>
        </div>
        <nav>
          {NAV_SECTIONS.map((section) => (
            <div key={section.header} className="nav-section">
              <div className="nav-header">{section.header}</div>
              {section.links.map((link) => (
                <NavLink key={link.to} to={link.to} end className={({ isActive }) =>
                  `nav-link${isActive ? " active" : ""}`}
                >
                  {link.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="search-slot" />
          <div className="top-actions">
            <span className="user-chip">{user?.display_name ?? user?.email}</span>
            <button className="ghost-btn" onClick={handleLogout}>
              Log out
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
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
