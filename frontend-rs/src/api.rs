//! Typed fetch wrapper for the MyCloud API, mirroring `frontend/src/services/api.ts`.
//! - sends the session cookie (httpOnly) with every request
//! - attaches the session-scoped CSRF token on mutating methods
//! - non-2xx responses surface as `ApiError`

use serde::de::DeserializeOwned;
use sha2::Digest;
use wasm_bindgen::closure::Closure;
use wasm_bindgen::{JsCast, JsValue};
use wasm_bindgen_futures::JsFuture;

use crate::util;

#[derive(Debug, Clone)]
pub struct ApiError {
    pub status: u16,
    pub message: String,
}

impl std::fmt::Display for ApiError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "API {}", self.status)?;
        if !self.message.is_empty() {
            write!(f, ": {}", self.message)?;
        }
        Ok(())
    }
}

async fn read_error(response: &web_sys::Response) -> ApiError {
    let status = response.status();
    let text = match response.text() {
        Ok(promise) => JsFuture::from(promise)
            .await
            .ok()
            .and_then(|v| v.as_string())
            .unwrap_or_default(),
        Err(_) => String::new(),
    };
    let message = serde_json::from_str::<serde_json::Value>(&text)
        .ok()
        .and_then(|payload| {
            // detail may be a validation array, an object with "error", or a string
            if let Some(list) = payload.get("detail").and_then(|d| d.as_array()) {
                list.first()
                    .and_then(|first| first.get("msg").and_then(|m| m.as_str()))
                    .map(str::to_string)
            } else if let Some(err) = payload.get("detail").and_then(|d| d.get("error")) {
                err.as_str().map(str::to_string)
            } else if let Some(s) = payload.get("detail").and_then(|d| d.as_str()) {
                Some(s.to_string())
            } else if let Some(s) = payload.get("error").and_then(|e| e.as_str()) {
                Some(s.to_string())
            } else {
                None
            }
        })
        .unwrap_or(text);
    ApiError { status, message }
}

fn error_from_message(status: u16, message: String) -> ApiError {
    ApiError { status, message }
}

async fn perform(
    path: &str,
    method: &str,
    body: Option<JsValue>,
    headers: Vec<(&str, String)>,
) -> Result<web_sys::Response, ApiError> {
    let window = web_sys::window().ok_or_else(|| error_from_message(0, "no window".into()))?;
    let has_body = body.is_some();
    let init = web_sys::RequestInit::new();
    init.set_method(method);
    init.set_credentials(web_sys::RequestCredentials::Include);
    if let Some(body) = &body {
        init.set_body(body);
    }

    let header_map = web_sys::Headers::new().map_err(|_| error_from_message(0, "headers".into()))?;
    if has_body {
        header_map
            .set("Content-Type", "application/json")
            .map_err(|_| error_from_message(0, "header".into()))?;
    }
    if method != "GET" {
        if let Some(token) = util::get_csrf_token() {
            header_map
                .set("X-CSRF-Token", &token)
                .map_err(|_| error_from_message(0, "header".into()))?;
        }
    }
    for (name, value) in headers {
        header_map
            .set(name, &value)
            .map_err(|_| error_from_message(0, "header".into()))?;
    }
    init.set_headers(&header_map.into());

    let request = web_sys::Request::new_with_str_and_init(&format!("/api{path}"), &init)
        .map_err(|_| error_from_message(0, "request".into()))?;

    let promise = window.fetch_with_request(&request);
    let response = JsFuture::from(promise)
        .await
        .map_err(|e| error_from_message(0, e.as_string().unwrap_or_else(|| "network error".into())))?;
    let response: web_sys::Response = response.dyn_into().map_err(|_| error_from_message(0, "response cast".into()))?;

    if !response.ok() {
        return Err(read_error(&response).await);
    }
    Ok(response)
}

/// GET a JSON endpoint.
pub async fn get<T: DeserializeOwned>(path: &str) -> Result<T, ApiError> {
    let response = perform(path, "GET", None, Vec::new()).await?;
    let text = JsFuture::from(response.text().map_err(|_| error_from_message(0, "text".into()))?)
        .await
        .map_err(|_| error_from_message(0, "text read".into()))?
        .as_string()
        .unwrap_or_default();
    serde_json::from_str(&text).map_err(|e| error_from_message(0, e.to_string()))
}

