"""Build and verify a native macOS app on a Mac of the target architecture."""
from pathlib import Path
import hashlib
import json
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_release import prepare
from label_editor import __version__


def run(*args, **kwargs):
    subprocess.run([str(a) for a in args], check=True, cwd=ROOT, **kwargs)


def selftest(app, output):
    output.mkdir(parents=True, exist_ok=True)
    (output / "result.json").unlink(missing_ok=True)
    run(app / "Contents/MacOS/LabelEditor", "--self-test", output, timeout=180)
    assert json.loads((output / "result.json").read_text())["ok"] is True


def main():
    if sys.platform != "darwin":
        raise SystemExit("Run this build on macOS. Cross-compilation from Windows is not supported.")
    from PIL import Image
    arch = platform.machine()
    assert arch in ("arm64", "x86_64"), arch
    (ROOT / "build").mkdir(exist_ok=True)
    icon = ROOT / "build/LabelEditor.icns"
    Image.open(ROOT / "assets/app.png").save(icon)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
        "--name", "LabelEditor", "--icon", icon, "--add-data", "assets:assets",
        "--collect-submodules", "fontTools.ttLib.tables", "--target-architecture", arch,
        "--osx-bundle-identifier", "io.github.lorizhang2026.labeleditor",
        "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets", "main.py")
    app = ROOT / "dist/LabelEditor.app"
    run("codesign", "--verify", "--deep", "--strict", app)
    run("file", app / "Contents/MacOS/LabelEditor")
    selftest(app, ROOT / "tmp/qa/macos-bundle")
    name = f"LabelEditor-macOS-{arch}-v{__version__}"
    stage = ROOT / "dist" / name
    if stage.exists():
        raise SystemExit(f"Staging directory already exists: {stage}. Use a fresh build directory.")
    stage.mkdir()
    shutil.copytree(app, stage / app.name, symlinks=True)
    prepare(stage)
    archive = ROOT / "dist" / f"{name}.zip"
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", stage, archive)
    extracted = ROOT / "tmp/qa/extracted"
    extracted.mkdir(parents=True, exist_ok=True)
    run("ditto", "-x", "-k", archive, extracted)
    restored = extracted / name / app.name
    run("codesign", "--verify", "--deep", "--strict", restored)
    selftest(restored, ROOT / "tmp/qa/macos-extracted")
    with archive.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    (ROOT / "dist" / f"SHA256SUMS-macOS-{arch}.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print("Verified native app, extracted app, signature and ZIP:", archive)


if __name__ == "__main__":
    main()
