//! Employee-build authorization. This is not enforcement on unmanaged clients.
use hbb_common::{bail, config::LocalConfig, log, rendezvous_proto::ConnType, tokio, ResultType};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;
use tokio::sync::mpsc;

pub fn api_url() -> Option<&'static str> {
    if option_env!("SASTHOTECH_EMPLOYEE_MODE") == Some("1") {
        Some(option_env!("SASTHOTECH_EMPLOYEE_API").unwrap_or(""))
    } else {
        None
    }
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Policy {
    pub allow_remote_control: bool,
    pub allow_file_transfer: bool,
    pub allow_clipboard: bool,
    pub allow_tcp_tunnel: bool,
    pub allow_terminal: bool,
    pub allow_camera: bool,
}

impl Policy {
    pub fn permits_message(&self, msg: &hbb_common::message_proto::Message) -> bool {
        use hbb_common::message_proto::message::Union;
        match &msg.union {
            Some(Union::Clipboard(_)) | Some(Union::MultiClipboards(_)) => self.allow_clipboard,
            Some(Union::Cliprdr(_)) => self.allow_clipboard && self.allow_file_transfer,
            Some(Union::FileAction(_)) | Some(Union::FileResponse(_)) => self.allow_file_transfer,
            _ => true,
        }
    }

    pub fn permits_data(&self, data: &crate::client::Data) -> bool {
        use crate::client::Data;
        match data {
            Data::Message(message) => self.permits_message(message),
            Data::SendFiles(_) | Data::AddJob(_) | Data::ResumeJob(_) | Data::RemoveDirAll(_)
            | Data::ConfirmDeleteFiles(_) | Data::RemoveDir(_) | Data::RemoveFile(_)
            | Data::CreateDir(_) | Data::SetConfirmOverrideFile(_) | Data::RenameFile(_) => self.allow_file_transfer,
            _ => true,
        }
    }
}

#[derive(Deserialize)]
struct Authorization {
    id: String,
    target_id: String,
    employee_id: String,
    policy: Policy,
}

struct Event {
    id: uuid::Uuid,
    kind: &'static str,
    outcome: Option<&'static str>,
}

pub struct Audit {
    pub policy: Policy,
    sender: mpsc::Sender<Event>,
    authenticated: AtomicBool,
    finished: AtomicBool,
    worker: Option<tokio::task::JoinHandle<()>>,
}

impl Audit {
    pub async fn flush(mut self) {
        self.finish("connection_error");
        if let Some(worker) = self.worker.take() {
            if tokio::time::timeout(Duration::from_secs(40), worker).await.is_err() {
                log::warn!("Employee audit flush timed out; reporting incomplete");
            }
        }
    }
    pub fn authenticated(&self) {
        if !self.authenticated.swap(true, Ordering::SeqCst) {
            self.enqueue("authenticated", None);
        }
    }

    pub fn finish(&self, outcome: &'static str) {
        if !self.finished.swap(true, Ordering::SeqCst) {
            self.enqueue(if self.authenticated.load(Ordering::SeqCst) { "closed" } else { "failed" },
                         Some(if outcome == "completed" && !self.authenticated.load(Ordering::SeqCst) { "cancelled" } else { outcome }));
        }
    }

    fn enqueue(&self, kind: &'static str, outcome: Option<&'static str>) {
        if self.sender.try_send(Event { id: uuid::Uuid::new_v4(), kind, outcome }).is_err() {
            log::warn!("Employee audit event queue unavailable; session reporting incomplete");
        }
    }
}

impl Drop for Audit {
    fn drop(&mut self) {
        self.finish("connection_error");
    }
}

fn mode(conn_type: ConnType) -> ResultType<&'static str> {
    match conn_type {
        ConnType::DEFAULT_CONN => Ok("remote_control"),
        ConnType::FILE_TRANSFER => Ok("file_transfer"),
        ConnType::PORT_FORWARD => Ok("tcp_tunnel"),
        ConnType::RDP => Ok("rdp"),
        ConnType::TERMINAL => Ok("terminal"),
        ConnType::VIEW_CAMERA => Ok("camera"),
        _ => bail!("Unsupported managed connection mode"),
    }
}

