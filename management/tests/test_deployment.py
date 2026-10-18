from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_isolated_local_deployment():
    compose = (ROOT / 'compose.yml').read_text()
    assert '127.0.0.1:21114:21114' in compose
    assert 'management-data:/data' in compose
    assert 'hbbs:' not in compose and 'hbbr:' not in compose
    assert 'no-new-privileges:true' in compose
    dockerfile = (ROOT / 'Dockerfile').read_text()
    assert 'USER 10001:10001' in dockerfile
    assert '--no-proxy-headers' in dockerfile
    assert '--workers", "1"' in dockerfile


def test_examples_contain_no_bootstrap_credentials():
    assert 'PASSWORD=' not in (ROOT / '.env.example').read_text()
    assert 'TOKEN=' not in (ROOT / '.env.example').read_text()
