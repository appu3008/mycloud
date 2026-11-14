import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { api } from "../services/api";
import type { CloudFile } from "../services/api";
import { PageTitle } from "../components/Layout";

function humanSize(bytes: number): string {
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
}

export function OverviewPage() {
  const { user, loading } = useAuth();
  const [recent, setRecent] = useState<CloudFile[]>([]);
  const [disk, setDisk] = useState<{
    free_bytes: number;
    total_bytes: number;
    used_percent: number;
  } | null>(null);

  useEffect(() => {
    void api<{ disk: { free_bytes: number; total_bytes: number; used_percent: number } }>(
      "/health",
    )
      .then((health) => setDisk(health.disk))
      .catch(() => setDisk(null));
    void api<{ items: CloudFile[] }>("/v1/files?sort=mtime&order=desc&page_size=5")
      .then((payload) => setRecent(payload.items))
      .catch(() => setRecent([]));
  }, []);

  if (loading) return <div className="empty-cell">Loading…</div>;
  if (!user) return <Navigate to="/login" replace />;

  return (
    <div>
      <PageTitle title={`Welcome, ${user.display_name}`} />
      <div className="cards">
        {disk && (
          <div className="card">
            <div className="card-label">Server disk</div>
            <div className="card-value">
              {humanSize(disk.total_bytes - disk.free_bytes)} / {humanSize(disk.total_bytes)}
            </div>
            <progress max={100} value={disk.used_percent} />
            <div className="card-sub">{disk.used_percent.toFixed(1)}% used · guardrails active</div>
          </div>
        )}
        <div className="card">
          <div className="card-label">Your files</div>
          <div className="card-value">{recent.length ? recent.length : "—"} shown</div>
          <div className="card-sub">Recent activity below</div>
        </div>
      </div>
      <PageTitle title="Recent uploads" />
      {recent.length === 0 ? (
        <div className="empty-cell">
          Nothing yet — head to <Link to="/files">My Files</Link> to upload.
        </div>
      ) : (
        <ul className="recent-list">
          {recent.map((file) => (
            <li key={file.id}>
              <Link to="/files">{file.name}</Link>
              <span>{humanSize(file.size_bytes)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
