"""Injects the current version into manifest.json."""

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
except Exception:  # noqa: BLE001
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
        Path(self.root)  # type: ignore[attr-defined]

        src_manifest = MANIFEST_REL_PATH

        _inject_version(src_manifest, version)

        # Force-include the modified manifest at the same relative path
        force_include = build_data.setdefault("force_include", {})
        force_include[str(MANIFEST_REL_PATH)] = str(src_manifest)


def _cli(argv: list[str]) -> int:
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
