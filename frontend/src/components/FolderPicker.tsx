import { useEffect, useState } from "react";
import { folderTree } from "../services/api";
import type { FolderTreeNode } from "../services/api";

/**
 * Folder tree browser for "Move to…" targets. Root is always offered as the
 * top destination. Excludes a subtree (can't move a folder into itself).
 */
export function FolderPicker({
  excludeId,
  onPick,
}: {
  excludeId: string | null;
  onPick: (folderId: string | null) => void;
}) {
  const [tree, setTree] = useState<FolderTreeNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    folderTree()
      .then((nodes) => {
        if (!cancelled) setTree(nodes);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load folders");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div className="form-error">{error}</div>;
  if (tree === null) return <div className="empty-cell">Loading folders…</div>;

  const filtered = excludeId
    ? tree.filter((node) => stripSubtree(node, excludeId) !== true)
    : tree;

  return (
    <div className="folder-picker">
      <button className="picker-row" onClick={() => onPick(null)}>
        🏠 My Files <span className="picker-hint">(root)</span>
      </button>
      {filtered.map((node) => (
        <PickerNode key={node.id} node={node} depth={1} onPick={onPick} />
      ))}
    </div>
  );
}

/** True if `node` subtree contains `id`; mutates `node.children` when found. */
function stripSubtree(node: FolderTreeNode, id: string): boolean {
  if (node.id === id) return true;
  node.children = node.children.filter((child) => !stripSubtree(child, id));
  return false;
}

function PickerNode({
  node,
  depth,
  onPick,
}: {
  node: FolderTreeNode;
  depth: number;
  onPick: (folderId: string | null) => void;
}) {
  return (
    <>
      <button
        className="picker-row"
        style={{ paddingLeft: `${8 + depth * 18}px` }}
        onClick={() => onPick(node.id)}
      >
        📁 {node.name}
      </button>
      {node.children.map((child) => (
        <PickerNode key={child.id} node={child} depth={depth + 1} onPick={onPick} />
      ))}
    </>
  );
}
