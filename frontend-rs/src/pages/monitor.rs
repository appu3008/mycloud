//! Server Monitor page: live server disk, your storage vs quota, and an
//! exact-duplicate report (files sharing content-addressed blobs).

use yew::prelude::*;

use crate::api::{self, DuplicateGroup};
use crate::layout::{eyebrow, page_tagline};
use crate::util::human_size;

const ICON_SERVER: &str = "/assets/figma/icon-server.svg";

#[function_component(MonitorPage)]
pub fn monitor_page() -> Html {
    let health = use_state(|| None::<api::Health>);
    let usage = use_state(|| None::<api::StorageUsage>);
    let duplicates = use_state(|| None::<api::DuplicatesReport>);
    let alerts = use_state(|| None::<api::AlertStatus>);

    {
        let health = health.clone();
        let usage = usage.clone();
        let duplicates = duplicates.clone();
        let alerts = alerts.clone();
        use_effect_with((), move |_| {
            wasm_bindgen_futures::spawn_local(async move {
                health.set(api::health().await.ok());
            });
            wasm_bindgen_futures::spawn_local(async move {
                usage.set(api::storage_usage().await.ok());
            });
            wasm_bindgen_futures::spawn_local(async move {
                duplicates.set(api::duplicates().await.ok());
            });
            wasm_bindgen_futures::spawn_local(async move {
                alerts.set(api::alerts().await.ok());
            });
            || {}
        });
    }

    let health = (*health).clone();
    let usage = (*usage).clone();
    let duplicates = (*duplicates).clone();
    let dismiss_alert = {
        let alerts_handle = alerts.clone();
        Callback::from(move |id: String| {
            let alerts = alerts_handle.clone();
            wasm_bindgen_futures::spawn_local(async move {
                if api::dismiss_alert(&id).await.is_ok() {
                    if let Some(status) = api::alerts().await.ok() {
                        alerts.set(Some(status));
                    }
                }
            });
        })
    };

    let disk_section = match health.as_ref() {
        Some(h) => {
            let disk = &h.disk;
            let percent = disk.used_percent.min(100.0);
            html! {
                <div class="storage-stats">
                    <div class="storage-used">
                        <span class="storage-value">{human_size(disk.used_bytes)}</span>
                        <span class="storage-caption mono-label">
                            {format!("used of {} total", human_size(disk.total_bytes))}
                        </span>
                    </div>
                    <div class="storage-meter">
                        <span class="storage-bar" aria-hidden="true">
                            <span style={format!("width: {percent}%;")} />
                        </span>
                        <div class="meter-caption">
                            <span class="mono-label">{format!("{} free", human_size(disk.free_bytes))}</span>
                            <span class="mono-label">{format!("{:.1}% used", disk.used_percent)}</span>
                        </div>
                    </div>
                </div>
            }
        }
        None => html! {
            <div class="storage-stats">
                <div class="storage-used">
                    <span class="storage-value">{"\u{2014}"}</span>
                    <span class="storage-caption mono-label">{"waiting for server"}</span>
                </div>
            </div>
        },
    };

    let quota_section = match usage.as_ref() {
        Some(u) => {
            let percent = if u.quota_bytes > 0 {
                (u.used_bytes as f64 / u.quota_bytes as f64 * 100.0).min(100.0)
            } else {
                0.0
            };
            html! {
                <div class="storage-stats">
                    <div class="storage-used">
                        <span class="storage-value">{human_size(u.used_bytes)}</span>
                        <span class="storage-caption mono-label">
                            {format!("of {} quota", human_size(u.quota_bytes))}
                        </span>
                    </div>
                    <div class="storage-meter">
                        <span class="storage-bar" aria-hidden="true">
                            <span style={format!("width: {percent}%;")} />
                        </span>
                        <div class="meter-caption">
                            <span class="mono-label">
                                {format!("{} files \u{00B7} {} folders", u.file_count, u.folder_count)}
                            </span>
                            <span class="mono-label">{format!("{percent:.1}% of quota")}</span>
                        </div>
                    </div>
                </div>
            }
        }
        None => html! {
            <div class="storage-stats">
                <div class="storage-used">
                    <span class="storage-value">{"\u{2014}"}</span>
                    <span class="storage-caption mono-label">{"waiting for server"}</span>
                </div>
            </div>
        },
    };

    let alerts = (*alerts).clone();

    let duplicates_section = match duplicates.as_ref() {
        Some(report) if report.groups.is_empty() => html! {
            <p class="dupes-empty">
                {"No duplicate files. Identical content is stored once \u{2014} uploads with the same bytes already share storage."}
            </p>
        },
        Some(report) => html! {
            <>
                <div class="dupes-summary mono-label">
                    {format!("{} group{} \u{00B7} {} recoverable by removing extra copies",
                        report.group_count,
                        if report.group_count == 1 { "" } else { "s" },
                        human_size(report.total_wasted_bytes))}
                </div>
                {for report.groups.iter().map(|group| dupe_group_row(group))}
            </>
        },
        None => html! { <p class="dupes-empty mono-label">{"Loading duplicates\u{2026}"}</p> },
    };

    html! {
        <div class="overview-page">
            {eyebrow(Some(ICON_SERVER), "Server Monitor")}
            <div class="page-title-row">
                <h1>{"Server Monitor"}</h1>
            </div>
            <p class="page-sub">{"What your server holds, and where storage can be saved."}</p>

            <section class="card storage-card">
                <div class="storage-left">
                    <div class="storage-head">
                        <img src={ICON_SERVER} alt="" width={24} height={24} />
                        <span class="storage-title mono-label">{"Server disk"}</span>
                    </div>
                </div>
                {disk_section}
            </section>

            <section class="card storage-card">
                <div class="storage-left">
                    <div class="storage-head">
                        <img src="/assets/figma/icon-tray.svg" alt="" width={24} height={24} />
                        <span class="storage-title mono-label">{"Your storage"}</span>
                    </div>
                </div>
                {quota_section}
            </section>

            {alerts.as_ref().map(|status| html! {
                <section class="card recent-card">
                    <div class="recent-head">
                        <span class="mono-label">{"Quota alerts"}</span>
                        <span class="mono-label hint">
                            {format!("{}% used \u{00B7} warn at {}%", status.percent, status.threshold)}
                        </span>
                    </div>
                    {if status.notifications.is_empty() {
                        html! { <p class="recent-lede">{"No alerts. Your usage is below the warning threshold."}</p> }
                    } else {
                        html! {
                            <ul class="recent-list activity-list">
                                {for status.notifications.iter().map(|note| {
                                    let dismiss = dismiss_alert.clone();
                                    let id = note.id.clone();
                                    let do_dismiss = Callback::from(move |_| dismiss.emit(id.clone()));
                                    html! {
                                        <li key={note.id.clone()} class="activity-row">
                                            <span class="chip">{note.kind.clone()}</span>
                                            <span class="activity-summary">
                                                {format!("{} of {} ({}%) used",
                                                    human_size(note.payload["used_bytes"].as_u64().unwrap_or(0)),
                                                    human_size(note.payload["quota_bytes"].as_u64().unwrap_or(0)),
                                                    note.payload["percent"].as_i64().unwrap_or(0))}
                                            </span>
                                            {(!note.is_read).then(|| html! {
                                                <button class="ghost-btn mono-label" onclick={do_dismiss}>
                                                    {"Dismiss"}
                                                </button>
                                            })}
                                        </li>
                                    }
                                })}
                            </ul>
                        }
                    }}
                </section>
            }).unwrap_or_default()}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Duplicate files"}</span>
                    <span class="mono-label hint">{"exact copies \u{00B7} biggest waste first"}</span>
                </div>
                {duplicates_section}
            </section>

            {page_tagline("Real numbers. Nothing invented.")}
        </div>
    }
}

fn dupe_group_row(group: &DuplicateGroup) -> Html {
    let sha_short: String = group.sha256.chars().take(12).collect();
    html! {
        <div class="dupe-group" key={group.sha256.clone()}>
            <div class="dupe-group-head">
                <span class="mono-label">
                    {format!("{} \u{00D7} identical \u{00B7} {} each \u{00B7} {} wasted",
                        group.copies, human_size(group.size_bytes), human_size(group.wasted_bytes))}
                </span>
                <span class="mono-label hint">{format!("content {sha_short}\u{2026}")}</span>
            </div>
            <ul class="dupe-items">
                {for group.items.iter().map(|item| html! {
                    <li key={item.id.clone()}>
                        <span class="recent-name">{item.name.clone()}</span>
                        <span class="recent-meta mono-label">{format_date_only(&item.mtime)}</span>
                    </li>
                })}
            </ul>
        </div>
    }
}

fn format_date_only(value: &str) -> String {
    crate::util::format_date(value, true)
}
