import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  api,
  batchFiles,
  batchFolders,
  createFolder as createFolderApi,
  deleteFolder as deleteFolderApi,
  downloadContent,
  folderDetail,
  listFolders,
  renameFile,
  renameFolder,
  uploadFileResumable,
} from "../services/api";
import type { CloudFile, CloudFolder, FolderDetail } from "../services/api";
import { PageTitle } from "../components/Layout";
import { Modal } from "../components/Modal";
import { FolderPicker } from "../components/FolderPicker";
import { useAuth } from "../contexts/AuthContext";
import "../styles/files.css";

export interface FileListPayload {
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

/** Payload carried by internal drag operations. */
interface DragSelection {
  files: string[];
  folders: string[];
}

const DRAG_TYPE = "application/x-mycloud-items";

type ModalState =
  | { kind: "none" }
  | { kind: "create" }
  | { kind: "move" }
  | { kind: "rename"; targetType: "file" | "folder"; id: string; initial: string };

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
  useAuth(); // page renders only inside the authed layout
  const [searchParams, setSearchParams] = useSearchParams();
  const folderId = searchParams.get("folder");

  const [folders, setFolders] = useState<CloudFolder[]>([]);
  const [files, setFiles] = useState<CloudFile[]>([]);
  const [breadcrumb, setBreadcrumb] = useState<CloudFolder[]>([]);
  const [total, setTotal] = useState(0);
  const [uploads, setUploads] = useState<UploadRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<Set<string>>(new Set());
  const [selectedFolders, setSelectedFolders] = useState<Set<string>>(new Set());
  const [modal, setModal] = useState<ModalState>({ kind: "none" });
  const [modalText, setModalText] = useState("");
  const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
  const [pageDragOver, setPageDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const requests: [Promise<{ items: CloudFolder[] }>, Promise<FileListPayload>, Promise<FolderDetail | null>] = [
        listFolders(folderId),
        api<FileListPayload>(`/v1/files?page=0&page_size=100${folderId ? `&folder_id=${folderId}` : ""}`),
        folderId ? folderDetail(folderId) : Promise.resolve(null),
      ];
      const [folderPayload, filePayload, detail] = await Promise.all(requests);
      setFolders(folderPayload.items);
      setFiles(filePayload.items);
      setTotal(filePayload.total);
      setBreadcrumb(detail ? detail.breadcrumb : []);
      setSelectedFiles(new Set());
      setSelectedFolders(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load folder");
    }
  }, [folderId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // --- uploads ---------------------------------------------------------------

  async function handlePick(picked: FileList | null) {
    if (!picked || picked.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of Array.from(picked)) {
        const rowId = `${file.name}-${file.size}`;
        setUploads((current) => [
          ...current,
          { id: rowId, name: file.name, sizeBytes: file.size, done: 0, totalChunks: 0, state: "uploading" },
        ]);
        try {
          await uploadFileResumable(file, {
            targetFolderId: folderId,
            onReserved: (_id, totalChunks) => {
              setUploads((current) =>
                current.map((row) => (row.id === rowId ? { ...row, totalChunks } : row)),
              );
            },
            onChunkDone: (done) => {
              setUploads((current) =>
                current.map((row) => (row.id === rowId ? { ...row, done } : row)),
              );
            },
          });
          setUploads((current) =>
            current.map((row) => (row.id === rowId ? { ...row, state: "completed" } : row)),
          );
        } catch {
          setUploads((current) =>
            current.map((row) => (row.id === rowId ? { ...row, state: "failed" } : row)),
          );
        }
      }
      await reload();
    } finally {
      setBusy(false);
    }
  }

  // --- mutations ---------------------------------------------------------------

