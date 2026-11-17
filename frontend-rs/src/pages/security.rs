//! Own-network auditing page: authorized private scopes, local-only port
//! scans, findings and hardening posture. Public targets are rejected server-side.

use yew::prelude::*;

use crate::api::{self, HardeningItem, NetworkScan, ScanFinding, ScanScope};
use crate::layout::{eyebrow, page_tagline};
use crate::util::format_date;

#[function_component(SecurityPage)]
pub fn security_page() -> Html {
    let scopes = use_state(Vec::<ScanScope>::new);
    let scans = use_state(Vec::<NetworkScan>::new);
    let findings = use_state(|| None::<Vec<ScanFinding>>);
    let hardening = use_state(Vec::<HardeningItem>::new);
    let scope_name = use_state(String::new);
    let scope_cidr = use_state(String::new);
    let target = use_state(String::new);
    let active_scope = use_state(String::new);
    let error = use_state(String::new);
    let notice = use_state(String::new);
    let busy = use_state(|| false);

    let reload = {
        let scopes = scopes.clone();
        let scans = scans.clone();
        let hardening = hardening.clone();
        let error = error.clone();
        move || {
            let scopes = scopes.clone();
            let scans = scans.clone();
            let hardening = hardening.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::scan_scopes().await {
                    Ok(list) => scopes.set(list),
                    Err(err) => error.set(err.to_string()),
                }
                if let Ok(list) = api::scan_history().await {
                    scans.set(list);
                }
                if let Ok(list) = api::hardening().await {
                    hardening.set(list);
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

    let bind = |setter: UseStateHandle<String>| -> Callback<yew::InputEvent> {
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            setter.set(input.value());
        })
    };

    let add_scope = {
        let scope_name = scope_name.clone();
        let scope_cidr = scope_cidr.clone();
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let reload = reload.clone();
        Callback::from(move |_| {
            let name = (*scope_name).trim().to_string();
            let cidr = (*scope_cidr).trim().to_string();
            if name.is_empty() || cidr.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                match api::create_scan_scope(&name, &cidr, None).await {
                    Ok(_) => {
                        notice.set(format!("Authorized {cidr}. Scan targets must stay inside it."));
                        reload();
                    }
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let scan = {
        let target = target.clone();
        let active_scope = active_scope.clone();
        let busy = busy.clone();
        let error = error.clone();
        let notice = notice.clone();
        let findings = findings.clone();
        let reload = reload.clone();
        Callback::from(move |_| {
            let scope_id = (*active_scope).clone();
            let target = (*target).trim().to_string();
            if scope_id.is_empty() || target.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let notice = notice.clone();
            let findings = findings.clone();
            let reload = reload.clone();
            busy.set(true);
            error.set(String::new());
            wasm_bindgen_futures::spawn_local(async move {
                match api::run_scan(&scope_id, &target).await {
                    Ok(result) => {
                        notice.set(format!(
                            "Scanned {}: {} open port(s) found.",
                            target, result.scan.findings_count
                        ));
                        findings.set(Some(result.findings));
                        reload();
                    }
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let disable = {
        let busy = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        Callback::from(move |id: String| {
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::disable_scan_scope(&id).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        })
    };

    let scope_rows: Html = scopes.iter().map(|scope| {
        let stop = disable.clone();
        let id = scope.id.clone();
        let do_stop = Callback::from(move |_| stop.emit(id.clone()));
        let pick = {
            let active_scope = active_scope.clone();
            let id = scope.id.clone();
            Callback::from(move |_| active_scope.set(id.clone()))
        };
        html! {
            <tr key={scope.id.clone()} class={if scope.enabled { "file-row" } else { "file-row revoked" }}>
                <td>{scope.name.clone()}</td>
                <td class="dim-cell">{scope.cidr.clone()}</td>
                <td class="dim-cell">
                    {scope.authorized_until.as_ref().map(|when| format_date(when, true))
                        .unwrap_or_else(|| "no expiry".into())}
                </td>
                <td class="dim-cell">{if scope.enabled { "active" } else { "disabled" }}</td>
                <td class="row-actions">
                    <button class="ghost-btn mono-label" disabled={*busy || !scope.enabled}
                            onclick={pick}>{"Scan"}</button>
                    <button class="ghost-btn mono-label danger" disabled={*busy || !scope.enabled}
                            onclick={do_stop}>{"Revoke"}</button>
                </td>
            </tr>
        }
    }).collect::<Html>();

    let scan_rows: Html = scans.iter().map(|scan| {
        html! {
            <tr key={scan.id.clone()} class="file-row">
                <td class="dim-cell">{scan.target.clone()}</td>
                <td class="dim-cell">{scan.state.clone()}</td>
                <td class="dim-cell">{scan.findings_count}</td>
                <td class="dim-cell">{format_date(&scan.started_at, true)}</td>
            </tr>
        }
    }).collect::<Html>();

    let findings_view: Html = findings.as_ref().map(|list| html! {
        <ul class="recent-list activity-list">
            {for list.iter().map(|finding| html! {
                <li key={finding.id.clone()} class="activity-row">
                    <span class="mono-label">{format!("port {}", finding.port)}</span>
                    <span class="chip">{finding.service.clone()}</span>
                    <span class="chip">{finding.severity.clone()}</span>
                    <span class="activity-summary">{finding.summary.clone()}</span>
                </li>
            })}
        </ul>
    }).unwrap_or_default();

    let hardening_rows: Html = hardening.iter().map(|item| html! {
        <li key={item.id.clone()} class="activity-row">
            <span class="chip">{item.status.clone()}</span>
            <span class="activity-summary">{item.title.clone()}</span>
            <span class="mono-label dim-cell">{item.detail.clone()}</span>
        </li>
    }).collect::<Html>();

    html! {
        <div class="files-page">
            {eyebrow(None, "Security Lab")}
            <div class="page-title-row">
                <h1>{"Security Lab"}</h1>
            </div>
            <p class="page-sub">{"Audit networks you own. Every scan needs an active scope and a private target."}</p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}
            {(!notice.is_empty()).then(|| html! { <div class="page-notice">{(*notice).clone()}</div> })}

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Authorized scopes"}</span>
                    <span class="mono-label hint">{"private address space only"}</span>
                </div>
                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Name"}</span></th>
                            <th><span class="mono-label">{"CIDR"}</span></th>
                            <th><span class="mono-label">{"Until"}</span></th>
                            <th><span class="mono-label">{"Status"}</span></th>
                            <th aria-label="actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {scope_rows}
                        {scopes.is_empty().then(|| html! {
                            <tr><td colspan="5" class="empty-state-cell">
                                <p class="empty-title">{"No scope authorized yet."}</p>
                                <p class="empty-sub">{"Add a private network you own before scanning."}</p>
                            </td></tr>
                        })}
                    </tbody>
                </table>
                <div class="settings-form">
                    <label class="modal-field">{"Scope name"}<input value={(*scope_name).clone()}
                        oninput={bind(scope_name.clone())} placeholder="Home lab" /></label>
                    <label class="modal-field">{"Private CIDR"}<input value={(*scope_cidr).clone()}
                        oninput={bind(scope_cidr.clone())} placeholder="192.168.1.0/24" /></label>
                    <button class="primary-btn" disabled={*busy || scope_name.is_empty() || scope_cidr.is_empty()}
                            onclick={add_scope}><span class="mono-label">{"Authorize"}</span></button>
                </div>
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Run a scan"}</span>
                    <span class="mono-label hint">
                        {format!("scope: {}", if active_scope.is_empty() { "none".into() } else { (*active_scope).clone() })}
                    </span>
                </div>
                <div class="settings-form">
                    <label class="modal-field">{"Target IP"}<input value={(*target).clone()}
                        oninput={bind(target.clone())} placeholder="127.0.0.1" /></label>
                    <button class="primary-btn" disabled={*busy || active_scope.is_empty() || target.is_empty()}
                            onclick={scan}><span class="mono-label">{"Scan"}</span></button>
                </div>
                {findings_view}
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Scan history"}</span>
                </div>
                <table class="files-table">
                    <thead>
                        <tr>
                            <th><span class="mono-label">{"Target"}</span></th>
                            <th><span class="mono-label">{"State"}</span></th>
                            <th><span class="mono-label">{"Findings"}</span></th>
                            <th><span class="mono-label">{"Started"}</span></th>
                        </tr>
                    </thead>
                    <tbody>
                        {scan_rows}
                        {scans.is_empty().then(|| html! {
                            <tr><td colspan="4" class="empty-state-cell">
                                <p class="empty-title">{"No scans yet."}</p>
                            </td></tr>
                        })}
                    </tbody>
                </table>
            </section>

            <section class="card recent-card">
                <div class="recent-head">
                    <span class="mono-label">{"Hardening posture"}</span>
                    <span class="mono-label hint">{"derived from real local config"}</span>
                </div>
                <ul class="recent-list activity-list">{hardening_rows}</ul>
            </section>

            {page_tagline("Authorized, local, logged. No external targets.")}
        </div>
    }
}
