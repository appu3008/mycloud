//! MyCloud web frontend, rewritten in Rust (Yew/WASM).
//! Boot: theme detection, auth bootstrap, then either the login screen or the
//! app shell with the three Figma screens (1:70 login, 1:294 overview, 1:636 files).

mod api;
mod auth;
mod folder_picker;
mod layout;
mod modal;
mod pages;
mod theme;
mod util;

use yew::prelude::*;
use yew_router::prelude::*;

use crate::auth::AuthState;
use crate::layout::Layout;
use crate::pages::files::FilesPage;
use crate::pages::login::LoginPage;
use crate::pages::overview::OverviewPage;
use crate::pages::placeholder::PlaceholderPage;
use crate::theme::Theme;

// Icon paths (served from public/assets/figma, same files as the React app).
pub const ICON_ARROW_BTN: &str = "/assets/figma/icon-arrow-btn.svg";
pub const ICON_LOCK: &str = "/assets/figma/icon-lock.svg";
pub const ICON_TRAY: &str = "/assets/figma/icon-tray.svg";
pub const ICON_PLUS: &str = "/assets/figma/icon-plus.svg";
pub const ICON_UPLOAD: &str = "/assets/figma/icon-upload.svg";
pub const ICON_UPLOAD_DARK: &str = "/assets/figma/icon-upload-dark.svg";
pub const ICON_UPLOAD_MD: &str = "/assets/figma/icon-upload-md.svg";
pub const ICON_CHEVRON_UP: &str = "/assets/figma/icon-chevron-up.svg";
pub const ICON_FOLDER_BIG: &str = "/assets/figma/icon-folder-big.svg";

#[derive(Clone, Routable, PartialEq)]
pub enum Route {
    #[at("/")]
    Overview,
    #[at("/files")]
    Files,
    #[at("/recent")]
    Recent,
    #[at("/favorites")]
    Favorites,
    #[at("/shared")]
    Shared,
    #[at("/recycle")]
    Recycle,
    #[at("/photos")]
    Photos,
    #[at("/videos")]
    Videos,
    #[at("/devices")]
    Devices,
    #[at("/activity")]
    Activity,
    #[at("/monitor")]
    Monitor,
    #[at("/settings")]
    Settings,
    #[at("/:path*")]
    NotFound,
}

#[function_component(App)]
fn app() -> Html {
    let theme = use_state(Theme::detect);
    let user = use_state(|| None::<api::MyCloudUser>);
    let loading = use_state(|| true);
    let enrollment_open = use_state(|| false);

    {
        let theme = theme.clone();
        use_effect_with((*theme).clone(), move |current| {
            current.apply();
            || {}
        });
    }

    let on_user_changed = {
        let user = user.clone();
        let loading = loading.clone();
        Callback::from(move |result: Option<auth::LoginResult>| {
            user.set(result.map(|r| r.user));
            loading.set(false);
        })
    };
    let on_enrollment = {
        let enrollment_open = enrollment_open.clone();
        Callback::from(move |open: bool| enrollment_open.set(open))
    };

    {
        let on_user_changed = on_user_changed.clone();
        let on_enrollment = on_enrollment.clone();
        use_effect_with((), move |_| {
            wasm_bindgen_futures::spawn_local(async move {
                auth::bootstrap(on_user_changed, on_enrollment).await;
            });
            || {}
        });
    }

    let on_logged_in = {
        let user = user.clone();
        Callback::from(move |logged_in: api::MyCloudUser| {
            user.set(Some(logged_in));
        })
    };
    let on_logout = {
        let user = user.clone();
        Callback::from(move |_| user.set(None))
    };
    let on_toggle_theme = {
        let theme = theme.clone();
        Callback::from(move |_| theme.set(theme.toggle()))
    };

    let auth = AuthState {
        user: (*user).clone(),
        loading: *loading,
        enrollment_open: *enrollment_open,
    };

    html! {
        <BrowserRouter>
            {
                if *loading {
                    html! { <div class="splash">{"Loading MyCloud\u{2026}"}</div> }
                } else if auth.user.is_none() {
                    html! {
                        <LoginPage enrollment_open={*enrollment_open} on_logged_in={on_logged_in} />
                    }
                } else {
                    let display_name = auth
                        .user
                        .as_ref()
                        .map(|u| u.display_name.clone())
                        .unwrap_or_default();
                    html! {
                        <Switch<Route> render={move |route: Route| {
                            let auth = auth.clone();
                            let theme = *theme;
                            let on_toggle_theme = on_toggle_theme.clone();
                            let display_name = display_name.clone();
                            let on_logout = on_logout.clone();
                            let page = match route {
                                Route::Overview => html! { <OverviewPage display_name={display_name} /> },
                                Route::Files => html! { <FilesPage /> },
                                _ => html! { <PlaceholderPage /> },
                            };
                            html! {
                                <Layout auth={auth} theme={theme} on_toggle_theme={on_toggle_theme} on_logout={on_logout}>
                                    {page}
                                </Layout>
                            }
                        }} />
                    }
                }
            }
        </BrowserRouter>
    }
}

fn main() {
    yew::Renderer::<App>::new().render();
}
