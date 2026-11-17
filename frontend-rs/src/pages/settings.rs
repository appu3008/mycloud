//! Settings page: backup jobs (admin only). Jobs are run manually; cron
//! strings are stored for documentation but nothing executes them yet.

use yew::prelude::*;

use crate::api::{self, BackupJob};
use crate::layout::{eyebrow, page_tagline};
use crate::util::human_size;

#[function_component(SettingsPage)]
pub fn settings_page() -> Html {
    let jobs = use_state(Vec::<BackupJob>::new);
    let busy = use_state(|| false);
    let error = use_state(String::new);
    let notice = use_state(String::new);
    let name = use_state(String::new);
    let retention = use_state(|| "3".to_string());
    let include_blobs = use_state(|| true);
    let admin_overview = use_state(|| None::<serde_json::Value>);
    let admin_users = use_state(Vec::<serde_json::Value>::new);
    let admin_audit = use_state(Vec::<serde_json::Value>::new);
    let passphrase = use_state(String::new);
    let e2e_notice = use_state(String::new);

    let reload = {
        let jobs = jobs.clone();
        let error = error.clone();
        move || {
            let jobs = jobs.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::list_backup_jobs().await {
                    Ok(payload) => jobs.set(payload.items),
                    Err(err) => error.set(err.to_string()),
                }
            });
        }
    };

    let reload_admin = {
        let admin_overview = admin_overview.clone();
        let admin_users = admin_users.clone();
        let admin_audit = admin_audit.clone();
        move || {
            let admin_overview = admin_overview.clone();
            let admin_users = admin_users.clone();
            let admin_audit = admin_audit.clone();
            wasm_bindgen_futures::spawn_local(async move {
                // These endpoints 403 for non-admins; the section stays hidden.
                if let Ok(value) = api::admin_overview().await {
                    admin_overview.set(Some(value));
                    if let Ok(users) = api::admin_users().await {
                        admin_users.set(users);
                    }
                    if let Ok(audit) = api::admin_audit().await {
                        admin_audit.set(audit);
                    }
                }
            });
        }
    };

    {
        let reload = reload.clone();
        let reload_admin = reload_admin.clone();
        use_effect_with((), move |_| {
            reload();
            reload_admin();
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
    let retention_input = {
        let retention = retention.clone();
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            retention.set(input.value());
        })
    };
    let blobs_toggle = {
        let include_blobs = include_blobs.clone();
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            include_blobs.set(input.checked());
        })
    };

    let create_job = {
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let name = name.clone();
        let retention = retention.clone();
        let include_blobs = include_blobs.clone();
        let reload = reload.clone();
        Callback::from(move |_| {
            let trimmed = (*name).trim().to_string();
            if trimmed.is_empty() {
                return;
            }
            let retention = (*retention).parse::<i64>().unwrap_or(3);
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let name = name.clone();
            let include_blobs = *include_blobs;
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            notice.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                match api::create_backup_job(&trimmed, None, include_blobs, retention).await {
                    Ok(_) => {
                        notice.set(format!("Backup job \u{201c}{trimmed}\u{201d} created."));
                        name.set(String::new());
                    }
                    Err(err) => error.set(err.to_string()),
                }
                reload();
                busy.set(false);
            });
        })
    };

    let run_job = {
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let reload = reload.clone();
        Callback::from(move |job_id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            notice.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                match api::run_backup_job(&job_id).await {
                    Ok(run) => notice.set(format!(
                        "Backup finished: {} ({} stored)",
                        run.state,
                        human_size(run.size_bytes)
                    )),
                    Err(err) => error.set(err.to_string()),
                }
                reload();
                busy.set(false);
            });
        })
    };

    let delete_job = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |job_id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::delete_backup_job(&job_id).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let job_rows: Html = jobs.iter().map(|job| {
        let run = run_job.clone();
        let delete = delete_job.clone();
        let job_id = job.id.clone();
        let do_run = Callback::from(move |_| run.emit(job_id.clone()));
        let job_id = job.id.clone();
        let do_delete = Callback::from(move |_| delete.emit(job_id.clone()));
        html! {
            <tr key={job.id.clone()} class="file-row">
                <td>{job.name.clone()}</td>
                <td class="dim-cell">{job.target_path.clone()}</td>
                <td class="dim-cell">
                    {if job.include_content_blobs { "db + blobs" } else { "db + manifest" }}
                </td>
                <td class="dim-cell">{format!("keep {}", job.retention_count)}</td>
                <td class="dim-cell">{job.backup_count}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy} onclick={do_run}>
                        {"Run now"}
                    </button>
                    <button class="ghost-btn mono-label danger" disabled={*busy} onclick={do_delete}>
                        {"Delete"}
                    </button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let toggle_admin = {
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let reload_admin = reload_admin.clone();
        Callback::from(move |(user_id, patch): (String, serde_json::Value)| {
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let reload_admin = reload_admin.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                match api::admin_update_user(&user_id, &patch).await {
                    Ok(_) => {
                        notice.set("User updated.".to_string());
                        reload_admin();
                    }
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let passphrase_input = {
        let passphrase = passphrase.clone();
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            passphrase.set(input.value());
        })
    };

    let vault_upload = {
        let passphrase = passphrase.clone();
        let e2e_notice = e2e_notice.clone();
        let busy = busy.clone();
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            let file = match input.files().and_then(|list| list.get(0)) {
                Some(file) => file,
                None => return,
            };
            let passphrase = (*passphrase).clone();
            let e2e_notice = e2e_notice.clone();
            let busy = busy.clone();
            busy.set(true);
            e2e_notice.set("Encrypting locally\u{2026}".to_string());
            wasm_bindgen_futures::spawn_local(async move {
                let result = async {
                    let plain = api::read_whole_file(&file).await.map_err(|err| err.to_string())?;
                    let envelope = crate::e2e::encrypt(&passphrase, &plain)
                        .await
                        .map_err(|err| err.to_string())?;
                    let name = format!("{}.vault", file.name());
                    let uploaded = api::upload_bytes(&name, &envelope).await.map_err(|err| err.to_string())?;
                    Ok::<String, String>(uploaded.name)
                }
                .await;
                match result {
                    Ok(name) => e2e_notice.set(format!(
                        "Uploaded {name} \u{2014} the server only stored ciphertext."
                    )),
                    Err(err) => e2e_notice.set(format!("Encryption failed: {err}")),
                }
                busy.set(false);
            });
        })
    };

    let vault_download = {
        let passphrase = passphrase.clone();
        let e2e_notice = e2e_notice.clone();
        let busy = busy.clone();
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            let file = match input.files().and_then(|list| list.get(0)) {
                Some(file) => file,
                None => return,
            };
            let passphrase = (*passphrase).clone();
            let e2e_notice = e2e_notice.clone();
            let busy = busy.clone();
            busy.set(true);
            e2e_notice.set("Decrypting locally\u{2026}".to_string());
            wasm_bindgen_futures::spawn_local(async move {
                let result = async {
                    let envelope = api::read_whole_file(&file).await.map_err(|err| err.to_string())?;
                    let plain = crate::e2e::decrypt(&passphrase, &envelope)
                        .await
                        .map_err(|err| err.to_string())?;
                    let name = file.name().strip_suffix(".vault").unwrap_or("decrypted").to_string();
                    crate::e2e::download_bytes(&name, &plain)
                        .map_err(|err| err.to_string())?;
                    Ok::<String, String>(name)
                }
                .await;
                match result {
                    Ok(name) => e2e_notice.set(format!("Decrypted {name} in your browser.")),
                    Err(err) => e2e_notice.set(format!("Decryption failed: {err}")),
                }
                busy.set(false);
            });
        })
    };

    let admin_view = match admin_overview.as_ref() {
        Some(overview) => {
            let user_rows: Html = admin_users.iter().map(|user| {
                let toggle = toggle_admin.clone();
                let id = user["id"].as_str().unwrap_or("").to_string();
                let is_admin = user["is_admin"].as_bool().unwrap_or(false);
                let id_toggle = id.clone();
                let do_toggle = Callback::from(move |_| {
                    toggle.emit((id_toggle.clone(), serde_json::json!({"is_admin": !is_admin})));
                });
                html! {
                    <tr key={id.clone()} class="file-row">
                        <td>{user["email"].as_str().unwrap_or("").to_string()}</td>
                        <td>{user["display_name"].as_str().unwrap_or("").to_string()}</td>
                        <td><span class="chip">{user["role"].as_str().unwrap_or("").to_string()}</span></td>
                        <td class="dim-cell">{user["file_count"].to_string()}</td>
                        <td class="dim-cell">{human_size(user["used_bytes"].as_u64().unwrap_or(0))}</td>
                        <td class="row-actions">
                            <button class="ghost-btn mono-label" disabled={*busy}
                                    onclick={do_toggle}>
                                {if is_admin { "Remove admin" } else { "Make admin" }}
                            </button>
                        </td>
                    </tr>
                }
            }).collect::<Html>();
            let audit_rows: Html = admin_audit.iter().take(12).map(|row| {
                html! {
                    <li key={row["id"].to_string()} class="activity-row">
                        <span class="activity-when mono-label">
                            {row["created_at"].as_str().unwrap_or("").to_string()}
                        </span>
                        <span class="chip">{row["action"].as_str().unwrap_or("").to_string()}</span>
                        <span class="activity-summary">
                            {row["actor_email"].as_str().unwrap_or("system").to_string()}
                        </span>
                    </li>
                }
            }).collect::<Html>();
            html! {
                <>
                    <section class="card recent-card">
                        <div class="recent-head">
                            <span class="mono-label">{"Administration"}</span>
                            <span class="mono-label hint">{"admins only"}</span>
                        </div>
                        <ul class="share-facts mono-label">
                            <li>{format!("{} users", overview["users"])}</li>
                            <li>{format!("{} files \u{00B7} {}", overview["files"], human_size(overview["bytes"].as_u64().unwrap_or(0)))}</li>
                            <li>{format!("{} sessions \u{00B7} {} devices", overview["active_sessions"], overview["devices"])}</li>
                            <li>{format!("{} audit events", overview["audit_events"])}</li>
                        </ul>
                        <table class="files-table">
                            <thead>
                                <tr>
                                    <th><span class="mono-label">{"Email"}</span></th>
                                    <th><span class="mono-label">{"Name"}</span></th>
                                    <th><span class="mono-label">{"Role"}</span></th>
                                    <th><span class="mono-label">{"Files"}</span></th>
                                    <th><span class="mono-label">{"Used"}</span></th>
                                    <th aria-label="actions"></th>
                                </tr>
                            </thead>
                            <tbody>{user_rows}</tbody>
                        </table>
                    </section>
                    <section class="card recent-card">
                        <div class="recent-head">
                            <span class="mono-label">{"Recent audit events"}</span>
                        </div>
                        <ul class="recent-list activity-list">{audit_rows}</ul>
                    </section>
                </>
            }
        }
        None => html! {},
    };

    html! {
        <div class="files-page">
            {eyebrow(None, "Settings")}
            <div class="page-title-row">
                <h1>{"Settings"}</h1>
            </div>
            <p class="page-sub">{"Backup jobs: snapshots of the database and content blobs."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}
            {(!notice.is_empty()).then(|| html! { <div class="page-notice">{(*notice).clone()}</div> })}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Backup jobs"}</span>
                    <span class="mono-label hint">{"run manually \u{2014} cron execution is not wired yet"}</span>
                </div>

                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Name"}</span></th>
                            <th><span class="mono-label">{"Target"}</span></th>
                            <th><span class="mono-label">{"Contents"}</span></th>
                            <th><span class="mono-label">{"Retention"}</span></th>
                            <th><span class="mono-label">{"Runs"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {job_rows}
                        {jobs.is_empty().then(|| html! {
                            <tr>
                                <td colspan="6" class="empty-state-cell">
                                    <p class="empty-title">{"No backup jobs yet."}</p>
                                    <p class="empty-sub">{"Create one below; each run writes a self-contained snapshot folder."}</p>
                                </td>
                            </tr>
                        })}
                    </tbody>
                </table>
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"New backup job"}</span>
                </div>
                <div class="settings-form">
                    <label class="modal-field">
                        {"Name"}
                        <input value={(*name).clone()} oninput={name_input}
                               placeholder="e.g. nightly" />
                    </label>
                    <label class="modal-field">
                        {"Keep how many runs"}
                        <input value={(*retention).clone()} oninput={retention_input}
                               inputmode="numeric" />
                    </label>
                    <label class="settings-check">
                        <input type="checkbox" checked={*include_blobs} onchange={blobs_toggle} />
                        <span>{"Copy blob files too (otherwise manifest only)"}</span>
                    </label>
                    <button class="primary-btn" disabled={*busy || name.trim().is_empty()}
                            onclick={create_job}>
                        <span class="mono-label">{"Create job"}</span>
                    </button>
                </div>
                <p class="settings-note">
                    {"Recovery: restore the snapshot database file and copy the blobs"}
                    {" back into the storage root \u{2014} the manifest lists every blob."}
                </p>
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"End-to-end encrypted vault"}</span>
                    <span class="mono-label hint">{"optional \u{00B7} browser-only keys"}</span>
                </div>
                <p class="modal-note">
                    {"Files are encrypted here with PBKDF2-SHA-256 (250k rounds) + AES-256-GCM before upload."}
                    {" The passphrase is never sent to the server, and there is no key recovery."}
                </p>
                <div class="settings-form">
                    <label class="modal-field">
                        {"Vault passphrase"}
                        <input type="password" value={(*passphrase).clone()}
                               oninput={passphrase_input} placeholder="At least 8 characters" />
                    </label>
                    <label class="upload-version-btn primary-btn">
                        <span class="mono-label">{"Encrypt + upload"}</span>
                        <input type="file" disabled={*busy} onchange={vault_upload} hidden={true} />
                    </label>
                    <label class="upload-version-btn ghost-btn">
                        <span class="mono-label">{"Decrypt .vault file"}</span>
                        <input type="file" disabled={*busy} onchange={vault_download} hidden={true} />
                    </label>
                </div>
                {(!e2e_notice.is_empty()).then(|| html! {
                    <p class="settings-note">{(*e2e_notice).clone()}</p>
                })}
            </section>

            {admin_view}
            {page_tagline("Safety net first.")}
        </div>
    }
}
