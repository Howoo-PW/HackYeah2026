"""The DB URL may choose the TLS mode; the default stays `require` (Supabase in the cloud)."""

from app.database import ssl_mode


def test_defaults_to_require():
    assert ssl_mode("postgresql://user:pw@db.example.supabase.co:6543/postgres") == "require"


def test_url_can_disable_tls_for_a_private_network_database():
    assert ssl_mode("postgresql://user:pw@10.0.0.5:54322/postgres?sslmode=disable") == "disable"


def test_url_can_ask_for_a_stricter_mode():
    assert ssl_mode("postgresql://user:pw@host/postgres?sslmode=verify-full") == "verify-full"


def test_garbage_falls_back_to_require():
    assert ssl_mode("") == "require"
    assert ssl_mode("not a url at all ::") == "require"
