//! Hosting app manager: register static/proxy apps, stage an nginx config,
//! and write small static files. Applying the config is a deliberate sudo
//! step performed by the operator — the server never touches /etc/nginx.

use yew::prelude::*;

use crate::api::{self, HostedApp};
use crate::layout::{eyebrow, page_tagline};
use crate::util::format_date;

#[function_component(HostingPage)]
pub fn hosting_page() -> Html {
    let apps = use_state(Vec::<HostedApp>::new);
    let config = use_state(String::new);
    let name = use_state(String::new);
    let domain = use_state(|| "localhost".to_string());
    let kind = use_state(|| "static".to_string());
    let port = use_state(String::new);
    let file_app = use_state(String::new);
    let file_path = use_state(String::new);
    let file_content = use_state(String::new);
    let notice = use_state(String::new);
    let error = use_state(String::new);
    let busy = use_state(|| false);

    let reload = {
        let apps = apps.clone();
        let config = config.clone();
        let error = error.clone();
        move || {
            let apps = apps.clone();
            let config = config.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::hosted_apps().await {
                    Ok(list) => apps.set(list.items),
                    Err(err) => error.set(err.to_string()),
                }
                if let Ok(text) = api::hosting_config_preview().await {
                    config.set(text);
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

    let bind_input = |setter: UseStateHandle<String>| -> Callback<yew::InputEvent> {
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            setter.set(input.value());
        })
    };

    let create = {
        let name = name.clone();
        let domain = domain.clone();
        let kind = kind.clone();
        let port = port.clone();
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let reload = reload.clone();
        Callback::from(move |_| {
            let name = (*name).trim().to_string();
            if name.is_empty() {
                return;
            }
            let port = (*port).parse::<i64>().ok();
            let kind = (*kind).clone();
            let domain = (*domain).clone();
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                match api::create_hosted_app(&name, &kind, &domain, "/", port).await {
                    Ok(_) => {
                        notice.set(format!("App {name} registered. Stage + apply the config to serve it."));
                        reload();
                    }
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let stage = {
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let config = config.clone();
        Callback::from(move |_| {
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let config = config.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                match api::stage_hosting_config().await {
                    Ok(text) => {
                        config.set(text);
                        notice.set("Config staged in your data dir. Review and run the apply script with sudo.".to_string());
                    }
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let toggle = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |(id, enabled): (String, bool)| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::update_hosted_app(&id, &serde_json::json!({"enabled": enabled})).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let delete = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::delete_hosted_app(&id).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let write_file = {
        let file_app = file_app.clone();
        let file_path = file_path.clone();
        let file_content = file_content.clone();
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        Callback::from(move |_| {
            let app_id = (*file_app).clone();
            let path = (*file_path).trim().to_string();
            if app_id.is_empty() || path.is_empty() {
                return;
            }
            let content = (*file_content).clone();
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                match api::write_static_file(&app_id, &path, &content).await {
                    Ok(_) => notice.set(format!("Wrote {path}")),
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let rows: Html = apps.iter().map(|app| {
        let toggle = toggle.clone();
        let delete = delete.clone();
        let id = app.id.clone();
        let enabled = app.enabled;
        let do_toggle = {
            let toggle = toggle.clone();
            let id = id.clone();
            Callback::from(move |_| toggle.emit((id.clone(), !enabled)))
        };
        let do_delete = Callback::from(move |_| delete.emit(id.clone()));
        let set_app = {
            let file_app = file_app.clone();
            let id = app.id.clone();
            Callback::from(move |_| file_app.set(id.clone()))
        };
        html! {
            <tr key={app.id.clone()} class={if app.enabled { "file-row" } else { "file-row revoked" }}>
                <td>{app.name.clone()}</td>
                <td><span class="chip">{app.kind.clone()}</span></td>
                <td class="dim-cell">{app.domain.clone()}{app.path_prefix.clone()}</td>
                <td class="dim-cell">
                    {app.upstream_port.map(|port| port.to_string())
                        .unwrap_or_else(|| "static files".into())}
                </td>
                <td class="dim-cell">{format_date(&app.created_at, true)}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={do_toggle}>
                        {if app.enabled { "Disable" } else { "Enable" }}
                    </button>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={set_app}>
                        {"Select"}
                    </button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={do_delete}>
                        {"Delete"}
                    </button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    html! {
        <div class="files-page">
            {eyebrow(None, "Hosting")}
            <div class="page-title-row">
                <h1>{"Hosting"}</h1>
                <div class="page-actions">
                    <span class="mono-label hint">{format!("{} app{}", apps.len(), if apps.len() == 1 { "" } else { "s" })}</span>
                </div>
            </div>
            <p class="page-sub">{"Run multiple sites/apps on this server. Config is staged, never applied silently."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}
            {(!notice.is_empty()).then(|| html! { <div class="page-notice">{(*notice).clone()}</div> })}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Apps"}</span>
                    <span class="mono-label hint">{"admin only"}</span>
                </div>
                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Name"}</span></th>
                            <th><span class="mono-label">{"Kind"}</span></th>
                            <th><span class="mono-label">{"Route"}</span></th>
                            <th><span class="mono-label">{"Upstream"}</span></th>
                            <th><span class="mono-label">{"Created"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}
                        {apps.is_empty().then(|| html! {
                            <tr><td colspan="6" class="empty-state-cell">
                                <p class="empty-title">{"No apps registered."}</p>
                            </td></tr>
                        })}
                    </tbody>
                </table>
                <div class="settings-form">
                    <label class="modal-field">{"Name"}<input value={(*name).clone()}
                        oninput={bind_input(name.clone())} placeholder="my-site" /></label>
                    <label class="modal-field">{"Domain"}<input value={(*domain).clone()}
                        oninput={bind_input(domain.clone())} /></label>
                    <label class="modal-field">{"Kind"}
                        <select value={(*kind).clone()} onchange={
                            let kind = kind.clone();
                            Callback::from(move |event: yew::Event| {
                                let input: web_sys::HtmlSelectElement = event.target_unchecked_into();
                                kind.set(input.value());
                            })
                        }>
                            <option value="static">{"Static files"}</option>
                            <option value="proxy">{"Proxy to port"}</option>
                        </select>
                    </label>
                    <label class="modal-field">{"Port (proxy)"}<input value={(*port).clone()}
                        oninput={bind_input(port.clone())} inputmode="numeric" placeholder="9101" /></label>
                    <button class="primary-btn" disabled={*busy || name.trim().is_empty()}
                            onclick={create}><span class="mono-label">{"Add app"}</span></button>
                </div>
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Static file writer"}</span>
                    <span class="mono-label hint">{format!("selected: {}", if file_app.is_empty() { "none".into() } else { (*file_app).clone() })}</span>
                </div>
                <div class="settings-form">
                    <label class="modal-field">{"Relative path"}<input value={(*file_path).clone()}
                        oninput={bind_input(file_path.clone())} placeholder="index.html" /></label>
                    <label class="modal-field">{"Content"}<input value={(*file_content).clone()}
                        oninput={bind_input(file_content.clone())} placeholder="&lt;h1&gt;Hello&lt;/h1&gt;" /></label>
                    <button class="ghost-btn mono-label" disabled={*busy || file_app.is_empty() || file_path.is_empty()}
                            onclick={write_file}>{"Write file"}</button>
                </div>
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Generated nginx config"}</span>
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={stage}>
                        {"Stage config"}
                    </button>
                </div>
                <pre class="config-preview">{(*config).clone()}</pre>
                <p class="settings-note">
                    {"Nothing was installed or reloaded. Review the staged file, then run"}
                    {" deployment/apply-hosting.sh.example with sudo to activate it."}
                </p>
            </section>

            {page_tagline("App manager · staged, reviewed, then applied.")}
        </div>
    }
}
