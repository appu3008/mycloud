//! Photo and video library: real uploads classified server-side, albums,
//! locally generated thumbnails (or inline originals), and Range-based video
//! playback through the existing file content endpoint.

use yew::prelude::*;

use crate::api::{self, AlbumInfo, MediaItem};
use crate::layout::{eyebrow, page_tagline};
use crate::util::{format_date, human_size};

#[derive(Clone, PartialEq, Properties)]
pub struct MediaPageProps {
    pub kind: String, // "photo" or "video"
}

#[function_component(MediaPage)]
pub fn media_page(props: &MediaPageProps) -> Html {
    let is_photo = props.kind == "photo";
    let kind = props.kind.clone();
    let items = use_state(Vec::<MediaItem>::new);
    let albums = use_state(Vec::<AlbumInfo>::new);
    let album_id = use_state(String::new);
    let new_album = use_state(String::new);
    let busy = use_state(|| false);
    let error = use_state(String::new);

    let reload = {
        let items = items.clone();
        let kind = kind.clone();
        let album_id = album_id.clone();
        let error = error.clone();
        move || {
            let items = items.clone();
            let kind = kind.clone();
            let album_id = album_id.clone();
            let error = error.clone();
            let selected = if album_id.is_empty() { None } else { Some((*album_id).clone()) };
            wasm_bindgen_futures::spawn_local(async move {
                error.set(String::new());
                match api::media(&kind, selected.as_deref()).await {
                    Ok(payload) => items.set(payload.items),
                    Err(err) => error.set(err.to_string()),
                }
            });
        }
    };

    let reload_albums = {
        let albums = albums.clone();
        let error = error.clone();
        move || {
            let albums = albums.clone();
            let error = error.clone();
            wasm_bindgen_futures::spawn_local(async move {
                match api::albums().await {
                    Ok(payload) => albums.set(payload.items),
                    Err(err) => error.set(err.to_string()),
                }
            });
        }
    };

    {
        let reload = reload.clone();
        let reload_albums = reload_albums.clone();
        use_effect_with((), move |_| {
            reload();
            reload_albums();
            || {}
        });
    }

    let album_change = {
        let album_id = album_id.clone();
        let reload = reload.clone();
        let busy = busy.clone();
        let busy2 = busy.clone();
        Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlSelectElement = event.target_unchecked_into();
            album_id.set(input.value());
            busy.set(true);
            reload();
            busy2.set(false);
        })
    };

    let name_input = {
        let new_album = new_album.clone();
        Callback::from(move |event: yew::InputEvent| {
            let input: web_sys::HtmlInputElement = event.target_unchecked_into();
            new_album.set(input.value());
        })
    };

    let create = {
        let new_album = new_album.clone();
        let busy = busy.clone();
        let error = error.clone();
        let reload_albums = reload_albums.clone();
        Callback::from(move |_| {
            let name = (*new_album).trim().to_string();
            if name.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let reload_albums = reload_albums.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                match api::create_album(&name).await {
                    Ok(_) => reload_albums(),
                    Err(err) => error.set(err.to_string()),
                }
                busy.set(false);
            });
        })
    };

    let remove_album = {
        let busy = busy.clone();
        let error = error.clone();
        let album_id = album_id.clone();
        let reload_albums = reload_albums.clone();
        let reload = reload.clone();
        Callback::from(move |_| {
            let id = (*album_id).clone();
            if id.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let album_id = album_id.clone();
            let reload_albums = reload_albums.clone();
            let reload = reload.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::delete_album(&id).await {
                    error.set(err.to_string());
                }
                album_id.set(String::new());
                reload_albums();
                reload();
                busy.set(false);
            });
        })
    };

    let tiles: Html = items.iter().map(|item| {
        let album_options = albums.clone();
        let busy = busy.clone();
        let busy_for_tile = busy.clone();
        let error = error.clone();
        let reload = reload.clone();
        let file_id = item.id.clone();
        let add_change = Callback::from(move |event: yew::Event| {
            let input: web_sys::HtmlSelectElement = event.target_unchecked_into();
            let album_id = input.value();
            if album_id.is_empty() {
                return;
            }
            let busy = busy.clone();
            let error = error.clone();
            let reload = reload.clone();
            let file_id = file_id.clone();
            busy.set(true);
            wasm_bindgen_futures::spawn_local(async move {
                if let Err(err) = api::add_to_album(&album_id, &file_id).await {
                    error.set(err.to_string());
                }
                reload();
                busy.set(false);
            });
        });
        let media_src = if is_photo {
            format!("/api/v1/media/{}/thumbnail", item.id)
        } else {
            format!("/api/v1/files/{}/content", item.id)
        };
        html! {
            <article class="card media-tile" key={item.id.clone()}>
                {if is_photo {
                    html! { <img class="media-thumb" src={media_src} alt={item.name.clone()} loading="lazy" /> }
                } else {
                    html! { <video class="media-thumb" src={media_src} controls={true} preload="metadata" /> }
                }}
                <div class="media-info">
                    <span class="media-name">{item.name.clone()}</span>
                    <span class="media-meta mono-label">
                        {format!("{} \u{00B7} {}", human_size(item.size_bytes), format_date(&item.mtime, true))}
                    </span>
                    {(!is_photo).then(|| html! {
                        <span class="media-meta mono-label">
                            {item.duration_seconds
                                .map(|seconds| format!("{:.0}s", seconds))
                                .unwrap_or_else(|| "duration unavailable".into())}
                        </span>
                    })}
                    <span class="media-meta mono-label">
                        {item.width.map(|width| format!("{} px wide", width))
                            .unwrap_or_else(|| "size unknown".into())}
                    </span>
                    <label class="media-album mono-label">
                        {"Add to album"}
                        <select disabled={*busy_for_tile} onchange={add_change}>
                            <option value="">{"..."}</option>
                            {for album_options.iter().map(|album| html! {
                                <option key={album.id.clone()} value={album.id.clone()}>
                                    {album.name.clone()}
                                </option>
                            })}
                        </select>
                    </label>
                </div>
            </article>
        }
    }).collect::<Html>();

    html! {
        <div class="files-page">
            {eyebrow(None, if is_photo { "Photos" } else { "Videos" })}
            <div class="page-title-row">
                <h1>{if is_photo { "Photos" } else { "Videos" }}</h1>
                <div class="page-actions">
                    <span class="mono-label hint">
                        {format!("{} item{}", items.len(), if items.len() == 1 { "" } else { "s" })}
                    </span>
                </div>
            </div>
            <p class="page-sub">
                {if is_photo {
                    "Images uploaded to your server. EXIF/GPS is never retained."
                } else {
                    "Videos play straight from your server with byte-range streaming."
                }}
            </p>

            {(!error.is_empty()).then(|| html! { <div class="page-error">{(*error).clone()}</div> })}

            <section class="card recent-card">
                <div class="albums-bar">
                    <span class="mono-label">{"Album"}</span>
                    <select value={(*album_id).clone()} onchange={album_change}>
                        <option value="">{"All media"}</option>
                        {for albums.iter().map(|album| html! {
                            <option key={album.id.clone()} value={album.id.clone()}>
                                {format!("{} ({})", album.name, album.file_count)}
                            </option>
                        })}
                    </select>
                    <input value={(*new_album).clone()} oninput={name_input}
                           placeholder="New album name" />
                    <button class="ghost-btn mono-label" disabled={*busy || new_album.trim().is_empty()}
                            onclick={create}>{"Create"}</button>
                    <button class="ghost-btn mono-label danger" disabled={*busy || album_id.is_empty()}
                            onclick={remove_album}>{"Delete album"}</button>
                </div>
            </section>

            {if items.is_empty() {
                html! {
                    <section class="card recent-card">
                        <p class="recent-lede">
                            {if is_photo {
                                "No photos yet. Upload an image in My Files and it appears here."
                            } else {
                                "No videos yet. Upload a video in My Files and it appears here."
                            }}
                        </p>
                    </section>
                }
            } else {
                html! { <div class="media-grid">{tiles}</div> }
            }}

            {page_tagline("Your media never leaves this server.")}
        </div>
    }
}
