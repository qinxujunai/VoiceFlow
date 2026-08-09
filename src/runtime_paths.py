"""Runtime path discovery and non-destructive user-data migration."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from platform_utils import default_data_dir


DATA_SCHEMA_VERSION = 3

LEGACY_VOCABULARY_FILES = (
    "ai-terms.txt",
    "company-terms.txt",
    "user-custom.txt",
)

# SHA-256 only: retired v1 private/company/product seeds are never shipped as
# readable strings again.  Normalization is ``line.strip().encode("utf-8")``.
PRIVATE_ENTRY_SHA256 = frozenset(
    {
        "05642da1523d47def94966340c594db95e3d4be8fc87fdb45e5b40d4cfef7db8",
        "0bb0c4666418e9f21fd8f0c2533e6ef2822d1f733b94e3590c44d461b2c04b59",
        "130f70ae5b44ed4c645aad5cf7cf18ad2413c48e754dbfdec86cc781a26a5624",
        "157b9ab49f3a8d955e5e01d49492023d3ba35c81427dacc05b59430334b4f1b4",
        "1baf3bd256f1b72e7994712f49535bedd5bd1b02c29d2a16323f1fde31befefe",
        "1f43d19d8f19de58b3cfc1464844dacd47e592ce2b1a8b6d540fc8b890a78250",
        "2a284da53148885a5b6380487c0e9070dabe91a7813585dd7f0e27c04f12f860",
        "2d514a4dcfb2b595d95e8636424792358a1fac89b612f090252b7b1e088474dc",
        "2e7d82270d09a95392c9895404d3a7e97b4d02b3a6bed2798f6c6b5a265fb5af",
        "3717b118798b0235e85db66dc5d77a10537750ba873f5ad8875f43c2c346219c",
        "39d7dad5f80cd955813f72d9ba9ffade86ee0899b1e209362c84b28e55ffb200",
        "3a11c09722ad9da448ea7deb175fa15d75b92818bc6f9803beb6a1dfafeffafb",
        "3fbd66d78edb61fa797746d797818f9970b47a0106748362a7adaa87ca4be712",
        "4a84c3a3108b4f8ce72a6749261f532c602d26969e450d3540b512de5c8e5111",
        "4b46e47584a7b8631ecc69ee1f09f43f6b341c32248b550676d1fc0798cdd597",
        "521eaf56b857d05cb7004a4048259bc5e84d0d6fbcc74b3905feb6ce6559dabb",
        "534d4e792a5020da3ace586b80d6a4ef3681e0fac27c5e0854db353ec82ef1a1",
        "6196293ad68e2e6203c6f99cc78e291b8b1219503427cc52a3e4be3a8f96d134",
        "62512116a7561f9ac23c709c001ca0b043130ed6507fd8f2ef15caa2194e2db2",
        "77fc03a0011993af1e9771f2846e286d43c99bd1776b282c7038c47fdb5cb6e3",
        "7d2bcecc270f31ba43d39a22e628b37fc41819cf9b0035b4ad3fa3aa9b3be1b3",
        "adc6b79bced5ada07b0e6c0f98774c86a2984864200e9928b10556ecfb74f183",
        "aeae1c799c943ce9f4f7a0dab148170ff513e8451433d99dbdeabaf4a0ff414c",
        "afdfdfba1b2750bcec2beddfd75451ed3e62eacec1ef5421ccfd98d7c5b2f1cb",
        "b932825fca6de767fa6e95d41fbe529123ac2bfc6636563989ecad72aea275ab",
        "c9f7c41baa5818d55617676f17dd780a105801983be93e8111d843b6320d652f",
        "cbfcf95ae22c811b36924e10da80d229ec109bbdf5658cefdc8b55cb66cfae97",
        "d3b5e6e368316b51c69be9ba2d3c072034d5cecd726380dc2ca4089a3db94bf1",
        "d6e46f95c5228b90c58e7dad929232c57fb149745a777b7d53b1ab567943c215",
        "df7d2f0899a60343566166863e93810e66f4b7f7d1f285c52a0c29f2c008367e",
        "e7180f8c68630108199dec2acd3bf106127d91da19ab1a554a91f048182b9e54",
        "ed1cc3b3909a9e8e38615ccb76c0494866804279897302434f2d5f2f38792c4c",
        "f0055891f09fff4839b344a4af5e0482696cab0e0bf307455661ba4056c787ee",
    }
)

LEGACY_FILE_SHA256 = {
    "ai-terms.txt": "74e7cd037f54d9976f14a59a96e2de7bddfc8445a59a64d7989d0260032b992b",
    "company-terms.txt": "8019e25488e2b15ec739d7cec0308c6bfc4ddb0995d5246a6b93707ad9e3c28f",
    "user-custom.txt": "ac0b305f9fad9e76de1012f3f033a90e2d02e39dde3587158c2412698699e093",
}


class RuntimeMode(Enum):
    SOURCE = "source"
    FROZEN = "frozen"


@dataclass(frozen=True)
class MigrationReport:
    schema_version: int
    copied: tuple[str, ...]
    sanitized: tuple[str, ...] = ()
    removed_legacy: tuple[str, ...] = ()


@dataclass(frozen=True)
class AppPaths:
    """Separates immutable application resources from writable user data."""

    mode: RuntimeMode
    install_dir: Path
    data_dir: Path
    executable: Path
    config_override: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "install_dir", Path(self.install_dir).resolve())
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        object.__setattr__(self, "executable", Path(self.executable).resolve())
        if self.config_override is not None:
            object.__setattr__(
                self,
                "config_override",
                Path(self.config_override).resolve(),
            )

    @classmethod
    def discover(
        cls,
        config_path: str | Path | None = None,
        *,
        frozen: bool | None = None,
        install_dir: str | Path | None = None,
        data_dir: str | Path | None = None,
        executable: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        platform_name: str | None = None,
        home: str | Path | None = None,
    ) -> AppPaths:
        is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        if config_path is not None:
            config = Path(config_path).resolve()
            root = config.parent
            return cls(
                mode=RuntimeMode.FROZEN if is_frozen else RuntimeMode.SOURCE,
                install_dir=Path(install_dir).resolve() if install_dir else root,
                data_dir=Path(data_dir).resolve() if data_dir else root,
                executable=Path(executable).resolve() if executable else Path(sys.executable),
                config_override=config,
            )

        mode = RuntimeMode.FROZEN if is_frozen else RuntimeMode.SOURCE
        resolved_executable = Path(executable or sys.executable).resolve()
        if install_dir is None:
            if is_frozen:
                install_dir = Path(
                    getattr(sys, "_MEIPASS", resolved_executable.parent)
                )
            else:
                install_dir = Path(__file__).resolve().parents[1]

        if data_dir is None:
            env = os.environ if environ is None else environ
            data_dir = env.get("VOICEFLOW_DATA_DIR") or default_data_dir(
                env,
                platform_name=platform_name,
                home=home,
            )

        return cls(
            mode=mode,
            install_dir=Path(install_dir),
            data_dir=Path(data_dir),
            executable=resolved_executable,
        )

    @property
    def config_file(self) -> Path:
        return self.config_override or self.data_dir / "config.yaml"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def history_file(self) -> Path:
        return self.logs_dir / "history.jsonl"

    @property
    def legacy_history_file(self) -> Path:
        return self.logs_dir / "history.txt"

    @property
    def knowledge_dir(self) -> Path:
        return self.data_dir / "knowledge-base"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def recovery_dir(self) -> Path:
        return self.data_dir / "recovery"

    @property
    def delivery_dir(self) -> Path:
        return self.data_dir / "delivery-pending"

    @property
    def model_switch_dir(self) -> Path:
        return self.data_dir / "model-switch"

    @property
    def schema_file(self) -> Path:
        return self.data_dir / "runtime-state.json"

    @property
    def manifest_file(self) -> Path:
        return self.install_dir / "model-manifest.json"

    @property
    def asset_roots(self) -> tuple[Path, ...]:
        if self.data_dir == self.install_dir:
            return (self.data_dir,)
        return (self.data_dir, self.install_dir)

    def resolve_asset(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        if path.is_absolute():
            return path
        for root in self.asset_roots:
            candidate = root / path
            if candidate.exists():
                return candidate
        return self.data_dir / path

    def install_resource(self, raw_path: str | Path) -> Path:
        path = Path(raw_path)
        return path if path.is_absolute() else self.install_dir / path


def _copy_if_missing(source: Path, destination: Path) -> bool:
    if not source.is_file() or destination.exists():
        return False
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.migrating")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)
    return True


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _line_digest(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()


def _write_lines_atomic(path: Path, lines: list[str]) -> None:
    content = "\n".join(lines)
    if content:
        content += "\n"
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _append_unique_lines(path: Path, values: list[str]) -> bool:
    existing_lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    existing_values = {
        line.strip()
        for line in existing_lines
        if line.strip() and not line.lstrip().startswith("#")
    }
    additions = [value for value in values if value and value not in existing_values]
    if not additions:
        return False
    if existing_lines and existing_lines[-1].strip():
        existing_lines.append("")
    existing_lines.extend(additions)
    _write_lines_atomic(path, existing_lines)
    return True


def _sanitize_active_vocabulary(path: Path, private_hashes: frozenset[str]) -> bool:
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    cleaned = [
        line
        for line in lines
        if not line.strip() or _line_digest(line) not in private_hashes
    ]
    if cleaned == lines:
        return False
    _write_lines_atomic(path, cleaned)
    return True


def _migrate_legacy_vocabulary(
    knowledge_dir: Path,
    private_hashes: frozenset[str],
) -> tuple[list[str], list[str]]:
    sanitized: list[str] = []
    removed: list[str] = []
    user_words: list[str] = []
    corrections: list[str] = []
    pending_removals: list[Path] = []

    for filename in LEGACY_VOCABULARY_FILES:
        path = knowledge_dir / filename
        if not path.is_file():
            continue
        raw = path.read_bytes()
        exact_v1_seed = hashlib.sha256(raw).hexdigest() == LEGACY_FILE_SHA256[filename]
        if not exact_v1_seed:
            for line in raw.decode("utf-8-sig").splitlines():
                value = line.strip()
                if (
                    not value
                    or value.startswith("#")
                    or _line_digest(value) in private_hashes
                ):
                    continue
                (corrections if "=" in value else user_words).append(value)
            sanitized.append(f"knowledge-base/{filename}")
        pending_removals.append(path)

    if _append_unique_lines(knowledge_dir / "user-dictionary.txt", user_words):
        sanitized.append("knowledge-base/user-dictionary.txt")
    if _append_unique_lines(knowledge_dir / "corrections.txt", corrections):
        sanitized.append("knowledge-base/corrections.txt")
    for path in pending_removals:
        path.unlink()
        removed.append(f"knowledge-base/{path.name}")
    return sanitized, removed


def _remove_legacy_config_entries(path: Path) -> bool:
    if not path.is_file():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    legacy_names = set(LEGACY_VOCABULARY_FILES)
    cleaned = []
    for line in lines:
        stripped = line.strip()
        value = stripped[1:].strip().strip("\"'") if stripped.startswith("-") else ""
        if value in legacy_names:
            continue
        cleaned.append(line)
    if cleaned == lines:
        return False
    _write_lines_atomic(path, cleaned)
    return True


def _stored_schema_version(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return int(payload.get("schema_version", 0))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def _migrate_v3_sensevoice_language(path: Path, previous_schema: int) -> bool:
    """Move the old implicit Chinese-first default to automatic bilingual mode.

    The migration runs only from the released v2 schema. Once v3 has been
    recorded, a user who deliberately selects Chinese-first keeps that choice.
    """
    if previous_schema != 2 or not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    section = re.search(r"(?m)^  sensevoice:\s*$", text)
    if section is None:
        return False
    following = re.search(r"(?m)^  \S[^:]*:\s*$", text[section.end():])
    end = section.end() + following.start() if following else len(text)
    block = text[section.end():end]
    updated, count = re.subn(
        r'(?m)^(    language:\s*)["\']?zh["\']?(?P<comment>\s*(?:#.*)?)$',
        lambda match: f'{match.group(1)}"auto"{match.group("comment")}',
        block,
        count=1,
    )
    if count != 1:
        return False
    temporary = path.with_name(f".{path.name}.language-v3.tmp")
    temporary.write_text(text[:section.end()] + updated + text[end:], encoding="utf-8")
    os.replace(temporary, path)
    return True


def prepare_runtime_layout(
    paths: AppPaths,
    *,
    legacy_root: str | Path | None = None,
    private_entry_hashes: set[str] | frozenset[str] | None = None,
) -> MigrationReport:
    """Create writable directories and copy legacy user data without overwrites.

    Model files are deliberately not copied. ``resolve_asset`` keeps an existing
    source-tree or bundled model usable while all future writable model storage
    lives under ``data_dir/models``.
    """

    legacy = Path(legacy_root).resolve() if legacy_root else paths.install_dir
    previous_schema = _stored_schema_version(paths.schema_file)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.knowledge_dir.mkdir(parents=True, exist_ok=True)
    paths.models_dir.mkdir(parents=True, exist_ok=True)
    paths.recovery_dir.mkdir(parents=True, exist_ok=True)
    paths.delivery_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    sanitized: list[str] = []
    removed_legacy: list[str] = []
    private_hashes = frozenset(
        PRIVATE_ENTRY_SHA256 if private_entry_hashes is None else private_entry_hashes
    )

    if _copy_if_missing(legacy / "config.yaml", paths.config_file):
        copied.append("config.yaml")
    if not paths.config_file.is_file():
        raise FileNotFoundError(
            f"VoiceFlow runtime config is missing: {paths.config_file}"
        )

    legacy_knowledge = legacy / "knowledge-base"
    if legacy_knowledge.is_dir():
        for source in sorted(path for path in legacy_knowledge.rglob("*") if path.is_file()):
            if source.name in LEGACY_VOCABULARY_FILES:
                continue
            relative = source.relative_to(legacy)
            destination = paths.data_dir / relative
            if _copy_if_missing(source, destination):
                copied.append(relative.as_posix())

    for filename in ("user-dictionary.txt", "phrases.txt", "corrections.txt"):
        path = paths.knowledge_dir / filename
        if _sanitize_active_vocabulary(path, private_hashes):
            sanitized.append(f"knowledge-base/{filename}")
    legacy_sanitized, legacy_removed = _migrate_legacy_vocabulary(
        paths.knowledge_dir,
        private_hashes,
    )
    sanitized.extend(legacy_sanitized)
    removed_legacy.extend(legacy_removed)
    if _remove_legacy_config_entries(paths.config_file):
        sanitized.append("config.yaml")
    if _migrate_v3_sensevoice_language(paths.config_file, previous_schema):
        sanitized.append("config.yaml: sensevoice language auto")

    for filename in ("history.jsonl", "history.txt"):
        source = legacy / "logs" / filename
        destination = paths.logs_dir / filename
        if _copy_if_missing(source, destination):
            copied.append(f"logs/{filename}")

    _write_json_atomic(
        paths.schema_file,
        {
            "schema_version": DATA_SCHEMA_VERSION,
            "install_dir": str(paths.install_dir),
            "runtime_mode": paths.mode.value,
        },
    )
    return MigrationReport(
        schema_version=DATA_SCHEMA_VERSION,
        copied=tuple(copied),
        sanitized=tuple(dict.fromkeys(sanitized)),
        removed_legacy=tuple(dict.fromkeys(removed_legacy)),
    )
