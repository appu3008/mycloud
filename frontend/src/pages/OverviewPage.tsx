import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../services/api";
import type { CloudFile } from "../services/api";
import { Eyebrow, PageTagline } from "../components/Layout";
import iconServer from "../assets/figma/icon-server.svg";
import iconFileDoc from "../assets/figma/icon-file-doc.svg";
import iconUploadCard from "../assets/figma/icon-upload-card.svg";
import iconArrow from "../assets/figma/icon-arrow.svg";
import iconArrowLink from "../assets/figma/icon-arrow-link.svg";
import iconArrowDark from "../assets/figma/icon-arrow-dark.svg";
import iconClock from "../assets/figma/icon-clock.svg";
import "../styles/overview.css";

interface Health {
  status: string;
  disk: { total_bytes: number; used_bytes: number; free_bytes: number; used_percent: number };
  errors: string[];
}

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

export function OverviewPage({ displayName }: { displayName: string }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [recent, setRecent] = useState<CloudFile[] | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    api<Health>("/health")
      .then((h) => {
        if (!cancelled) setHealth(h);
      })
      .catch(() => {
        if (!cancelled) setHealth(null);
      });
    api<{ items: CloudFile[] }>("/v1/files?sort=mtime&order=desc&page_size=5")
      .then((p) => {
        if (!cancelled) setRecent(p.items);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const diskUsable = health !== null && health.status === "ok" && health.errors.length === 0;

  return (
    <div className="overview-page">
      <Eyebrow>Your personal cloud</Eyebrow>
      <div className="page-title-row">
        <h1>Welcome back, {displayName}.</h1>
      </div>
      <p className="page-sub">A little closer to your files. A little more in control.</p>

      {/* server storage — real telemetry; unavailable state only when health fails */}
      <section className={`card storage-card${diskUsable ? "" : " unavailable"}`}>
        <div className="storage-head">
          <img src={iconServer} alt="" width={24} height={24} />
          <span className="mono-label">Server storage</span>
        </div>
        {diskUsable && health ? (
          <div className="storage-body">
            <div className="storage-stat">
              <span className="storage-bar" aria-hidden="true">
                <span style={{ width: `${Math.min(100, health.disk.used_percent)}%` }} />
              </span>
              <span className="storage-caption mono-label">
                {humanSize(health.disk.used_bytes)} used of {humanSize(health.disk.total_bytes)} total
              </span>
            </div>
            <div className="storage-stat">
              <span className="storage-bar thin" aria-hidden="true">
                <span style={{ width: `${Math.min(100, health.disk.used_percent)}%` }} />
              </span>
              <span className="storage-caption mono-label">
                {health.disk.used_percent.toFixed(1)}% used
              </span>
            </div>
            <p className="storage-note">
              {humanSize(health.disk.free_bytes)} free · quota and disk guardrails active.
            </p>
          </div>
        ) : (
          <div className="storage-body">
            <span className="chip">Awaiting server data</span>
            <div className="storage-unavailable mono-label">
              <span>— used of — total</span>
              <span>Usage unavailable · — % used</span>
            </div>
            <p className="storage-note">Disk usage will appear when your server responds.</p>
          </div>
        )}
      </section>

      <div className="overview-grid">
        {/* recent uploads — real data, designed empty state */}
        <section className="card recent-card">
          <div className="recent-head">
            <span className="mono-label">Recent uploads</span>
            <Link to="/files" className="recent-link mono-label">
              View all files <img src={iconArrowLink} alt="" width={20} height={20} />
            </Link>
          </div>
          {recent !== null && recent.length > 0 ? (
            <ul className="recent-list">
              {recent.map((file) => (
                <li key={file.id}>
                  <span className="recent-name">{file.name}</span>
                  <span className="recent-meta mono-label">
                    {humanSize(file.size_bytes)} · {new Date(file.mtime).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="recent-empty">
              <div className="recent-empty-row">
                <span className="recent-doc">
                  <img src={iconFileDoc} alt="" width={30} height={30} />
                </span>
                <div>
                  <p className="recent-empty-title">Your first upload starts here.</p>
                  <p className="recent-empty-sub">
                    Add a file in My Files to see it in your recent uploads.
                  </p>
                </div>
                <button className="ghost-btn mono-label with-arrow" onClick={() => navigate("/files")}>
                  Open My Files <img src={iconArrow} alt="" width={18} height={18} />
                </button>
              </div>
            </div>
          )}
        </section>

        {/* CTA card */}
        <section className="card cta-card">
          <img src={iconUploadCard} alt="" width={28} height={28} className="cta-icon" />
          <h2>A home for your files.</h2>
          <p>
            Bring your documents, photos, and
            <br />
            everyday essentials into your cloud.
          </p>
          <button className="primary-btn cta-btn" onClick={() => navigate("/files")}>
            <span className="mono-label">Go to My Files</span>
            <img src={iconArrowDark} alt="" width={20} height={20} />
          </button>
        </section>
      </div>

      <div className="grow-note">
        <img src={iconClock} alt="" width={20} height={20} />
        <div>
          <p className="grow-title">Room to grow</p>
          <p className="grow-sub">
            Media, sharing, recycle bin, and system pages are planned for a later phase.
          </p>
        </div>
      </div>

      <PageTagline>Self-hosted. Simply yours.</PageTagline>
    </div>
  );
}
