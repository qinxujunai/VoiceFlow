"""Collect unchanged wheel notices for distributions referenced by Analysis.

An empty notice list is reported explicitly and still requires release review.
"""

import importlib.metadata
from pathlib import Path, PurePosixPath
import re

from build_record import sha256_file


def collect_distribution_notices(entries):
    sources = {Path(origin).resolve() for _destination, origin, _kind in entries
               if origin != "-"}
    datas, report = [], []
    for distribution in importlib.metadata.distributions():
        files = distribution.files or ()
        if not any(Path(distribution.locate_file(entry)).resolve() in sources for entry in files):
            continue
        name, version = distribution.metadata["Name"], distribution.version
        normalized = re.sub(r"[-_.]+", "-", name.lower())
        if not re.fullmatch(r"[a-z0-9-]+", normalized) or not re.fullmatch(r"[A-Za-z0-9.+-]+", version):
            raise ValueError("unsafe distribution name or version in notice path")
        notices = []
        for entry in files:
            relative = PurePosixPath(str(entry).replace("\\", "/"))
            if ("licenses" not in {part.casefold() for part in relative.parts}
                    and not any(word in relative.name.casefold() for word in ("license", "copying", "notice", "copyright"))):
                continue
            if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
                raise ValueError("unsafe wheel notice path")
            source = Path(distribution.locate_file(entry)).resolve(strict=True)
            if not source.is_relative_to(Path(distribution.locate_file("")).resolve()):
                raise ValueError("wheel notice path leaves the distribution directory")
            destination = f"licenses/python/{normalized}-{version}/{relative}"
            datas.append((destination, str(source), "DATA"))
            notices.append({"path": destination, "sha256": sha256_file(source)})
        report.append({"name": name, "version": version, "notices": sorted(notices, key=lambda row: row["path"])})
    return sorted(datas), sorted(report, key=lambda row: row["name"].casefold())
