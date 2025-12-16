"""
Inject git tag into manifest.json.

A utility module for handling version injection into a manifest.json file and managing build hooks
for Home Assistant custom integrations.

This module provides a Hatch build hook (CustomHook) for version injection into
`manifest.json`, resolving versions from Git tags when operating outside of Hatch, and
a CLI for creating zip releases with the computed version values.

The exported functionality includes:
- Resolving versions based on Git tags.
- Injecting version data into `manifest.json`.
- A CLI entry point for performing version injection.

Classes:
- CustomHook: A custom build hook for Hatch to inject computed version into `manifest.json`.

Functions:
- resolve_version_from_git_tag: Resolves the integration version, falling back to `0.0.0`
  when no Git tag is available.
- _cli: Handles the command-line interface for direct invocation of the versioning process.

Constants:
- MANIFEST_REL_PATH: Relative path to the `manifest.json` file within a Home Assistant custom component.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    # Available during Hatch builds
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
except ImportError:
    # Not available outside Hatch so we have CustomHook use object as its base class
    BuildHookInterface = object  # type: ignore[misc,assignment]


MANIFEST_REL_PATH = Path("custom_components/run_chicken/manifest.json")


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _inject_version(manifest_path: Path, version: str) -> None:
    data = _read_json(manifest_path)
    data["version"] = version
    _write_json(manifest_path, data)


def resolve_version_from_git_tag() -> str:
    """
    Best-effort version resolution from Git tags when outside Hatch.

    Returns the tag without a leading 'v' if present. Falls back to '0.0.0'.
    """
    try:
        # Prefer the ref name provided by CI
        ref_name = os.environ.get("GITHUB_REF_NAME")
        if ref_name:
            tag = ref_name
        else:
            tag = subprocess.check_output(["git", "describe", "--tags", "--abbrev=0"], text=True).strip()

    except (OSError, subprocess.CalledProcessError):
        return "0.0.0"

    return tag.removeprefix("v")


class CustomHook(BuildHookInterface):  # type: ignore[misc]
    """
    Hatch custom build hook to inject the computed version into manifest.json.

    This operates on a staged temp copy and force-includes it for both wheel and sdist,
    leaving the repository file untouched.
    """

    def initialize(self, version: str, build_data: dict) -> None:  # type: ignore[override]
        """
        Occurs immediately before each build.

        Any modifications to the build data will be seen by the build target.
        """
        # "version" passed to this function only tells you the _kind_ of build: "standard"
        version = self.metadata.version

        _inject_version(MANIFEST_REL_PATH, version)

        # Force-include the modified manifest at the same relative path
        force_include = build_data.setdefault("force_include", {})
        force_include[str(MANIFEST_REL_PATH)] = str(MANIFEST_REL_PATH)


def _cli(argv: list[str]) -> int:
    """CLI entrypoint used by GitHub Actions to create a zip release."""
    parser = argparse.ArgumentParser(description="Inject version into Home Assistant manifest.json")
    parser.add_argument("--version", help="Version to inject; if omitted, derived from git tag.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Path to a manifest.json to rewrite in-place.")
    group.add_argument(
        "--copy-dir",
        nargs=2,
        metavar=("SRC_DIR", "DEST_DIR"),
        help=(
            "Copy the integration directory from SRC_DIR to DEST_DIR and rewrite the copied "
            "manifest.json with the resolved version."
        ),
    )

    args = parser.parse_args(argv)
    version = args.version or resolve_version_from_git_tag()

    if args.file:
        _inject_version(args.file, version)
        return 0

    src_dir, dest_dir = map(Path, args.copy_dir)
    if not (src_dir / MANIFEST_REL_PATH).is_file():
        parser.error(f"Could not find {MANIFEST_REL_PATH} under {src_dir}")

    # Copy tree, then rewrite manifest in the copied location
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(src_dir, dest_dir)
    copied_manifest = dest_dir / MANIFEST_REL_PATH
    _inject_version(copied_manifest, version)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli(sys.argv[1:]))
