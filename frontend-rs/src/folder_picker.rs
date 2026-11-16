//! Folder tree browser for "Move to..." targets. Root is always offered as the
//! top destination. Excludes a subtree (can't move a folder into itself).

use yew::prelude::*;

use crate::api;

fn strip_subtree(node: &mut api::FolderTreeNode, id: &str) -> bool {
    if node.id == id {
        return true;
    }
    node.children.retain_mut(|child| !strip_subtree(child, id));
    false
}

#[derive(Clone, PartialEq, Properties)]
pub struct FolderPickerProps {
    pub exclude_id: Option<String>,
    pub on_pick: Callback<Option<String>>,
}

#[function_component(FolderPicker)]
pub fn folder_picker(props: &FolderPickerProps) -> Html {
    let tree = use_state(|| -> Option<Vec<api::FolderTreeNode>> { None });
    let error = use_state(String::new);

    {
        let tree = tree.clone();
        let error = error.clone();
        use_effect_with((), move |_| {
            wasm_bindgen_futures::spawn_local(async move {
                match api::folder_tree().await {
                    Ok(nodes) => tree.set(Some(nodes)),
                    Err(err) => error.set(err.to_string()),
                }
            });
            || {}
        });
    }

    if !error.is_empty() {
        return html! { <div class="form-error">{(*error).clone()}</div> };
    }
    let Some(nodes) = (*tree).clone() else {
        return html! { <div class="empty-cell">{"Loading folders\u{2026}"}</div> };
    };

    let mut filtered = nodes;
    if let Some(exclude_id) = &props.exclude_id {
        filtered.retain_mut(|node| !strip_subtree(node, exclude_id));
    }

    let on_pick_root = props.on_pick.clone();
    html! {
        <div class="folder-picker">
            <button class="picker-row" onclick={move |_| on_pick_root.emit(None)}>
                {"\u{1F3E0} My Files "} <span class="picker-hint">{"(root)"}</span>
            </button>
            {filtered
                .iter()
                .map(|node| html! { <PickerNode node={node.clone()} depth={1} on_pick={props.on_pick.clone()} /> })
                .collect::<Html>()}
        </div>
    }
}

#[derive(Clone, PartialEq, Properties)]
struct PickerNodeProps {
    node: api::FolderTreeNode,
    depth: u32,
    on_pick: Callback<Option<String>>,
}

#[function_component(PickerNode)]
fn picker_node(props: &PickerNodeProps) -> Html {
    let on_pick = props.on_pick.clone();
    let id = props.node.id.clone();
    let indent = format!("{}px", 8 + props.depth * 18);
    let children = props
        .node
        .children
        .iter()
        .map(|child| html! { <PickerNode node={child.clone()} depth={props.depth + 1} on_pick={props.on_pick.clone()} /> })
        .collect::<Html>();

    html! {
        <>
            <button class="picker-row" style={format!("padding-left: {indent};")} onclick={move |_| on_pick.emit(Some(id.clone()))}>
                {"\u{1F4C1} "}{props.node.name.clone()}
            </button>
            {children}
        </>
    }
}
