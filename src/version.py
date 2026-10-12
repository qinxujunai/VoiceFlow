"""Single source of truth for the public version and traceable build revision."""

APP_VERSION = "0.3.9"
BUILD_ID = "261012.5"
WINDOWS_REVISION = 5


def display_version() -> str:
    return f"{APP_VERSION} · build {BUILD_ID}"
