#!/usr/bin/env python3
"""Refresh the pinned CMUdict data snapshot after reviewing a new release."""

import hashlib
import json
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "1.1.3"
EXPECTED = {
    "cmudict.dict": "81917843c7f44ce2b094ac63873c2c7a4cf802040792c455ba3ca406891c3d22",
    "LICENSE": "bd4ce8e44170a5f9f481310ca85c51de3c4f851a65e679b40e603b143bd3542a",
}
MEMBERS = {
    "cmudict.dict": "cmudict/data/cmudict.dict",
    "LICENSE": "cmudict/data/LICENSE",
}
ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "third_party" / "cmudict"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    with urllib.request.urlopen(
        f"https://pypi.org/pypi/cmudict/{VERSION}/json", timeout=30
    ) as response:
        release = json.load(response)
    wheel = next(item for item in release["urls"] if item["filename"].endswith(".whl"))

    with tempfile.TemporaryDirectory(prefix="cmudict-update-") as temporary_directory:
        archive_path = Path(temporary_directory) / wheel["filename"]
        urllib.request.urlretrieve(wheel["url"], archive_path)
        archive_payload = archive_path.read_bytes()
        if sha256(archive_payload) != wheel["digests"]["sha256"]:
            raise RuntimeError("Downloaded wheel does not match PyPI's SHA-256 digest")

        with zipfile.ZipFile(archive_path) as archive:
            payloads = {name: archive.read(member) for name, member in MEMBERS.items()}

    for name, payload in payloads.items():
        actual = sha256(payload)
        if actual != EXPECTED[name]:
            raise RuntimeError(f"{name} changed: expected {EXPECTED[name]}, received {actual}")

    TARGET.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        (TARGET / name).write_bytes(payload)
        print(f"updated {name}: {EXPECTED[name]}")


if __name__ == "__main__":
    main()
