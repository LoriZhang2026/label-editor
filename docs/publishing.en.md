# Build and publish

[简体中文](GitHub发布指南.md) | **English**

## Requirements

Use Python 3.12 on the target operating system. Create a virtual environment and install `requirements-dev.txt`. The project uses PySide6, PyMuPDF, fontTools, ReportLab, Pillow and PyInstaller. Source is licensed under AGPL v3; retain project and dependency notices.

Windows sample regeneration uses Microsoft YaHei. Mac builds use the committed fictitious PDF sample and do not require Windows fonts. Two tests specific to manually selecting Windows fonts are skipped when those fonts are unavailable; general PDF and automatic Arimo tests still run.

## Windows

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m pytest -q
powershell -ExecutionPolicy Bypass -File build.ps1
.venv/Scripts/python.exe scripts/package_release.py
```

The result is a ZIP in `dist/`, with `SHA256SUMS.txt`. The package script runs the actual bundled executable's PDF and UI self-tests before archiving.

## macOS

Build separately on Apple Silicon and Intel Macs. Do not cross-compile from Windows.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
python build_macos.py
```

The script builds a native `.app`, verifies its ad-hoc signature, runs the packaged self-test, bundles source and bilingual documentation outside the signed app, and creates a ZIP using `ditto` to preserve symlinks and permissions. It then extracts the ZIP and repeats the signature and runtime checks. Output names contain `arm64` or `x86_64`.

The **Build and verify macOS** GitHub Actions workflow can be dispatched manually. It uses `macos-15` and `macos-15-intel`, uploads each tested archive and checksum, and preserves verification screenshots and JSON results. It does not publish automatically. Downloads target macOS 15 or later.

No Apple Developer ID or notarization credentials are configured. Disclose this in the release and link the first-launch instructions. Do not describe an ad-hoc signature as Apple notarization.

## GitHub connection and release

Install Git and [GitHub CLI](https://cli.github.com/) and run `gh auth login --hostname github.com --git-protocol https --web`, then `gh auth setup-git`. Complete authorization in the browser; do not place credentials in project files.

For a new version, update `label_editor/__init__.py`, both READMEs, both changelogs, and `docs/releases/vVERSION.md`. Commit and push. Run all platform builds against that same commit, then create and push `vVERSION` pointing to it. Do not move an already published version tag.

Create the Release with a UTF-8 notes file and attach the Windows ZIP, both Mac ZIPs and combined SHA-256 checksums. Verify the source commit, public release state, asset sizes, download links and digests. Keep real customer PDFs and local environment files out of Git.

The Windows-only `scripts/publish_release.ps1 -Repository OWNER/REPO` remains available for Windows-only releases; it does not fetch Mac workflow artifacts or publish a multi-platform release by itself.

References: [GitHub releases](https://cli.github.com/manual/gh_release_create), [GitHub runner images](https://github.com/actions/runner-images), [PyInstaller macOS options](https://pyinstaller.org/en/stable/usage.html).
