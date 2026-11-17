//! Optional client-side end-to-end encryption (E2E vault).
//!
//! Encryption happens in the browser with WebCrypto (PBKDF2-SHA-256,
//! 250 000 iterations -> AES-256-GCM). The passphrase and plaintext never
//! leave the browser; the server only ever stores the opaque envelope below.
//! There is no key recovery: losing the passphrase loses the data.
//!
//! Envelope layout: b"MYCE1" | salt[16] | iv[12] | AES-GCM ciphertext+tag.

use js_sys::{Array, ArrayBuffer, Object, Reflect, Uint8Array};
use wasm_bindgen::{JsCast, JsValue};
use wasm_bindgen_futures::JsFuture;
use web_sys::{CryptoKey, SubtleCrypto};

const MAGIC: &[u8; 5] = b"MYCE1";
const SALT_BYTES: usize = 16;
const IV_BYTES: usize = 12;
const ITERATIONS: u32 = 250_000;

fn subtle() -> Result<SubtleCrypto, String> {
    let subtle = web_sys::window()
        .ok_or_else(|| "no browser window".to_string())?
        .crypto()
        .map_err(|_| "WebCrypto unavailable (use HTTPS or localhost)".to_string())?
        .subtle();
    Ok(subtle)
}

fn set(target: &Object, key: &str, value: &JsValue) -> Result<(), String> {
    Reflect::set(target, &JsValue::from_str(key), value)
        .map_err(|_| format!("could not set {key}"))?;
    Ok(())
}

fn bytes(value: &[u8]) -> Object {
    let array = Uint8Array::new_with_length(value.len() as u32);
    array.copy_from(value);
    array.into()
}

fn random(len: usize) -> Result<Vec<u8>, String> {
    let mut buffer = vec![0u8; len];
    web_sys::window()
        .ok_or_else(|| "no browser window".to_string())?
        .crypto()
        .map_err(|_| "WebCrypto unavailable".to_string())?
        .get_random_values_with_u8_array(&mut buffer)
        .map_err(|_| "could not generate random bytes".to_string())?;
    Ok(buffer)
}

async fn derive_key(subtle: &SubtleCrypto, passphrase: &str, salt: &[u8]) -> Result<CryptoKey, String> {
    let base_usages = Array::of1(&JsValue::from_str("deriveKey"));
    let base = JsFuture::from(
        subtle
            .import_key_with_str("raw", &bytes(passphrase.as_bytes()), "PBKDF2", false, &base_usages)
            .map_err(|_| "could not import passphrase".to_string())?,
    )
    .await
    .map_err(|_| "could not import passphrase".to_string())?
    .unchecked_into::<CryptoKey>();

    let params = Object::new();
    set(&params, "name", &JsValue::from_str("PBKDF2"))?;
    set(&params, "salt", &bytes(salt))?;
    set(&params, "iterations", &JsValue::from_f64(ITERATIONS as f64))?;
    set(&params, "hash", &JsValue::from_str("SHA-256"))?;

    let derived = Object::new();
    set(&derived, "name", &JsValue::from_str("AES-GCM"))?;
    set(&derived, "length", &JsValue::from_f64(256.0))?;

    let usages = Array::of2(&JsValue::from_str("encrypt"), &JsValue::from_str("decrypt"));
    JsFuture::from(
        subtle
            .derive_key_with_str_and_object("PBKDF2", &base, &derived, false, &usages)
            .map_err(|_| "could not derive key".to_string())?,
    )
    .await
    .map_err(|_| "could not derive key (wrong passphrase?)".to_string())
    .map(|value| value.unchecked_into::<CryptoKey>())
}

fn to_vec(value: JsValue) -> Result<Vec<u8>, String> {
    let buffer = value
        .dyn_into::<ArrayBuffer>()
        .map_err(|_| "unexpected crypto result".to_string())?;
    Ok(Uint8Array::new(&buffer).to_vec())
}

/// Encrypt plaintext into a self-describing vault envelope.
pub async fn encrypt(passphrase: &str, plaintext: &[u8]) -> Result<Vec<u8>, String> {
    if passphrase.len() < 8 {
        return Err("passphrase must be at least 8 characters".to_string());
    }
    let subtle = subtle()?;
    let salt = random(SALT_BYTES)?;
    let iv = random(IV_BYTES)?;
    let key = derive_key(&subtle, passphrase, &salt).await?;

    let params = Object::new();
    set(&params, "name", &JsValue::from_str("AES-GCM"))?;
    set(&params, "iv", &bytes(&iv))?;
    set(&params, "tagLength", &JsValue::from_f64(128.0))?;

    let ciphertext = to_vec(
        JsFuture::from(
            subtle
                .encrypt_with_str_and_buffer_source("AES-GCM", &key, &params)
                .map_err(|_| "encryption failed".to_string())?,
        )
        .await
        .map_err(|_| "encryption failed".to_string())?,
    )?;

    let mut envelope = Vec::with_capacity(MAGIC.len() + SALT_BYTES + IV_BYTES + ciphertext.len());
    envelope.extend_from_slice(MAGIC);
    envelope.extend_from_slice(&salt);
    envelope.extend_from_slice(&iv);
    envelope.extend_from_slice(&ciphertext);
    Ok(envelope)
}

/// Offer decrypted bytes to the browser as a download (no server round-trip).
pub fn download_bytes(filename: &str, bytes: &[u8]) -> Result<(), String> {
    use web_sys::HtmlAnchorElement;

    let parts = Array::of1(&Uint8Array::from(bytes).into());
    let blob = web_sys::Blob::new_with_u8_array_sequence(&parts)
        .map_err(|_| "could not build download blob".to_string())?;
    let url = web_sys::Url::create_object_url_with_blob(&blob)
        .map_err(|_| "could not create download URL".to_string())?;
    let document = web_sys::window()
        .ok_or_else(|| "no browser window".to_string())?
        .document()
        .ok_or_else(|| "no document".to_string())?;
    let anchor = document
        .create_element("a")
        .map_err(|_| "could not create link".to_string())?
        .dyn_into::<HtmlAnchorElement>()
        .map_err(|_| "could not create link".to_string())?;
    anchor.set_href(&url);
    anchor.set_download(filename);
    anchor.click();
    let _ = web_sys::Url::revoke_object_url(&url);
    Ok(())
}

/// Decrypt a vault envelope produced by `encrypt`.
pub async fn decrypt(passphrase: &str, envelope: &[u8]) -> Result<Vec<u8>, String> {
    let header = MAGIC.len() + SALT_BYTES + IV_BYTES;
    if envelope.len() < header || &envelope[..MAGIC.len()] != MAGIC {
        return Err("not a MyCloud vault file".to_string());
    }
    let salt = &envelope[MAGIC.len()..MAGIC.len() + SALT_BYTES];
    let iv = &envelope[MAGIC.len() + SALT_BYTES..header];
    let ciphertext = &envelope[header..];

    let subtle = subtle()?;
    let key = derive_key(&subtle, passphrase, salt).await?;
    let params = Object::new();
    set(&params, "name", &JsValue::from_str("AES-GCM"))?;
    set(&params, "iv", &bytes(iv))?;
    set(&params, "tagLength", &JsValue::from_f64(128.0))?;

    to_vec(
        JsFuture::from(
            subtle
                .decrypt_with_str_and_buffer_source("AES-GCM", &key, &params)
                .map_err(|_| "decryption failed".to_string())?,
        )
        .await
        .map_err(|_| "wrong passphrase or corrupted vault file".to_string())?,
    )
}
