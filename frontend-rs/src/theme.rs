//! Theme handling: localStorage-backed light/dark with `prefers-color-scheme`
//! default, mirroring the React ThemeContext.

use crate::util;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Theme {
    Light,
    Dark,
}

impl Theme {
    pub fn as_str(self) -> &'static str {
        match self {
            Theme::Light => "light",
            Theme::Dark => "dark",
        }
    }

    pub fn toggle(self) -> Theme {
        match self {
            Theme::Light => Theme::Dark,
            Theme::Dark => Theme::Light,
        }
    }

    /// Stored preference first, then `prefers-color-scheme`, then light.
    pub fn detect() -> Theme {
        match util::storage_get("local", "mycloud_theme").as_deref() {
            Some("dark") => return Theme::Dark,
            Some("light") => return Theme::Light,
            _ => {}
        }
        let dark = web_sys::window()
            .and_then(|window| window.match_media("(prefers-color-scheme: dark)").ok().flatten())
            .map(|list| list.matches())
            .unwrap_or(false);
        if dark { Theme::Dark } else { Theme::Light }
    }

    /// Apply to the document root and remember the choice.
    pub fn apply(self) {
        if let Some(document) = web_sys::window().and_then(|w| w.document()) {
            if let Some(root) = document.document_element() {
                let _ = root.set_attribute("data-theme", self.as_str());
            }
        }
        util::storage_set("local", "mycloud_theme", self.as_str());
    }
}
