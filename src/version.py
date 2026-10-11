"""Single source of truth for the public version and traceable build revision."""

APP_VERSION = "0.3.8"
BUILD_ID = "261011.3"
WINDOWS_REVISION = 3


def display_version() -> str:
    return f"{APP_VERSION} · build {BUILD_ID}"
