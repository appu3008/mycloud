//! Auth state for the app (mirrors AuthContext): /me on boot, login/enroll,
//! logout, and the enrollment window status shown by the login screen.

use yew::prelude::*;

use crate::api::{self, MyCloudUser};
use crate::util;

#[derive(Clone, PartialEq)]
pub struct AuthState {
    pub user: Option<MyCloudUser>,
    pub loading: bool,
    pub enrollment_open: bool,
}

#[derive(Clone, PartialEq)]
pub struct LoginResult {
    pub user: MyCloudUser,
}

impl AuthState {
    pub fn role_label(&self) -> &'static str {
        if self.user.as_ref().map(|u| u.role.as_str()) == Some("admin") {
            "Administrator"
        } else {
            "Member"
        }
    }
}

/// Probe `/me`, then the enrollment status when unauthenticated.
pub async fn bootstrap(on_user_changed: Callback<Option<LoginResult>>, on_enrollment: Callback<bool>) {
    let user = match api::me().await {
        Ok(me) => Some(me),
        Err(_) => {
            let open = api::enrollment_status()
                .await
                .map(|status| status.enrollment_open)
                .unwrap_or(false);
            on_enrollment.emit(open);
            None
        }
    };
    on_user_changed.emit(user.map(|user| LoginResult { user }));
}

/// Perform a login (or first-run enrollment) and remember the CSRF token.
pub async fn authenticate(
    email: &str,
    password: &str,
    display_name: &str,
    enroll: bool,
) -> Result<LoginResult, String> {
    if enroll {
        if !email.contains('@') {
            return Err("Email looks invalid".into());
        }
        let payload = api::enroll(email, display_name, password)
            .await
            .map_err(|err| err.message.clone())?;
        util::set_csrf_token(&payload.csrf_token, true);
        Ok(LoginResult { user: payload.user })
    } else {
        let payload = api::login(email, password)
            .await
            .map_err(|err| err.message.clone())?;
        util::set_csrf_token(&payload.csrf_token, true);
        Ok(LoginResult { user: payload.user })
    }
}
