"""Create a checked portable archive and SHA-256 file for GitHub Releases."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from label_editor import __version__
from prepare_release import prepare


def main():
    exe = ROOT / 'dist/LabelEditor/LabelEditor.exe'
    if not exe.exists():
        raise SystemExit('Run build.ps1 first.')
    prepare()
    qa = ROOT / 'tmp/qa/release-package'
    qa.mkdir(parents=True, exist_ok=True)
    (qa / 'result.json').unlink(missing_ok=True)
    subprocess.run([str(exe), '--self-test', str(qa)], check=True, timeout=60)
    result = json.loads((qa / 'result.json').read_text(encoding='utf-8'))
    if result.get('ok') is not True:
        raise SystemExit('Packaged self-test failed.')
    name = f'LabelEditor-Windows-x64-v{__version__}'
    archive = Path(shutil.make_archive(str(ROOT / 'dist' / name), 'zip', ROOT / 'dist', 'LabelEditor'))
    with zipfile.ZipFile(archive) as z:
        if z.testzip():
            raise SystemExit('Archive integrity check failed.')
        for entry in ['LabelEditor.exe', 'LICENSE', 'docs/使用指南.md',
                      '_internal/assets/fonts/Arimo/Arimo-Regular.ttf', 'source/main.py']:
            if f'LabelEditor/{entry}' not in z.namelist():
                raise SystemExit(f'Missing archive entry: {entry}')
        if z.read('LabelEditor/source/label_editor/core.py') != (ROOT / 'label_editor/core.py').read_bytes():
            raise SystemExit('Bundled source mismatch.')
    checksum = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    (ROOT / 'dist/SHA256SUMS.txt').write_text(f'{checksum}  {archive.name}\n', encoding='ascii')
    print(f'Validated: {archive.name}; {archive.stat().st_size / 1024 / 1024:.1f} MB')
    print('SHA256:', checksum)


if __name__ == '__main__':
    main()