  async function runMutation(action: () => Promise<unknown>, successNote: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await reload();
      setModal({ kind: "none" });
      setModalText("");
      return successNote;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
      return null;
    } finally {
      setBusy(false);
    }
  }

  const selectionCount = selectedFiles.size + selectedFolders.size;

  function moveSelectionTo(targetId: string | null, payload: DragSelection) {
    // A folder cannot be moved into itself or its own selection targets.
    const folderIds = payload.folders.filter((id) => id !== targetId);
    return runMutation(async () => {
      if (payload.files.length > 0) {
        await batchFiles("move", payload.files, targetId);
      }
      if (folderIds.length > 0) {
        await batchFolders("move", folderIds, targetId);
      }
    }, "Moved");
  }

  function deleteSelection() {
    return runMutation(async () => {
      if (selectedFiles.size > 0) await batchFiles("delete", [...selectedFiles]);
      if (selectedFolders.size > 0) await batchFolders("delete", [...selectedFolders]);
    }, "Moved to recycle bin");
  }

  function copyOne(fileId: string) {
    return runMutation(() => batchFiles("copy", [fileId], folderId), "Copied");
  }

  function confirmCreate(name: string) {
    return runMutation(() => createFolderApi(name, folderId), "Folder created");
  }

  function confirmRename(state: ModalState & { kind: "rename" }, name: string) {
    return runMutation(
      () =>
        state.targetType === "file"
          ? renameFile(state.id, name)
          : renameFolder(state.id, name),
      "Renamed",
    );
  }

  function deleteOneFolder(id: string) {
    return runMutation(() => deleteFolderApi(id), "Moved to recycle bin");
  }

  // --- selection & drag --------------------------------------------------------

  function toggle(kind: "file" | "folder", id: string) {
    const setter = kind === "file" ? setSelectedFiles : setSelectedFolders;
    setter((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllVisible() {
    const allFiles = files.length === selectedFiles.size && files.length > 0;
    const allFolders = folders.length === selectedFolders.size && folders.length > 0;
    if (allFiles && allFolders) {
      setSelectedFiles(new Set());
      setSelectedFolders(new Set());
    } else {
      setSelectedFiles(new Set(files.map((f) => f.id)));
      setSelectedFolders(new Set(folders.map((f) => f.id)));
    }
  }

  function dragSelectionFor(kind: "file" | "folder", id: string): DragSelection {
    if (kind === "file" && selectedFiles.has(id) && selectedFiles.size > 0) {
      return { files: [...selectedFiles], folders: [...selectedFolders] };
    }
    if (kind === "folder" && selectedFolders.has(id) && selectionCount > 0) {
      return { files: [...selectedFiles], folders: [...selectedFolders] };
    }
    return kind === "file" ? { files: [id], folders: [] } : { files: [], folders: [id] };
  }

  function navigateTo(folder: string | null) {
    setSearchParams(folder ? { folder } : {});
  }

  const hasInternalPayload = (event: React.DragEvent) =>
    Array.from(event.dataTransfer.types).includes(DRAG_TYPE);

  return (
    <div
      className={`files-page${pageDragOver ? " page-drag-over" : ""}`}
      onDragOver={(e) => {
        if (!hasInternalPayload(e) && e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setPageDragOver(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setPageDragOver(false);
      }}
      onDrop={(e) => {
        if (!hasInternalPayload(e) && e.dataTransfer.files.length > 0) {
          e.preventDefault();
          setPageDragOver(false);
          void handlePick(e.dataTransfer.files);
        }
      }}
    >
      <PageTitle
        title={breadcrumb.length > 0 ? breadcrumb[breadcrumb.length - 1].name : "My Files"}
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
            <button className="ghost-btn" disabled={busy} onClick={() => setModal({ kind: "create" })}>
              + New folder
            </button>
            <button
              className="primary-btn"
              disabled={busy}
              onClick={() => fileInputRef.current?.click()}
            >
              {busy ? "Working…" : "+ Upload"}
            </button>
          </>
        }
      />

      <div className="breadcrumb-bar">
        <button className="crumb" onClick={() => navigateTo(null)}>
          My Files
        </button>
        {breadcrumb.map((crumb) => (
          <span key={crumb.id} className="crumb-segment">
            <span className="crumb-sep">/</span>
            <button className="crumb" onClick={() => navigateTo(crumb.id)}>
              {crumb.name}
            </button>
          </span>
        ))}
      </div>

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

      {selectionCount > 0 && (
        <div className="selection-toolbar">
          <span>{selectionCount} selected</span>
          <button
            className="ghost-btn"
            disabled={busy}
            onClick={() => {
              setModal({ kind: "move" });
            }}
          >
            Move to…
          </button>
          <button className="ghost-btn danger" disabled={busy} onClick={() => void deleteSelection()}>
            Delete
          </button>
          <button
            className="ghost-btn"
            onClick={() => {
              setSelectedFiles(new Set());
              setSelectedFolders(new Set());
            }}
          >
            Clear
          </button>
        </div>
      )}

      <table className="files-table">
        <thead>
          <tr>
            <th className="col-check">
              <input
                type="checkbox"
                aria-label="Select all"
                checked={files.length + folders.length > 0 && selectionCount === files.length + folders.length}
                onChange={selectAllVisible}
              />
            </th>
            <th>Name</th>
            <th>Size</th>
            <th>Type</th>
            <th>Modified</th>
            <th aria-label="actions" />
          </tr>
        </thead>
        <tbody>
          {folders.map((folder) => (
            <tr
              key={folder.id}
              className={`folder-row${selectedFolders.has(folder.id) ? " selected" : ""}${
                dragOverFolder === folder.id ? " drop-target" : ""
              }`}
              onDragOver={(e) => {
                if (hasInternalPayload(e)) {
                  e.preventDefault();
                  setDragOverFolder(folder.id);
                }
              }}
              onDragLeave={() => setDragOverFolder((current) => (current === folder.id ? null : current))}
              onDrop={(e) => {
                if (!hasInternalPayload(e)) return;
                e.preventDefault();
                e.stopPropagation();
                setDragOverFolder(null);
                const raw = e.dataTransfer.getData(DRAG_TYPE);
                try {
                  const payload = JSON.parse(raw) as DragSelection;
                  if (payload.files.length + payload.folders.length > 0) {
                    void moveSelectionTo(folder.id, payload);
                  }
                } catch {
                  setError("Could not read dragged items");
                }
              }}
            >
              <td className="col-check">
                <input
                  type="checkbox"
                  aria-label={`Select ${folder.name}`}
                  checked={selectedFolders.has(folder.id)}
                  onChange={() => toggle("folder", folder.id)}
                />
              </td>
              <td
                draggable
                onDragStart={(e) =>
                  e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(dragSelectionFor("folder", folder.id)))
                }
              >
                <button className="row-link" onClick={() => navigateTo(folder.id)}>
                  📁 {folder.name}
                </button>
              </td>
              <td>—</td>
              <td>
                <span className="chip">folder</span>
              </td>
              <td>{new Date(folder.updated_at).toLocaleString()}</td>
              <td className="row-actions">
                <button
                  className="ghost-btn"
                  disabled={busy}
                  onClick={() => {
                    setModal({ kind: "rename", targetType: "folder", id: folder.id, initial: folder.name });
                    setModalText(folder.name);
                  }}
                >
                  Rename
                </button>
                <button className="ghost-btn danger" disabled={busy} onClick={() => void deleteOneFolder(folder.id)}>
                  Delete
                </button>
              </td>
            </tr>
          ))}

          {files.map((file) => (
            <tr
              key={file.id}
              className={`file-row${selectedFiles.has(file.id) ? " selected" : ""}`}
              draggable
              onDragStart={(e) =>
                e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(dragSelectionFor("file", file.id)))
              }
            >
              <td className="col-check">
                <input
                  type="checkbox"
                  aria-label={`Select ${file.name}`}
                  checked={selectedFiles.has(file.id)}
                  onChange={() => toggle("file", file.id)}
                />
              </td>
              <td>{file.name}</td>
              <td>{humanSize(file.size_bytes)}</td>
              <td>
                <span className="chip">{file.extension || file.mime_type}</span>
              </td>
              <td>{new Date(file.mtime).toLocaleString()}</td>
              <td className="row-actions">
                <button className="ghost-btn" onClick={() => downloadContent(file.id, file.name)}>
                  Download
                </button>
                <button className="ghost-btn" disabled={busy} onClick={() => void copyOne(file.id)}>
                  Copy
                </button>
                <button
                  className="ghost-btn"
                  disabled={busy}
                  onClick={() => {
                    setModal({ kind: "rename", targetType: "file", id: file.id, initial: file.name });
                    setModalText(file.name);
                  }}
                >
                  Rename
                </button>
              </td>
            </tr>
          ))}

          {folders.length === 0 && files.length === 0 && (
            <tr>
              <td colSpan={6} className="empty-cell">
                Empty folder — upload files or create a folder. You can also drag files
                from your computer onto this page.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {folders.length + files.length > 0 && (
        <div className="table-footer">{total} file(s) · {folders.length} folder(s) here</div>
      )}

      {pageDragOver && <div className="drop-overlay">Drop files to upload here</div>}

      {modal.kind === "create" && (
        <Modal
          title="New folder"
          onClose={() => setModal({ kind: "none" })}
          footer={
            <button
              className="primary-btn"
              disabled={busy || modalText.trim() === ""}
              onClick={() => void confirmCreate(modalText.trim())}
            >
              Create
            </button>
          }
        >
          <label className="modal-field">
            Folder name
            <input
              autoFocus
              value={modalText}
              onChange={(e) => setModalText(e.target.value)}
              placeholder="e.g. Projects"
              onKeyDown={(e) => {
                if (e.key === "Enter" && modalText.trim()) void confirmCreate(modalText.trim());
              }}
            />
          </label>
        </Modal>
      )}

      {modal.kind === "rename" && (
        <Modal
          title={`Rename ${modal.targetType}`}
          onClose={() => setModal({ kind: "none" })}
          footer={
            <button
              className="primary-btn"
              disabled={busy || modalText.trim() === ""}
              onClick={() => void confirmRename(modal, modalText.trim())}
            >
              Rename
            </button>
          }
        >
          <label className="modal-field">
            Name
            <input
              autoFocus
              value={modalText}
              onChange={(e) => setModalText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && modalText.trim()) void confirmRename(modal, modalText.trim());
              }}
            />
          </label>
        </Modal>
      )}

      {modal.kind === "move" && (
        <Modal title="Move to…" onClose={() => setModal({ kind: "none" })}>
          <FolderPicker
            excludeId={selectedFolders.size === 1 && selectedFiles.size === 0 ? [...selectedFolders][0] : null}
            onPick={(target) => {
              void moveSelectionTo(target, {
                files: [...selectedFiles],
                folders: [...selectedFolders],
              });
            }}
          />
        </Modal>
      )}
    </div>
  );
}
