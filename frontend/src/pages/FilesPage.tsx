import { useCallback, useEffect, useRef, useState } from "react";
import { api, downloadContent, uploadFileResumable } from "../services/api";
import { PageTitle } from "../components/Layout";
import "../styles/files.css";

export interface CloudFile {
  id: string;
  name: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  folder_id: string | null;
  created_at: string;
  updated_at: string;
  mtime: string;
  is_favorite: boolean;
}

interface FileListPayload {
  items: CloudFile[];
  total: number;
  page: number;
  page_size: number;
}

interface UploadRow {
  id: string;
  name: string;
  sizeBytes: number;
  done: number;
  totalChunks: number;
  state: "uploading" | "completed" | "failed";
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

export function FilesPage() {
  const [files, setFiles] = useState<CloudFile[]>([]);
  const [total, setTotal] = useState(0);
  const [uploads, setUploads] = useState<UploadRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    try {
      const payload = await api<FileListPayload>("/v1/files?page=0&page_size=100");
      setFiles(payload.items);
      setTotal(payload.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list files");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  async function handlePick(files: FileList | null) {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        const rowId = `${file.name}-${file.size}`;
        setUploads((current) => [
          ...current,
          {
            id: rowId,
            name: file.name,
            sizeBytes: file.size,
            done: 0,
            totalChunks: 0,
            state: "uploading",
          },
        ]);
        try {
          await uploadFileResumable(file, {
            onReserved: (_id, totalChunks) => {
              setUploads((current) =>
                current.map((row) =>
                  row.id === rowId ? { ...row, totalChunks } : row,
                ),
              );
            },
            onChunkDone: (done) => {
              setUploads((current) =>
                current.map((row) =>
                  row.id === rowId ? { ...row, done } : row,
                ),
              );
            },
          });
          setUploads((current) =>
            current.map((row) =>
              row.id === rowId ? { ...row, state: "completed" } : row,
            ),
          );
        } catch {
          setUploads((current) =>
            current.map((row) =>
              row.id === rowId ? { ...row, state: "failed" } : row,
            ),
          );
        }
      }
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageTitle
        title="My Files"
        actions={
          <>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                void handlePick(e.target.files);
                e.target.value = "";
              }}
            />
            <button
              className="primary-btn"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              {busy ? "Uploading…" : "+ Upload"}
            </button>
          </>
        }
      />

      {uploads.length > 0 && (
        <div className="upload-tray">
          {uploads.map((row) => (
            <div key={row.id} className={`upload-row ${row.state}`}>
              <div className="upload-meta">
                <span className="upload-name">{row.name}</span>
                <span className="upload-size">
                  {humanSize(row.sizeBytes)}
                  {row.totalChunks > 0 ? ` · chunk ${row.done}/${row.totalChunks}` : ""}
                </span>
              </div>
              <progress
                max={row.totalChunks || 1}
                value={row.state === "completed" ? row.totalChunks || 1 : row.done}
              />
            </div>
          ))}
        </div>
      )}

      {error && <div className="page-error">{error}</div>}

      <table className="files-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Size</th>
            <th>Type</th>
            <th>Modified</th>
            <th aria-label="actions" />
          </tr>
        </thead>
        <tbody>
          {files.map((file) => (
            <tr key={file.id}>
              <td>{file.name}</td>
              <td>{humanSize(file.size_bytes)}</td>
              <td>
                <span className="chip">{file.extension || file.mime_type}</span>
              </td>
              <td>{new Date(file.mtime).toLocaleString()}</td>
              <td className="row-actions">
                <button
                  className="ghost-btn"
                  onClick={() => downloadContent(file.id, file.name)}
                >
                  Download
                </button>
              </td>
            </tr>
          ))}
          {files.length === 0 && (
            <tr>
              <td colSpan={5} className="empty-cell">
                No files yet — click + Upload to add your first file.
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {files.length > 0 && (
        <div className="table-footer">{total} item(s)</div>
      )}
    </div>
  );
}
