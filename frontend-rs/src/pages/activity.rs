//! Activity page: the user's recent event timeline (uploads, deletes,
//! restores, shares, sign-ins) — real events only, newest first.

use yew::prelude::*;

use crate::api::{self, ActivityItem};
use crate::layout::{eyebrow, page_tagline};
use crate::util::format_date;

const PAGE_SIZE: i64 = 30;

fn kind_chip(kind: &str) -> Html {
    html! { <span class="chip">{kind.to_string()}</span> }
}

#[function_component(ActivityPage)]
pub fn activity_page() -> Html {
    let events = use_state(Vec::<ActivityItem>::new);
    let total = use_state(|| 0i64);
    let page = use_state(|| 0i64);
    let busy = use_state(|| false);
    let error = use_state(String::new);

    let reload = {
        let events = events.clone();
        let total = total.clone();
        let error = error.clone();
        let page = *page;
        move || {
            let events = events.clone();
            let total = total.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::activity(page, PAGE_SIZE).await {
                    Ok(payload) => {
                        events.set(payload.items);
                        total.set(payload.total);
                    }
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

    let go_page = {
        let page = page.clone();
        let busy = busy.clone();
        let reload = reload.clone();
        Callback::from(move |next: i64| {
            let page = page.clone();
            let busy = busy.clone();
            let reload = reload.clone();
            busy.set(true);
            page.set(next);
            busy.set(false);
            reload();
        })
    };

    let pages = ((*total + PAGE_SIZE - 1) / PAGE_SIZE).max(1);
    let is_empty = events.is_empty();

    let rows: Html = events.iter().map(|event| {
        html! {
            <li key={event.id.clone()} class="activity-row">
                <span class="activity-when mono-label">{format_date(&event.created_at, true)}</span>
                {kind_chip(&event.kind)}
                <span class="activity-summary">{event.summary.clone()}</span>
            </li>
        }
    }).collect::<Html>();

    html! {
        <div class="files-page">
            {eyebrow(None, "Activity")}
            <div class="page-title-row">
                <h1>{"Activity"}</h1>
                <div class="page-actions">
                    <span class="mono-label hint">{format!("{} event{} recorded", *total, if *total == 1 { "" } else { "s" })}</span>
                </div>
            </div>
            <p class="page-sub">{"What has been happening on your server."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Recent events"}</span>
                    <span class="mono-label hint">{"newest first"}</span>
                </div>
                {if is_empty {
                    html! {
                        <p class="recent-lede">
                            {"No activity yet. Upload a file or share a link to start the trail."}
                        </p>
                    }
                } else {
                    html! { <ul class="recent-list activity-list">{rows}</ul> }
                }}
            </section>

            {(pages > 1).then(|| html! {
                <div class="selection-toolbar">
                    <button class="ghost-btn mono-label" disabled={*busy || *page == 0}
                            onclick={go_page.reform(|_| 0i64)}>
                        {"First"}
                    </button>
                    <span class="mono-label">{format!("Page {} of {}", *page + 1, pages)}</span>
                    <button class="ghost-btn mono-label"
                            disabled={*busy || *page + 1 >= pages}
                            onclick={go_page.reform(move |_| *page + 1)}>
                        {"Next"}
                    </button>
                </div>
            })}

            {page_tagline("Every event is real — nothing invented.")}
        </div>
    }
}
