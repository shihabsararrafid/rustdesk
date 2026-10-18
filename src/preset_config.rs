// Single source of truth for Sasthotech's custom-client configuration.
// Change these values and rebuild to retarget the client.
use hbb_common::config;

pub const PRESET_ID_SERVER: &str = "185.202.236.146";
pub const PRESET_RELAY_SERVER: &str = "185.202.236.146";
pub const PRESET_KEY: &str = "K0CUWJeu+T6GD12zdvpcn1f5uJbDSgvdG5qEpW6K7xQ=";
pub const PRESET_APP_NAME: &str = "Sasthotech Remote";

// Preset permanent password (overridable). Hash only — never plaintext.
// Format: "00" + base64(SHA256(password || salt)). Regenerate to rotate.
pub const PRESET_PASSWORD_STORAGE: &str = "00eyl15sYlCDaN4SEJq/iyD1sPR5nAKixwltCxcRl+5UE=";
pub const PRESET_PASSWORD_SALT: &str = "2ZVNxXswWhRcRYuDF7b9Ox1U5sosQyKE";

/// Seed built-in defaults. Called once at startup from `load_custom_client()`,
/// before user config is read, so these act as editable prefilled defaults
/// (a value the user later saves locally wins via the normal option lookup).
pub fn apply() {
    if let Some(url) = crate::employee_management::api_url() {
        let mut enforced = config::OVERWRITE_SETTINGS.write().unwrap();
        enforced.insert("api-server".to_owned(), url.to_owned());
        enforced.insert("employee-management-url".to_owned(), url.to_owned());
    }
    *config::APP_NAME.write().unwrap() = PRESET_APP_NAME.to_owned();

    {
        let mut d = config::DEFAULT_SETTINGS.write().unwrap();
        d.insert(
            config::keys::OPTION_CUSTOM_RENDEZVOUS_SERVER.to_owned(),
            PRESET_ID_SERVER.to_owned(),
        );
        d.insert(
            config::keys::OPTION_RELAY_SERVER.to_owned(),
            PRESET_RELAY_SERVER.to_owned(),
        );
        d.insert(config::keys::OPTION_KEY.to_owned(), PRESET_KEY.to_owned());
    }

    {
        let mut h = config::HARD_SETTINGS.write().unwrap();
        h.insert("password".to_owned(), PRESET_PASSWORD_STORAGE.to_owned());
        h.insert("salt".to_owned(), PRESET_PASSWORD_SALT.to_owned());
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use hbb_common::config;

    #[test]
    fn test_apply_seeds_network_defaults_and_app_name() {
        apply();
        let d = config::DEFAULT_SETTINGS.read().unwrap();
        assert_eq!(
            d.get(config::keys::OPTION_CUSTOM_RENDEZVOUS_SERVER)
                .map(String::as_str),
            Some(PRESET_ID_SERVER)
        );
        assert_eq!(
            d.get(config::keys::OPTION_RELAY_SERVER).map(String::as_str),
            Some(PRESET_RELAY_SERVER)
        );
        assert_eq!(
            d.get(config::keys::OPTION_KEY).map(String::as_str),
            Some(PRESET_KEY)
        );
        assert_eq!(*config::APP_NAME.read().unwrap(), PRESET_APP_NAME);
    }

    #[test]
    fn test_preset_password_is_valid_and_applied() {
        // Format must be accepted by the auth path.
        assert!(config::preset_permanent_password_storage_is_usable_for_auth(
            PRESET_PASSWORD_STORAGE,
            PRESET_PASSWORD_SALT
        ));
        apply();
        let h = config::HARD_SETTINGS.read().unwrap();
        assert_eq!(
            h.get("password").map(String::as_str),
            Some(PRESET_PASSWORD_STORAGE)
        );
        assert_eq!(
            h.get("salt").map(String::as_str),
            Some(PRESET_PASSWORD_SALT)
        );
    }
}
