"""Source-boundary regressions, not a substitute for Rust/Flutter compilation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EmployeeSourceContracts(unittest.TestCase):
    def test_authorization_precedes_native_connection(self):
        source = (ROOT / 'src/client.rs').read_text()
        start = source[source.index('pub async fn start('):source.index('async fn _start(')]
        self.assertLess(start.index('employee_management::authorize'), start.index('Self::_start'))

    def test_customer_builds_are_not_managed_by_default(self):
        source = (ROOT / 'src/employee_management.rs').read_text()
        self.assertIn('option_env!("SASTHOTECH_EMPLOYEE_MODE") == Some("1")', source)
        self.assertIn('is_valid_untrusted_peer_id(target)', source)
        self.assertIn('redirect(reqwest::redirect::Policy::none())', source)

    def test_clipboard_direct_path_checks_policy(self):
        source = (ROOT / 'src/client/io_loop.rs').read_text()
        path = source[source.index('async fn handle_local_clipboard_msg('):source.index('async fn handle_msg_from_ui(')]
        self.assertLess(path.index('!a.policy.allow_clipboard'), path.index('peer.send(&msg)'))
        self.assertIn('!a.policy.allow_file_transfer', path)

    def test_tunnel_runtime_joins_audit_tasks(self):
        source = (ROOT / 'src/port_forward.rs').read_text()
        self.assertIn('tokio::task::JoinSet::new()', source)
        self.assertIn('shutdown.send(true)', source)
        self.assertIn('forwards.join_next().await', source)
        self.assertIn('audit.flush().await', source)
        outer = (ROOT / 'src/ui_session_interface.rs').read_text()
        self.assertIn('listeners.join_next().await', outer)
        self.assertIn('queue.send(Data::Close)', outer)

    def test_original_connection_surface_remains_accessible(self):
        source = (ROOT / 'flutter/lib/desktop/widgets/employee_directory.dart').read_text()
        self.assertIn('TabBarView(children: [directory, widget.child])', source)
        self.assertIn('SizedBox(width: 96', source)


if __name__ == '__main__':
    unittest.main()
