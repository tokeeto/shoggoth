"""Shared login helper for Shoggoth Cloud -- the one place the actual
login network call + error handling lives, used by both SettingsDialog's
Publishing tab and the standalone Cloud-menu Sign In dialog."""
from shoggoth.cloud import client


def login(base_url: str, email: str, password: str) -> tuple[str, dict]:
    """Returns (token, user_dict). Raises client.PublishError on failure
    (bad credentials, unreachable server, no access, ...) -- the message is
    already safe to show directly in a dialog."""
    token = client.login_with_password(base_url, email, password)
    user = client.verify_token(base_url, token)
    return token, user
