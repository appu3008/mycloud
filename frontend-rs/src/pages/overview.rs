//! Overview dashboard (Figma node 1:294): server storage telemetry, recent
//! uploads, and the CTA card.

use yew::prelude::*;
use yew_router::prelude::*;

use crate::api;
use crate::layout::{eyebrow, page_tagline};
use crate::util::{format_date, human_size};
use crate::Route;

const ICON_SERVER: &str = "/assets/figma/icon-server.svg";
const ICON_FILE_DOC: &str = "/assets/figma/icon-file-doc.svg";
const ICON_UPLOAD_CARD: &str = "/assets/figma/icon-upload-card.svg";
const ICON_ARROW: &str = "/assets/figma/icon-arrow.svg";
const ICON_ARROW_LINK: &str = "/assets/figma/icon-arrow-link.svg";
const ICON_ARROW_DARK: &str = "/assets/figma/icon-arrow-dark.svg";
const ICON_CLOCK: &str = "/assets/figma/icon-clock.svg";

#[derive(Clone, PartialEq, Properties)]
pub struct OverviewPageProps {
    pub display_name: String,
}

#[function_component(OverviewPage)]
pub fn overview_page(props: &OverviewPageProps) -> Html {
    let health = use_state(|| None::<api::Health>);
    let recent = use_state(|| None::<Vec<api::CloudFile>>);
    let navigator = use_navigator().unwrap();

    {
        let health = health.clone();
        let recent = recent.clone();
        use_effect_with((), move |_| {
            wasm_bindgen_futures::spawn_local(async move {
                health.set(api::health().await.ok());
            });
            wasm_bindgen_futures::spawn_local(async move {
                let items = api::recent_files().await.unwrap_or_default();
                recent.set(Some(items));
            });
            || {}
        });
    }

    let disk_usable = health
        .as_ref()
        .map(|h| h.status == "ok" && h.errors.is_empty())
        .unwrap_or(false);
    let health = (*health).clone();

    let open_files = {
        let navigator = navigator.clone();
        Callback::from(move |_| navigator.push(&Route::Files))
    };

    let recent_inner = match recent.as_ref() {
        Some(files) if !files.is_empty() => html! {
            <ul class="recent-list">
                {files.iter().map(|file| html! {
                    <li key={file.id.clone()}>
                        <span class="recent-name">{file.name.clone()}</span>
                        <span class="recent-meta mono-label">
                            {format!("{} \u{00B7} {}", human_size(file.size_bytes), format_date(&file.mtime, true))}
                        </span>
                    </li>
                }).collect::<Html>()}
            </ul>
        },
        Some(_) => html! {
            <div class="recent-empty">
                <p class="recent-lede">{"Your latest files will appear here."}</p>
                <div class="recent-empty-row">
                    <span class="recent-doc">
                        <img src={ICON_FILE_DOC} alt="" width={30} height={30} />
                    </span>
                    <div>
                        <p class="recent-empty-title">{"Your first upload starts here."}</p>
                        <p class="recent-empty-sub">
                            {"Add a file in My Files to see it in your recent uploads."}
                        </p>
                    </div>
                    <button class="ghost-btn mono-label with-arrow" onclick={open_files.clone()}>
                        {"Open My Files "} <img src={ICON_ARROW} alt="" width={18} height={18} />
                    </button>
                </div>
            </div>
        },
        None => html! {},
    };

    let storage = if disk_usable {
        let disk = health.as_ref().unwrap().disk.clone();
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
    } else {
        html! {
            <div class="storage-stats">
                <div class="storage-used">
                    <span class="storage-value">{"\u{2014}"}</span>
                    <span class="storage-caption mono-label">{"used of \u{2014} total"}</span>
                </div>
                <div class="storage-meter">
                    <span class="storage-bar" aria-hidden="true" />
                    <div class="meter-caption">
                        <span class="mono-label">{"Usage unavailable"}</span>
                        <span class="mono-label">{"\u{2014} % used"}</span>
                    </div>
                </div>
            </div>
        }
    };

    let note = if disk_usable {
        "Quota and disk guardrails active."
    } else {
        "Disk usage will appear when your server responds."
    };

    html! {
        <div class="overview-page">
            {eyebrow(None, "Your personal cloud")}
            <div class="page-title-row">
                <h1>{format!("Welcome back, {}.", props.display_name)}</h1>
            </div>
            <p class="page-sub">{"A little closer to your files. A little more in control."}</p>

            <section class={classes!("card", "storage-card", (!disk_usable).then_some("unavailable"))}>
                <div class="storage-left">
                    <div class="storage-head">
                        <img src={ICON_SERVER} alt="" width={24} height={24} />
                        <span class="storage-title mono-label">{"Server storage"}</span>
                    </div>
                    {(!disk_usable).then(|| html! { <span class="chip">{"Awaiting server data"}</span> })}
                </div>
                {storage}
                <p class="storage-note">{note}</p>
            </section>

            <div class="overview-grid">
                <section class="card recent-card">
                    <div class="recent-head">
                        <span class="mono-label">{"Recent uploads"}</span>
                        <Link<Route> to={Route::Files} classes="recent-link mono-label">
                            {"View all files "} <img src={ICON_ARROW_LINK} alt="" width={20} height={20} />
                        </Link<Route>>
                    </div>
                    {recent_inner}
                </section>

                <section class="card cta-card">
                    <img src={ICON_UPLOAD_CARD} alt="" width={28} height={28} class="cta-icon" />
                    <h2>{"A home for your files."}</h2>
                    <p>
                        {"Bring your documents, photos, and"}
                        <br />
                        {"everyday essentials into your cloud."}
                    </p>
                    <button class="primary-btn cta-btn" onclick={open_files}>
                        <span class="mono-label">{"Go to My Files"}</span>
                        <img src={ICON_ARROW_DARK} alt="" width={20} height={20} />
                    </button>
                </section>
            </div>

            <div class="grow-note">
                <img src={ICON_CLOCK} alt="" width={20} height={20} />
                <div>
                    <p class="grow-title">{"Room to grow"}</p>
                    <p class="grow-sub">
                        {"Media, sharing, recycle bin, and system pages are planned for a later phase."}
                    </p>
                </div>
            </div>

            {page_tagline("Self-hosted. Simply yours.")}
        </div>
    }
}
