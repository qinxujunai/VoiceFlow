"""Single source of truth for the public version and traceable build revision."""

APP_VERSION = "0.3.7"
BUILD_ID = "261011.1"
WINDOWS_REVISION = 1


def display_version() -> str:
    return f"{APP_VERSION} · build {BUILD_ID}"
