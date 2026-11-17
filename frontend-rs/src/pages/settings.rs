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

            {page_tagline("Safety net first.")}
        </div>
    }
}
