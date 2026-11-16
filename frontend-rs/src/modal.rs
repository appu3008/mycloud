//! Minimal dialog shell: overlay + panel + optional footer actions.

use yew::prelude::*;

#[derive(Clone, PartialEq, Properties)]
pub struct ModalProps {
    pub title: String,
    pub children: Children,
    #[prop_or_default]
    pub footer: Option<Html>,
    pub on_close: Callback<()>,
}

#[function_component(Modal)]
pub fn modal(props: &ModalProps) -> Html {
    let on_close = props.on_close.clone();
    let overlay_onclick = on_close.clone().reform(|_| ());
    let overlay_onkeydown = Callback::from(move |e: KeyboardEvent| {
        if e.key() == "Escape" {
            on_close.emit(());
        }
    });
    let panel_onclick = Callback::from(|e: MouseEvent| e.stop_propagation());
    let panel_onkeydown = Callback::from(|e: KeyboardEvent| e.stop_propagation());
    let close_onclick = props.on_close.reform(|_| ());

    html! {
        <div class="modal-overlay" onclick={overlay_onclick} onkeydown={overlay_onkeydown}>
            <div class="modal-panel" role="dialog" aria-modal="true" aria-label={props.title.clone()}
                 onclick={panel_onclick} onkeydown={panel_onkeydown}>
                <div class="modal-title-row">
                    <h2>{props.title.clone()}</h2>
                    <button class="ghost-btn icon-btn" onclick={close_onclick} aria-label="Close">
                        {"\u{2715}"}
                    </button>
                </div>
                <div class="modal-body">{for props.children.iter()}</div>
                {props.footer.clone().map(|footer| html! { <div class="modal-footer">{footer}</div> })}
            </div>
        </div>
    }
}
