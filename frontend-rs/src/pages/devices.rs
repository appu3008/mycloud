//! Devices page: registered clients, trust controls and sync-job conflicts.
//! Backup-config is fetched on demand so Android clients have an honest,
//! discoverable path to the resumable upload API.

use yew::prelude::*;

use crate::api::{self, BackupConfig, DeviceInfo, SyncJobInfo};
use crate::layout::{eyebrow, page_tagline};
use crate::util::format_date;

#[function_component(DevicesPage)]
pub fn devices_page() -> Html {
    let devices = use_state(Vec::<DeviceInfo>::new);
    let jobs = use_state(Vec::<SyncJobInfo>::new);
    let config = use_state(|| None::<BackupConfig>);
    let name = use_state(String::new);
    let platform = use_state(|| "android".to_string());
    let busy = use_state(|| false);
    let error = use_state(String::new);

    let reload = {
        let devices = devices.clone();
        let jobs = jobs.clone();
        let error = error.clone();
        move || {
            let devices = devices.clone();
            let jobs = jobs.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::devices().await {
                    Ok(list) => devices.set(list.items),
                    Err(err) => error.set(err.to_string()),
                }
                match api::sync_jobs(None).await {
                    Ok(list) => jobs.set(list.items),
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

    let name_input = {
        let name = name.clone();
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            name.set(input.value());
        })
    };
    let platform_input = {
        let platform = platform.clone();
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlSelectElement = event.target_unchecked_into();
            platform.set(input.value());
        })
    };

    let register = {
        let name = name.clone();
        let platform = platform.clone();
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |_| {
            let device_name = (*name).trim().to_string();
            if device_name.is_empty() {
                return;
            }
            let platform = (*platform).clone();
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                match api::register_device(&device_name, &platform).await {
                    Ok(_) => reload(),
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let patch_device = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |(device_id, patch): (String, serde_json::Value)| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::update_device(&device_id, &patch).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let show_config = {
        let config = config.clone();
        let error = error.clone();
        Callback::from(move |device_id: String| {
            let config = config.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                match api::backup_config(&device_id).await {
                    Ok(value) => config.set(Some(value)),
                    Err(err) => error.set(err.to_string()),
                }
            });
        })
    };

    let resolve = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |(job_id, strategy): (String, String)| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::resolve_conflict(&job_id, &strategy).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let device_rows: Html = devices.iter().map(|device| {
        let patch = patch_device.clone();
        let config = show_config.clone();
        let id = device.id.clone();
        let trust_patch = patch.clone();
        let trust_id = id.clone();
        let trust = Callback::from(move |_| {
            trust_patch.emit((trust_id.clone(), serde_json::json!({
                "trust_level": "trusted", "can_sync": true, "can_backup": true
            })));
        });
        let id_revoke = id.clone();
        let revoke = Callback::from(move |_| {
            patch.emit((id_revoke.clone(), serde_json::json!({"revoke": true})));
        });
        let id_config = id.clone();
        let view_config = Callback::from(move |_| config.emit(id_config.clone()));
        let revoked = device.revoked_at.is_some();
        html! {
            <tr key={device.id.clone()} class={if revoked { "file-row revoked" } else { "file-row" }}>
                <td>{device.name.clone()}</td>
                <td><span class="chip">{device.platform.clone()}</span></td>
                <td class="dim-cell">
                    {if device.has_public_key { "key present" } else { "no key" }}
                </td>
                <td class="dim-cell">
                    {format!("{} \u{00B7} {}{}", device.trust_level,
                        if device.can_sync { "sync" } else { "no sync" },
                        if device.can_backup { " \u{00B7} backup" } else { "" })}
                </td>
                <td class="dim-cell">
                    {device.last_seen_at.as_ref()
                        .map(|when| format_date(when, true))
                        .unwrap_or_else(|| "never".into())}
                </td>
                <td class="dim-cell">
                    {format!("{} job{} \u{00B7} {} conflict{}", device.job_count,
                        if device.job_count == 1 { "" } else { "s" },
                        device.conflict_count,
                        if device.conflict_count == 1 { "" } else { "s" })}
                </td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy || revoked || device.trust_level == "trusted"}
                            onclick={trust}>{"Trust"}</button>
                    <button class="ghost-btn mono-label" disabled={*busy || revoked}
                            onclick={view_config}>{"Backup config"}</button>
                    <button class="ghost-btn mono-label danger" disabled={*busy || revoked}
                            onclick={revoke}>{"Revoke"}</button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let job_rows: Html = jobs.iter().map(|job| {
        let resolve = resolve.clone();
        let job_id = job.id.clone();
        let accept_server = {
            let resolve = resolve.clone();
            let id = job_id.clone();
            Callback::from(move |_| resolve.emit((id.clone(), "accept_server".to_string())))
        };
        let accept_local = Callback::from(move |_| {
            resolve.emit((job_id.clone(), "accept_local".to_string()))
        });
        let conflict = job.state == "conflict";
        html! {
            <tr key={job.id.clone()} class="file-row">
                <td class="dim-cell">{job.direction.clone()}</td>
                <td class="dim-cell">{job.state.clone()}</td>
                <td class="dim-cell">{job.id.clone()}</td>
                <td class="dim-cell">{job.attempts}</td>
                <td class="dim-cell">{format_date(&job.created_at, true)}</td>
                <td class="row-actions">
                    {conflict.then(|| html! {
                        <>
                            <button class="ghost-btn mono-label" disabled={*busy}
                                    onclick={accept_server}>{"Keep server"}</button>
                            <button class="ghost-btn mono-label" disabled={*busy}
                                    onclick={accept_local}>{"Keep device"}</button>
                        </>
                    })}
                </td>
            </tr>
        }
    }).collect::<Html>();

    html! {
        <div class="files-page">
            {eyebrow(None, "Devices")}
            <div class="page-title-row">
                <h1>{"Devices"}</h1>
                <div class="page-actions">
                    <span class="mono-label hint">
                        {format!("{} device{}", devices.len(), if devices.len() == 1 { "" } else { "s" })}
                    </span>
                </div>
            </div>
            <p class="page-sub">{"Phones and computers that talk to this server. Trust is explicit."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Registered devices"}</span>
                    <span class="mono-label hint">{"new devices start untrusted"}</span>
                </div>
                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Name"}</span></th>
                            <th><span class="mono-label">{"Platform"}</span></th>
                            <th><span class="mono-label">{"Key"}</span></th>
                            <th><span class="mono-label">{"Access"}</span></th>
                            <th><span class="mono-label">{"Last seen"}</span></th>
                            <th><span class="mono-label">{"Sync"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {device_rows}
                        {devices.is_empty().then(|| html! {
                            <tr><td colspan="7" class="empty-state-cell">
                                <p class="empty-title">{"No devices registered."}</p>
                                <p class="empty-sub">{"Register a device below, then trust it before syncing."}</p>
                            </td></tr>
                        })}
                    </tbody>
                </table>
                <div class="settings-form">
                    <label class="modal-field">
                        {"Device name"}
                        <input value={(*name).clone()} oninput={name_input} placeholder="e.g. Pixel 8" />
                    </label>
                    <label class="modal-field">
                        {"Platform"}
                        <select value={(*platform).clone()} onchange={platform_input}>
                            <option value="android">{"Android"}</option>
                            <option value="ios">{"iOS"}</option>
                            <option value="linux">{"Linux"}</option>
                            <option value="macos">{"macOS"}</option>
                            <option value="windows">{"Windows"}</option>
                            <option value="generic">{"Other"}</option>
                        </select>
                    </label>
                    <button class="primary-btn" disabled={*busy || name.trim().is_empty()}
                            onclick={register}>
                        <span class="mono-label">{"Register"}</span>
                    </button>
                </div>
            </section>

            {config.as_ref().map(|cfg| html! {
                <section class="card recent-card">
                    <div class="recent-head">
                        <span class="mono-label">{format!("Backup config \u{2014} {}", cfg.device_name)}</span>
                    </div>
                    <ul class="share-facts mono-label">
                        <li>{format!("Upload: {} \u{2192} {}", cfg.upload_endpoint, cfg.chunk_endpoint)}</li>
                        <li>{format!("Complete: {}", cfg.complete_endpoint)}</li>
                        <li>{format!("Auth: {}", cfg.auth)}</li>
                        <li>{format!("Checksum header: {}", cfg.chunk_checksum_header)}</li>
                        <li>{format!("Max chunk: {} MiB", cfg.max_chunk_mb)}</li>
                    </ul>
                </section>
            }).unwrap_or_default()}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Sync jobs"}</span>
                    <span class="mono-label hint">{"conflicts need a human decision"}</span>
                </div>
                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Direction"}</span></th>
                            <th><span class="mono-label">{"State"}</span></th>
                            <th><span class="mono-label">{"Job"}</span></th>
                            <th><span class="mono-label">{"Attempts"}</span></th>
                            <th><span class="mono-label">{"Queued"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {job_rows}
                        {jobs.is_empty().then(|| html! {
                            <tr><td colspan="6" class="empty-state-cell">
                                <p class="empty-title">{"No sync jobs yet."}</p>
                            </td></tr>
                        })}
                    </tbody>
                </table>
            </section>

            {page_tagline("Trust is granted, never assumed.")}
        </div>
    }
}
