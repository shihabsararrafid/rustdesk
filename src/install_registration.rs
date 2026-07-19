use chrono::Utc;
use hbb_common::config::Config;
use serde::{Deserialize, Serialize};
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