fn client(base: &str) -> ResultType<reqwest::Client> {
    let parsed = url::Url::parse(base)?;
    if parsed.scheme() != "https" || parsed.host_str().is_none()
        || !parsed.username().is_empty() || parsed.password().is_some()
        || parsed.query().is_some() || parsed.fragment().is_some()
        || parsed.path() != "/"
    {
        bail!("Employee management requires an HTTPS origin without credentials or a path");
    }
    Ok(reqwest::Client::builder().connect_timeout(Duration::from_secs(5))
       .timeout(Duration::from_secs(10)).redirect(reqwest::redirect::Policy::none()).build()?)
}

pub async fn authorize(target: &str, conn_type: ConnType) -> ResultType<Option<Audit>> {
    let base = match api_url() { Some(base) => base.trim_end_matches('/'), None => return Ok(None) };
    // Preserve the exact normalized native target, including direct endpoints
    // and alternate-server suffixes; never audit a stripped, different ID.
    if !crate::common::is_valid_untrusted_peer_id(target) {
        bail!("Invalid managed connection target");
    }
    let token = LocalConfig::get_option("access_token");
    if token.is_empty() { bail!("Sign in to your employee account before connecting"); }
    let http = client(base)?;
    let request_id = uuid::Uuid::new_v4();
    let body = serde_json::json!({"request_id": request_id.to_string(), "target_id": target, "mode": mode(conn_type)?});
    let response = http.post(format!("{base}/api/management/sessions")).bearer_auth(&token)
        .json(&body).send().await.map_err(|_| hbb_common::anyhow::anyhow!("Employee authorization service unavailable"))?;
    if !response.status().is_success() {
        bail!("Employee authorization denied (HTTP {})", response.status().as_u16());
    }
    let auth: Authorization = response.json().await?;
    if auth.target_id != target || auth.employee_id.is_empty() || uuid::Uuid::parse_str(&auth.id).is_err() {
        bail!("Invalid employee authorization response");
    }
    let (sender, mut receiver) = mpsc::channel::<Event>(8);
    let endpoint = format!("{base}/api/management/sessions/{}/events", auth.id);
    let worker = tokio::spawn(async move {
        let mut tick = tokio::time::interval(Duration::from_secs(30));
        let mut reporting = false;
        let mut telemetry_gap = false;
        loop {
            let event = tokio::select! {
                item = receiver.recv() => match item { Some(item) => item, None => break },
                _ = tick.tick(), if reporting => Event { id: uuid::Uuid::new_v4(), kind: "heartbeat", outcome: None },
            };
            let body = serde_json::json!({"event_id": event.id.to_string(), "kind": event.kind,
                "outcome": event.outcome, "telemetry_gap": telemetry_gap});
            let mut delivered = false;
            for attempt in 0..3 {
                match http.post(&endpoint).bearer_auth(&token).json(&body).send().await {
                    Ok(response) if response.status().is_success() => { delivered = true; break; }
                    Ok(response) if response.status().is_client_error() => break,
                    _ => tokio::time::sleep(Duration::from_secs(1 << attempt)).await,
                }
            }
            if !delivered {
                telemetry_gap = true;
                log::warn!("Employee audit delivery failed; report may contain a telemetry gap");
                // Do not keep an unauthenticated server record alive with
                // heartbeats after losing its authentication transition.
                if event.kind == "authenticated" { break; }
            } else {
                telemetry_gap = false;
            }
            if event.kind == "authenticated" { reporting = true; }
            if event.kind == "closed" || event.kind == "failed" { break; }
        }
    });
    Ok(Some(Audit { policy: auth.policy, sender, authenticated: AtomicBool::new(false), finished: AtomicBool::new(false), worker: Some(worker) }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validates_managed_origin_without_network() {
        assert!(client("http://example.com").is_err());
        assert!(client("https://user:secret@example.com").is_err());
        assert!(client("https://example.com/path").is_err());
        assert!(client("https://example.com?token=secret").is_err());
    }

    #[test]
    fn maps_all_existing_connection_modes() {
        assert_eq!(mode(ConnType::RDP).unwrap(), "rdp");
        assert_eq!(mode(ConnType::VIEW_CAMERA).unwrap(), "camera");
        assert_eq!(mode(ConnType::TERMINAL).unwrap(), "terminal");
        assert_eq!(mode(ConnType::FILE_TRANSFER).unwrap(), "file_transfer");
    }
}
