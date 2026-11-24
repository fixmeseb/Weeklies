"""Settings read from the environment: the session signing key and feature flags."""

import logging
import os
import secrets

SECRET_KEY_ENV = "WEEKLIES_SECRET_KEY"


def _read_key_file(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _write_key_file(path, key) -> bool:
    """Create the key file readable only by the owner. Returns False if it can't be written."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key + "\n")
        return True
    except OSError:
        return False


def load_secret_key(environ=None, key_file=None) -> str:
    """
    Return the session signing key.
    Args:
        environ: Mapping to read from (defaults to os.environ; injectable for tests).
        key_file: Optional git-ignored file used when the env var is unset. The first
            run generates a key and saves it there; later runs and auto-reloads reuse
            it, so local logins survive restarts with no setup.
    Returns:
        str: WEEKLIES_SECRET_KEY if set; else the saved key; else a new random key.
    """
    environ = os.environ if environ is None else environ
    key = (environ.get(SECRET_KEY_ENV) or "").strip()
    if key:
        return key
    # A key committed to the repo lets anyone forge session cookies, so never
    # fall back to a fixed string.
    log = logging.getLogger(__name__)
    if key_file:
        saved = _read_key_file(key_file)
        if saved:
            return saved
        key = secrets.token_hex(32)
        if _write_key_file(key_file, key):
            log.warning("%s is not set; generated a local key in %s.", SECRET_KEY_ENV, key_file)
            return key
    log.warning(
        "%s is not set; using a random key, so logins reset when the server restarts.",
        SECRET_KEY_ENV,
    )
    return key or secrets.token_hex(32)


# Anchored to this file: Flask's instance_path depends on how the module was imported
# (it differed between running from the repo root and from proj2/).
SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "secret_key")


# The database viewer is a developer tool: it shows every user's email and phone,
# so it is off unless explicitly enabled (team decision, option A on the /db issue).
DB_VIEW_ENV = "WEEKLIES_ENABLE_DB_VIEW"


def env_flag(name, environ=None) -> bool:
    """
    Read a boolean environment variable.
    Args:
        name: Variable name.
        environ: Mapping to read from (defaults to os.environ; injectable for tests).
    Returns:
        bool: True for 1/true/yes/on (any case, surrounding spaces ignored), else False.
    """
    environ = os.environ if environ is None else environ
    return (environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}
