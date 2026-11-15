import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./contexts/AuthContext";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { FilesPage } from "./pages/FilesPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

export function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="splash">Loading MyCloud…</div>;
  }
  if (!user) {
    return <LoginPage />;
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<OverviewPage displayName={user.display_name} />} />
        <Route path="/files" element={<FilesPage />} />
        {(
          [
            "/recent",
            "/favorites",
            "/shared",
            "/recycle",
            "/photos",
            "/videos",
            "/devices",
            "/activity",
            "/monitor",
            "/settings",
          ] as const
        ).map((path) => (
          <Route key={path} path={path} element={<PlaceholderPage />} />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
