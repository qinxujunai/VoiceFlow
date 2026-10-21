"""Single source of truth for the public version and traceable build revision."""

APP_VERSION = "0.3.9"
BUILD_ID = "261021.6"
WINDOWS_REVISION = 6


def display_version() -> str:
    return f"{APP_VERSION} · build {BUILD_ID}"