/// Send JSON, expecting a JSON response.
pub async fn send_json<T: DeserializeOwned>(path: &str, method: &str, json: &impl serde::Serialize) -> Result<T, ApiError> {
    // Bodies must be a JSON *string* (like JSON.stringify): a plain JS object
    // is coerced by the browser to "[object Object]" and the API 422s.
    let text = serde_json::to_string(json).map_err(|e| error_from_message(0, e.to_string()))?;
    let body = JsValue::from_str(&text);
    let response = perform(path, method, Some(body), Vec::new()).await?;
    if response.status() == 204 {
        return serde_json::from_str("null")
            .map_err(|e| error_from_message(0, e.to_string()));
    }
    let text = JsFuture::from(response.text().map_err(|_| error_from_message(0, "text".into()))?)
        .await
        .map_err(|_| error_from_message(0, "text read".into()))?
        .as_string()
        .unwrap_or_default();
    serde_json::from_str(&text).map_err(|e| error_from_message(0, e.to_string()))
}

/// Send JSON, ignoring the response body.
pub async fn send_json_unit(path: &str, method: &str, json: &impl serde::Serialize) -> Result<(), ApiError> {
    send_json::<serde_json::Value>(path, method, json).await.map(|_| ())
}

/// PUT raw bytes (chunked upload) with a custom header.
pub async fn put_bytes(path: &str, bytes: &[u8], header: (&str, String)) -> Result<(), ApiError> {
    let array = js_sys::Uint8Array::from(bytes);
    let response = perform(path, "PUT", Some(array.into()), vec![header]).await?;
    if response.status() == 204 {
        return Ok(());
    }
    let text = JsFuture::from(response.text().map_err(|_| error_from_message(0, "text".into()))?)
        .await
        .map_err(|_| error_from_message(0, "text read".into()))?
        .as_string()
        .unwrap_or_default();
    serde_json::from_str::<serde_json::Value>(&text)
        .map(|_| ())
        .map_err(|e| error_from_message(0, e.to_string()))
}

