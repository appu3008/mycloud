//! Browser storage helpers (localStorage / sessionStorage).
use wasm_bindgen::JsCast;
use wasm_bindgen::JsValue;

pub const CSRF_STORAGE_KEY: &str = "mycloud_csrf";

pub fn storage_get(storage: &str, key: &str) -> Option<String> {
    let window = web_sys::window()?;
    let store = if storage == "local" {
        window.local_storage().ok().flatten()?
    } else {
        window.session_storage().ok().flatten()?
    };
    store.get_item(key).ok().flatten()
}

pub fn storage_set(storage: &str, key: &str, value: &str) {
    if let Some(window) = web_sys::window() {
        let store = if storage == "local" {
            window.local_storage().ok().flatten()
        } else {
            window.session_storage().ok().flatten()
        };
        if let Some(store) = store {
            let _ = store.set_item(key, value);
        }
    }
}

pub fn storage_remove(storage: &str, key: &str) {
    if let Some(window) = web_sys::window() {
        let store = if storage == "local" {
            window.local_storage().ok().flatten()
        } else {
            window.session_storage().ok().flatten()
        };
        if let Some(store) = store {
            let _ = store.remove_item(key);
        }
    }
}

pub fn get_csrf_token() -> Option<String> {
    storage_get("session", CSRF_STORAGE_KEY)
        .or_else(|| storage_get("local", CSRF_STORAGE_KEY))
}

pub fn set_csrf_token(token: &str, remember: bool) {
    if remember {
        storage_set("local", CSRF_STORAGE_KEY, token);
    } else {
        storage_set("session", CSRF_STORAGE_KEY, token);
    }
}

pub fn clear_csrf_token() {
    storage_remove("session", CSRF_STORAGE_KEY);
    storage_remove("local", CSRF_STORAGE_KEY);
}

/// `new Date(value).toLocaleString()` / `toLocaleDateString()` via JS,
/// matching the React app's formatting exactly.
pub fn format_date(value: &str, date_only: bool) -> String {
    let date = js_sys::Date::new(&JsValue::from_str(value));
    let method = if date_only {
        "toLocaleDateString"
    } else {
        "toLocaleString"
    };
    js_sys::Reflect::get(&date, &JsValue::from_str(method))
        .ok()
        .and_then(|f| f.dyn_into::<js_sys::Function>().ok())
        .and_then(|f| f.call0(&date).ok())
        .and_then(|r| r.as_string())
        .unwrap_or_default()
}

/// Human-readable byte size, identical to the React app's `humanSize`.
pub fn human_size(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KiB", "MiB", "GiB", "TiB"];
    let mut value = bytes as f64;
    let mut unit = 0usize;
    while value >= 1024.0 && unit < UNITS.len() - 1 {
        value /= 1024.0;
        unit += 1;
    }
    let digits = if value < 10.0 && unit > 0 { 1 } else { 0 };
    format!("{:.*} {}", digits, value, UNITS[unit])
}
