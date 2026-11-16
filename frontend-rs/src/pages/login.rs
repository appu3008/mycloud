//! Login / first-run enrollment screen (Figma node 1:70).

use yew::prelude::*;
use yew_router::prelude::*;

use crate::auth::authenticate;
use crate::Route;
use crate::ICON_ARROW_BTN;
use crate::ICON_LOCK;

fn eye_icon(open: bool) -> Html {
    // The design's toggle glyph (Figma 1:70), with a slash added when revealed.
    let mut html = yew::html! {
        <svg width="17" height="17" viewBox="0 0 21 21" fill="none" aria-hidden="true">
            <path
                d="M1.75 10.5C1.75 10.5 4.8125 4.375 10.5 4.375C16.1875 4.375 19.25 10.5 19.25 10.5C19.25 10.5 16.1875 16.625 10.5 16.625C4.8125 16.625 1.75 10.5 1.75 10.5Z"
                stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
            />
            <circle cx="10.5" cy="10.5" r="2.625" stroke="currentColor" stroke-width="1.6" />
        </svg>
    };
    if open {
        html = yew::html! {
            <svg width="17" height="17" viewBox="0 0 21 21" fill="none" aria-hidden="true">
                <path
                    d="M1.75 10.5C1.75 10.5 4.8125 4.375 10.5 4.375C16.1875 4.375 19.25 10.5 19.25 10.5C19.25 10.5 16.1875 16.625 10.5 16.625C4.8125 16.625 1.75 10.5 1.75 10.5Z"
                    stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
                />
                <circle cx="10.5" cy="10.5" r="2.625" stroke="currentColor" stroke-width="1.6" />
                <path d="M3 3l15 15" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
        };
    }
    html
}

#[derive(Clone, PartialEq, Properties)]
pub struct LoginPageProps {
    pub enrollment_open: bool,
    pub on_logged_in: yew::Callback<crate::api::MyCloudUser>,
}

#[function_component(LoginPage)]
pub fn login_page(props: &LoginPageProps) -> Html {
    let email = use_state(String::new);
    let display_name = use_state(String::new);
    let password = use_state(String::new);
    let show_password = use_state(|| false);
    let error = use_state(String::new);
    let busy = use_state(|| false);
    let navigator = use_navigator().unwrap();

    let enrollment_open = props.enrollment_open;

    let on_submit = {
        let email = email.clone();
        let display_name = display_name.clone();
        let password = password.clone();
        let error = error.clone();
        let busy = busy.clone();
        let navigator = navigator.clone();
        let on_logged_in = props.on_logged_in.clone();
        Callback::from(move |event: web_sys::SubmitEvent| {
            event.prevent_default();
            let email_value = (*email).clone();
            let password_value = (*password).clone();
            let display_name_value = (*display_name).clone();
            let navigator = navigator.clone();
            let on_logged_in = on_logged_in.clone();
            let error = error.clone();
            let busy = busy.clone();
            wasm_bindgen_futures::spawn_local(async move {
                busy.set(true);
                error.set(String::new());
                match authenticate(&email_value, &password_value, &display_name_value, enrollment_open).await {
                    Ok(result) => {
                        on_logged_in.emit(result.user);
                        navigator.replace(&Route::Overview);
                    }
                    Err(message) => {
                        error.set(message);
                        busy.set(false);
                    }
                }
            });
        })
    };

    let email_oninput = {
        let email = email.clone();
        Callback::from(move |e: yew::InputEvent| {
            email.set(e.target_unchecked_into::<web_sys::HtmlInputElement>().value());
        })
    };
    let display_name_oninput = {
        let display_name = display_name.clone();
        Callback::from(move |e: yew::InputEvent| {
            display_name.set(e.target_unchecked_into::<web_sys::HtmlInputElement>().value());
        })
    };
    let password_oninput = {
        let password = password.clone();
        Callback::from(move |e: yew::InputEvent| {
            password.set(e.target_unchecked_into::<web_sys::HtmlInputElement>().value());
        })
    };
    let toggle_password = {
        let show_password = show_password.clone();
        Callback::from(move |_| show_password.set(!*show_password))
    };

    let badge = if enrollment_open { "First-run setup" } else { "Administrator account access" };
    let heading = if enrollment_open { "Create the administrator." } else { "Welcome back to your account." };
    let sub = if enrollment_open {
        "Claim this cloud. The window closes permanently once the first admin exists."
    } else {
        "Sign in to access your personal cloud and manage your files."
    };
    let password_placeholder = if enrollment_open {
        "Choose a long, unique password"
    } else {
        "Enter the password for your administrator account"
    };
    let password_autocomplete = if enrollment_open { "new-password" } else { "current-password" };
    let submit_label = if *busy {
        "Working\u{2026}"
    } else if enrollment_open {
        "Create the administrator"
    } else {
        "Sign in to your account"
    };

    html! {
        <div class="login-wrap">
            <form class="login-card" onsubmit={on_submit}>
                <span class="login-badge mono-label">{badge}</span>
                <h1>{heading}</h1>
                <p class="login-sub">{sub}</p>

                <label class="login-field">
                    <span>{"Enter your email address"}</span>
                    <input
                        type="email"
                        value={(*email).clone()}
                        oninput={email_oninput}
                        placeholder="you@example.com"
                        autocomplete="username"
                        required={true}
                    />
                </label>

                {enrollment_open.then(|| html! {
                    <label class="login-field">
                        <span>{"Display name"}</span>
                        <input
                            type="text"
                            value={(*display_name).clone()}
                            oninput={display_name_oninput}
                            placeholder="Shown in the UI"
                            required={true}
                        />
                    </label>
                })}

                <label class="login-field">
                    <span>{"Enter your password"}</span>
                    <div class="password-box">
                        <input
                            type={if *show_password { "text" } else { "password" }}
                            value={(*password).clone()}
                            oninput={password_oninput}
                            placeholder={password_placeholder}
                            autocomplete={password_autocomplete}
                            minlength={if enrollment_open { "10" } else { "1" }}
                            required={true}
                        />
                        <button type="button" class="eye-toggle" onclick={toggle_password}
                                aria-label={if *show_password { "Hide password" } else { "Show password" }}>
                            {eye_icon(*show_password)}
                        </button>
                    </div>
                </label>

                {(!error.is_empty()).then(|| html! { <div class="form-error">{(*error).clone()}</div> })}

                <button class="primary-btn login-submit" type="submit" disabled={*busy}>
                    <span>{submit_label}</span>
                    {(!*busy).then(|| html! { <img src={ICON_ARROW_BTN} alt="" width={20} height={20} /> })}
                </button>

                <div class={classes!("login-note", enrollment_open.then_some("open"))}>
                    <img src={ICON_LOCK} alt="" width={18} height={18} />
                    <p>
                        {if enrollment_open {
                            "One-time window: the first account created here owns the server. It closes forever afterwards."
                        } else {
                            "New administrator enrollment is currently closed. Only an existing administrator can sign in and access this cloud."
                        }}
                    </p>
                </div>

                <div class="login-tagline">
                    {"Your personal cloud begins at home, keeping your files close and accessible."}
                </div>
            </form>
        </div>
    }
}