// --- types -------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct MyCloudUser {
    pub id: String,
    pub email: String,
    pub display_name: String,
    pub role: String,
    pub is_admin: bool,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct Health {
    pub status: String,
    pub disk: HealthDisk,
    pub errors: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct HealthDisk {
    pub total_bytes: u64,
    pub used_bytes: u64,
    pub free_bytes: u64,
    pub used_percent: f64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct CloudFile {
    pub id: String,
    pub name: String,
    pub extension: String,
    pub mime_type: String,
    pub size_bytes: u64,
    pub folder_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub mtime: String,
    pub is_favorite: bool,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct CloudFolder {
    pub id: String,
    pub parent_id: Option<String>,
    pub name: String,
    pub path: String,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct FolderDetail {
    #[serde(flatten)]
    pub folder: CloudFolder,
    pub breadcrumb: Vec<CloudFolder>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct FolderTreeNode {
    pub id: String,
    pub name: String,
    pub path: String,
    pub children: Vec<FolderTreeNode>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct FileListPayload {
    pub items: Vec<CloudFile>,
    pub total: i64,
    pub page: i64,
    pub page_size: i64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct FolderListPayload {
    pub items: Vec<CloudFolder>,
    pub total: i64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct LoginPayload {
    pub user: MyCloudUser,
    pub csrf_token: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct EnrollmentStatus {
    pub enrollment_open: bool,
    pub reason: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct UploadReserved {
    pub upload_id: String,
    pub chunk_size: u64,
    pub total_chunks: u64,
    pub state: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct CompletedUpload {
    pub id: String,
    pub name: String,
    pub size_bytes: u64,
    pub mime_type: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct DeleteReport {
    pub deleted: DeleteCounts,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct DeleteCounts {
    pub folders: i64,
    pub files: i64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct BatchReport {
    pub updated: i64,
}

// --- trash (recycle bin) -----------------------------------------------------

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct TrashFile {
    pub id: String,
    pub name: String,
    pub extension: String,
    pub mime_type: String,
    pub size_bytes: u64,
    pub folder_id: Option<String>,
    pub mtime: String,
    pub deleted_at: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct TrashFolder {
    pub id: String,
    pub parent_id: Option<String>,
    pub name: String,
    pub path: String,
    pub deleted_at: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct TrashPayload {
    pub files: Vec<TrashFile>,
    pub folders: Vec<TrashFolder>,
    pub total_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct TrashCounts {
    pub files: i64,
    pub folders: i64,
    #[serde(default)]
    pub bytes_freed: u64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct RestoreReport {
    pub restored: TrashCounts,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PurgeReport {
    pub purged: TrashCounts,
}

pub async fn trash() -> Result<TrashPayload, ApiError> {
    get("/v1/trash").await
}

pub async fn restore_from_trash(
    file_ids: &[String],
    folder_ids: &[String],
) -> Result<RestoreReport, ApiError> {
    send_json(
        "/v1/trash/restore",
        "POST",
        &serde_json::json!({ "file_ids": file_ids, "folder_ids": folder_ids }),
    )
    .await
}

pub async fn purge_trash(
    file_ids: &[String],
    folder_ids: &[String],
) -> Result<PurgeReport, ApiError> {
    send_json(
        "/v1/trash/purge",
        "POST",
        &serde_json::json!({ "mode": "items", "file_ids": file_ids, "folder_ids": folder_ids }),
    )
    .await
}

// --- storage analytics + duplicates ------------------------------------------

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct StorageUsage {
    pub used_bytes: u64,
    pub quota_bytes: u64,
    pub file_count: u64,
    pub folder_count: u64,
    pub trash_files: u64,
    pub trash_bytes: u64,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct DuplicateItem {
    pub id: String,
    pub name: String,
    pub folder_id: Option<String>,
    pub size_bytes: u64,
    pub created_at: String,
    pub mtime: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct DuplicateGroup {
    pub sha256: String,
    pub size_bytes: u64,
    pub copies: u64,
    pub wasted_bytes: u64,
    pub items: Vec<DuplicateItem>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct DuplicatesReport {
    pub groups: Vec<DuplicateGroup>,
    pub group_count: u64,
    pub total_wasted_bytes: u64,
}

pub async fn storage_usage() -> Result<StorageUsage, ApiError> {
    get("/v1/storage/usage").await
}

pub async fn duplicates() -> Result<DuplicatesReport, ApiError> {
    get("/v1/duplicates").await
}

// --- shares -------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ShareInfo {
    pub id: String,
    pub resource_type: String,
    pub file_id: Option<String>,
    pub folder_id: Option<String>,
    pub resource_name: String,
    pub password_protected: bool,
    pub max_downloads: Option<i64>,
    pub download_count: i64,
    pub expires_at: Option<String>,
    pub revoked_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ShareCreated {
    pub share: ShareInfo,
    pub token: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ShareList {
    pub items: Vec<ShareInfo>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PublicShareMeta {
    pub kind: String,
    pub name: String,
    pub owner_name: String,
    pub size_bytes: u64,
    pub has_password: bool,
    pub expires_at: Option<String>,
    pub downloads_remaining: Option<i64>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PublicShareItem {
    pub id: String,
    pub name: String,
    pub size_bytes: u64,
    pub mtime: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct PublicShareItems {
    pub folder: PublicShareMeta,
    pub items: Vec<PublicShareItem>,
}

pub async fn create_share(
    resource_type: &str,
    resource_id: &str,
    expires_in_hours: Option<u64>,
    max_downloads: Option<u64>,
    password: Option<&str>,
) -> Result<ShareCreated, ApiError> {
    send_json(
        "/v1/shares",
        "POST",
        &serde_json::json!({
            "resource_type": resource_type,
            "resource_id": resource_id,
            "expires_in_hours": expires_in_hours,
            "max_downloads": max_downloads,
            "password": password,
        }),
    )
    .await
}

pub async fn list_shares() -> Result<ShareList, ApiError> {
    get("/v1/shares").await
}

pub async fn revoke_share(share_id: &str) -> Result<(), ApiError> {
    send_json_unit(&format!("/v1/shares/{share_id}"), "DELETE", &serde_json::json!({})).await
}

// Public endpoints: these go through the raw fetch wrapper but live at the
// same /api base; they need no CSRF and no session.
pub async fn public_share_meta(token: &str) -> Result<PublicShareMeta, ApiError> {
    get(&format!("/v1/public/shares/{token}")).await
}

pub async fn public_share_items(token: &str) -> Result<PublicShareItems, ApiError> {
    get(&format!("/v1/public/shares/{token}/items")).await
}

/// Open the public download in a new tab (so the browser streams it).
pub fn download_public_share(token: &str, password: Option<&str>, item_id: Option<&str>) {
    let path = match item_id {
        Some(id) => format!("/api/v1/public/shares/{token}/items/{id}/download"),
        None => format!("/api/v1/public/shares/{token}/download"),
    };
    let url = match password {
        Some(pw) => format!("{path}?password={}", js_sys::encode_uri_component(pw).as_string().unwrap_or_default()),
        None => path,
    };
    let window = web_sys::window().expect("no window");
    let _ = window.open_with_url_and_target(&url, "_self");
}

// --- activity timeline ----------------------------------------------------------

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ActivityItem {
    pub id: String,
    pub kind: String,
    pub summary: String,
    pub created_at: String,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ActivityList {
    pub items: Vec<ActivityItem>,
    pub total: i64,
}

pub async fn activity(page: i64, limit: i64) -> Result<ActivityList, ApiError> {
    get(&format!("/v1/activity?page={page}&limit={limit}")).await
}

// --- auth --------------------------------------------------------------------

pub async fn me() -> Result<MyCloudUser, ApiError> {
    get("/v1/auth/me").await
}

pub async fn enrollment_status() -> Result<EnrollmentStatus, ApiError> {
    get("/v1/auth/provider/init/status").await
}

pub async fn login(email: &str, password: &str) -> Result<LoginPayload, ApiError> {
    send_json(
        "/v1/auth/login",
        "POST",
        &serde_json::json!({ "email": email, "password": password }),
    )
    .await
}

pub async fn enroll(email: &str, display_name: &str, password: &str) -> Result<LoginPayload, ApiError> {
    send_json(
        "/v1/auth/provider/init",
        "POST",
        &serde_json::json!({ "email": email, "display_name": display_name, "password": password }),
    )
    .await
}

pub async fn logout() -> Result<(), ApiError> {
    send_json_unit("/v1/auth/logout", "POST", &serde_json::json!({})).await
}

// --- health & files -----------------------------------------------------------

pub async fn health() -> Result<Health, ApiError> {
    get("/health").await
}

pub async fn list_files(sort_key: &str, asc: bool, folder_id: Option<&str>) -> Result<FileListPayload, ApiError> {
    let order = if asc { "asc" } else { "desc" };
    let mut query = format!("/v1/files?page=0&page_size=100&sort={sort_key}&order={order}");
    if let Some(folder) = folder_id {
        query.push_str(&format!("&folder_id={folder}"));
    }
    get(&query).await
}

pub async fn recent_files() -> Result<Vec<CloudFile>, ApiError> {
    get::<FileListPayload>("/v1/files?sort=mtime&order=desc&page_size=5")
        .await
        .map(|p| p.items)
}

pub async fn rename_file(file_id: &str, name: &str) -> Result<(), ApiError> {
    send_json_unit(
        &format!("/v1/files/{file_id}"),
        "PATCH",
        &serde_json::json!({ "name": name }),
    )
    .await
}

// --- folders & batch operations (phase 5) --------------------------------------

pub async fn list_folders(parent_id: Option<&str>) -> Result<FolderListPayload, ApiError> {
    let query = parent_id
        .map(|id| format!("?parent_id={id}"))
        .unwrap_or_default();
    get(&format!("/v1/folders{query}")).await
}

pub async fn folder_detail(folder_id: &str) -> Result<FolderDetail, ApiError> {
    get(&format!("/v1/folders/{folder_id}")).await
}

pub async fn folder_tree() -> Result<Vec<FolderTreeNode>, ApiError> {
    get("/v1/folders/tree").await
}

pub async fn create_folder(name: &str, parent_id: Option<&str>) -> Result<CloudFolder, ApiError> {
    send_json(
        "/v1/folders",
        "POST",
        &serde_json::json!({ "name": name, "parent_id": parent_id }),
    )
    .await
}

pub async fn rename_folder(folder_id: &str, name: &str) -> Result<(), ApiError> {
    send_json_unit(
        &format!("/v1/folders/{folder_id}"),
        "PATCH",
        &serde_json::json!({ "name": name }),
    )
    .await
}

pub async fn delete_folder(folder_id: &str) -> Result<DeleteReport, ApiError> {
    send_json(
        &format!("/v1/folders/{folder_id}"),
        "DELETE",
        &serde_json::json!({}),
    )
    .await
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FileBatchAction {
    Delete,
    Move,
    Copy,
}

impl FileBatchAction {
    fn as_str(self) -> &'static str {
        match self {
            FileBatchAction::Delete => "delete",
            FileBatchAction::Move => "move",
            FileBatchAction::Copy => "copy",
        }
    }
}

pub async fn batch_files(action: FileBatchAction, file_ids: &[String], target_folder_id: Option<&str>) -> Result<BatchReport, ApiError> {
    send_json(
        "/v1/files/batch",
        "POST",
        &serde_json::json!({ "action": action.as_str(), "file_ids": file_ids, "target_folder_id": target_folder_id }),
    )
    .await
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum FolderBatchAction {
    Delete,
    Move,
}

impl FolderBatchAction {
    fn as_str(self) -> &'static str {
        match self {
            FolderBatchAction::Delete => "delete",
            FolderBatchAction::Move => "move",
        }
    }
}

pub async fn batch_folders(action: FolderBatchAction, folder_ids: &[String], parent_id: Option<&str>) -> Result<(), ApiError> {
    send_json(
        "/v1/folders/batch",
        "POST",
        &serde_json::json!({ "action": action.as_str(), "folder_ids": folder_ids, "parent_id": parent_id }),
    )
    .await
}

// --- resumable chunked upload ---------------------------------------------------

/// Stream a File through the resumable chunked upload API, reporting progress
/// through the callbacks (mirrors `uploadFileResumable`).
pub struct UploadHooks {
    pub on_reserved: Option<Box<dyn FnOnce(u64)>>,
    pub on_chunk_done: Option<Box<dyn Fn(u64, u64)>>,
}

pub async fn upload_file_resumable(
    file: &web_sys::File,
    target_folder_id: Option<&str>,
    hooks: UploadHooks,
) -> Result<CompletedUpload, ApiError> {
    let one_mib = 1024f64 * 1024f64;
    let size = file.size();
    let chunk_size_mb = ((size / one_mib / 64.0).ceil() as u64).clamp(1, 16).max(1);
    let reserved: UploadReserved = send_json(
        "/v1/uploads",
        "POST",
        &serde_json::json!({
            "filename": file.name(),
            "size_bytes": size as u64,
            "target_folder_id": target_folder_id,
            "chunk_size_mb": chunk_size_mb,
        }),
    )
    .await?;

    if let Some(on_reserved) = hooks.on_reserved {
        on_reserved(reserved.total_chunks);
    }

    let total = reserved.total_chunks;
    for number in 1..=total {
        let start = (number - 1) * reserved.chunk_size;
        let end = (size as u64).min(start + reserved.chunk_size);
        let bytes = read_file_slice(file, start, end).await?;
        let digest = sha2::Sha256::digest(&bytes);
        put_bytes(
            &format!("/v1/uploads/{}/chunks/{number}", reserved.upload_id),
            &bytes,
            ("X-Chunk-Sha256", hex_encode(&digest)),
        )
        .await?;
        if let Some(on_chunk_done) = &hooks.on_chunk_done {
            on_chunk_done(number, total);
        }
    }

    send_json(
        &format!("/v1/uploads/{}/complete", reserved.upload_id),
        "POST",
        &serde_json::json!({}),
    )
    .await
}

fn hex_encode(bytes: &[u8]) -> String {
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push_str(&format!("{byte:02x}"));
    }
    out
}

/// Read a byte range of a Blob via FileReader (`end` is exclusive, as in Blob.slice).
async fn read_file_slice(file: &web_sys::File, start: u64, end: u64) -> Result<Vec<u8>, ApiError> {
    let slice: web_sys::Blob = file
        .slice_with_i32_and_i32(start as i32, end as i32)
        .map_err(|_| error_from_message(0, "slice failed".into()))?;
    let (sender, receiver) = futures_channel::oneshot::channel::<Result<Vec<u8>, String>>();
    let reader = web_sys::FileReader::new().map_err(|_| error_from_message(0, "FileReader".into()))?;
    let onload = Closure::<dyn FnMut(_)>::once(move |event: web_sys::ProgressEvent| {
        let reader: web_sys::FileReader = event
            .target()
            .unwrap()
            .dyn_into()
            .unwrap();
        let result = reader.result().unwrap_or_default();
        let bytes = js_sys::Uint8Array::new(&result).to_vec();
        let _ = sender.send(Ok(bytes));
    });
    reader.set_onloadend(Some(onload.as_ref().unchecked_ref()));
    reader
        .read_as_array_buffer(&slice)
        .map_err(|_| error_from_message(0, "read failed".into()))?;
    onload.forget();
    match receiver.await {
        Ok(Ok(bytes)) => Ok(bytes),
        Ok(Err(message)) => Err(error_from_message(0, message)),
        Err(_) => Err(error_from_message(0, "read cancelled".into())),
    }
}

/// Download a file by navigating an anchor (same as the React `downloadContent`).
pub fn download_content(file_id: &str, filename: &str) {
    let document = web_sys::window().and_then(|w| w.document());
    if let Some(document) = document {
        if let Ok(anchor) = document.create_element("a") {
            let _ = anchor.set_attribute("href", &format!("/api/v1/files/{file_id}/content"));
            let _ = anchor.set_attribute("download", filename);
            if let Some(body) = document.body() {
                let _ = body.append_child(&anchor);
                let html_anchor: web_sys::HtmlElement = anchor.dyn_into().unwrap();
                html_anchor.click();
                let _ = body.remove_child(&html_anchor);
            }
        }
    }
}
