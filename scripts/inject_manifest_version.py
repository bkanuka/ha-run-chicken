"""
Inject a version string into the Home Assistant manifest.json.

Used by the release workflow to stamp the git tag version into
``custom_components/run_chicken/manifest.json`` before packaging the HACS zip.
The repository copy stays at the ``0.0.0`` placeholder; the version is only
injected into the ephemeral CI checkout that gets zipped.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MANIFEST_REL_PATH = Path("custom_components/run_chicken/manifest.json")


def resolve_version_from_git_tag() -> str:
    """
    Resolve the version from the git tag, dropping a leading ``v``.

    Prefers the ref name provided by CI (``GITHUB_REF_NAME``) and falls back to
    ``git describe``. Returns ``0.0.0`` when no tag is available.
    """
    try:
        ref_name = os.environ.get("GITHUB_REF_NAME")
        tag = ref_name or subprocess.check_output(["git", "describe", "--tags", "--abbrev=0"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "0.0.0"
    return tag.removeprefix("v")


def inject_version(manifest_path: Path, version: str) -> None:
    """Write ``version`` into the manifest at ``manifest_path``."""
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    data["version"] = version
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    """Inject a version into a manifest.json (CLI entry point)."""
    parser = argparse.ArgumentParser(description="Inject a version into manifest.json")
    parser.add_argument("--version", help="Version to inject; derived from the git tag if omitted.")
    parser.add_argument(
        "--file",
        type=Path,
        default=MANIFEST_REL_PATH,
        help="Path to the manifest.json to rewrite in place.",
    )
    args = parser.parse_args(argv)

    inject_version(args.file, args.version or resolve_version_from_git_tag())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
