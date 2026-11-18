"""Development-only download. The released application never needs the network."""
from pathlib import Path
from urllib.request import urlopen
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "22e482e2ce0ebb2e6f88ba49d029d60f558d5d67"
BASE = f"https://raw.githubusercontent.com/googlefonts/Arimo/{COMMIT}/"

if __name__ == "__main__":
    destination = ROOT / "assets" / "fonts" / "Arimo"
    destination.mkdir(parents=True, exist_ok=True)
    files = [f"fonts/ttf/Arimo-{style}.ttf" for style in ("Regular", "Bold", "Italic", "BoldItalic")]
    files.append("OFL.txt")
    provenance = {"repository": "https://github.com/googlefonts/Arimo", "commit": COMMIT, "files": []}
    for relative in files:
        data = urlopen(BASE + relative, timeout=30).read()
        target = destination / Path(relative).name
        target.write_bytes(data)
        provenance["files"].append({"file": target.name, "url": BASE + relative,
                                    "sha256": hashlib.sha256(data).hexdigest()})
        print(target.name, len(data))
    (destination / "SOURCE.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
