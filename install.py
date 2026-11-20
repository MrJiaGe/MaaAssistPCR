"""Build a Windows x64 development package from pinned upstream releases."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent
DEPS = ROOT / "deps"
NATIVE = "runtimes/win-x64/native/"
FRAMEWORK_RELEASE = "https://github.com/MaaXYZ/MaaFramework/releases/download/v5.16.1"
GUI_RELEASE = "https://github.com/MaaXYZ/MFAAvalonia/releases/download/v2.16.4"
GUI_LICENSE = "https://raw.githubusercontent.com/MaaXYZ/MFAAvalonia/v2.16.4/LICENSE"


def verify_hash(path: Path, sha256: str) -> None:
    """Reject a cached or downloaded file unless it matches the pinned SHA-256."""
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != sha256:
        raise ValueError(f"SHA-256 mismatch for {path}: {actual} (expected {sha256}).")


def cached_download(url: str, filename: str, sha256: str) -> Path:
    """Fetch a pinned input when absent and verify it before use."""
    path = DEPS / filename
    if path.exists():
        verify_hash(path, sha256)
        return path

    DEPS.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=DEPS) as temp:
        candidate = Path(temp) / filename
        subprocess.run(
            [
                "curl.exe", "--disable", "--fail", "--location", "--show-error",
                "--silent", "--retry", "4", "--retry-all-errors",
                "--connect-timeout", "20", "--max-time", "180",
                "--output", str(candidate), url,
            ],
            check=True,
        )
        verify_hash(candidate, sha256)
        candidate.replace(path)
    return path


def copy_member(archive: ZipFile, member: str, destination: Path) -> None:
    """Copy a file from a verified release archive to its package path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member) as source, destination.open("wb") as output:
        shutil.copyfileobj(source, output)


def assemble(output: Path, version: str) -> None:
    """Assemble a fresh development package without loading legacy resources or Agent."""
    if output.exists():
        raise FileExistsError(f"Choose a new output directory; {output} already exists.")

    framework_name = "MAA-win-x86_64-v5.16.1.zip"
    gui_name = "MFAAvalonia-v2.16.4-win-x64.zip"
    framework = cached_download(
        f"{FRAMEWORK_RELEASE}/{framework_name}", framework_name,
        "19588e6fda8d977496eb143cce157ce0c21890bee62aef8fdf1696930fe1286e",
    )
    gui = cached_download(
        f"{GUI_RELEASE}/{gui_name}", gui_name,
        "e44c4e95d41d6566a38020550128726bfc91b96056602f8e320239671fab40fa",
    )
    gui_license = cached_download(
        GUI_LICENSE, "MFAAvalonia-v2.16.4-LICENSE.txt",
        "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent, prefix="maa-build-") as temp:
        staging = Path(temp) / "package"
        with ZipFile(gui) as archive:
            archive.extractall(
                staging,
                (member for member in archive.namelist()
                 if not member.startswith(NATIVE)
                 and member != "plugins/win-x64/MaaPluginDemo.dll"),
            )
        with ZipFile(framework) as archive:
            for member in archive.namelist():
                if member.startswith("bin/") and member.count("/") == 1 and member.endswith(".dll"):
                    copy_member(archive, member, staging / NATIVE / Path(member).name)
                elif member.startswith("share/MaaAgentBinary/") and not member.endswith("/"):
                    copy_member(archive, member, staging / member.removeprefix("share/"))
                elif member.startswith("share/licenses/") and not member.endswith("/"):
                    copy_member(archive, member, staging / member.removeprefix("share/"))
            copy_member(archive, "LICENSE.md", staging / "licenses/MaaFramework.md")

        assets = ROOT / "assets"
        shutil.copytree(assets / "resource", staging / "resource", ignore=shutil.ignore_patterns(".gitignore"))
        interface = json.loads((assets / "interface.json").read_text(encoding="utf-8"))
        interface["version"] = version
        (staging / "interface.json").write_text(
            json.dumps(interface, ensure_ascii=False, indent=4) + "\n", encoding="utf-8",
        )
        shutil.copy2(ROOT / "LICENSE", staging / "LICENSE")
        shutil.copy2(ROOT / "docs/GUI-Packaging.md", staging / "README.md")
        shutil.copy2(gui_license, staging / "licenses/MFAAvalonia.txt")
        for filename in ("MFAAvalonia.exe", f"{NATIVE}MaaFramework.dll", f"{NATIVE}MaaAdbControlUnit.dll"):
            if not (staging / filename).is_file():
                raise ValueError(f"Missing package component: {filename}")
        staging.rename(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "install/MaaAssistPCR-win-x64")
    parser.add_argument("--version", default="0.0.0-dev")
    args = parser.parse_args()
    try:
        assemble(args.output.resolve(), args.version)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Packaging failed: {error}\n")
    print(f"Built {args.output.resolve()}")


if __name__ == "__main__":
    main()
