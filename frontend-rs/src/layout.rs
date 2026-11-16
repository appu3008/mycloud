//! App shell: brand bar + tab nav (Figma 1:294/1:636), plus the small
//! page furniture components (PageTitle, PageTagline, Eyebrow).

use yew::prelude::*;
use yew_router::prelude::*;

use crate::auth::AuthState;
use crate::theme::Theme;
use crate::Route;

pub const LOGO: &str = "/assets/figma/logo-cloud.svg";
const ICON_SUN: &str = "/assets/figma/icon-sun.svg";
const ICON_MOON: &str = "/assets/figma/icon-moon.svg";

struct NavItem {
    to: Route,
    label: &'static str,
    icon: &'static str,
}

const CLOUD_NAV: [NavItem; 6] = [
    NavItem { to: Route::Overview, label: "Overview", icon: "/assets/figma/nav-overview.svg" },
    NavItem { to: Route::Files, label: "My Files", icon: "/assets/figma/nav-myfiles.svg" },
    NavItem { to: Route::Recent, label: "Recent Files", icon: "/assets/figma/nav-recent.svg" },
    NavItem { to: Route::Favorites, label: "Favorites", icon: "/assets/figma/nav-favorites.svg" },
    NavItem { to: Route::Shared, label: "Shared Files", icon: "/assets/figma/nav-shared.svg" },
    NavItem { to: Route::Recycle, label: "Recycle Bin", icon: "/assets/figma/nav-recycle.svg" },
];
const MEDIA_NAV: [NavItem; 2] = [
    NavItem { to: Route::Photos, label: "Photos", icon: "/assets/figma/nav-photos.svg" },
    NavItem { to: Route::Videos, label: "Videos", icon: "/assets/figma/nav-videos.svg" },
];
const SYSTEM_NAV: [NavItem; 4] = [
    NavItem { to: Route::Devices, label: "Devices", icon: "/assets/figma/nav-devices.svg" },
    NavItem { to: Route::Activity, label: "Activity", icon: "/assets/figma/nav-activity.svg" },
    NavItem { to: Route::Monitor, label: "Server Monitor", icon: "/assets/figma/nav-monitor.svg" },
    NavItem { to: Route::Settings, label: "Settings", icon: "/assets/figma/nav-settings.svg" },
];

#[derive(Clone, PartialEq, Properties)]
pub struct LayoutProps {
    pub auth: AuthState,
    pub theme: Theme,
    pub on_toggle_theme: Callback<()>,
    pub on_logout: Callback<()>,
    pub children: Children,
}

fn nav_tabs(items: &[NavItem], current_path: Option<String>) -> Html {
    items
        .iter()
        .map(|item| {
            let class = if current_path.as_deref() == Some(item.to.to_path().as_str()) {
                "nav-tab active"
            } else {
                "nav-tab"
            };
            html! {
                <Link<Route> to={item.to.clone()} classes={class}>
                    <img src={item.icon} alt="" width={14} height={14} />
                    <span>{item.label}</span>
                </Link<Route>>
            }
        })
        .collect()
}

#[function_component(Layout)]
pub fn layout(props: &LayoutProps) -> Html {
    let auth = props.auth.clone();
    let theme = props.theme.clone();
    let current_path = use_location().map(|location| location.path().to_string());

    let on_logout_click = {
        let on_logout = props.on_logout.clone();
        Callback::from(move |_| {
            let on_logout = on_logout.clone();
            wasm_bindgen_futures::spawn_local(async move {
                let _ = crate::api::logout().await;
                crate::util::clear_csrf_token();
                on_logout.emit(());
            });
        })
    };
    let on_theme_light = {
        let on_toggle_theme = props.on_toggle_theme.clone();
        let theme = props.theme.clone();
        Callback::from(move |_| if theme != Theme::Light { on_toggle_theme.emit(()) })
    };
    let on_theme_dark = {
        let on_toggle_theme = props.on_toggle_theme.clone();
        let theme = props.theme.clone();
        Callback::from(move |_| if theme != Theme::Dark { on_toggle_theme.emit(()) })
    };

    html! {
        <div class="app-shell">
            <header class="topbar">
                <div class="brand-cell">
                    <img src={LOGO} alt="" width={22} height={22} class="brand-mark" />
                    <span class="brand-name">{"localcloud"}</span>
                </div>
                <div class="server-cell">
                    <span class="mono-label">{"Your personal server"}</span>
                    <span class="mono-label">{"Hosted on your laptop"}</span>
                </div>
                <div class="workspace-cell mono-label">{"Personal workspace"}</div>
                <div class="top-actions">
                    <div class="theme-toggle" role="group" aria-label="Theme">
                        <button
                            class={classes!("theme-opt", (theme == Theme::Light).then_some("active"))}
                            onclick={on_theme_light}
                        >
                            <img src={ICON_SUN} alt="" width={12} height={12} />
                            <span>{"Light"}</span>
                        </button>
                        <button
                            class={classes!("theme-opt", (theme == Theme::Dark).then_some("active"))}
                            onclick={on_theme_dark}
                        >
                            <img src={ICON_MOON} alt="" width={12} height={12} />
                            <span>{"Dark"}</span>
                        </button>
                    </div>
                    <span class="role-chip mono-label">{auth.role_label()}</span>
                    <button class="ghost-btn mono-label" onclick={on_logout_click}>
                        {"Log out"}
                    </button>
                </div>
            </header>

            <nav class="nav-rows" aria-label="Primary">
                <div class="nav-row">
                    <span class="nav-group mono-label">{"Cloud"}</span>
                    <div class="nav-tabs">
                        {nav_tabs(&CLOUD_NAV, current_path.clone())}
                        <span class="nav-disabled mono-label" aria-hidden="true">{"Media"}</span>
                        {nav_tabs(&MEDIA_NAV, current_path.clone())}
                    </div>
                </div>
                <div class="nav-row">
                    <span class="nav-group mono-label">{"System"}</span>
                    <div class="nav-tabs">
                        {nav_tabs(&SYSTEM_NAV, current_path.clone())}
                    </div>
                </div>
            </nav>

            <main class="content">
                {for props.children.iter()}
            </main>
        </div>
    }
}

pub fn page_title(title: &str) -> Html {
    html! {
        <div class="page-title-row">
            <h1>{title}</h1>
        </div>
    }
}

pub fn page_tagline(text: &str) -> Html {
    html! {
        <div class="page-tagline mono-label">{text}</div>
    }
}

/// Eyebrow row above the page title (small icon + mono label), per design.
pub fn eyebrow(icon: Option<&'static str>, text: &str) -> Html {
    html! {
        <div class="page-eyebrow mono-label">
            {if let Some(icon) = icon {
                html! { <img src={icon} alt="" width={12} height={12} /> }
            } else {
                html! {}
            }}
            <span>{text}</span>
        </div>
    }
}
