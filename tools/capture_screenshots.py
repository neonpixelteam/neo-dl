"""Generate README screenshots from the real UI (no downloads are started).

Usage:
    python tools/capture_screenshots.py          # English  -> docs/screenshots/en/
    python tools/capture_screenshots.py fa       # Persian  -> docs/screenshots/fa/
    python tools/capture_screenshots.py ar       # Arabic   -> docs/screenshots/ar/
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import neo_dl  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

lang = sys.argv[1] if len(sys.argv) > 1 else "en"
if lang not in neo_dl.I18N:
    raise SystemExit(f"unknown language: {lang}")

app = QApplication(sys.argv)
neo_dl.LANG = lang
if lang in neo_dl.RTL_LANGS:
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
neo_dl.MONO = neo_dl.pick_mono()
app.setStyleSheet(neo_dl.QSS.replace("%MONO%", neo_dl.MONO))

win = neo_dl.Main()
win.resize(1120, 700)
win.show()

out = ROOT / "docs" / "screenshots" / lang
out.mkdir(parents=True, exist_ok=True)


def settle(ms=1200):
    end = time.time() + ms / 1000
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(name):
    settle()
    win.grab().save(str(out / f"{name}.png"))
    print("saved", out / f"{name}.png")


# 1. Downloads page with the live ASCII scene
win.show_page(0)
shot("downloads")

# 2. Add page, filled with sample links (only text, nothing is queued)
win.show_page(1)
win.add_page.te.setPlainText(
    "https://example.com/files/part1.zip\n"
    "https://example.com/files/part2.zip\n"
    "https://example.com/files/part3.zip"
)
shot("add")

# 3. File explorer
win.show_page(2)
shot("files")

# 4. Settings
win.show_page(3)
shot("settings")

win.close()
