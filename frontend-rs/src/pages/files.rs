//! My Files page (Figma node 1:636): folder navigation, resumable uploads,
//! multi-select with batch operations, drag-and-drop, sorting, and the
//! folder/rename modals.

use std::collections::HashSet;

use serde::{Deserialize, Serialize};
use yew::prelude::*;
use yew_router::prelude::*;

use crate::api::{self, CloudFile, CloudFolder, FileBatchAction, FolderBatchAction};
use crate::folder_picker::FolderPicker;
use crate::layout::{eyebrow, page_tagline};
use crate::modal::Modal;
use crate::Route;
use crate::{ICON_PLUS, ICON_TRAY, ICON_UPLOAD, ICON_UPLOAD_DARK, ICON_UPLOAD_MD};
use crate::ICON_CHEVRON_UP;
use crate::ICON_FOLDER_BIG;
use crate::util::{format_date, human_size};

const DRAG_TYPE: &str = "application/x-mycloud-items";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SortKey {
    Name,
    Size,
    Mtime,
}

impl SortKey {
    fn as_str(self) -> &'static str {
        match self {
            SortKey::Name => "name",
            SortKey::Size => "size",
            SortKey::Mtime => "mtime",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
enum UploadState {
    Uploading,
    Completed,
    Failed,
}

#[derive(Debug, Clone, PartialEq)]
struct UploadRow {
    id: String,
    name: String,
    size_bytes: u64,
    done: u64,
    total_chunks: u64,
    state: UploadState,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
struct DragSelection {
    #[serde(default)]
    files: Vec<String>,
    #[serde(default)]
    folders: Vec<String>,
}

#[derive(Debug, Clone, PartialEq)]
enum ModalState {
    None,
    Create,
    Move,
    Rename { target_is_file: bool, id: String },
    Share { target_is_file: bool, id: String, name: String },
    History { file_id: String, name: String },
}

fn drag_types(event: &DragEvent) -> Vec<String> {
    event
        .data_transfer()
        .map(|dt| {
            let types = dt.types();
            (0..types.length())
                .filter_map(|i| types.get(i).as_string())
                .collect()
        })
        .unwrap_or_default()
}

fn picked_files(list: Option<web_sys::FileList>) -> Vec<web_sys::File> {
    list.map(|files| (0..files.length()).filter_map(|i| files.item(i)).collect())
        .unwrap_or_default()
}

fn percent_decode(value: &str) -> String {
    if let Ok(decoded) = js_sys::decode_uri_component(value) {
        decoded.as_string().unwrap_or_else(|| value.to_string())
    } else {
        value.to_string()
    }
}

fn patch_row(uploads: &UseStateHandle<Vec<UploadRow>>, row_id: &str, patch: impl Fn(&mut UploadRow)) {
    uploads.set(
        (*uploads)
            .iter()
            .map(|row| {
                let mut row = row.clone();
                if row.id == row_id {
                    patch(&mut row);
                }
                row
            })
            .collect(),
    );
}

fn toggle_set(set: &HashSet<String>, id: &str) -> HashSet<String> {
    let mut next = set.clone();
    if !next.remove(id) {
        next.insert(id.to_string());
    }
    next
}

#[allow(clippy::too_many_arguments)]
fn drag_selection_for(
    selected_files: &HashSet<String>,
    selected_folders: &HashSet<String>,
    selection_count: usize,
    kind: &str,
    id: &str,
) -> String {
    if (kind == "file" && selected_files.contains(id))
        || (kind == "folder" && selected_folders.contains(id) && selection_count > 0)
    {
        return serde_json::to_string(&DragSelection {
            files: selected_files.iter().cloned().collect(),
            folders: selected_folders.iter().cloned().collect(),
        })
        .unwrap_or_default();
    }
    let payload = if kind == "file" {
        DragSelection {
            files: vec![id.to_string()],
            folders: Vec::new(),
        }
    } else {
        DragSelection {
            files: Vec::new(),
            folders: vec![id.to_string()],
        }
    };
    serde_json::to_string(&payload).unwrap_or_default()
}

#[function_component(FilesPage)]
pub fn files_page() -> Html {
    // ?folder=<id> query param (parsed manually; matches the React app's
    // useSearchParams behaviour for this single parameter)
    let folder_id: Option<String> = use_location().and_then(|location| {
        location
            .query_str()
            .strip_prefix('?')
            .unwrap_or(location.query_str())
            .split('&')
            .find_map(|pair| {
                let (key, value) = pair.split_once('=')?;
                if key == "folder" {
                    Some(
                        percent_decode(value),
                    )
                } else {
                    None
                }
            })
    });

    let folders = use_state(Vec::<CloudFolder>::new);
    let files = use_state(Vec::<CloudFile>::new);
    let breadcrumb = use_state(Vec::<CloudFolder>::new);
    let total = use_state(|| 0i64);
    let sort_key = use_state(|| SortKey::Name);
    let sort_asc = use_state(|| true);
    let uploads = use_state(Vec::<UploadRow>::new);
    let busy = use_state(|| false);
    let error = use_state(String::new);
    let selected_files = use_state(HashSet::<String>::new);
    let selected_folders = use_state(HashSet::<String>::new);
    let modal = use_state(|| ModalState::None);
    let modal_text = use_state(String::new);
    let drag_over_folder = use_state(|| None::<String>);
    let page_drag_over = use_state(|| false);
    let file_input_ref = use_node_ref();
    let versions = use_state(Vec::<api::VersionItem>::new);
    let versions_error = use_state(String::new);

    // --- listing -----------------------------------------------------------

    let reload = {
        let folder_id = folder_id.clone();
        let sort_key = *sort_key;
        let sort_asc = *sort_asc;
        let folders = folders.clone();
        let files = files.clone();
        let breadcrumb = breadcrumb.clone();
        let total = total.clone();
        let error = error.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        move || {
            let folder_id = folder_id.clone();
            let folders = folders.clone();
            let files = files.clone();
            let breadcrumb = breadcrumb.clone();
            let total = total.clone();
            let error = error.clone();
            let selected_files = selected_files.clone();
            let selected_folders = selected_folders.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                let folder_result = api::list_folders(folder_id.as_deref()).await;
                let file_result = api::list_files(sort_key.as_str(), sort_asc, folder_id.as_deref()).await;
                let detail_result = match &folder_id {
                    Some(id) => api::folder_detail(id).await.map(Some),
                    None => Ok(None),
                };
                match (folder_result, file_result, detail_result) {
                    (Ok(folder_payload), Ok(file_payload), Ok(detail)) => {
                        folders.set(folder_payload.items);
                        files.set(file_payload.items);
                        total.set(file_payload.total);
                        if let Some(detail) = detail {
                            breadcrumb.set(detail.breadcrumb);
                        } else {
                            breadcrumb.set(Vec::new());
                        }
                        selected_files.set(HashSet::new());
                        selected_folders.set(HashSet::new());
                    }
                    (Err(err), _, _) | (_, Err(err), _) | (_, _, Err(err)) => error.set(err.to_string()),
                }
            });
        }
    };

    {
        let reload = reload.clone();
        let deps = (folder_id.clone(), *sort_key, *sort_asc);
        use_effect_with(deps, move |_| {
            reload();
            || {}
        });
    }

    // --- uploads (target the open folder, as the design promises) -----------

    let handle_pick = {
        let busy = busy.clone();
        let error = error.clone();
        let uploads = uploads.clone();
        let reload = reload.clone();
        let folder_id = folder_id.clone();
        move |picked: Vec<web_sys::File>| {
            if picked.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let uploads = uploads.clone();
            let reload = reload.clone();
            let folder_id = folder_id.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                for file in picked {
                    let row_id = format!("{}-{}", file.name(), file.size() as u64);
                    uploads.set({
                        let mut current = (*uploads).clone();
                        current.push(UploadRow {
                            id: row_id.clone(),
                            name: file.name(),
                            size_bytes: file.size() as u64,
                            done: 0,
                            total_chunks: 0,
                            state: UploadState::Uploading,
                        });
                        current
                    });
                    let reserved_patch = uploads.clone();
                    let chunk_patch = uploads.clone();
                    let finished_patch = uploads.clone();
                    let failed_patch = uploads.clone();
                    let reserved_row = row_id.clone();
                    let chunk_row = row_id.clone();
                    let hooks = api::UploadHooks {
                        on_reserved: Some(Box::new(move |total_chunks| {
                            patch_row(&reserved_patch, &reserved_row, |row| row.total_chunks = total_chunks);
                        })),
                        on_chunk_done: Some(Box::new(move |done, _total| {
                            patch_row(&chunk_patch, &chunk_row, |row| row.done = done);
                        })),
                    };
                    match api::upload_file_resumable(&file, folder_id.as_deref(), hooks, None).await {
                        Ok(_) => patch_row(&finished_patch, &row_id, |row| {
                            row.state = UploadState::Completed;
                            row.done = row.total_chunks;
                        }),
                        Err(_) => patch_row(&failed_patch, &row_id, |row| row.state = UploadState::Failed),
                    }
                }
                reload();
                busy.set(false);
            });
        }
    };

    // --- mutations ------------------------------------------------------------

    let selection_count = selected_files.len() + selected_folders.len();

    let move_selection_to = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let modal = modal.clone();
        Callback::from(move |(target_id, payload): (Option<String>, DragSelection)| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let modal = modal.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                let folder_ids: Vec<String> = payload
                    .folders
                    .iter()
                    .filter(|id| Some(*id) != target_id.as_ref())
                    .cloned()
                    .collect();
                let mut failed = String::new();
                if !payload.files.is_empty() {
                    if let Err(err) = api::batch_files(FileBatchAction::Move, &payload.files, target_id.as_deref()).await {
                        failed = err.to_string();
                    }
                }
                if failed.is_empty() && !folder_ids.is_empty() {
                    if let Err(err) = api::batch_folders(FolderBatchAction::Move, &folder_ids, target_id.as_deref()).await {
                        failed = err.to_string();
                    }
                }
                if failed.is_empty() {
                    modal.set(ModalState::None);
                } else {
                    error.set(failed);
                }
                reload();
                busy.set(false);
            });
        })
    };

    let delete_selection = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        Callback::from(move |_| {
            let file_ids: Vec<String> = selected_files.iter().cloned().collect();
            let folder_ids: Vec<String> = selected_folders.iter().cloned().collect();
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                let mut failed = String::new();
                if !file_ids.is_empty() {
                    if let Err(err) = api::batch_files(FileBatchAction::Delete, &file_ids, None).await {
                        failed = err.to_string();
                    }
                }
                if failed.is_empty() && !folder_ids.is_empty() {
                    if let Err(err) = api::batch_folders(FolderBatchAction::Delete, &folder_ids, None).await {
                        failed = err.to_string();
                    }
                }
                if !failed.is_empty() {
                    error.set(failed);
                }
                reload();
                busy.set(false);
            });
        })
    };

    let copy_one = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let folder_id = folder_id.clone();
        Callback::from(move |file_id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let folder_id = folder_id.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::batch_files(FileBatchAction::Copy, &[file_id], folder_id.as_deref()).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let confirm_create = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let modal = modal.clone();
        let modal_text = modal_text.clone();
        let folder_id = folder_id.clone();
        Callback::from(move |_| {
            let name = modal_text.trim().to_string();
            if name.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let modal = modal.clone();
            let folder_id = folder_id.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::create_folder(&name, folder_id.as_deref()).await {
                    error.set(err.to_string());
                } else {
                    modal.set(ModalState::None);
                }
                reload();
                busy.set(false);
            });
        })
    };

    let confirm_rename = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let modal = modal.clone();
        let modal_text = modal_text.clone();
        Callback::from(move |_| {
            let name = modal_text.trim().to_string();
            let ModalState::Rename { target_is_file, id } = (*modal).clone() else {
                return;
            };
            if name.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let modal = modal.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                let result = if target_is_file {
                    api::rename_file(&id, &name).await
                } else {
                    api::rename_folder(&id, &name).await
                };
                if let Err(err) = result {
                    error.set(err.to_string());
                } else {
                    modal.set(ModalState::None);
                }
                reload();
                busy.set(false);
            });
        })
    };

    let delete_one_folder = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::delete_folder(&id).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    // --- sharing -------------------------------------------------------------

    let share_expiry = use_state(String::new);   // "", "24", "168", "720" (hours)
    let share_max = use_state(String::new);      // "", "1", "5", "25" (downloads)
    let share_password = use_state(String::new);
    let share_result = use_state(|| None::<api::ShareCreated>);

    let confirm_share = {
        let busy = busy.clone();
        let error = error.clone();
        let modal = modal.clone();
        let share_expiry = share_expiry.clone();
        let share_max = share_max.clone();
        let share_password = share_password.clone();
        let share_result = share_result.clone();
        Callback::from(move |_| {
            let ModalState::Share { target_is_file, id, .. } = (*modal).clone() else {
                return;
            };
            let kind = if target_is_file { "file" } else { "folder" };
            let expiry = (*share_expiry).parse::<u64>().ok();
            let max = (*share_max).parse::<u64>().ok();
            let password = (*share_password).trim().to_string();
            let password: Option<String> = (!password.is_empty()).then_some(password);
            let busy = busy.clone();
            let error = error.clone();
            let share_result = share_result.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                match api::create_share(kind, &id, expiry, max, password.as_deref()).await {
                    Ok(created) => share_result.set(Some(created)),
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let copy_share_link = {
        let share_result = share_result.clone();
        Callback::from(move |_| {
            if let Some(created) = (*share_result).clone() {
                if let Some(window) = web_sys::window() {
                    let url = format!(
                        "{}/share/{}",
                        window.location().origin().unwrap_or_default(),
                        created.token
                    );
                    if let Some(clipboard) = Some(window.navigator().clipboard()) {
                        let _ = clipboard.write_text(&url);
                    }
                }
            }
        })
    };

    let share_field_input = |setter: UseStateHandle<String>| -> Callback<yew::Event> {
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            setter.set(input.value());
        })
    };
    let share_password_input = {
        let share_password = share_password.clone();
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            share_password.set(input.value());
        })
    };

    // --- version history ----------------------------------------------------

    let load_versions = {
        let versions = versions.clone();
        let versions_error = versions_error.clone();
        Callback::from(move |file_id: String| {
            let versions = versions.clone();
            let versions_error = versions_error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                versions_error.set(String::new());
                match api::list_versions(&file_id).await {
                    Ok(list) => versions.set(list.items),
                    Err(err) => versions_error.set(err.to_string()),
                }
            });
        })
    };

    let restore_version = {
        let busy = busy.clone();
        let error = error.clone();
        let modal = modal.clone();
        let reload = reload.clone();
        let load_versions = load_versions.clone();
        Callback::from(move |(file_id, version_id): (String, String)| {
            let busy = busy.clone();
            let error = error.clone();
            let modal = modal.clone();
            let reload = reload.clone();
            let load_versions = load_versions.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::restore_version(&file_id, &version_id).await {
                    error.set(err.to_string());
                }
                load_versions.emit(file_id);
                reload();
                modal.set(ModalState::None);
                busy.set(false);
            });
        })
    };

    let replace_file = {
        let busy = busy.clone();
        let error = error.clone();
        let modal = modal.clone();
        let reload = reload.clone();
        let load_versions = load_versions.clone();
        Callback::from(move |(file, file_id): (web_sys::File, String)| {
            let busy = busy.clone();
            let error = error.clone();
            let modal = modal.clone();
            let reload = reload.clone();
            let load_versions = load_versions.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                let hooks = api::UploadHooks { on_reserved: None, on_chunk_done: None };
                match api::upload_file_resumable(&file, None, hooks, Some(&file_id)).await {
                    Ok(_) => {
                        load_versions.emit(file_id);
                        reload();
                        modal.set(ModalState::None);
                    }
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    // --- selection, sorting & drag ------------------------------------------

    let toggle_file = {
        let selected_files = selected_files.clone();
        Callback::from(move |id: String| {
            selected_files.set(toggle_set(&selected_files, &id));
        })
    };
    let toggle_folder = {
        let selected_folders = selected_folders.clone();
        Callback::from(move |id: String| {
            selected_folders.set(toggle_set(&selected_folders, &id));
        })
    };

    let select_all_visible = {
        let files = files.clone();
        let folders = folders.clone();
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        let selection_count = selection_count;
        Callback::from(move |_| {
            let all_selected =
                files.len() + folders.len() > 0 && selection_count == files.len() + folders.len();
            if all_selected {
                selected_files.set(HashSet::new());
                selected_folders.set(HashSet::new());
            } else {
                selected_files.set(files.iter().map(|f| f.id.clone()).collect());
                selected_folders.set(folders.iter().map(|f| f.id.clone()).collect());
            }
        })
    };

    let sort_by = {
        let sort_key = sort_key.clone();
        let sort_asc = sort_asc.clone();
        Callback::from(move |key: SortKey| {
            if key == *sort_key {
                sort_asc.set(!*sort_asc);
            } else {
                sort_key.set(key);
                sort_asc.set(true);
            }
        })
    };

    let navigate_to = {
        let navigator = use_navigator().unwrap();
        Callback::from(move |target: Option<String>| {
            if let Some(folder) = target {
                let _ = navigator.push_with_query(&Route::Files, serde_json::json!({ "folder": folder }));
            } else {
                navigator.push(&Route::Files);
            }
        })
    };

    let clear_selection = {
        let selected_files = selected_files.clone();
        let selected_folders = selected_folders.clone();
        Callback::from(move |_| {
            selected_files.set(HashSet::new());
            selected_folders.set(HashSet::new());
        })
    };

    let open_create_modal = {
        let modal = modal.clone();
        Callback::from(move |_| modal.set(ModalState::Create))
    };
    let open_move_modal = {
        let modal = modal.clone();
        Callback::from(move |_| modal.set(ModalState::Move))
    };
    let close_modal = {
        let modal = modal.clone();
        let modal_text = modal_text.clone();
        Callback::from(move |_| {
            modal.set(ModalState::None);
            modal_text.set(String::new());
        })
    };
    let modal_input = {
        let modal_text = modal_text.clone();
        Callback::from(move |event: yew::InputEvent| {
            modal_text.set(event.target_unchecked_into::<web_sys::HtmlInputElement>().value());
        })
    };
    let modal_enter_submit = |submit: Callback<MouseEvent>| -> Callback<KeyboardEvent> {
        Callback::from(move |event: KeyboardEvent| {
            if event.key() == "Enter" {
                event.prevent_default();
                if let Ok(click) = MouseEvent::new("click") {
                    submit.emit(click);
                }
            }
        })
    };

    // --- drag & drop -----------------------------------------------------------

    let page_on_drag_over = {
        let page_drag_over = page_drag_over.clone();
        Callback::from(move |event: DragEvent| {
            if drag_types(&event).iter().any(|t| t == "Files") {
                event.prevent_default();
                page_drag_over.set(true);
            }
        })
    };
    let page_on_drag_leave = {
        let page_drag_over = page_drag_over.clone();
        Callback::from(move |event: DragEvent| {
            if event.target() == event.current_target() {
                page_drag_over.set(false);
            }
        })
    };
    let page_on_drop = {
        let page_drag_over = page_drag_over.clone();
        let handle_pick = handle_pick.clone();
        Callback::from(move |event: DragEvent| {
            if drag_types(&event).iter().any(|t| t == DRAG_TYPE) {
                return;
            }
            if let Some(files) = event.data_transfer().and_then(|dt| dt.files()) {
                if files.length() > 0 {
                    event.prevent_default();
                    page_drag_over.set(false);
                    handle_pick(picked_files(Some(files)));
                }
            }
        })
    };

    let open_picker_click = {
        let file_input_ref = file_input_ref.clone();
        Callback::from(move |_| {
            if let Some(input) = file_input_ref.cast::<web_sys::HtmlInputElement>() {
                input.click();
            }
        })
    };
    let input_onchange = {
        let handle_pick = handle_pick.clone();
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            handle_pick(picked_files(input.files()));
            input.set_value("");
        })
    };

    // --- view ----------------------------------------------------------------

    let is_empty = folders.is_empty() && files.is_empty();
    let active_uploads = (*uploads)
        .iter()
        .filter(|row| row.state == UploadState::Uploading)
        .count();
    let all_selected =
        files.len() + folders.len() > 0 && selection_count == files.len() + folders.len();
    let page_class = if *page_drag_over {
        "files-page page-drag-over"
    } else {
        "files-page"
    };

    let sort_btn = |key: SortKey, label: &'static str| -> Html {
        let active = *sort_key == key;
        let class = if active {
            if *sort_asc { "asc" } else { "desc" }
        } else {
            "asc"
        };
        html! {
            <button class="sort-btn mono-label" onclick={sort_by.clone().reform(move |_| key)}>
                {label}
                {active.then(|| html! {
                    <img src={ICON_CHEVRON_UP} alt="" width={16} height={16} class={class} />
                })}
            </button>
        }
    };

    let file_rows: Html = files.iter().map(|file| {
        let selected = selected_files.contains(&file.id);
        let drag_payload = drag_selection_for(&selected_files, &selected_folders, selection_count, "file", &file.id);
        let on_drag_start = {
            let drag_payload = drag_payload.clone();
            Callback::from(move |event: DragEvent| {
                if let Some(dt) = event.data_transfer() {
                    let _ = dt.set_data(DRAG_TYPE, &drag_payload);
                }
            })
        };
        let row_class = if selected { "file-row selected" } else { "file-row" };
        let download = {
            let id = file.id.clone();
            let name = file.name.clone();
            Callback::from(move |_| api::download_content(&id, &name))
        };
        let copy = {
            let copy_one = copy_one.clone();
            let id = file.id.clone();
            Callback::from(move |_| copy_one.emit(id.clone()))
        };
        let rename = {
            let modal = modal.clone();
            let modal_text = modal_text.clone();
            let id = file.id.clone();
            let name = file.name.clone();
            Callback::from(move |_| {
                modal.set(ModalState::Rename { target_is_file: true, id: id.clone() });
                modal_text.set(name.clone());
            })
        };
        let share = {
            let modal = modal.clone();
            let share_expiry = share_expiry.clone();
            let share_max = share_max.clone();
            let share_password = share_password.clone();
            let share_result = share_result.clone();
            let id = file.id.clone();
            let name = file.name.clone();
            Callback::from(move |_| {
                share_result.set(None);
                share_expiry.set(String::new());
                share_max.set(String::new());
                share_password.set(String::new());
                modal.set(ModalState::Share {
                    target_is_file: true,
                    id: id.clone(),
                    name: name.clone(),
                });
            })
        };
        let history = {
            let modal = modal.clone();
            let load_versions = load_versions.clone();
            let id = file.id.clone();
            let name = file.name.clone();
            Callback::from(move |_| {
                load_versions.emit(id.clone());
                modal.set(ModalState::History {
                    file_id: id.clone(),
                    name: name.clone(),
                });
            })
        };
        let toggle = toggle_file.clone();
        let id = file.id.clone();
        html! {
            <tr key={file.id.clone()} class={row_class} draggable={true} ondragstart={on_drag_start}>
                <td class="col-check">
                    <input type="checkbox" aria-label={format!("Select {}", file.name)} checked={selected}
                           onchange={move |_| toggle.emit(id.clone())} />
                </td>
                <td>{file.name.clone()}</td>
                <td class="dim-cell">{human_size(file.size_bytes)}</td>
                <td><span class="chip">{if file.extension.is_empty() { file.mime_type.clone() } else { file.extension.clone() }}</span></td>
                <td class="dim-cell">{format_date(&file.mtime, false)}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" onclick={download}>{"Download"}</button>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={copy}>{"Copy"}</button>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={rename}>{"Rename"}</button>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={history}>{"History"}</button>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={share}>{"Share"}</button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let folder_rows: Html = folders.iter().map(|folder| {
        let selected = selected_folders.contains(&folder.id);
        let drop_target = drag_over_folder.as_ref() == Some(&folder.id);
        let drag_payload = drag_selection_for(&selected_files, &selected_folders, selection_count, "folder", &folder.id);
        let on_drag_start = {
            let drag_payload = drag_payload.clone();
            Callback::from(move |event: DragEvent| {
                if let Some(dt) = event.data_transfer() {
                    let _ = dt.set_data(DRAG_TYPE, &drag_payload);
                }
            })
        };
        let on_drag_over = {
            let drag_over_folder = drag_over_folder.clone();
            let folder_id = folder.id.clone();
            Callback::from(move |event: DragEvent| {
                if drag_types(&event).iter().any(|t| t == DRAG_TYPE) {
                    event.prevent_default();
                    drag_over_folder.set(Some(folder_id.clone()));
                }
            })
        };
        let on_drag_leave = {
            let drag_over_folder = drag_over_folder.clone();
            let folder_id = folder.id.clone();
            Callback::from(move |_| {
                if drag_over_folder.as_ref() == Some(&folder_id) {
                    drag_over_folder.set(None);
                }
            })
        };
        let on_drop = {
            let drag_over_folder = drag_over_folder.clone();
            let move_selection_to = move_selection_to.clone();
            let folder_id = folder.id.clone();
            Callback::from(move |event: DragEvent| {
                if !drag_types(&event).iter().any(|t| t == DRAG_TYPE) {
                    return;
                }
                event.prevent_default();
                event.stop_propagation();
                drag_over_folder.set(None);
                let payload = event
                    .data_transfer()
                    .and_then(|dt| dt.get_data(DRAG_TYPE).ok())
                    .and_then(|data| serde_json::from_str::<DragSelection>(&data).ok())
                    .unwrap_or(DragSelection { files: Vec::new(), folders: Vec::new() });
                if !payload.files.is_empty() || !payload.folders.is_empty() {
                    move_selection_to.emit((Some(folder_id.clone()), payload));
                }
            })
        };
        let navigate = {
            let navigate_to = navigate_to.clone();
            let id = folder.id.clone();
            Callback::from(move |_| navigate_to.emit(Some(id.clone())))
        };
        let rename = {
            let modal = modal.clone();
            let modal_text = modal_text.clone();
            let id = folder.id.clone();
            let name = folder.name.clone();
            Callback::from(move |_| {
                modal.set(ModalState::Rename { target_is_file: false, id: id.clone() });
                modal_text.set(name.clone());
            })
        };
        let share = {
            let modal = modal.clone();
            let share_expiry = share_expiry.clone();
            let share_max = share_max.clone();
            let share_password = share_password.clone();
            let share_result = share_result.clone();
            let id = folder.id.clone();
            let name = folder.name.clone();
            Callback::from(move |_| {
                share_result.set(None);
                share_expiry.set(String::new());
                share_max.set(String::new());
                share_password.set(String::new());
                modal.set(ModalState::Share {
                    target_is_file: false,
                    id: id.clone(),
                    name: name.clone(),
                });
            })
        };
        let delete_folder = {
            let delete_one_folder = delete_one_folder.clone();
            let id = folder.id.clone();
            Callback::from(move |_| delete_one_folder.emit(id.clone()))
        };
        let toggle = toggle_folder.clone();
        let id = folder.id.clone();
        let row_class = match (selected, drop_target) {
            (true, true) => "folder-row selected drop-target",
            (true, false) => "folder-row selected",
            (false, true) => "folder-row drop-target",
            (false, false) => "folder-row",
        };
        html! {
            <tr key={folder.id.clone()} class={row_class}
                ondragover={on_drag_over} ondragleave={on_drag_leave} ondrop={on_drop}>
                <td class="col-check">
                    <input type="checkbox" aria-label={format!("Select {}", folder.name)} checked={selected}
                           onchange={move |_| toggle.emit(id.clone())} />
                </td>
                <td draggable={true} ondragstart={on_drag_start}>
                    <button class="row-link" onclick={navigate}>{folder.name.clone()}</button>
                </td>
                <td class="dim-cell">{"\u{2014}"}</td>
                <td><span class="chip">{"folder"}</span></td>
                <td class="dim-cell">{format_date(&folder.updated_at, false)}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={rename}>{"Rename"}</button>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={share}>{"Share"}</button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={delete_folder}>{"Delete"}</button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let breadcrumbs = {
        let navigate_to = navigate_to.clone();
        html! {
            <span class="path-crumbs mono-label">
                <button class="crumb" onclick={navigate_to.reform(|_| None::<String>)}>{"My Files"}</button>
                {for breadcrumb.iter().map(|crumb| {
                    let navigate_to = navigate_to.clone();
                    let id = crumb.id.clone();
                    html! {
                        <span>
                            {" / "}
                            <button class="crumb" onclick={move |_| navigate_to.emit(Some(id.clone()))}>{crumb.name.clone()}</button>
                        </span>
                    }
                })}
                {" /"}
            </span>
        }
    };

    let upload_rows = if uploads.is_empty() {
        html! {}
    } else {
        html! {
            <div class="upload-rows">
                {for uploads.iter().map(|row| {
                    let (state_class, state_label) = match row.state {
                        UploadState::Uploading => ("uploading", "Uploading"),
                        UploadState::Completed => ("completed", "Done"),
                        UploadState::Failed => ("failed", "Failed"),
                    };
                    let meta = if row.total_chunks > 0 {
                        format!("{} \u{00B7} chunk {}/{}", human_size(row.size_bytes), row.done, row.total_chunks)
                    } else {
                        human_size(row.size_bytes)
                    };
                    let progress_value = if row.state == UploadState::Completed {
                        row.total_chunks.max(1)
                    } else {
                        row.done
                    };
                    html! {
                        <div key={row.id.clone()} class={format!("upload-row {state_class}")}>
                            <img src={ICON_UPLOAD_MD} alt="" width={20} height={20} />
                            <span class="upload-name">{row.name.clone()}</span>
                            <span class="upload-meta mono-label">{meta}</span>
                            <progress max={row.total_chunks.max(1).to_string()} value={progress_value.to_string()} />
                            <span class="upload-state mono-label">{state_label}</span>
                        </div>
                    }
                })}
            </div>
        }
    };

    let modal_view = match (*modal).clone() {
        ModalState::None => html! {},
        ModalState::Create => html! {
            <Modal title="New folder" on_close={close_modal.clone()}
                   footer={html! {
                       <button class="primary-btn" disabled={*busy || modal_text.trim().is_empty()}
                               onclick={confirm_create.clone()}>
                           {"Create"}
                       </button>
                   }}>
                <label class="modal-field">
                    {"Folder name"}
                    <input autofocus={true} value={(*modal_text).clone()}
                           oninput={modal_input.clone()}
                           placeholder="e.g. Projects"
                           onkeydown={modal_enter_submit(confirm_create.clone())} />
                </label>
            </Modal>
        },
        ModalState::Move => html! {
            <Modal title="Move to\u{2026}" on_close={close_modal.clone()}>
                <FolderPicker
                    exclude_id={if selected_folders.len() == 1 && selected_files.is_empty() {
                        selected_folders.iter().next().cloned()
                    } else {
                        None
                    }}
                    on_pick={move_selection_to.reform({
                        let selected_files = selected_files.clone();
                        let selected_folders = selected_folders.clone();
                        move |target: Option<String>| {
                            (target, DragSelection {
                                files: selected_files.iter().cloned().collect(),
                                folders: selected_folders.iter().cloned().collect(),
                            })
                        }
                    })}
                />
            </Modal>
        },
        ModalState::History { file_id, name } => {
            let restore = restore_version.clone();
            let replace = replace_file.clone();
            let file_id_for_upload = file_id.clone();
            let upload_change = Callback::from(move |event: yew::Event| {
                let input: web_sys::HtmlInputElement = event.target_unchecked_into();
                if let Some(file) = input.files().and_then(|list| list.get(0)) {
                    replace.emit((file, file_id_for_upload.clone()));
                }
            });
            html! {
                <Modal title={format!("History \u{2014} {}", name)} on_close={close_modal.clone()}>
                    <p class="modal-note">
                        {"Uploading a new version keeps the previous content here. Old versions stay downloadable."}
                    </p>
                    {(!versions_error.is_empty()).then(|| html! {
                        <div class="page-error">{(*versions_error).clone()}</div>
                    })}
                    <ul class="version-list">
                        {for versions.iter().map(|version| {
                            let restore = restore.clone();
                            let id = file_id.clone();
                            let version_id = version.id.clone();
                            let id_for_link = id.clone();
                            let do_restore = Callback::from(move |_| {
                                restore.emit((id.clone(), version_id.clone()));
                            });
                            html! {
                                <li key={version.id.clone()} class="version-row">
                                    <span class="mono-label">{format!("v{}", version.version_number)}</span>
                                    <span class="dim-cell">{human_size(version.size_bytes)}</span>
                                    <span class="dim-cell">{format_date(&version.created_at, true)}</span>
                                    <a class="ghost-btn mono-label"
                                       href={format!("/api/v1/files/{}/versions/{}/content", id_for_link, version.id)}>
                                        {"Download"}
                                    </a>
                                    <button class="ghost-btn mono-label" disabled={*busy}
                                            onclick={do_restore}>{"Restore"}</button>
                                </li>
                            }
                        })}
                        {versions.is_empty().then(|| html! {
                            <li class="version-row">
                                <span class="dim-cell">{"No older versions. Upload a replacement to create one."}</span>
                            </li>
                        })}
                    </ul>
                    <label class="upload-version-btn primary-btn">
                        <span class="mono-label">{"Upload new version"}</span>
                        <input type="file" onchange={upload_change} hidden={true} />
                    </label>
                </Modal>
            }
        },
        ModalState::Share { target_is_file, name, .. } => {
            let share_link = (*share_result).as_ref().map(|created| {
                web_sys::window()
                    .and_then(|w| w.location().origin().ok())
                    .map(|origin| format!("{origin}/share/{}", created.token))
                    .unwrap_or_default()
            });
            html! {
                <Modal title={format!("Share \u{201C}{}\u{201D}", name)}
                       on_close={close_modal.clone()}>
                    {share_link.map(|link| html! {
                        <>
                            <p class="share-created-note">
                                {"Link created \u{2014} copy it now; it is not shown again."}
                            </p>
                            <label class="modal-field">
                                {"Share link"}
                                <input readonly={true} value={link} />
                            </label>
                            <div class="modal-footer-inline">
                                <button class="ghost-btn mono-label" onclick={copy_share_link.clone()}>
                                    {"Copy link"}
                                </button>
                                <button class="primary-btn"
                                        onclick={close_modal.clone().reform(|_| ())}>
                                    <span class="mono-label">{"Done"}</span>
                                </button>
                            </div>
                        </>
                    }).unwrap_or_else(|| html! {
                        <>
                            <p class="modal-note">
                                {format!("Anyone with the link can download this {}.",
                                    if target_is_file { "file" } else { "folder and everything in it" })}
                            </p>
                            <label class="modal-field">
                                {"Expires"}
                                <select value={(*share_expiry).clone()}
                                        onchange={share_field_input(share_expiry.clone())}>
                                    <option value="">{"Never"}</option>
                                    <option value="24">{"In 24 hours"}</option>
                                    <option value="168">{"In 7 days"}</option>
                                    <option value="720">{"In 30 days"}</option>
                                </select>
                            </label>
                            <label class="modal-field">
                                {"Download limit"}
                                <select value={(*share_max).clone()}
                                        onchange={share_field_input(share_max.clone())}>
                                    <option value="">{"Unlimited"}</option>
                                    <option value="1">{"1 download"}</option>
                                    <option value="5">{"5 downloads"}</option>
                                    <option value="25">{"25 downloads"}</option>
                                </select>
                            </label>
                            <label class="modal-field">
                                {"Password (optional)"}
                                <input value={(*share_password).clone()}
                                       oninput={share_password_input}
                                       placeholder="Min 4 characters" />
                            </label>
                            <div class="modal-footer-inline">
                                <button class="primary-btn" disabled={*busy}
                                        onclick={confirm_share.clone()}>
                                    {"Create link"}
                                </button>
                            </div>
                        </>
                    })}
                </Modal>
            }
        },
        ModalState::Rename { target_is_file, .. } => html! {
            <Modal title={format!("Rename {}", if target_is_file { "file" } else { "folder" })}
                   on_close={close_modal.clone()}
                   footer={html! {
                       <button class="primary-btn" disabled={*busy || modal_text.trim().is_empty()}
                               onclick={confirm_rename.clone()}>
                           {"Rename"}
                       </button>
                   }}>
                <label class="modal-field">
                    {"Name"}
                    <input autofocus={true} value={(*modal_text).clone()}
                           oninput={modal_input.clone()}
                           onkeydown={modal_enter_submit(confirm_rename.clone())} />
                </label>
            </Modal>
        },
    };

    html! {
        <div class={page_class}
             ondragover={page_on_drag_over} ondragleave={page_on_drag_leave} ondrop={page_on_drop}>
            {eyebrow(Some(ICON_TRAY), "My Files")}
            <div class="page-title-row">
                <h1>{"My Files"}</h1>
                <div class="page-actions">
                    <input ref={file_input_ref} type="file" multiple={true} hidden={true}
                           onchange={input_onchange} />
                    <button class="ghost-btn with-icon" disabled={*busy} onclick={open_create_modal}>
                        <img src={ICON_PLUS} alt="" width={18} height={18} />
                        <span class="mono-label">{"New folder"}</span>
                    </button>
                    <button class="primary-btn" disabled={*busy} onclick={open_picker_click.clone()}>
                        {if *busy {
                            html! { <span class="mono-label">{"Working\u{2026}"}</span> }
                        } else {
                            html! {
                                <>
                                    <img src={ICON_UPLOAD_DARK} alt="" width={18} height={18} />
                                    <span class="mono-label">{"Upload files"}</span>
                                </>
                            }
                        }}
                    </button>
                </div>
            </div>
            <p class="page-sub">{"Everything you keep, right where you left it."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}

            {(selection_count > 0).then(|| html! {
                <div class="selection-toolbar">
                    <span class="mono-label">{format!("{selection_count} selected")}</span>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={open_move_modal}>
                        {"Move to\u{2026}"}
                    </button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={delete_selection}>
                        {"Delete"}
                    </button>
                    <button class="ghost-btn mono-label" onclick={clear_selection}>{"Clear"}</button>
                </div>
            })}

            <section class="card files-panel">
                <div class="files-panel-head">
                    <span class="all-files">
                        <span class="mono-label">{"All files"}</span>
                        <span class="chip">{files.len()}</span>
                    </span>
                    <span class="mono-label hint">{"Folders appear first"}</span>
                </div>

                <table class="files-table">
                    <thead>
                        <tr>
                            <th class="col-check">
                                <input type="checkbox" aria-label="Select all" checked={all_selected}
                                       onchange={select_all_visible} />
                            </th>
                            <th>{sort_btn(SortKey::Name, "Name")}</th>
                            <th>{sort_btn(SortKey::Size, "Size")}</th>
                            <th><span class="mono-label">{"Type"}</span></th>
                            <th>{sort_btn(SortKey::Mtime, "Modified")}</th>
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
                                        <p class="empty-title">{"Make yourself at home."}</p>
                                        <p class="empty-sub">
                                            {"This folder is empty. Upload your first file,"}
                                            <br />
                                            {"or create a folder to start organizing."}
                                        </p>
                                        <button class="primary-btn" onclick={open_picker_click.clone()}>
                                            <img src={ICON_UPLOAD} alt="" width={23} height={23} />
                                            <span class="mono-label">{"Upload your files"}</span>
                                        </button>
                                        <p class="empty-hint">{"You can also drag files anywhere onto this page."}</p>
                                    </div>
                                </td>
                            </tr>
                        })}
                    </tbody>
                </table>

                <div class="files-panel-foot">
                    <span class="mono-label">{format!("{} item{}", *total, if *total == 1 { "" } else { "s" })}</span>
                    {breadcrumbs}
                </div>
            </section>

            <section class="card uploads-strip">
                <div class="uploads-head">
                    <img src={ICON_TRAY} alt="" width={17} height={17} />
                    <div>
                        <p class="mono-label strip-label">{"Uploads"}</p>
                        <p class="strip-sub">
                            {if active_uploads == 0 {
                                "No uploads in progress".to_string()
                            } else if active_uploads == 1 {
                                "1 upload in progress".to_string()
                            } else {
                                format!("{active_uploads} uploads in progress")
                            }}
                        </p>
                    </div>
                    <span class="strip-hint mono-label">{"Uploads go to the folder you have open."}</span>
                </div>
                {upload_rows}
            </section>

            {(*page_drag_over).then(|| html! { <div class="drop-overlay">{"Drop files to upload here"}</div> })}

            {modal_view}

            {page_tagline("Your space. Your pace.")}
        </div>
    }
}
