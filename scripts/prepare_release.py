"""Add editable source and dependency notices to the portable distribution."""
from pathlib import Path
from importlib.metadata import distribution
import shutil
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "dist" / "LabelEditor"


def exclude_incompatible_icu():
    """Qt uses Windows' unversioned ICU API, not Poppler's versioned ICU.

    Some managed Python runtimes inject native tool directories into DLL search
    paths even when PATH is clean. Validate exports before keeping a collected ICU.
    Never copy or modify system libraries.
    """
    import pefile
    root = DEST / "_internal"
    bundled = root / "icuuc.dll"
    if not bundled.exists():
        return
    with pefile.PE(str(root / "PySide6" / "Qt6Core.dll")) as qt:
        needed = {i.name for dll in qt.DIRECTORY_ENTRY_IMPORT
                  if dll.dll.lower() == b"icuuc.dll" for i in dll.imports if i.name}
    with pefile.PE(str(bundled)) as lib:
        provided = {e.name for e in lib.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
        data_dlls = [d.dll.decode("ascii") for d in lib.DIRECTORY_ENTRY_IMPORT
                     if d.dll.lower().startswith(b"icudt")]
    if needed <= provided:
        return
    system_icu = Path(os.environ.get("WINDIR", "C:/Windows")) / "System32" / "icuuc.dll"
    with pefile.PE(str(system_icu)) as system:
        available = {e.name for e in system.DIRECTORY_ENTRY_EXPORT.symbols if e.name}
    if not needed <= available:
        raise RuntimeError("This Windows version does not provide the ICU API required by Qt.")
    bundled.unlink()
    for name in data_dlls:
        if Path(name).name != name:
            raise RuntimeError("Unexpected ICU dependency path")
        (root / name).unlink(missing_ok=True)
    print("Excluded incompatible development ICU; Qt will use the Windows system API.")


def prepare(destination=None):
    destination = Path(destination) if destination else DEST
    if sys.platform == "win32":
        exclude_incompatible_icu()
    source = destination / "source"
    source.mkdir(parents=True, exist_ok=True)
    for name in ["main.py", "README.md", "requirements.txt", "requirements-dev.txt", "build.ps1",
                 "LICENSE", "THIRD_PARTY.md", "CHANGELOG.md", "验收记录.md", "README.en.md", "build_macos.py"]:
        shutil.copy2(ROOT / name, source / name)
    for name in ["label_editor", "scripts", "tests", "assets", "docs"]:
        shutil.copytree(ROOT / name, source / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    notices = destination / "licenses"
    notices.mkdir(exist_ok=True)
    arimo = notices / "Arimo"
    arimo.mkdir(exist_ok=True)
    for filename in ("OFL.txt", "SOURCE.json"):
        shutil.copy2(ROOT / "assets/fonts/Arimo" / filename, arimo / filename)
    summary = []
    for name in ["PyMuPDF", "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "fonttools"]:
        dist = distribution(name)
        summary.append(f"{name} {dist.version}\n{dist.metadata.get('License', '')}\n")
        for entry in dist.files or []:
            low = str(entry).lower()
            if any(part in low for part in ["license", "copying", "notice"]) and not low.endswith((".py", ".pyc", ".pyd", ".dll")):
                original = Path(dist.locate_file(entry))
                if original.is_file():
                    target = notices / name / Path(str(entry))
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
    (notices / "THIRD_PARTY.txt").write_text("\n".join(summary), encoding="utf-8")
    shutil.copy2(ROOT / "README.md", destination / "README.md")
    shutil.copy2(ROOT / "README.en.md", destination / "README.en.md")
    for name in ["LICENSE", "THIRD_PARTY.md", "CHANGELOG.md", "验收记录.md"]:
        shutil.copy2(ROOT / name, destination / name)
    shutil.copytree(ROOT / "docs", destination / "docs", dirs_exist_ok=True)
    print(destination)


if __name__ == "__main__":
    prepare()
