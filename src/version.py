"""Single source of truth for the public version and traceable build revision."""

APP_VERSION = "0.3.5"
BUILD_ID = "261001.3"


def display_version() -> str:
    return f"{APP_VERSION} · build {BUILD_ID}"
