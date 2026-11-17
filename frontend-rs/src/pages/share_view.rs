//! Public share view (no login required): what a link recipient sees.
//! Files download directly; folders list their contents. Password-protected
//! links ask for the password before any download.

use yew::prelude::*;

use crate::api::{self, PublicShareItem, PublicShareMeta};
use crate::layout::page_tagline;
use crate::util::{format_date, human_size};

#[derive(Clone, PartialEq)]
enum Loaded {
    Pending,
    Ready(PublicShareMeta),
    Failed(String),
}

#[function_component(ShareViewPage)]
pub fn share_view_page(props: &ShareViewProps) -> Html {
    let token = props.token.clone();
    let loaded = use_state(|| Loaded::Pending);
    let items = use_state(Vec::<PublicShareItem>::new);
    let password = use_state(String::new);
    let busy = use_state(|| false);

    {
        let token = token.clone();
        let loaded = loaded.clone();
        use_effect_with((), move |_| {
            let token = token.clone();
            let loaded = loaded.clone();
            wasm_bindgen_futures::spawn_local(async move {
                match api::public_share_meta(&token).await {
                    Ok(meta) => loaded.set(Loaded::Ready(meta)),
                    Err(err) => loaded.set(Loaded::Failed(err.to_string())),
                }
            });
            || {}
        });
    }

    let load_items = {
        let token = token.clone();
        let items = items.clone();
        let password = (*password).clone();
        Callback::from(move |_| {
            let token = token.clone();
            let items = items.clone();
            let password = password.clone();
            wasm_bindgen_futures::spawn_local(async move {
                // Password lives in the URL query; re-fetch with it.
                if let Ok(payload) = fetch_items_with_password(&token, &password).await {
                    items.set(payload);
                }
            });
        })
    };

    let password_input = {
        let password = password.clone();
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            password.set(input.value());
        })
    };

    let download = {
        let token = token.clone();
        let password = (*password).clone();
        let busy = busy.clone();
        Callback::from(move |item_id: Option<String>| {
            let token = token.clone();
            let password = password.clone();
            let busy = busy.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                api::download_public_share(
                    &token,
                    (!password.is_empty()).then_some(password.as_str()),
                    item_id.as_deref(),
                );
                busy.set(false);
            });
        })
    };

    let inner = match &*loaded {
        Loaded::Pending => html! { <p class="share-note mono-label">{"Opening link\u{2026}"}</p> },
        Loaded::Failed(message) => html! {
            <div class="card share-card">
                <h1>{"This link is not available"}</h1>
                <p class="share-note">{message.clone()}</p>
                <p class="share-note mono-label">{"The link may be revoked, expired, or mistyped."}</p>
            </div>
        },
        Loaded::Ready(meta) => {
            let folder_items_view = if meta.kind == "folder" {
                html! {
                    <section class="card files-panel">
                        <div class="files-panel-head">
                            <span class="all-files">
                                <span class="mono-label">{"Files"}</span>
                                <span class="chip">{items.len()}</span>
                            </span>
                        </div>
                        <table class="files-table">
                            <thead>
                                <tr>
                                    <th><span class="mono-label">{"Name"}</span></th>
                                    <th><span class="mono-label">{"Size"}</span></th>
                                    <th aria-label="actions"></th>
                                </tr>
                            </thead>
                            <tbody>
                                {for items.iter().map(|item| {
                                    let download = download.clone();
                                    let id = item.id.clone();
                                    html! {
                                        <tr key={item.id.clone()} class="file-row">
                                            <td>{item.name.clone()}</td>
                                            <td class="dim-cell">{human_size(item.size_bytes)}</td>
                                            <td class="row-actions">
                                                <button class="ghost-btn mono-label"
                                                        disabled={*busy}
                                                        onclick={move |_| download.emit(Some(id.clone()))}>
                                                    {"Download"}
                                                </button>
                                            </td>
                                        </tr>
                                    }
                                })}
                                {items.is_empty().then(|| html! {
                                    <tr>
                                        <td colspan="3" class="empty-state-cell">
                                            <p class="empty-title">{"Folder is empty."}</p>
                                        </td>
                                    </tr>
                                })}
                            </tbody>
                        </table>
                    </section>
                }
            } else {
                html! {}
            };

            html! {
                <>
                    <div class="card share-card">
                        <p class="mono-label eyebrow-line">
                            {format!("Shared by {}", meta.owner_name)}
                        </p>
                        <h1>{meta.name.clone()}</h1>
                        {(meta.kind == "file").then(|| html! {
                            <p class="share-note">
                                {format!("{} \u{00B7} one file", human_size(meta.size_bytes))}
                            </p>
                        })}
                        {(meta.kind != "file").then(|| html! {
                            <p class="share-note">
                                {format!("{} \u{00B7} folder", human_size(meta.size_bytes))}
                            </p>
                        })}
                        <ul class="share-facts mono-label">
                            {meta.expires_at.as_ref().map(|when| html! {
                                <li>{format!("Expires {}", format_date(when, false))}</li>
                            }).unwrap_or_else(|| html! { <li>{"No expiry"}</li> })}
                            {meta.downloads_remaining.map(|left| html! {
                                <li>{format!("{left} download{} left", if left == 1 { "" } else { "s" })}</li>
                            })}
                        </ul>

                        {(meta.has_password).then(|| html! {
                            <label class="modal-field share-password">
                                {"Password"}
                                <input value={(*password).clone()} oninput={password_input}
                                       placeholder="Required for downloads" />
                            </label>
                        })}

                        {(meta.kind == "file").then(|| html! {
                            <button class="primary-btn" disabled={*busy}
                                    onclick={download.reform(|_| None::<String>)}>
                                <span class="mono-label">{"Download"}</span>
                            </button>
                        })}
                        {(meta.kind == "folder" && !meta.has_password).then(|| html! {
                            <button class="ghost-btn mono-label" disabled={*busy}
                                    onclick={load_items.clone()}>
                                {"List files"}
                            </button>
                        })}
                    </div>
                    {folder_items_view}
                </>
            }
        },
    };

    html! {
        <div class="share-page">
            {inner}
            {page_tagline("localcloud \u{2014} a personal server.")}
        </div>
    }
}

async fn fetch_items_with_password(
    token: &str,
    password: &str,
) -> Result<Vec<PublicShareItem>, String> {
    if password.is_empty() {
        return match api::public_share_items(token).await {
            Ok(payload) => Ok(payload.items),
            Err(err) => Err(err.to_string()),
        };
    }
    let path = format!(
        "/v1/public/shares/{token}/items?password={}",
        js_sys::encode_uri_component(password).as_string().unwrap_or_default()
    );
    match api::get::<api::PublicShareItems>(&path).await {
        Ok(payload) => Ok(payload.items),
        Err(err) => Err(err.to_string()),
    }
}

#[derive(Clone, PartialEq, Properties)]
pub struct ShareViewProps {
    pub token: String,
}
