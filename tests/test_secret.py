import secrets

from logfire.secret import get_or_generate_secret


def test_secret_generation(monkeypatch):
    monkeypatch.setattr(secrets, 'token_bytes', lambda n: b'\x00' * n)

    secret = get_or_generate_secret(reset=True)
    assert secret == '00000000-0000-0000-0000-000000000000'


def test_secret_is_repeated():
    secret = get_or_generate_secret()
    assert secret == get_or_generate_secret()

    assert secret != get_or_generate_secret(reset=True)
