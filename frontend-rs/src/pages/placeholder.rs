//! Honest placeholder for pages that ship in later phases — labeled as such,
//! no fake data, no pretend functionality (spec rules 11 / 22).

use yew::prelude::*;

use crate::layout::{page_tagline, page_title};

#[function_component(PlaceholderPage)]
pub fn placeholder_page() -> Html {
    html! {
        <div>
            {page_title("Coming up")}
            <div class="placeholder-body card">
                <p class="mono-label">{"Not built yet"}</p>
                <p>
                    {"This feature ships in a later phase of the build plan. The navigation"}
                    {"stays honest about it rather than showing placeholder content."}
                </p>
            </div>
            {page_tagline("Built in order. Nothing faked.")}
        </div>
    }
}
