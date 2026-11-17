//! Recycle Bin page: lists top-level deleted items, batch/single restore,
//! permanent delete ("delete forever") and "empty bin" — all confirm-gated.

use std::collections::HashSet;

use yew::prelude::*;

use crate::api::{self, TrashFile, TrashFolder};
use crate::layout::{eyebrow, page_tagline};
use crate::modal::Modal;
use crate::util::{format_date, human_size};
use crate::ICON_FOLDER_BIG;

const RECYCLE_ICON: &str = "/assets/figma/nav-recycle.svg";

#[derive(Debug, Clone, PartialEq)]
enum Confirm {
    None,
    /// Permanent delete: message shown, exact ids to purge.
    Purge {
        message: String,
        file_ids: Vec<String>,
        folder_ids: Vec<String>,
    },
}

fn toggle_set(set: &HashSet<String>, id: &str) -> HashSet<String> {
    let mut next = set.clone();
    if !next.remove(id) {
        next.insert(id.to_string());
    }
    next
}

#[function_component(TrashPage)]
pub fn trash_page() -> Html {
    let files = use_state(Vec::<TrashFile>::new);
    let folders = use_state(Vec::<TrashFolder>::new);
    let total_bytes = use_state(|| 0u64);
    let busy = use_state(|| false);
    let error = use_state(String::new);
    let selected_files = use_state(HashSet::<String>::new);
    let selected_folders = use_state(HashSet::<String>::new);
    let confirm = use_state(|| Confirm::None);

    // --- listing -----------------------------------------------------------

    let reload = {
        let files = files.clone();
        let folders = folders.clone();
        let total_bytes = total_bytes.clone();
        let error = error.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        move || {
            let files = files.clone();
            let folders = folders.clone();
            let total_bytes = total_bytes.clone();
            let error = error.clone();
            let selected_files = selected_files.clone();
            let selected_folders = selected_folders.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::trash().await {
                    Ok(payload) => {
                        files.set(payload.files);
                        folders.set(payload.folders);
                        total_bytes.set(payload.total_bytes);
                        selected_files.set(HashSet::new());
                        selected_folders.set(HashSet::new());
                    }
                    Err(err) => error.set(err.to_string()),
                }
            });
        }
    };

    {
        let reload = reload.clone();
        use_effect_with((), move |_| {
            reload();
            || {}
        });
    }

    // --- mutations -----------------------------------------------------------

    let selection_count = selected_files.len() + selected_folders.len();

    let restore_items = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        move |file_ids: Vec<String>, folder_ids: Vec<String>| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let selected_files = selected_files.clone();
            let selected_folders = selected_folders.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                match api::restore_from_trash(&file_ids, &folder_ids).await {
                    Ok(_) => {
                        selected_files.set(HashSet::new());
                        selected_folders.set(HashSet::new());
                    }
                    Err(err) => error.set(err.to_string()),
                }
                reload();
                busy.set(false);
            });
        }
    };

    let purge_items = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let confirm = confirm.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        move |file_ids: Vec<String>, folder_ids: Vec<String>| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let confirm = confirm.clone();
            let selected_files = selected_files.clone();
            let selected_folders = selected_folders.clone();
            busy.set(true);
            error.set(String::new());
            confirm.set(Confirm::None);
            wasm_bindgen_futures::spawn_local(async move {
                match api::purge_trash(&file_ids, &folder_ids).await {
                    Ok(_) => {
                        selected_files.set(HashSet::new());
                        selected_folders.set(HashSet::new());
                    }
                    Err(err) => error.set(err.to_string()),
                }
                reload();
                busy.set(false);
            });
        }
    };

    let ask_purge = {
        let confirm = confirm.clone();
        move |file_ids: Vec<String>, folder_ids: Vec<String>, message: String| {
            confirm.set(Confirm::Purge { message, file_ids, folder_ids });
        }
    };

    let close_confirm = {
        let confirm = confirm.clone();
        Callback::from(move |_| confirm.set(Confirm::None))
    };

    let confirm_purge_now = {
        let purge_items = purge_items.clone();
        let confirm = confirm.clone();
        Callback::from(move |_| {
            if let Confirm::Purge { file_ids, folder_ids, .. } = (*confirm).clone() {
                purge_items(file_ids, folder_ids);
            }
        })
    };

    // --- view ----------------------------------------------------------------

    let is_empty = files.is_empty() && folders.is_empty();
    let all_selected = !is_empty && selection_count == files.len() + folders.len();

    let file_rows: Html = files.iter().map(|file| {
        let selected = selected_files.contains(&file.id);
        let row_class = if selected { "file-row selected" } else { "file-row" };
        let restore = {
            let restore_items = restore_items.clone();
            let id = file.id.clone();
            Callback::from(move |_| restore_items(vec![id.clone()], Vec::new()))
        };
        let remove = {
            let ask_purge = ask_purge.clone();
            let id = file.id.clone();
            let name = file.name.clone();
            Callback::from(move |_| {
                ask_purge(
                    vec![id.clone()],
                    Vec::new(),
                    format!("Delete \u{201C}{}\u{201D} permanently? This cannot be undone.", name),
                )
            })
        };
        let toggle = {
            let selected_files = selected_files.clone();
            let id = file.id.clone();
            Callback::from(move |_| selected_files.set(toggle_set(&selected_files, &id)))
        };
        html! {
            <tr key={file.id.clone()} class={row_class}>
                <td class="col-check">
                    <input type="checkbox" aria-label={format!("Select {}", file.name)}
                           checked={selected} onchange={toggle} />
                </td>
                <td>{file.name.clone()}</td>
                <td><span class="chip">{if file.extension.is_empty() { file.mime_type.clone() } else { file.extension.clone() }}</span></td>
                <td class="dim-cell">{human_size(file.size_bytes)}</td>
                <td class="dim-cell">{format_date(&file.deleted_at, false)}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={restore}>{"Restore"}</button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={remove}>{"Delete forever"}</button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let folder_rows: Html = folders.iter().map(|folder| {
        let selected = selected_folders.contains(&folder.id);
        let row_class = if selected { "file-row selected" } else { "file-row" };
        let restore = {
            let restore_items = restore_items.clone();
            let id = folder.id.clone();
            Callback::from(move |_| restore_items(Vec::new(), vec![id.clone()]))
        };
        let remove = {
            let ask_purge = ask_purge.clone();
            let id = folder.id.clone();
            let name = folder.name.clone();
            Callback::from(move |_| {
                ask_purge(
                    Vec::new(),
                    vec![id.clone()],
                    format!("Delete folder \u{201C}{}\u{201D} and everything inside it permanently? This cannot be undone.", name),
                )
            })
        };
        let toggle = {
            let selected_folders = selected_folders.clone();
            let id = folder.id.clone();
            Callback::from(move |_| selected_folders.set(toggle_set(&selected_folders, &id)))
        };
        html! {
            <tr key={folder.id.clone()} class={row_class}>
                <td class="col-check">
                    <input type="checkbox" aria-label={format!("Select {}", folder.name)}
                           checked={selected} onchange={toggle} />
                </td>
                <td><span class="folder-name-cell">{folder.name.clone()}</span></td>
                <td><span class="chip">{"folder"}</span></td>
                <td class="dim-cell">{"\u{2014}"}</td>
                <td class="dim-cell">{format_date(&folder.deleted_at, false)}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={restore}>{"Restore"}</button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={remove}>{"Delete forever"}</button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let select_all_visible = {
        let files = files.clone();
        let folders = folders.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        Callback::from(move |_| {
            if all_selected {
                selected_files.set(HashSet::new());
                selected_folders.set(HashSet::new());
            } else {
                selected_files.set(files.iter().map(|f| f.id.clone()).collect());
                selected_folders.set(folders.iter().map(|f| f.id.clone()).collect());
            }
        })
    };

    let empty_bin = {
        let ask_purge = ask_purge.clone();
        Callback::from(move |_| {
            ask_purge(
                Vec::new(),
                Vec::new(),
                "Empty the entire recycle bin? Everything in it will be deleted permanently. This cannot be undone.".to_string(),
            )
        })
    };

    let purge_selection = {
        let ask_purge = ask_purge.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        Callback::from(move |_| {
            let files: Vec<String> = selected_files.iter().cloned().collect();
            let folders: Vec<String> = selected_folders.iter().cloned().collect();
            ask_purge(
                files,
                folders,
                format!("Delete {} selected item{} permanently? This cannot be undone.",
                    selection_count, if selection_count == 1 { "" } else { "s" }),
            )
        })
    };

    let confirm_modal = match (*confirm).clone() {
        Confirm::None => html! {},
        Confirm::Purge { message, .. } => html! {
            <Modal title="Delete forever" on_close={close_confirm.clone()}
                   footer={html! {
                       <>
                           <button class="ghost-btn mono-label"
                                   onclick={close_confirm.clone().reform(|_| ())}>{"Cancel"}</button>
                           <button class="primary-btn danger" disabled={*busy}
                                   onclick={confirm_purge_now.clone()}>
                               {"Delete forever"}
                           </button>
                       </>
                   }}>
                <p class="modal-note">{message}</p>
            </Modal>
        },
    };

    html! {
        <div class="files-page">
            {eyebrow(Some(RECYCLE_ICON), "Recycle Bin")}
            <div class="page-title-row">
                <h1>{"Recycle Bin"}</h1>
                <div class="page-actions">
                    {(!is_empty).then(|| html! {
                        <button class="ghost-btn mono-label danger" disabled={*busy} onclick={empty_bin}>
                            {"Empty bin"}
                        </button>
                    })}
                </div>
            </div>
            <p class="page-sub">{"Deleted items wait here. Restore them, or let them go."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}

            {(selection_count > 0).then(|| html! {
                <div class="selection-toolbar">
                    <span class="mono-label">{format!("{selection_count} selected")}</span>
                    <button class="ghost-btn mono-label" disabled={*busy}
                            onclick={Callback::from({
                                let restore_items = restore_items.clone();
                                let selected_files = selected_files.clone();
                                let selected_folders = selected_folders.clone();
                                move |_| {
                                    restore_items(
                                        selected_files.iter().cloned().collect(),
                                        selected_folders.iter().cloned().collect(),
                                    )
                                }
                            })}>
                        {"Restore"}
                    </button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={purge_selection}>
                        {"Delete forever"}
                    </button>
                    <button class="ghost-btn mono-label"
                            onclick={Callback::from(move |_| {
                                selected_files.set(HashSet::new());
                                selected_folders.set(HashSet::new());
                            })}>
                        {"Clear"}
                    </button>
                </div>
            })}

            <section class="card files-panel">
                <div class="files-panel-head">
                    <span class="all-files">
                        <span class="mono-label">{"Deleted items"}</span>
                        <span class="chip">{files.len() + folders.len()}</span>
                    </span>
                    <span class="mono-label hint">{format!("Holding {} of storage", human_size(*total_bytes))}</span>
                </div>

                <table class="files-table">
                    <thead>
                        <tr>
                            <th class="col-check">
                                <input type="checkbox" aria-label="Select all" checked={all_selected}
                                       onchange={select_all_visible} />
                            </th>
                            <th><span class="mono-label">{"Name"}</span></th>
                            <th><span class="mono-label">{"Type"}</span></th>
                            <th><span class="mono-label">{"Size"}</span></th>
                            <th><span class="mono-label">{"Deleted"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {folder_rows}
                        {file_rows}

                        {is_empty.then(|| html! {
                            <tr>
                                <td colspan="6" class="empty-state-cell">
                                    <div class="empty-state">
                                        <span class="empty-folder-tile">
                                            <img src={ICON_FOLDER_BIG} alt="" width={46} height={46} />
                                        </span>
                                        <p class="empty-title">{"Nothing in the bin."}</p>
                                        <p class="empty-sub">
                                            {"Deleted files and folders land here first."}
                                            <br />
                                            {"Nothing to recover right now."}
                                        </p>
                                    </div>
                                </td>
                            </tr>
                        })}
                    </tbody>
                </table>

                <div class="files-panel-foot">
                    <span class="mono-label">
                        {format!("{} item{} \u{00B7} {} recoverable",
                            files.len() + folders.len(),
                            if files.len() + folders.len() == 1 { "" } else { "s" },
                            human_size(*total_bytes))}
                    </span>
                    <span class="mono-label hint">{"Items inside a deleted folder are restored with it."}</span>
                </div>
            </section>

            {confirm_modal}

            {page_tagline("Nothing is gone until you say so.")}
        </div>
    }
}
