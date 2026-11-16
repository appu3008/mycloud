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
import { Eyebrow, PageTagline } from "../components/Layout";
import { Modal } from "../components/Modal";
import { FolderPicker } from "../components/FolderPicker";
import iconTray from "../assets/figma/icon-tray.svg";
import iconChevronUp from "../assets/figma/icon-chevron-up.svg";
import iconFolderBig from "../assets/figma/icon-folder-big.svg";
import iconPlus from "../assets/figma/icon-plus.svg";
import iconUploadDark from "../assets/figma/icon-upload-dark.svg";
import iconUpload from "../assets/figma/icon-upload.svg";
import iconUploadMd from "../assets/figma/icon-upload-md.svg";
import "../styles/files.css";

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

type SortKey = "name" | "size" | "mtime";

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
  const [searchParams, setSearchParams] = useSearchParams();
  const folderId = searchParams.get("folder");

  const [folders, setFolders] = useState<CloudFolder[]>([]);
  const [files, setFiles] = useState<CloudFile[]>([]);
  const [breadcrumb, setBreadcrumb] = useState<CloudFolder[]>([]);
  const [total, setTotal] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortAsc, setSortAsc] = useState(true);
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
      const order = sortAsc ? "asc" : "desc";
      const listQuery = `/v1/files?page=0&page_size=100&sort=${sortKey}&order=${order}${folderId ? `&folder_id=${folderId}` : ""}`;
      const requests: [Promise<{ items: CloudFolder[] }>, Promise<FileListPayload>, Promise<FolderDetail | null>] = [
        listFolders(folderId),
        api<FileListPayload>(listQuery),
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
  }, [folderId, sortKey, sortAsc]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // --- uploads (target the open folder, as the design promises) ---------------

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

  // --- mutations ----------------------------------------------------------------

  async function runMutation(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await reload();
      setModal({ kind: "none" });
      setModalText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setBusy(false);
    }
  }

  const selectionCount = selectedFiles.size + selectedFolders.size;

  function moveSelectionTo(targetId: string | null, payload: DragSelection) {
    const folderIds = payload.folders.filter((id) => id !== targetId);
    return runMutation(async () => {
      if (payload.files.length > 0) await batchFiles("move", payload.files, targetId);
      if (folderIds.length > 0) await batchFolders("move", folderIds, targetId);
    });
  }

  const deleteSelection = () =>
    runMutation(async () => {
      if (selectedFiles.size > 0) await batchFiles("delete", [...selectedFiles]);
      if (selectedFolders.size > 0) await batchFolders("delete", [...selectedFolders]);
    });

  const copyOne = (fileId: string) => runMutation(() => batchFiles("copy", [fileId], folderId));

  const confirmCreate = (name: string) => runMutation(() => createFolderApi(name, folderId));

  const confirmRename = (state: ModalState & { kind: "rename" }, name: string) =>
    runMutation(() =>
      state.targetType === "file" ? renameFile(state.id, name) : renameFolder(state.id, name),
    );

  const deleteOneFolder = (id: string) => runMutation(() => deleteFolderApi(id));

  // --- selection, sorting & drag --------------------------------------------------

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
    const allSelected =
      files.length + folders.length > 0 && selectionCount === files.length + folders.length;
    if (allSelected) {
      setSelectedFiles(new Set());
      setSelectedFolders(new Set());
    } else {
      setSelectedFiles(new Set(files.map((f) => f.id)));
      setSelectedFolders(new Set(folders.map((f) => f.id)));
    }
  }

  function sortBy(key: SortKey) {
    if (key === sortKey) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  function dragSelectionFor(kind: "file" | "folder", id: string): DragSelection {
    if (kind === "file" && selectedFiles.has(id)) {
      return { files: [...selectedFiles], folders: [...selectedFolders] };
    }
    if (kind === "folder" && selectedFolders.has(id) && selectionCount > 0) {
      return { files: [...selectedFiles], folders: [...selectedFolders] };
    }
    return kind === "file" ? { files: [id], folders: [] } : { files: [], folders: [id] };
  }

  function navigateTo(target: string | null) {
    setSearchParams(target ? { folder: target } : {});
  }

  const hasInternalPayload = (event: React.DragEvent) =>
    Array.from(event.dataTransfer.types).includes(DRAG_TYPE);

  const isEmpty = folders.length === 0 && files.length === 0;

  const activeUploads = uploads.filter((row) => row.state === "uploading");

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
      <Eyebrow icon={iconTray}>My Files</Eyebrow>
      <div className="page-title-row">
        <h1>My Files</h1>
        <div className="page-actions">
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
            className="ghost-btn with-icon"
            disabled={busy}
            onClick={() => setModal({ kind: "create" })}
          >
            <img src={iconPlus} alt="" width={18} height={18} />
            <span className="mono-label">New folder</span>
          </button>
          <button
            className="primary-btn"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            {busy ? (
              <span className="mono-label">Working…</span>
            ) : (
              <>
                <img src={iconUploadDark} alt="" width={18} height={18} />
                <span className="mono-label">Upload files</span>
              </>
            )}
          </button>
        </div>
      </div>
      <p className="page-sub">Everything you keep, right where you left it.</p>

      {error && <div className="page-error">{error}</div>}

      {selectionCount > 0 && (
        <div className="selection-toolbar">
          <span className="mono-label">{selectionCount} selected</span>
          <button
            className="ghost-btn mono-label"
            disabled={busy}
            onClick={() => setModal({ kind: "move" })}
          >
            Move to…
          </button>
          <button className="ghost-btn mono-label danger" disabled={busy} onClick={() => void deleteSelection()}>
            Delete
          </button>
          <button
            className="ghost-btn mono-label"
            onClick={() => {
              setSelectedFiles(new Set());
              setSelectedFolders(new Set());
            }}
          >
            Clear
          </button>
        </div>
      )}

      <section className="card files-panel">
        <div className="files-panel-head">
          <span className="all-files">
            <span className="mono-label">All files</span>
            <span className="chip">{files.length}</span>
          </span>
          <span className="mono-label hint">Folders appear first</span>
        </div>

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
              <th>
                <button className="sort-btn mono-label" onClick={() => sortBy("name")}>
                  Name
                  {sortKey === "name" && (
                    <img
                      src={iconChevronUp}
                      alt=""
                      width={16}
                      height={16}
                      className={sortAsc ? "asc" : "desc"}
                    />
                  )}
                </button>
              </th>
              <th>
                <button className="sort-btn mono-label" onClick={() => sortBy("size")}>
                  Size
                  {sortKey === "size" && (
                    <img
                      src={iconChevronUp}
                      alt=""
                      width={16}
                      height={16}
                      className={sortAsc ? "asc" : "desc"}
                    />
                  )}
                </button>
              </th>
              <th><span className="mono-label">Type</span></th>
              <th>
                <button className="sort-btn mono-label" onClick={() => sortBy("mtime")}>
                  Modified
                  {sortKey === "mtime" && (
                    <img
                      src={iconChevronUp}
                      alt=""
                      width={16}
                      height={16}
                      className={sortAsc ? "asc" : "desc"}
                    />
                  )}
                </button>
              </th>
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
                  try {
                    const payload = JSON.parse(e.dataTransfer.getData(DRAG_TYPE)) as DragSelection;
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
                <td draggable onDragStart={(e) => e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(dragSelectionFor("folder", folder.id)))}>
                  <button className="row-link" onClick={() => navigateTo(folder.id)}>
                    {folder.name}
                  </button>
                </td>
                <td className="dim-cell">—</td>
                <td><span className="chip">folder</span></td>
                <td className="dim-cell">{new Date(folder.updated_at).toLocaleString()}</td>
                <td className="row-actions">
                  <button
                    className="ghost-btn mono-label"
                    disabled={busy}
                    onClick={() => {
                      setModal({ kind: "rename", targetType: "folder", id: folder.id, initial: folder.name });
                      setModalText(folder.name);
                    }}
                  >
                    Rename
                  </button>
                  <button className="ghost-btn mono-label danger" disabled={busy} onClick={() => void deleteOneFolder(folder.id)}>
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
                onDragStart={(e) => e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(dragSelectionFor("file", file.id)))}
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
                <td className="dim-cell">{humanSize(file.size_bytes)}</td>
                <td><span className="chip">{file.extension || file.mime_type}</span></td>
                <td className="dim-cell">{new Date(file.mtime).toLocaleString()}</td>
                <td className="row-actions">
                  <button className="ghost-btn mono-label" onClick={() => downloadContent(file.id, file.name)}>
                    Download
                  </button>
                  <button className="ghost-btn mono-label" disabled={busy} onClick={() => void copyOne(file.id)}>
                    Copy
                  </button>
                  <button
                    className="ghost-btn mono-label"
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

            {isEmpty && (
              <tr>
                <td colSpan={6} className="empty-state-cell">
                  <div className="empty-state">
                    <span className="empty-folder-tile">
                      <img src={iconFolderBig} alt="" width={46} height={46} />
                    </span>
                    <p className="empty-title">Make yourself at home.</p>
                    <p className="empty-sub">
                      This folder is empty. Upload your first file,
                      <br />
                      or create a folder to start organizing.
                    </p>
                    <button className="primary-btn" onClick={() => fileInputRef.current?.click()}>
                      <img src={iconUpload} alt="" width={23} height={23} />
                      <span className="mono-label">Upload your files</span>
                    </button>
                    <p className="empty-hint">You can also drag files anywhere onto this page.</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div className="files-panel-foot">
          <span className="mono-label">{total} item{total === 1 ? "" : "s"}</span>
          <span className="path-crumbs mono-label">
            <button className="crumb" onClick={() => navigateTo(null)}>My Files</button>
            {breadcrumb.map((crumb) => (
              <span key={crumb.id}>
                {" / "}
                <button className="crumb" onClick={() => navigateTo(crumb.id)}>{crumb.name}</button>
              </span>
            ))}
            {" /"}
          </span>
        </div>
      </section>

      <section className="card uploads-strip">
        <div className="uploads-head">
          <img src={iconTray} alt="" width={17} height={17} />
          <div>
            <p className="mono-label strip-label">Uploads</p>
            {activeUploads.length === 0 ? (
              <p className="strip-sub">No uploads in progress</p>
            ) : (
              <p className="strip-sub">
                {activeUploads.length} upload{activeUploads.length === 1 ? "" : "s"} in progress
              </p>
            )}
          </div>
          <span className="strip-hint mono-label">Uploads go to the folder you have open.</span>
        </div>
        {uploads.length > 0 && (
          <div className="upload-rows">
            {uploads.map((row) => (
              <div key={row.id} className={`upload-row ${row.state}`}>
                <img src={iconUploadMd} alt="" width={20} height={20} />
                <span className="upload-name">{row.name}</span>
                <span className="upload-meta mono-label">
                  {humanSize(row.sizeBytes)}
                  {row.totalChunks > 0 ? ` · chunk ${row.done}/${row.totalChunks}` : ""}
                </span>
                <progress
                  max={row.totalChunks || 1}
                  value={row.state === "completed" ? row.totalChunks || 1 : row.done}
                />
                <span className="upload-state mono-label">
                  {row.state === "uploading" ? "Uploading" : row.state === "completed" ? "Done" : "Failed"}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

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

      <PageTagline>Your space. Your pace.</PageTagline>
    </div>
  );
}
