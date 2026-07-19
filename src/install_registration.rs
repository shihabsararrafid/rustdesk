use chrono::Utc;
use hbb_common::{config::Config, log, tokio};
use serde::{Deserialize, Serialize};
use std::{
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use uuid::Uuid;

const INSTALLATION_ID_OPTION: &str = "sasthotech-installation-id";
const NOTIFIED_OPTION: &str = "sasthotech-registration-notified";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
struct RegistrationPayload {
    installation_id: String,
    rustdesk_id: String,
    hostname: String,
    os: String,
    app_version: String,
    registered_at: String,
}

fn normalize_or_generate_id(existing: &str, generate: impl FnOnce() -> String) -> String {
    if Uuid::parse_str(existing).is_ok() {
        existing.to_owned()
    } else {
        generate()
    }
}

fn get_or_create_installation_id() -> String {
    let existing = Config::get_option(INSTALLATION_ID_OPTION);
    let installation_id =
        normalize_or_generate_id(&existing, || Uuid::new_v4().to_string());
    if installation_id != existing {
        Config::set_option(
            INSTALLATION_ID_OPTION.to_owned(),
            installation_id.clone(),
        );
    }
    installation_id
}

fn build_payload() -> RegistrationPayload {
    RegistrationPayload {
        installation_id: get_or_create_installation_id(),
        rustdesk_id: Config::get_id(),
        hostname: crate::common::hostname(),
        os: std::env::consts::OS.to_owned(),
        app_version: crate::VERSION.to_owned(),
        registered_at: Utc::now().to_rfc3339(),
    }
}

fn is_notified() -> bool {
    Config::get_option(NOTIFIED_OPTION) == "Y"
}

fn mark_notified() {
    Config::set_option(NOTIFIED_OPTION.to_owned(), "Y".to_owned());
}

#[derive(Serialize)]
struct RegistrationRequest<'a> {
    token: &'a str,
    #[serde(flatten)]
    payload: &'a RegistrationPayload,
}

#[derive(Debug, Deserialize)]
struct RegistrationResponse {
    accepted: bool,
    #[serde(default)]
    duplicate: bool,
}

fn parse_response(body: &str) -> bool {
    serde_json::from_str::<RegistrationResponse>(body)
        .map(|response| response.accepted)
        .unwrap_or(false)
}

static IN_FLIGHT: AtomicBool = AtomicBool::new(false);
static EXHAUSTED_THIS_PROCESS: AtomicBool = AtomicBool::new(false);

fn endpoint_config() -> Option<(&'static str, &'static str)> {
    let url = option_env!("SASTHOTECH_REGISTRATION_URL")?.trim();
    let token = option_env!("SASTHOTECH_REGISTRATION_TOKEN")?.trim();
    if url.starts_with("https://") && !token.is_empty() {
        Some((url, token))
    } else {
        None
    }
}

async fn send_registration(
    url: &str,
    token: &str,
    payload: &RegistrationPayload,
) -> Result<bool, reqwest::Error> {
    let client = reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::limited(3))
        .build()?;
    let response = client
        .post(url)
        .json(&RegistrationRequest { token, payload })
        .send()
        .await?
        .error_for_status()?;
    Ok(parse_response(&response.text().await?))
}

pub fn notify_after_server_registration() {
    if is_notified() || EXHAUSTED_THIS_PROCESS.load(Ordering::SeqCst) {
        return;
    }
    let Some((url, token)) = endpoint_config() else {
        return;
    };
    if IN_FLIGHT
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return;
    }
    let payload = build_payload();
    tokio::spawn(async move {
        for delay_seconds in [0, 30, 120] {
            if delay_seconds > 0 {
                tokio::time::sleep(Duration::from_secs(delay_seconds)).await;
            }
            match send_registration(url, token, &payload).await {
                Ok(true) => {
                    mark_notified();
                    IN_FLIGHT.store(false, Ordering::SeqCst);
                    return;
                }
                Ok(false) => {
                    log::warn!("Client registration webhook rejected the payload")
                }
                Err(error) => {
                    log::warn!("Client registration webhook failed: {error}")
                }
            }
        }
        EXHAUSTED_THIS_PROCESS.store(true, Ordering::SeqCst);
        IN_FLIGHT.store(false, Ordering::SeqCst);
    });
}

#[cfg(test)]
mod response_tests {
    use super::*;

    #[test]
    fn accepts_new_and_duplicate_success_responses() {
        assert!(parse_response(r#"{"accepted":true,"duplicate":false}"#));
        assert!(parse_response(r#"{"accepted":true,"duplicate":true}"#));
    }

    #[test]
    fn rejects_malformed_or_negative_responses() {
        assert!(!parse_response("not json"));
        assert!(!parse_response(r#"{"accepted":false}"#));
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payload_serialization_contains_only_approved_fields() {
        let payload = RegistrationPayload {
            installation_id: "3d9d36e2-70c1-4c1d-a63d-cf45f314e922".into(),
            rustdesk_id: "123456789".into(),
            hostname: "front-desk".into(),
            os: "windows".into(),
            app_version: "1.4.9".into(),
            registered_at: "2026-07-19T12:00:00Z".into(),
        };
        let value = serde_json::to_value(payload).unwrap();
        assert_eq!(value.as_object().unwrap().len(), 6);
        assert!(value.get("public_ip").is_none());
        assert!(value.get("username").is_none());
        assert!(value.get("hardware").is_none());
    }

    #[test]
    fn valid_installation_id_is_reused() {
        let existing = "3d9d36e2-70c1-4c1d-a63d-cf45f314e922";
        assert_eq!(normalize_or_generate_id(existing, || unreachable!()), existing);
    }

    #[test]
    fn invalid_installation_id_is_replaced() {
        let generated = "d9994a64-b08b-4657-8d2f-ac74793f8288";
        assert_eq!(
            normalize_or_generate_id("not-a-uuid", || generated.to_owned()),
            generated
        );
    }
}
