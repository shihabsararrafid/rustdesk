"""Source-level regression checks for client registration hooks.

Cargo is not required: these tests verify the committed source contracts that
CI and Apps Script depend on.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "src/lib.rs"
MEDIATOR = ROOT / "src/rendezvous_mediator.rs"
REGISTRATION = ROOT / "src/install_registration.rs"

DESKTOP_CFG = (
    '#[cfg(any(target_os = "windows", target_os = "linux", target_os = "macos"))]'
)
NOTIFY = "crate::install_registration::notify_after_server_registration()"


class RegistrationSourceTests(unittest.TestCase):
    def test_module_is_desktop_gated(self):
        text = LIB.read_text()
        self.assertRegex(
            text,
            re.compile(
                r'#\[cfg\(any\(target_os = "windows", target_os = "linux", '
                r'target_os = "macos"\)\)\]\s*mod install_registration;',
                re.MULTILINE,
            ),
        )

    def test_authoritative_rendezvous_hooks_are_present(self):
        text = MEDIATOR.read_text()
        peer = text.index("RegisterPeerResponse(rpr)")
        peer_hook = text.index(NOTIFY, peer)
        peer_cfg = text.rfind(DESKTOP_CFG, peer, peer_hook)
        self.assertNotEqual(peer_cfg, -1)
        self.assertIn("if rpr.request_pk", text[peer:peer_hook])
        self.assertIn("else", text[peer:peer_hook])

        pk = text.index("RegisterPkResponse(rpr)")
        pk_ok = text.index("register_pk_response::Result::OK", pk)
        pk_hook = text.index(NOTIFY, pk_ok)
        pk_cfg = text.rfind(DESKTOP_CFG, pk_ok, pk_hook)
        self.assertNotEqual(pk_cfg, -1)
        self.assertLess(pk_ok, pk_hook)

        # Both authoritative paths must call the same notify entry point.
        self.assertEqual(text.count(NOTIFY), 2)

    def test_bounded_retry_delays_and_completion_gate(self):
        text = REGISTRATION.read_text()
        self.assertIn("for delay_seconds in [0, 30, 120]", text)
        ok_true = re.search(
            r"Ok\(true\)\s*=>\s*\{[^}]*mark_notified\(\)",
            text,
            re.DOTALL,
        )
        self.assertIsNotNone(ok_true)
        self.assertIn("EXHAUSTED_THIS_PROCESS.store(true", text)
        rejected = text.index("Ok(false) =>")
        exhausted = text.index("EXHAUSTED_THIS_PROCESS.store(true")
        self.assertNotIn("mark_notified()", text[rejected:exhausted])
