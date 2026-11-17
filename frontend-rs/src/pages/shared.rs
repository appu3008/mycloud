//! Shared Files page: the owner's view of their share links (create links
//! from My Files; links are copyable exactly once, at creation).

use yew::prelude::*;

use crate::api;
use crate::layout::{eyebrow, page_tagline};
use crate::util::format_date;

#[function_component(SharedPage)]
pub fn shared_page() -> Html {
    let shares = use_state(Vec::<api::ShareInfo>::new);
    let busy = use_state(|| false);
    let error = use_state(String::new);

    let reload = {
        let shares = shares.clone();
        let error = error.clone();
        move || {
            let shares = shares.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::list_shares().await {
                    Ok(payload) => shares.set(payload.items),
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

    let revoke = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |share_id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::revoke_share(&share_id).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let is_empty = shares.is_empty();

    let rows: Html = shares.iter().map(|share| {
        let revoked = share.revoked_at.is_some();
        let row_class = if revoked { "file-row revoked" } else { "file-row" };
        let do_revoke = {
            let revoke = revoke.clone();
            let id = share.id.clone();
            Callback::from(move |_| revoke.emit(id.clone()))
        };
        let downloads = match share.max_downloads {
            Some(max) => format!("{} / {}", share.download_count, max),
            None => share.download_count.to_string(),
        };
        html! {
            <tr key={share.id.clone()} class={row_class}>
                <td>{share.resource_name.clone()}</td>
                <td><span class="chip">{share.resource_type.clone()}</span></td>
                <td class="dim-cell">
                    {if share.password_protected { "password" } else { "open" }}
                </td>
                <td class="dim-cell">{downloads}</td>
                <td class="dim-cell">{format_date(&share.created_at, false)}</td>
                <td class="dim-cell">
                    {share.expires_at.as_ref()
                        .map(|when| format_date(when, false))
                        .unwrap_or_else(|| "never".into())}
                </td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label danger" disabled={*busy || revoked}
                            onclick={do_revoke}>
                        {if revoked { "Revoked" } else { "Revoke" }}
                    </button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    html! {
        <div class="files-page">
            {eyebrow(None, "Shared Files")}
            <div class="page-title-row">
                <h1>{"Shared Files"}</h1>
                <div class="page-actions">
                    <span class="mono-label hint">{"Create links from My Files"}</span>
                </div>
            </div>
            <p class="page-sub">{"Every link you handed out, in one place."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}

            <section class="card files-panel">
                <div class="files-panel-head">
                    <span class="all-files">
                        <span class="mono-label">{"Active links"}</span>
                        <span class="chip">{shares.iter().filter(|s| s.revoked_at.is_none()).count()}</span>
                    </span>
                    <span class="mono-label hint">{"Tokens are stored hashed \u{2014} a link is copyable only when created."}</span>
                </div>

                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Name"}</span></th>
                            <th><span class="mono-label">{"Kind"}</span></th>
                            <th><span class="mono-label">{"Access"}</span></th>
                            <th><span class="mono-label">{"Downloads"}</span></th>
                            <th><span class="mono-label">{"Created"}</span></th>
                            <th><span class="mono-label">{"Expires"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows}

                        {is_empty.then(|| html! {
                            <tr>
                                <td colspan="7" class="empty-state-cell">
                                    <div class="empty-state">
                                        <p class="empty-title">{"No links yet."}</p>
                                        <p class="empty-sub">
                                            {"Open My Files, pick a file or folder,"}
                                            <br />
                                            {"and choose Share to hand out a link."}
                                        </p>
                                    </div>
                                </td>
                            </tr>
                        })}
                    </tbody>
                </table>

                <div class="files-panel-foot">
                    <span class="mono-label">
                        {format!("{} link{}", shares.len(), if shares.len() == 1 { "" } else { "s" })}
                    </span>
                    <span class="mono-label hint">{"Revoked links stop working immediately."}</span>
                </div>
            </section>

            {page_tagline("Share on your terms.")}
        </div>
    }
}
