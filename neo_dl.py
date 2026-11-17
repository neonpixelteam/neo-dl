#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEO·DL — دانلود منیجر مشکی/سفید با UI گوشه‌تیز و انیمیشن‌های ASCII

نصب:      pip install PyQt6 requests
(پروکسی SOCKS:  pip install "requests[socks]")
اجرا:     python neo_dl.py

موتور دانلود (مناسب اینترنت ناپایدار / اینترنت ایران):
  • دانلود چندبخشی (Range) با قطعه‌های کوچک و صف کار (work queue)
  • هر قطعه جداگانه retry می‌شود (backoff + jitter) و از همان بایت ادامه می‌یابد
  • Resume کامل حتی بعد از بستن برنامه (فایل .part و .part.json)
  • Accept-Encoding: identity  تا فایل با gzip خراب نشود
  • تأیید اندازه نهایی و (اختیاری) چک‌سام md5 / sha1 / sha256
  • اگر سرور Range را نپذیرد، خودکار به حالت تک‌اتصال با resume برمی‌گردد
  • پروکسی HTTP/SOCKS، محدودیت سرعت، تنظیم تعداد اتصال و ...
"""
import sys, os, re, json, time, math, random, threading, socket, hashlib, queue, subprocess, uuid
from collections import deque
from pathlib import Path
from urllib.parse import urlparse, unquote

import requests
from requests.adapters import HTTPAdapter
from PyQt6.QtCore import Qt, QTimer, QSize, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetricsF, QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit,
    QPlainTextEdit, QListWidget, QListWidgetItem, QStackedWidget, QStackedLayout, QSplitter,
    QSpinBox, QCheckBox, QComboBox, QFileDialog, QMessageBox, QSizeGrip, QAbstractItemView, QFrame,
)

APP_DIR = Path.home() / ".neo_dl"
APP_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = APP_DIR / "settings.json"
QUEUE_FILE = APP_DIR / "queue.json"

# ───────────────────────── theme ─────────────────────────
FG, DIM, LINE, BG = "#f2f2f2", "#8a8a8a", "#3a3a3a", "#000000"
MONO = "Consolas"


def pick_mono():
    fams = set(QFontDatabase.families())
    for f in ("Cascadia Mono", "JetBrains Mono", "Consolas", "DejaVu Sans Mono", "Menlo", "Liberation Mono", "Courier New"):
        if f in fams:
            return f
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


def mono(px):
    f = QFont(MONO)
    f.setPixelSize(px)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


QSS = """
* { font-family: "%MONO%"; font-size: 12px; color: #f2f2f2; }
QWidget#root { background: #000; border: 1px solid #6a6a6a; }
QLabel#dim { color: #8a8a8a; }
QPushButton { background: #000; border: 1px solid #5a5a5a; border-radius: 0; padding: 5px 12px; }
QPushButton:hover { background: #f2f2f2; color: #000; border-color: #f2f2f2; }
QPushButton:pressed { background: #bdbdbd; color: #000; }
QPushButton:checked { background: #f2f2f2; color: #000; border-color: #f2f2f2; }
QPushButton:disabled { color: #555; border-color: #262626; }
QPushButton#nav { border: none; border-bottom: 2px solid #000; padding: 7px 16px; }
QPushButton#nav:hover { background: #111; color: #f2f2f2; }
QPushButton#nav:checked { background: #000; color: #fff; border-bottom: 2px solid #f2f2f2; }
QPushButton#win { border: none; padding: 4px 14px; font-size: 13px; }
QPushButton#win:hover { background: #f2f2f2; color: #000; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox { background: #050505; border: 1px solid #3a3a3a; border-radius: 0;
    padding: 4px 6px; selection-background-color: #f2f2f2; selection-color: #000; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #cfcfcf; }
QPlainTextEdit#drop { border: 1px dashed #8a8a8a; }
QSpinBox::up-button, QSpinBox::down-button { width: 14px; border: none; background: #111; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView { background: #000; selection-background-color: #f2f2f2; selection-color: #000; border: 1px solid #6a6a6a; outline: 0; }
QCheckBox::indicator { width: 12px; height: 12px; border: 1px solid #8a8a8a; background: #000; }
QCheckBox::indicator:checked { background: #f2f2f2; }
QListWidget { background: #000; border: none; outline: 0; }
QListWidget#files::item { padding: 1px 4px; }
QListWidget#files::item:selected { background: #f2f2f2; color: #000; }
QScrollBar:vertical { background: #000; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #4a4a4a; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #8a8a8a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { height: 0; }
QSplitter::handle { background: #1a1a1a; }
QToolTip { background: #000; color: #f2f2f2; border: 1px solid #8a8a8a; }
QMessageBox { background: #000; }
"""

# ───────────────────────── settings ─────────────────────────

# ───────────────────────── i18n ─────────────────────────
I18N = {
 "en": {
  "nav_dl": "DOWNLOADS", "nav_add": "ADD", "nav_files": "FILES", "nav_set": "SETTINGS",
  "q_on": "▶ QUEUE: ON", "q_off": "‖ QUEUE: OFF", "subtitle": "download manager",
  "paste_hint": "paste a link and press Enter ↵", "add_btn": "＋ ADD",
  "start": "▶ START", "pause": "‖ PAUSE", "remove": "✕ REMOVE", "open": "OPEN", "folder": "FOLDER", "clear_done": "CLEAR DONE",
  "queue_title": "DOWNLOAD QUEUE", "live": "LIVE", "add_title": "ADD LINKS",
  "add_hint": "One link per line — the order here is the download order.\\nOptional checksum after a link:   https://site/part1.zip  sha256hex",
  "save_to": "SAVE TO", "mode": "MODE", "position": "POSITION", "browse": "BROWSE", "paste": "PASTE", "clear": "CLEAR",
  "add_queue": "  ADD TO QUEUE →  ", "save": "  SAVE  ",
  "mode_ordered": "ORDERED — one by one, part 2 starts after part 1 finishes", "mode_parallel": "PARALLEL — several files at the same time",
  "pos_end": "append to end of queue", "pos_top": "put on top of queue",
  "nat": "sort links naturally (part2 before part10)", "go": "start the queue right away",
  "files_title": "FILE EXPLORER", "refresh": "REFRESH", "delete": "DELETE", "settings_title": "SETTINGS",
  "s_dir": "Download folder", "s_conn": "Connections per file", "s_chunk": "Chunk size", "s_par": "Files at once",
  "s_speed": "Speed limit", "s_retries": "Retries", "s_timeout": "Timeout", "s_proxy": "Proxy", "s_ua": "User-Agent",
  "s_ssl": "Verify SSL certificates", "s_stop": "Stop the queue on error", "s_auto": "Start queue when app opens",
  "s_scene": "ASCII live scene", "s_fps": "Scene FPS", "s_scene_mode": "Scene", "s_lang": "Language",
  "s_random": "Random — each download gets its own",
  "restart_note": "Language saved. Restart NEO·DL to apply it.", "valid_links": "valid links",
 },
 "fa": {
  "nav_dl": "دانلودها", "nav_add": "افزودن", "nav_files": "فایل‌ها", "nav_set": "تنظیمات",
  "q_on": "▶ صف: روشن", "q_off": "‖ صف: خاموش", "subtitle": "مدیر دانلود",
  "paste_hint": "لینک را بچسبانید و Enter بزنید ↵", "add_btn": "＋ افزودن",
  "start": "▶ شروع", "pause": "‖ توقف", "remove": "✕ حذف", "open": "باز کردن", "folder": "پوشه", "clear_done": "پاک‌کردن تکمیل‌شده‌ها",
  "queue_title": "صف دانلود", "live": "زنده", "add_title": "افزودن لینک‌ها",
  "add_hint": "هر لینک در یک خط — ترتیب اینجا ترتیب دانلود است.\\nچک‌سام اختیاری بعد از لینک:   https://site/part1.zip  sha256hex",
  "save_to": "ذخیره در", "mode": "حالت", "position": "موقعیت", "browse": "انتخاب", "paste": "چسباندن", "clear": "پاک‌کردن",
  "add_queue": "  افزودن به صف ←  ", "save": "  ذخیره  ",
  "mode_ordered": "ترتیبی — یکی‌یکی؛ بخش ۲ بعد از اتمام بخش ۱ شروع می‌شود", "mode_parallel": "موازی — چند فایل هم‌زمان",
  "pos_end": "افزودن به انتهای صف", "pos_top": "قرار دادن در بالای صف",
  "nat": "مرتب‌سازی طبیعی لینک‌ها (part2 قبل از part10)", "go": "شروع فوری صف",
  "files_title": "مدیر فایل", "refresh": "بازخوانی", "delete": "حذف", "settings_title": "تنظیمات",
  "s_dir": "پوشه دانلود", "s_conn": "اتصال در هر فایل", "s_chunk": "اندازه هر تکه", "s_par": "فایل هم‌زمان",
  "s_speed": "محدودیت سرعت", "s_retries": "تعداد تلاش مجدد", "s_timeout": "زمان انتظار", "s_proxy": "پروکسی", "s_ua": "User-Agent",
  "s_ssl": "بررسی گواهی SSL", "s_stop": "توقف صف هنگام خطا", "s_auto": "شروع صف هنگام باز شدن برنامه",
  "s_scene": "انیمیشن ASCII", "s_fps": "FPS انیمیشن", "s_scene_mode": "صحنه", "s_lang": "زبان",
  "s_random": "تصادفی — هر دانلود انیمیشن خودش را دارد",
  "restart_note": "زبان ذخیره شد. برای اعمال، NEO·DL را دوباره اجرا کنید.", "valid_links": "لینک معتبر",
 },
 "ar": {
  "nav_dl": "التنزيلات", "nav_add": "إضافة", "nav_files": "الملفات", "nav_set": "الإعدادات",
  "q_on": "▶ الطابور: مفعّل", "q_off": "‖ الطابور: متوقف", "subtitle": "مدير التنزيلات",
  "paste_hint": "الصق الرابط ثم اضغط Enter ↵", "add_btn": "＋ إضافة",
  "start": "▶ ابدأ", "pause": "‖ إيقاف مؤقت", "remove": "✕ إزالة", "open": "فتح", "folder": "المجلد", "clear_done": "مسح المكتمل",
  "queue_title": "طابور التنزيل", "live": "مباشر", "add_title": "إضافة الروابط",
  "add_hint": "رابط واحد في كل سطر — الترتيب هنا هو ترتيب التنزيل.\\nمجموع تحقق اختياري بعد الرابط:   https://site/part1.zip  sha256hex",
  "save_to": "الحفظ في", "mode": "الوضع", "position": "الموقع", "browse": "استعراض", "paste": "لصق", "clear": "مسح",
  "add_queue": "  إضافة إلى الطابور ←  ", "save": "  حفظ  ",
  "mode_ordered": "بالترتيب — واحد تلو الآخر، يبدأ الجزء 2 بعد انتهاء الجزء 1", "mode_parallel": "متوازٍ — عدة ملفات في وقت واحد",
  "pos_end": "إضافة إلى نهاية الطابور", "pos_top": "وضع في أعلى الطابور",
  "nat": "ترتيب الروابط طبيعياً (part2 قبل part10)", "go": "ابدأ الطابور فوراً",
  "files_title": "مستكشف الملفات", "refresh": "تحديث", "delete": "حذف", "settings_title": "الإعدادات",
  "s_dir": "مجلد التنزيل", "s_conn": "الاتصالات لكل ملف", "s_chunk": "حجم القطعة", "s_par": "الملفات في وقت واحد",
  "s_speed": "حد السرعة", "s_retries": "عدد المحاولات", "s_timeout": "المهلة", "s_proxy": "الوكيل", "s_ua": "User-Agent",
  "s_ssl": "التحقق من شهادات SSL", "s_stop": "إيقاف الطابور عند الخطأ", "s_auto": "تشغيل الطابور عند فتح التطبيق",
  "s_scene": "الرسوم المتحركة ASCII", "s_fps": "إطارات الرسوم", "s_scene_mode": "المشهد", "s_lang": "اللغة",
  "s_random": "عشوائي — لكل تنزيل مشهده الخاص",
  "restart_note": "تم حفظ اللغة. أعد تشغيل NEO·DL لتطبيقها.", "valid_links": "رابط صالح",
 },
}
RTL_LANGS = {"fa", "ar"}
LANG = "en"


def tr(k):
    return I18N.get(LANG, I18N["en"]).get(k) or I18N["en"].get(k, k)


DEFAULTS = {
    "download_dir": str(Path.home() / "Downloads"),
    "connections": 8,          # اتصال همزمان برای هر فایل
    "chunk_mb": 4,             # اندازه هر قطعه
    "max_parallel": 1,         # 1 = ترتیبی (اول پارت ۱، بعد پارت ۲ ...)
    "speed_limit_kb": 0,       # 0 = بدون محدودیت
    "retries": 8,
    "timeout": 20,
    "proxy": "",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "verify_ssl": True,
    "stop_on_error": False,
    "auto_start": True,
    "scene_enabled": True,
    "scene_fps": 12,
    "language": "en",
    "win_w": 1120,
    "win_h": 700,
    "last_page": 0,
    "scene_mode": -1,          # -1 = رندوم برای هر دانلود
}


class Settings:
    def __init__(self):
        self.d = dict(DEFAULTS)
        try:
            self.d.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
        except Exception:
            pass

    def __getitem__(self, k):
        return self.d[k]

    def __setitem__(self, k, v):
        self.d[k] = v

    def save(self):
        try:
            SETTINGS_FILE.write_text(json.dumps(self.d, indent=2, ensure_ascii=False), "utf-8")
        except Exception:
            pass


# ───────────────────────── helpers ─────────────────────────
def fmt_size(b):
    b = float(b)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return f"{b:.0f} {u}" if u == "B" else f"{b:.1f} {u}"
        b /= 1024


def fmt_speed(bps):
    return fmt_size(bps) + "/s"


def fmt_eta(s):
    s = int(max(0, s))
    if s >= 86400:
        return ">1d"
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    return f"{h:d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def safe_name(n):
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", n).strip(" .")
    return n or "download"


def name_from_url(url):
    u = urlparse(url)
    return safe_name(unquote(os.path.basename(u.path))) if os.path.basename(u.path) else safe_name(u.hostname or "download")


def name_from_cd(cd):
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", cd, re.I)
    if m:
        return safe_name(unquote(m.group(1).strip().strip('"')))
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
    return safe_name(m.group(1).strip()) if m else ""


def unique_path(p: Path):
    if not p.exists():
        return p
    i = 1
    while True:
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists():
            return q
        i += 1


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def open_path(p):
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])
    except Exception:
        pass


def reveal(p):
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", p])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(p) or "."])
    except Exception:
        pass


def parse_links(text):
    """هر خط: URL  [checksum]"""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        url = parts[0]
        if not re.match(r"^https?://", url, re.I):
            continue
        ck = ""
        if len(parts) > 1:
            c = parts[1].split(":")[-1].lower()
            if re.fullmatch(r"[0-9a-f]+", c) and len(c) in (32, 40, 64):
                ck = c
        out.append((url, ck))
    return out


def geo_lookup(ip=""):
    """موقعیت بر اساس IP"""
    try:
        r = requests.get(f"https://ipwho.is/{ip}", timeout=6)
        j = r.json()
        if j.get("success", True):
            loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
            isp = (j.get("connection") or {}).get("isp", "")
            return j.get("ip", ip), loc, isp
    except Exception:
        pass
    return ip, "", ""


# ───────────────────────── ASCII scene kit ─────────────────────────
def hx(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgbhex(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in c)


def mixc(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def gradient(stops, n):
    cs = [hx(s) for s in stops]
    out = []
    for i in range(n):
        t = i / max(1, n - 1) * (len(cs) - 1)
        k = min(len(cs) - 2, int(t))
        out.append(rgbhex(mixc(cs[k], cs[k + 1], t - k)))
    return out


def ramp(stops, t):
    t = clamp(t)
    for i in range(1, len(stops)):
        if t <= stops[i][0]:
            a, b = stops[i - 1], stops[i]
            return mixc(hx(a[1]), hx(b[1]), (t - a[0]) / ((b[0] - a[0]) or 1))
    return hx(stops[-1][1])


def pal(colors):
    n = len(colors)
    return lambda v: colors[0 if v <= 0 else n - 1 if v >= 1 else int(v * n)]


_r = random.Random(1234)
_T = [_r.random() for _ in range(65536)]


def noise2(x, y, seed=0):
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)
    ox, oy = (ix + seed * 57) & 255, (iy + seed * 131) & 255
    ox1, oy1 = (ox + 1) & 255, (oy + 1) & 255
    a, b, c, d = _T[(ox << 8) | oy], _T[(ox1 << 8) | oy], _T[(ox << 8) | oy1], _T[(ox1 << 8) | oy1]
    return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy


def fbm(x, y, octv=3, seed=0):
    s, amp, tot, f = 0.0, 0.5, 0.0, 1.0
    for i in range(octv):
        s += amp * noise2(x * f, y * f, seed + i)
        tot += amp
        amp *= 0.5
        f *= 2.0
    return s / tot


class Grid:
    def __init__(self, cols, rows):
        self.cols, self.rows = cols, rows
        self.n = cols * rows
        self.ch = [" "] * self.n
        self.co = ["#000000"] * self.n

    def clear(self):
        self.ch = [" "] * self.n
        self.co = ["#000000"] * self.n

    def load(self, ch, co):
        self.ch = ch[:]
        self.co = co[:]

    def set(self, x, y, c, col):
        x = math.floor(x + 0.5)
        y = math.floor(y + 0.5)
        if 0 <= x < self.cols and 0 <= y < self.rows:
            i = y * self.cols + x
            self.ch[i] = c
            self.co[i] = col

    def get(self, x, y):
        x, y = int(x), int(y)
        return self.ch[y * self.cols + x] if 0 <= x < self.cols and 0 <= y < self.rows else " "

    def text(self, x, y, s, col):
        for i, c in enumerate(s):
            self.set(x + i, y, c, col)

    def line(self, x0, y0, x1, y1, c, col):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) or 1
        for i in range(steps + 1):
            t = i / steps
            self.set(lerp(x0, x1, t), lerp(y0, y1, t), c, col)

    def frame(self):
        C = self.cols
        return [("".join(self.ch[r * C:(r + 1) * C]), self.co[r * C:(r + 1) * C]) for r in range(self.rows)]


# ── Scene 1: campfire ──
class CampfireScene:
    name = "Campfire Under Stars"
    cols, rows = 100, 36
    SKY = gradient(["#02030a", "#070b1e", "#101a36", "#1c2a4e"], 6)
    MW = gradient(["#1a1a40", "#3a2e6a", "#6a5a9a", "#a898c8", "#e8e0f8"], 6)
    STAR = ["#6a78a0", "#c8d4ff", "#ffffff", "#ffe8c0"]
    TREE = ["#020306", "#060a10"]
    FIRE = gradient(["#5a0a04", "#b02a08", "#ec5a10", "#ff9a2a", "#ffd25a", "#fff6c0"], 10)
    LOG = ["#2a1608", "#5a3418", "#8a5428"]
    GROUND = gradient(["#06060a", "#1a120e", "#3a2414", "#6a3e1c", "#a0602a"], 8)
    TENT = gradient(["#0c0c14", "#2a1e1a", "#6a3a22", "#b0602e"], 5)

    def __init__(self):
        self.g = Grid(self.cols, self.rows)
        r = random.Random(17)
        self.hz, self.fx, self.fy = 24, 58, 30
        self.stars = [[int(r.random() * 100), int(r.random() * 24), r.random(), r.random() * 6.28] for _ in range(140)]
        self.trees = []
        for x in range(100):
            pine = abs(((x * 0.37) % 1) - 0.5) * 2
            self.trees.append(self.hz - 1 - round((1 - pine) * (3 + fbm(x * 0.1, 0, 2, 5) * 6)))
        self.sparks = [[r.random() * 6.28, 1 + r.random() * 2, r.random() * 3, r.random()] for _ in range(36)]

    def frame(self, t):
        g, hz, fx, fy = self.g, self.hz, self.fx, self.fy
        S, MW, STAR, FIRE = self.SKY, self.MW, self.STAR, self.FIRE
        g.clear()
        flick = 0.85 + 0.15 * math.sin(t * 13) * math.sin(t * 7.3)
        for y in range(hz):
            for x in range(100):
                bd = (y - (x * 0.32 - 4)) / 6
                n = fbm(x * 0.08 + t * 0.01, y * 0.2, 3, 3)
                dust = math.exp(-bd * bd) * (0.4 + n)
                dark = abs(bd) < 0.6 and fbm(x * 0.15, y * 0.4, 2, 9) > 0.62
                if dust > 0.4 and not dark:
                    g.set(x, y, "▓" if dust > 1 else "▒" if dust > 0.7 else "░", MW[int(clamp(math.floor((dust - 0.3) * 5), 0, 5))])
                else:
                    col = S[int(clamp(math.floor(y / hz * 4 + n), 0, 5))] if n > 0.6 else S[0]
                    g.set(x, y, "░", col)
        for sx, sy, b, ph in self.stars:
            v = b * 0.6 + (0.5 + 0.5 * math.sin(t * 2.2 + ph)) * 0.4
            if v > 0.35:
                k = (2 if v > 0.85 else 1 if v > 0.6 else 0) + (1 if b > 0.97 else 0)
                g.set(sx, sy, "*" if v > 0.85 else "•" if v > 0.6 else "·", STAR[min(3, k)])
        for x in range(100):
            for y in range(self.trees[x], hz + 1):
                g.set(x, y, "█", self.TREE[1 if y > hz - 2 else 0])
        for y in range(hz, 36):
            for x in range(100):
                d = math.hypot((x - fx) / 2.2, (y - fy) * 1.1)
                n = fbm(x * 0.2, y * 0.6, 2, 4)
                v = clamp(math.exp(-d / 14) * flick * 1.15 + (n - 0.5) * 0.25 + (y - hz) * 0.01)
                g.set(x, y, "▓" if v > 0.6 else "▒" if v > 0.3 else "░", self.GROUND[int(clamp(math.floor(v * 8), 0, 7))])
        tx, tb, th = 24, 32, 13
        for y in range(tb - th, tb + 1):
            hw = (y - (tb - th)) * 1.5
            for x in range(round(tx - hw), round(tx + hw) + 1):
                side = (x - tx) / max(1, hw)
                v = clamp(0.25 + side * 0.4 * flick + (y - (tb - th)) * 0.02)
                door = abs(x - tx) < (y - (tb - th)) * 0.45 and y > tb - 7
                ch = "▒" if door else "\\" if side > 0.9 else "/" if side < -0.9 else "█"
                g.set(x, y, ch, self.TENT[0] if door else self.TENT[int(clamp(math.floor(v * 5), 0, 4))])
        g.set(tx, tb - th - 1, "│", self.TENT[1])
        g.line(tx + 18, tb + 1, tx + 1, tb - th, "·", self.TENT[2])
        g.text(fx - 6, fy + 1, "▄██▀▀▄▄  ▄▄▀▀██▄", self.LOG[1])
        g.text(fx - 7, fy + 2, "●▀▀●▀▀●▀▀●▀▀●▀▀●", self.GROUND[3])
        for y in range(fy - 14, fy + 2):
            for x in range(fx - 9, fx + 10):
                h = (fy + 1 - y) / 15
                width = (1 - h) * 8 * (0.7 + 0.3 * h) + 0.5
                n = noise2(x * 0.5, y * 0.45 + t * 6, 3) * 0.6 + noise2(x * 1.1, y * 0.9 + t * 9, 8) * 0.4
                e = 1 - abs(x - fx - math.sin(t * 3 + y * 0.4) * h * 1.5) / width
                v = e * 1.2 - h * 0.6 + (n - 0.5) * 0.9
                if v > 0.05:
                    g.set(x, y, "█" if v > 0.7 else "▓" if v > 0.4 else "▒" if v > 0.2 else "░",
                          FIRE[int(clamp(math.floor(v * 10 * flick), 0, 9))])
        for ph, sp, off, sway in self.sparks:
            life = (t * 0.35 * sp + off) % 1
            x = fx + math.sin(ph + t * 1.5) * (1 + life * 6) + (sway - 0.5) * life * 14
            y = fy - 6 - life * 24
            if math.sin(t * 20 + ph * 7) > -0.3:
                g.set(x, y, "*" if life < 0.3 else "•" if life < 0.7 else "·", FIRE[int(clamp(9 - math.floor(life * 8), 3, 9))])
        return g.frame()


# ── Scene 2: bridge in fog ──
class GoldenGateScene:
    name = "Bridge in the Fog"
    cols, rows = 100, 36
    SKY = staticmethod(pal(gradient(["#2a4a7a", "#5a7aa8", "#c8a8a8", "#f8c890", "#ffe4b8"], 12)))
    HILL = staticmethod(pal(["#2a3448", "#3e4a60", "#5a6478"]))
    SEA = staticmethod(pal(gradient(["#0e1e30", "#1e3450", "#34506e"], 5)))
    RED = staticmethod(pal(["#5a1408", "#8e2412", "#c4381a", "#e8582a"]))
    FOG = staticmethod(pal(gradient(["#8a90a0", "#b4b8c4", "#dcdee4", "#f6f6f8"], 8)))
    LIGHT = "#ffd88a"
    DECK, T1, T2, TOP, HZ = 21, 27, 73, 3, 23

    def __init__(self):
        C = 100
        self.g = Grid(C, 36)
        D, T1, T2, TOP, HZ = self.DECK, self.T1, self.T2, self.TOP, self.HZ
        self.cable = []
        for x in range(C):
            if x < T1:
                u = x / T1
                self.cable.append(D - 3 - (D - 3 - TOP - 1) * u * u)
            elif x > T2:
                u = (C - 1 - x) / (C - 1 - T2)
                self.cable.append(D - 3 - (D - 3 - TOP - 1) * u * u)
            else:
                u = (x - (T1 + T2) / 2) / ((T2 - T1) / 2)
                self.cable.append(D - 2 - (D - 2 - TOP - 1) * u * u)
        self.hill = [HZ - 1 - max(0, 6 * math.exp(-(((x - 90) / 14) ** 2)) + 4 * math.exp(-(((x - 6) / 12) ** 2))) - fbm(x * 0.1, 1, 2, 3) * 1.5
                     for x in range(C)]

    def tower(self, tx, below):
        g, D, TOP, RED = self.g, self.DECK, self.TOP, self.RED
        for y in range(TOP, 36):
            if (y <= D + 1) if below else (y > D + 1):
                continue
            for lx in (tx - 2, tx + 2):
                g.set(lx, y, "█", RED(1 if lx > tx else 2))
                g.set(lx + (1 if lx > tx else -1), y, "▌", RED(0))
            if not below and y in (TOP, TOP + 5, TOP + 10, TOP + 14):
                for x in range(tx - 1, tx + 2):
                    g.set(x, y, "█" if y == TOP else "▀", RED(2))
        if not below:
            g.set(tx - 2, TOP - 1, "▄", RED(2))
            g.set(tx + 2, TOP - 1, "▄", RED(2))

    def frame(self, t):
        g, C, R = self.g, 100, 36
        D, T1, T2, TOP, HZ = self.DECK, self.T1, self.T2, self.TOP, self.HZ
        SKY, HILL, SEA, RED, FOG = self.SKY, self.HILL, self.SEA, self.RED, self.FOG
        g.clear()
        for y in range(HZ):
            for x in range(C):
                v = clamp((y / HZ) ** 1.2 + (fbm(x * 0.03 - t * 0.03, y * 0.3, 2, 2) - 0.5) * 0.3
                          + math.exp(-math.hypot((x - 50) / 30, y - HZ) / 3) * 0.1)
                g.set(x, y, "█" if v > 0.35 else "▓", SKY(v))
        for x in range(C):
            hx_ = self.hill[x]
            for y in range(math.ceil(hx_), HZ):
                g.set(x, y, "█", HILL(2 if y - hx_ < 1 else 1))
        for y in range(HZ, R):
            for x in range(C):
                w = noise2(x * 0.2 - t * 0.3, y * 0.9, 4)
                g.set(x, y, "▓" if w > 0.6 else "█", SEA(clamp((y - HZ) / 12 + (w - 0.5) * 0.6)))
        self.tower(T1, True)
        self.tower(T2, True)
        sw = math.sin(t * 0.2) * 0.3
        for y in range(12, R):
            body_base = (0.9 - (y - D) * 0.02) if y > D else (0.9 - (D - y) * 0.11)
            for x in range(C):
                n = fbm(x * 0.05 - t * 0.35, y * 0.22 + sw, 3, 7)
                f = n * body_base * 1.6 + math.sin(x * 0.09 - t * 0.6 + y * 0.2) * 0.12 - 0.62
                if f > 0:
                    g.set(x, y, "█" if f > 0.24 else "▓" if f > 0.12 else "▒", FOG(clamp(0.2 + f * 2.2)))
        self.tower(T1, False)
        self.tower(T2, False)
        blink = int(t * 8) % 6
        for x in range(C):
            cy = self.cable[x]
            g.set(x, cy, "█", RED(2))
            if x % 2 == 0 and abs(x - T1) > 2 and abs(x - T2) > 2:
                for y in range(math.floor(cy) + 1, D):
                    g.set(x, y, "│", RED(1))
            g.set(x, D, "▀", RED(3))
            g.set(x, D + 1, "█", RED(0))
            if x % 6 == blink:
                g.set(x, D, "▀", self.LIGHT)
        for tx in (T1, T2):
            g.set(tx, TOP - 2, "•", self.LIGHT)
        for y in range(D - 3, D + 3):
            for x in range(C):
                n = fbm(x * 0.07 - t * 0.5, y * 0.4 + 9, 2, 11)
                if n > 0.66:
                    g.set(x, y, "▓" if n > 0.72 else "▒", FOG(clamp((n - 0.6) * 5)))
        return g.frame()


# ── Scene 3: Fuji dawn (lite) ──
class FujiScene:
    name = "Fuji Dawn Lake"
    cols, rows = 100, 36
    HOR = 24

    def __init__(self):
        C, R, H = 100, 36, self.HOR
        self.g = Grid(C, R)
        ch, co, lay = [" "] * (C * R), ["#000000"] * (C * R), [0] * (C * R)
        SUN = (80, 17)
        self.SUN = SUN
        sky_stops = [(0, "#3c4a86"), (0.35, "#6a64a6"), (0.6, "#b884b4"), (0.8, "#e59bb0"), (0.92, "#ffbf96"), (1, "#ffdca0")]

        def put(x, y, c, col, L):
            if 0 <= x < C and 0 <= y < R:
                i = y * C + x
                ch[i], co[i], lay[i] = c, col, L

        for y in range(H):
            for x in range(C):
                c = ramp(sky_stops, y / H)
                d = math.hypot((x - SUN[0]) * 0.5, (y - SUN[1]) * 1.2)
                c = mixc(c, hx("#ffdca0"), clamp(1 - d / 14) * 0.6)
                put(x, y, "█", rgbhex(c), 0)
        for x in range(C):
            ft = 20 + 2 * math.sin(x / 9 + 1) + fbm(x / 12, 2, 2, 4)
            for y in range(math.floor(ft), H):
                put(x, y, "█", rgbhex(mixc(hx("#7a6aa0"), hx("#5c5490"), clamp((y - ft) / 4))), 1)
        CX, PEAK = 44, 4
        for x in range(C):
            d = abs(x - CX)
            top = PEAK + (1 if d < 1 else 0) if d < 3 else PEAK + (H - PEAK) * (1 - (1 - clamp((d - 3) / 46)) ** 1.75)
            sl = 10 + 5 * (fbm(x * 0.45, 9, 2, 21) - 0.5) + d * 0.06
            lit = clamp((x - CX + 4) / 30)
            for y in range(max(0, math.floor(top)), H):
                if y < sl:
                    c = mixc(mixc(hx("#c7c3e6"), hx("#fff2ea"), clamp(lit * 1.3 + (noise2(x / 1.5, y / 2, 5) - 0.5) * 0.3)), hx("#e6dcf0"), 0.15)
                    put(x, y, "█", rgbhex(c), 2)
                else:
                    n = fbm(x / 3, y / 2, 2, 13)
                    c = mixc(hx("#565a98"), hx("#8a76ae"), clamp(lit * 0.9 + (n - 0.5) * 0.4))
                    c = mixc(c, hx("#857ab4"), clamp((y - sl) / 14) * 0.5 * (1 - lit * 0.5))
                    put(x, y, "█", rgbhex(c), 2)
        for x in range(C):
            nt = 22 + 1.2 * math.sin(x / 6 + 3) + fbm(x / 8, 5, 2, 8)
            for y in range(math.floor(nt), H):
                put(x, y, "█", rgbhex(mixc(hx("#4a4678"), hx("#3e4280"), clamp((y - nt) / 2))), 1)
        # pine point on the left
        for x in range(24):
            for y in range(21 + x // 8, H + 1):
                put(x, y, "█", "#1c1a33", 4)
        for px, h in ((3, 9), (8, 11), (13, 8), (18, 7), (22, 5)):
            for j in range(h):
                w = max(0, round((h - j) * 0.3 + (1 if j % 3 == 0 else 0)))
                for x in range(px - w, px + w + 1):
                    put(x, H - 2 - j + 1, "█", "#1e2a3a" if x <= px else "#2c3a48", 4)
        # lake = mirrored scene
        self.lake_base = {}
        for y in range(H, R):
            for x in range(C):
                sy = max(0, H - 1 - int((y - H) * 1.2))
                i = sy * C + x
                c = mixc(hx(co[i]), hx("#2b2f5c"), 0.15 + 0.35 * (y - H) / (R - H))
                self.lake_base[(x, y)] = c
                put(x, y, "▒", rgbhex(c), 3)
        # foreground shore
        for x in range(C):
            sh = 33 + math.sin(x / 11) * 0.8 - clamp((x - 70) / 30) * 1.5
            for y in range(math.floor(sh), R):
                put(x, y, "█", "#110f22" if fbm(x / 3, y, 2, 31) > 0.5 else "#2a2440", 5)
        self.base_ch, self.base_co, self.lay = ch, co, lay
        self.reeds = [(80 + i * 1.5 + math.sin(i * 7.1), 3 + (i * 37) % 5, i * 0.61) for i in range(12)]

    def frame(self, t):
        g, C, R, H = self.g, 100, 36, self.HOR
        g.load(self.base_ch, self.base_co)
        lay = self.lay
        SX, SY = self.SUN
        for y in range(SY - 4, SY + 4):
            for x in range(SX - 8, SX + 9):
                if 0 <= y < R and lay[y * C + x] == 0 and math.hypot((x - SX) * 0.5, (y - SY)) < 3:
                    g.set(x, y, "█", "#fff8e0")
        for y in range(15, H):
            for x in range(C):
                if lay[y * C + x] == 0:
                    continue
                a = clamp((fbm(x * 0.06 - t * 0.05, y * 0.3, 2, 7) - 0.45) * 2.4) * 0.5 * math.sin((y - 15) / 9 * math.pi)
                if a > 0.1:
                    i = y * C + x
                    g.co[i] = rgbhex(mixc(hx(g.co[i]), hx("#f0c0c8"), a))
        for y in range(H, R):
            k = (y - H) / (R - H)
            for x in range(C):
                if lay[y * C + x] != 3:
                    continue
                base = self.lake_base[(x, y)]
                w = math.sin(x * 0.55 + y * 1.9 - t * 1.6 + math.sin(x * 0.13 + t * 0.4) * 2)
                sd = abs(x - SX) / (2 + k * 8)
                if sd < 1 and w > -0.2:
                    c, ch = mixc(base, hx("#ffd48a"), (1 - sd) * 0.7), "▓"
                elif w > 0.6:
                    c, ch = mixc(base, hx("#8a6c98"), 0.5), "▒"
                else:
                    c, ch = base, "░" if w < -0.5 else "▒"
                g.set(x, y, ch, rgbhex(c))
        ct = ((t + 8) % 34) / 34
        cx0, cy0 = lerp(130, -30, ct), 5 + math.sin(ct * 5) * 1.5
        for k, (ox, oy) in enumerate(((0, 0), (7, 2), (14, -1))):
            up = math.sin(t * 3.2 + k * 1.3) > 0
            g.text(round(cx0 + ox) - 1, round(cy0 + oy + math.sin(t * 0.9 + k) * 0.6), "\\v/" if up else "_▬_", "#fff2ea")
        bx = lerp(-12, 112, ((t + 30) % 70) / 70)
        by = 29
        ink = "#110f22"
        g.text(round(bx) - 4, by, "▄▄▄▄▄▄▄▄", ink)
        g.text(round(bx) - 3, by - 1, "▄██", ink)
        g.set(bx + 2, by - 1, "█", ink)
        g.set(bx + 2, by - 2, "█", ink)
        g.set(bx + 2, by - 3, "▲", ink)
        g.line(bx + 3, by - 2, bx + 3 + math.sin(t * 0.8) * 1.5, by + 3, "│", ink)
        g.text(round(bx) - 4, by + 1, "▀▀▀▀▀▀▀▀", "#2b2f5c")
        for x0, h, ph in self.reeds:
            sway = math.sin(t * 1.1 + ph) * 1.2
            for j in range(h):
                kk = j / h
                g.set(x0 + sway * kk * kk, 33 - j, "│", "#110f22" if kk < 0.8 else "#2a2440")
        return g.frame()


SCENES = [CampfireScene, GoldenGateScene, FujiScene]


class SceneRunner(threading.Thread):
    """فریم‌های ASCII را در ترد جدا می‌سازد تا UI قفل نشود."""

    def __init__(self, S):
        super().__init__(daemon=True)
        self.S, self.idx, self.frame, self.run_flag, self.active = S, 0, None, True, True
        self.cache, self.t0, self.err = {}, time.time(), ""

    def run(self):
        while self.run_flag:
            if not self.active or not self.S["scene_enabled"]:
                time.sleep(0.15)
                continue
            t = time.time()
            try:
                idx = self.idx
                sc = self.cache.get(idx)
                if sc is None:
                    sc = self.cache[idx] = SCENES[idx]()
                self.frame = sc.frame(time.time() - self.t0)
            except Exception as e:
                self.err = repr(e)
                time.sleep(0.5)
            time.sleep(max(0.02, 1.0 / max(1, int(self.S["scene_fps"])) - (time.time() - t)))


# ───────────────────────── download engine ─────────────────────────
class Fatal(Exception):
    pass


class RangeUnsupported(Exception):
    pass


class Limiter:
    def __init__(self, get):
        self.get, self.lock, self.nxt = get, threading.Lock(), time.monotonic()

    def wait(self, n):
        lim = self.get() * 1024
        if lim <= 0:
            return
        with self.lock:
            now = time.monotonic()
            self.nxt = max(self.nxt, now) + n / lim
            delay = self.nxt - now
        if delay > 0:
            time.sleep(min(delay, 2))


class Download:
    def __init__(self, mgr, url, dest_dir, name="", checksum="", scene=None):
        self.mgr, self.S = mgr, mgr.S
        self.id = uuid.uuid4().hex[:8]
        self.url, self.dir = url.strip(), dest_dir
        self.name = name or name_from_url(url)
        self.name_locked = bool(name)
        self.checksum = checksum
        self.status = "queued"          # queued running paused done error verifying
        self.total = self.got = 0
        self.speed = 0.0
        self.error = self.info = ""
        self.host = urlparse(url).hostname or ""
        self.ip = self.loc = ""
        self.scene = scene if scene is not None else random.randrange(len(SCENES))
        self.ranged, self.etag, self.path = None, "", ""
        self.chunks, self.lock = [], threading.Lock()
        self.stop = threading.Event()
        self.thread, self.session = None, None
        self.active = self.remaining = self.fail_streak = 0
        self.fatal, self.last_err = None, ""
        self.samples = deque(maxlen=30)

    # ---- control
    def start(self):
        if self.thread and self.thread.is_alive():
            self.stop.set()
            self.thread.join(3)
        self.stop.clear()
        self.status, self.error = "running", ""
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def pause(self):
        self.stop.set()
        if self.status in ("running", "verifying"):
            self.status = "paused"
        self.save_meta()

    def cancel(self, delete_part=True):
        self.stop.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(2)
        if delete_part and self.path and self.status != "done":
            for p in (self._part(), self._meta()):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def tick(self):
        now = time.time()
        if self.status == "running":
            self.samples.append((now, self.got))
            while len(self.samples) > 1 and now - self.samples[0][0] > 3:
                self.samples.popleft()
            if len(self.samples) > 1:
                dt = self.samples[-1][0] - self.samples[0][0]
                self.speed = (self.samples[-1][1] - self.samples[0][1]) / dt if dt > 0 else 0
        else:
            self.speed = 0
            self.samples.clear()

    # ---- paths / meta
    def _part(self):
        return self.path + ".part"

    def _meta(self):
        return self.path + ".part.json"

    def save_meta(self):
        if not self.path or not self.chunks or self.status == "done":
            return
        try:
            with open(self._meta(), "w") as f:
                json.dump({"url": self.url, "total": self.total, "etag": self.etag, "chunks": self.chunks}, f)
        except Exception:
            pass

    # ---- main
    def _run(self):
        try:
            self.info = "connecting"
            self._make_session()
            self._probe()
            if self.stop.is_set():
                return
            threading.Thread(target=self._geo, daemon=True).start()
            try:
                if self.ranged and self.total > 0:
                    self._run_ranged()
                else:
                    self._run_single()
            except RangeUnsupported:
                self.ranged, self.chunks = False, []
                self._cleanup_part()
                self._run_single()
            if self.stop.is_set():
                return
            self._finish()
        except Exception as e:
            if self.stop.is_set():
                return
            self.status, self.error, self.info = "error", str(e)[:160], ""

    def _cleanup_part(self):
        for p in (self._part(), self._meta()):
            try:
                os.remove(p)
            except OSError:
                pass
        self.got = 0

    def _make_session(self):
        s = requests.Session()
        s.headers.update({"User-Agent": self.S["user_agent"], "Accept": "*/*", "Accept-Encoding": "identity"})
        if self.S["proxy"].strip():
            p = self.S["proxy"].strip()
            s.proxies = {"http": p, "https": p}
        s.verify = bool(self.S["verify_ssl"])
        ad = HTTPAdapter(pool_connections=4, pool_maxsize=int(self.S["connections"]) + 4, max_retries=0)
        s.mount("http://", ad)
        s.mount("https://", ad)
        self.session = s
        self.timeout = int(self.S["timeout"])
        self.retries = int(self.S["retries"])
        self.limiter = self.mgr.limiter

    def _probe(self):
        last = None
        for hdr in ({"Range": "bytes=0-0"}, {}):
            for attempt in range(3):
                try:
                    r = self.session.get(self.url, headers=hdr, stream=True, timeout=(10, self.timeout))
                except Exception as ex:
                    last = ex
                    self.info = f"connecting… {attempt + 1}"
                    if self.stop.wait(1.5):
                        return
                    continue
                with r:
                    code = r.status_code
                    if code in (200, 206):
                        if not self.name_locked:
                            n = name_from_cd(r.headers.get("Content-Disposition", ""))
                            if n:
                                self.name = n
                        et = r.headers.get("ETag", "")
                        self.etag = "" if et.startswith("W/") else et
                        if code == 206:
                            m = re.search(r"/(\d+)$", r.headers.get("Content-Range", ""))
                            self.total = int(m.group(1)) if m else 0
                            self.ranged = bool(m)
                        else:
                            self.total = int(r.headers.get("Content-Length") or 0)
                            self.ranged = r.headers.get("Accept-Ranges", "").lower() == "bytes" and self.total > 0
                        if not self.path:
                            os.makedirs(self.dir, exist_ok=True)
                            base = Path(self.dir) / self.name
                            if base.exists() and not Path(str(base) + ".part").exists():
                                base = unique_path(base)
                            self.path = str(base)
                            self.name = base.name
                        return
                    if code in (401, 403, 404, 410):
                        raise Fatal(f"HTTP {code}")
                    last = Exception(f"HTTP {code}")
                    break
        raise last or Exception("cannot connect")

    def _geo(self):
        try:
            ip = socket.gethostbyname(self.host)
            self.ip = ip
            _, loc, isp = geo_lookup(ip)
            self.loc = loc + (f"  · {isp}" if isp else "")
        except Exception:
            pass

    def _plan(self, total):
        cs = max(1, int(self.S["chunk_mb"])) * 1024 * 1024
        n = int(self.S["connections"])
        if total / cs < n:
            cs = max(256 * 1024, -(-total // n))
        chunks, s = [], 0
        while s < total:
            e = min(total - 1, s + cs - 1)
            chunks.append([s, e, s])
            s = e + 1
        return chunks

    def _run_ranged(self):
        total, part = self.total, self._part()
        chunks = None
        try:
            with open(self._meta()) as f:
                m = json.load(f)
            if (m.get("total") == total and m.get("url") == self.url and os.path.exists(part)
                    and os.path.getsize(part) == total and (not self.etag or m.get("etag") == self.etag)):
                chunks = m["chunks"]
        except Exception:
            pass
        if chunks is None:
            chunks = self._plan(total)
            with open(part, "wb") as f:
                f.truncate(total)
        self.chunks = chunks
        self.got = sum(min(c[2], c[1] + 1) - c[0] for c in chunks)
        pending = [i for i, c in enumerate(chunks) if c[2] <= c[1]]
        q = queue.Queue()
        for i in pending:
            q.put(i)
        self.remaining, self.fail_streak, self.fatal = len(pending), 0, None
        n = min(int(self.S["connections"]), len(pending))
        ths = [threading.Thread(target=self._worker, args=(q, part), daemon=True) for _ in range(n)]
        for t in ths:
            t.start()
        last = 0
        while any(t.is_alive() for t in ths):
            time.sleep(0.4)
            if time.time() - last > 2:
                self.save_meta()
                last = time.time()
        self.save_meta()
        if self.stop.is_set():
            return
        if self.fatal:
            raise self.fatal
        if self.remaining > 0:
            raise Exception(self.last_err or "incomplete download")
        if os.path.getsize(part) != total:
            raise Exception("size mismatch")

    def _worker(self, q, part):
        with open(part, "r+b") as f:
            while not self.stop.is_set() and self.fatal is None:
                with self.lock:
                    if self.remaining <= 0:
                        return
                try:
                    idx = q.get(timeout=0.4)
                except queue.Empty:
                    continue
                with self.lock:
                    self.active += 1
                try:
                    ok = self._fetch_chunk(idx, f)
                except (RangeUnsupported, Fatal) as ex:
                    self.fatal = ex
                    return
                finally:
                    with self.lock:
                        self.active -= 1
                if ok:
                    with self.lock:
                        self.remaining -= 1
                        self.fail_streak = 0
                else:
                    q.put(idx)
                    with self.lock:
                        self.fail_streak += 1
                        streak = self.fail_streak
                    if streak > self.retries * max(1, int(self.S["connections"])):
                        self.fatal = Exception(self.last_err or "too many errors")
                        return
                    self.info = f"retrying ({streak})"
                    self.stop.wait(min(2 ** min(streak, 5), 30) * (0.6 + random.random() * 0.8) / max(1, int(self.S["connections"]) / 2))

    def _fetch_chunk(self, idx, f):
        c = self.chunks[idx]
        s, e, pos = c
        if pos > e:
            return True
        hdr = {"Range": f"bytes={pos}-{e}"}
        if self.etag:
            hdr["If-Range"] = self.etag
        try:
            r = self.session.get(self.url, headers=hdr, stream=True, timeout=(10, self.timeout))
        except Exception as ex:
            self.last_err = str(ex)[:120]
            return False
        try:
            if r.status_code != 206:
                if r.status_code == 200:
                    raise RangeUnsupported()
                if r.status_code in (401, 403, 404, 410):
                    raise Fatal(f"HTTP {r.status_code}")
                self.last_err = f"HTTP {r.status_code}"
                return False
            f.seek(pos)
            for data in r.iter_content(65536):
                if self.stop.is_set():
                    return False
                left = e - pos + 1
                if len(data) > left:
                    data = data[:left]
                n = len(data)
                self.limiter.wait(n)
                f.write(data)
                pos += n
                c[2] = pos
                self.got += n
                if pos > e:
                    break
            return pos > e
        except (RangeUnsupported, Fatal):
            raise
        except Exception as ex:
            self.last_err = str(ex)[:120]
            return False
        finally:
            r.close()

    def _run_single(self):
        part, tries = self._part(), 0
        self.chunks = []
        while not self.stop.is_set():
            pos = os.path.getsize(part) if os.path.exists(part) else 0
            hdr = {"Range": f"bytes={pos}-"} if pos > 0 else {}
            try:
                r = self.session.get(self.url, headers=hdr, stream=True, timeout=(10, self.timeout))
                with r:
                    if r.status_code == 206 and pos > 0:
                        mode = "ab"
                    elif r.status_code == 200:
                        mode, pos = "wb", 0
                        self.total = int(r.headers.get("Content-Length") or 0)
                    elif r.status_code == 416 and pos > 0:
                        os.remove(part)
                        continue
                    elif r.status_code in (401, 403, 404, 410):
                        raise Fatal(f"HTTP {r.status_code}")
                    else:
                        raise Exception(f"HTTP {r.status_code}")
                    self.got = pos
                    with open(part, mode) as f:
                        for data in r.iter_content(65536):
                            if self.stop.is_set():
                                return
                            self.limiter.wait(len(data))
                            f.write(data)
                            self.got += len(data)
                if self.total and self.got != self.total:
                    raise Exception("incomplete download")
                self.total = self.total or self.got
                return
            except Fatal:
                raise
            except Exception as ex:
                tries += 1
                self.last_err = str(ex)[:120]
                self.info = f"retry {tries}"
                if tries > self.retries:
                    raise
                self.stop.wait(min(2 ** tries, 20))

    def _finish(self):
        part = self._part()
        if self.total and os.path.getsize(part) != self.total:
            raise Exception("size mismatch")
        os.replace(part, self.path)
        try:
            os.remove(self._meta())
        except OSError:
            pass
        self.got = self.total = os.path.getsize(self.path)
        if self.checksum:
            self.status, self.info = "verifying", "checksum"
            algo = {32: "md5", 40: "sha1", 64: "sha256"}.get(len(self.checksum))
            h = hashlib.new(algo)
            with open(self.path, "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            if h.hexdigest().lower() != self.checksum:
                self.status, self.error, self.info = "error", "checksum mismatch — file is corrupted", ""
                return
        self.status, self.info, self.speed = "done", "", 0


class Manager:
    def __init__(self, S):
        self.S = S
        self.items = []
        self.queue_on = bool(S["auto_start"])
        self.limiter = Limiter(lambda: int(self.S["speed_limit_kb"]))
        self._save_t = 0
        self.load()

    def add_many(self, entries, dest, top=False):
        new = [Download(self, u, dest, checksum=ck) for u, ck in entries]
        self.items = new + self.items if top else self.items + new
        self.save()
        return new

    def remove(self, d, delete_part=True):
        d.cancel(delete_part)
        if d in self.items:
            self.items.remove(d)
        self.save()

    def move(self, d, delta):
        i = self.items.index(d)
        j = i + delta
        if 0 <= j < len(self.items):
            self.items[i], self.items[j] = self.items[j], self.items[i]
            self.save()

    def sort_natural(self):
        self.items.sort(key=lambda d: natural_key(d.name))
        self.save()

    def clear_done(self):
        self.items = [d for d in self.items if d.status != "done"]
        self.save()

    def tick(self):
        for d in self.items:
            d.tick()
        if self.queue_on:
            running = sum(1 for d in self.items if d.status in ("running", "verifying"))
            slots = max(1, int(self.S["max_parallel"])) - running
            for d in self.items:
                if slots <= 0:
                    break
                if d.status == "error" and self.S["stop_on_error"]:
                    break
                if d.status == "queued":
                    d.start()
                    slots -= 1
        if time.time() - self._save_t > 5:
            self.save()

    def save(self):
        self._save_t = time.time()
        out = []
        for d in self.items:
            st = d.status if d.status in ("paused", "error", "done") else "queued"
            out.append(dict(url=d.url, dir=d.dir, name=d.name, path=d.path, total=d.total, got=d.got, status=st,
                            checksum=d.checksum, scene=d.scene, error=d.error, locked=d.name_locked))
        try:
            QUEUE_FILE.write_text(json.dumps(out, ensure_ascii=False), "utf-8")
        except Exception:
            pass

    def load(self):
        try:
            data = json.loads(QUEUE_FILE.read_text("utf-8"))
        except Exception:
            return
        for o in data:
            d = Download(self, o["url"], o["dir"], o["name"] if o.get("locked") or o.get("path") else "", o.get("checksum", ""), o.get("scene"))
            d.name, d.path, d.total, d.got = o["name"], o.get("path", ""), o.get("total", 0), o.get("got", 0)
            d.status, d.error = o["status"], o.get("error", "")
            d.name_locked = bool(d.path)
            self.items.append(d)

    def shutdown(self):
        for d in self.items:
            if d.status in ("running", "verifying"):
                d.stop.set()
        time.sleep(0.2)
        for d in self.items:
            d.save_meta()
        self.save()


# ───────────────────────── UI widgets ─────────────────────────
class Rule(QWidget):
    """سربرگ پنل به سبک ╭─ TITLE ────"""

    def __init__(self, title):
        super().__init__()
        self.t = title
        self.setFixedHeight(22)

    def paintEvent(self, _):
        p = QPainter(self)
        f = mono(12)
        p.setFont(f)
        fm = QFontMetricsF(f)
        s = f"╭─ {self.t} "
        p.setPen(QColor(FG))
        p.drawText(QPointF(0, fm.ascent() + 3), s)
        x = fm.horizontalAdvance(s)
        p.setPen(QColor(LINE))
        p.drawLine(QPointF(x, 12), QPointF(self.width(), 12))


class AsciiView(QWidget):
    def __init__(self):
        super().__init__()
        self.frame = None
        self._qc = {}
        self.setMinimumSize(320, 150)

    def set_frame(self, fr):
        self.frame = fr
        self.update()

    def _c(self, h):
        c = self._qc.get(h)
        if c is None:
            c = self._qc[h] = QColor(h)
        return c

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(BG))
        fr = self.frame
        if not fr:
            return
        rows, cols = len(fr), len(fr[0][0])
        ref = mono(100)
        rfm = QFontMetricsF(ref)
        aw, lh = rfm.horizontalAdvance("█") / 100, rfm.height() / 100
        px = max(4, int(min(self.width() / (cols * aw), self.height() / (rows * lh))))
        f = mono(px)
        p.setFont(f)
        fm = QFontMetricsF(f)
        cw, lhp = fm.horizontalAdvance("█"), fm.height()
        ox, oy = (self.width() - cw * cols) / 2, (self.height() - lhp * rows) / 2
        for r, (txt, cols_) in enumerate(fr):
            y = oy + r * lhp + fm.ascent()
            i, n = 0, len(txt)
            while i < n:
                c, j = cols_[i], i
                while j < n and cols_[j] == c:
                    j += 1
                seg = txt[i:j]
                if seg.strip():
                    p.setPen(self._c(c))
                    p.drawText(QPointF(ox + i * cw, y), seg)
                i = j


ICONS = {"queued": "…", "running": "↓", "paused": "‖", "done": "✓", "error": "✕", "verifying": "◇"}
ROW_H = 68


class RowWidget(QWidget):
    def __init__(self, d, mgr):
        super().__init__()
        self.d, self.mgr, self.sel = d, mgr, False
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _):
        d, W, H = self.d, self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(self.rect(), QColor("#161616" if self.sel else BG))
        if self.sel:
            p.fillRect(0, 0, 3, H, QColor(FG))
        p.setPen(QColor("#222"))
        p.drawLine(0, H - 1, W, H - 1)
        f = mono(12)
        p.setFont(f)
        fm = QFontMetricsF(f)
        cw, lh = fm.horizontalAdvance("M"), fm.height() + 3
        cols = max(24, int((W - 30) / cw))

        def T(col, row, s, color):
            p.setPen(QColor(color))
            p.drawText(QPointF(16 + col * cw, 8 + row * lh + fm.ascent()), s)

        try:
            idx = self.mgr.items.index(d) + 1
        except ValueError:
            idx = 0
        dim = d.status in ("queued", "paused")
        main = DIM if dim else FG
        sz = (f"{fmt_size(d.got)} / {fmt_size(d.total)}" if d.total and d.status != "done" else fmt_size(d.total or d.got))
        name = d.name
        room = cols - 7 - len(sz) - 2
        if len(name) > room:
            name = name[:max(1, room - 1)] + "…"
        T(0, 0, f"#{idx:02d}", DIM)
        T(4, 0, ICONS.get(d.status, "?"), "#ff7b72" if d.status == "error" else FG)
        T(6, 0, name, main)
        T(cols - len(sz), 0, sz, DIM)
        # bar
        blen = max(10, cols - 36)
        if d.total:
            frac = clamp(d.got / d.total)
            n = int(frac * blen)
            bar = "█" * n + "░" * (blen - n)
            pct = f"{int(frac * 100):3d}%"
        else:
            pos = int(time.time() * 12) % blen if d.status == "running" else 0
            bar = "░" * pos + "███" + "░" * max(0, blen - pos - 3)
            bar = bar[:blen]
            pct = " --%"
        T(0, 1, bar, main if d.status != "error" else "#ff7b72")
        eta = fmt_eta((d.total - d.got) / d.speed) if d.status == "running" and d.speed > 1 and d.total else "--:--"
        spd = fmt_speed(d.speed) if d.status == "running" else ""
        T(blen + 1, 1, f"{pct} {spd:>11} {eta:>8}", main)
        # info line
        right = {"running": f"{d.active}/{int(self.mgr.S['connections'])} conn" + (f" · {d.info}" if d.info else ""),
                 "queued": "waiting", "paused": "paused", "done": "saved ✓", "verifying": "verifying checksum",
                 "error": d.error}.get(d.status, "")
        left = f"⌖ {d.ip or d.host}" + (f"  {d.loc}" if d.loc else "")
        room = cols - len(right) - 2
        if len(left) > room:
            left = left[:max(1, room - 1)] + "…"
        T(0, 2, left, DIM)
        T(max(len(left) + 2, cols - len(right)), 2, right[:cols - len(left) - 2], "#ff7b72" if d.status == "error" else DIM)


class DLList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.itemSelectionChanged.connect(self._sync)

    def _sync(self):
        cur = self.currentItem()
        for i in range(self.count()):
            w = self.itemWidget(self.item(i))
            if w:
                w.sel = self.item(i) is cur and cur.isSelected()
                w.update()


EMPTY_ART = """\
╭╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╮
╎                                       ╎
╎                   ↑                   ╎
╎                 ──┴──                 ╎
╎                                       ╎
╎    Paste a link above, or open ADD    ╎
╎      to queue many links in order     ╎
╎                                       ╎
╰╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╯"""


class ScenePanel(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(Rule(tr("live")))
        self.view = AsciiView()
        lay.addWidget(self.view, 1)
        self.l_scene, self.l_file, self.l_bar, self.l_srv, self.l_loc = (QLabel() for _ in range(5))
        for l in (self.l_scene, self.l_srv, self.l_loc):
            l.setObjectName("dim")
        self.l_bar.setFont(mono(12))
        for l in (self.l_scene, self.l_file, self.l_bar, self.l_srv, self.l_loc):
            lay.addWidget(l)

    def update_info(self, d, scene_name):
        self.l_scene.setText(f"◢ {scene_name}")
        if not d:
            for l in (self.l_file, self.l_bar, self.l_srv, self.l_loc):
                l.setText("")
            return
        self.l_file.setText(d.name[:60])
        if d.total:
            fr = clamp(d.got / d.total)
            n = int(fr * 34)
            eta = fmt_eta((d.total - d.got) / d.speed) if d.speed > 1 and d.status == "running" else "--:--"
            self.l_bar.setText("█" * n + "░" * (34 - n) + f" {int(fr * 100):3d}%  {fmt_speed(d.speed) if d.status == 'running' else d.status}  {eta}")
        else:
            self.l_bar.setText(d.status)
        self.l_srv.setText(f"SERVER    {d.ip or d.host or '—'}")
        self.l_loc.setText(f"LOCATION  {d.loc or 'resolving…'}")


class DownloadsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.mgr, self.S = win, win.mgr, win.S
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        self.url = QLineEdit()
        self.url.setPlaceholderText(tr("paste_hint"))
        self.url.returnPressed.connect(self.quick_add)
        b = QPushButton(tr("add_btn"))
        b.clicked.connect(self.quick_add)
        bar.addWidget(self.url, 1)
        bar.addWidget(b)
        lay.addLayout(bar)
        tb = QHBoxLayout()
        tb.setSpacing(4)
        for text, fn, tip in ((tr("start"), self.act_start, "start / resume / retry selected"), (tr("pause"), self.act_pause, "pause selected"),
                              ("▲", lambda: self.act_move(-1), "move up in queue"), ("▼", lambda: self.act_move(1), "move down in queue"),
                              ("A→Z", self.act_sort, "sort queue by name (part1, part2, …)"), (tr("remove"), self.act_remove, "remove selected"),
                              (tr("open"), self.act_open, "open file"), (tr("folder"), self.act_folder, "show in folder"), (tr("clear_done"), self.act_clear, "")):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.clicked.connect(fn)
            tb.addWidget(btn)
        tb.addStretch(1)
        lay.addLayout(tb)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        ll.addWidget(Rule(tr("queue_title")))
        holder = QWidget()
        self.stack = QStackedLayout(holder)
        self.lw = DLList()
        self.lw.itemDoubleClicked.connect(self.act_double)
        self.empty = QLabel(EMPTY_ART)
        self.empty.setFont(mono(13))
        self.empty.setObjectName("dim")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(self.lw)
        self.stack.addWidget(self.empty)
        ll.addWidget(holder, 1)
        self.panel = ScenePanel()
        split.addWidget(left)
        split.addWidget(self.panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([620, 440])
        lay.addWidget(split, 1)
        self.rebuild()

    # ---- list
    def selected(self):
        it = self.lw.currentItem()
        if not it:
            return None
        i = self.lw.row(it)
        return self.mgr.items[i] if 0 <= i < len(self.mgr.items) else None

    def rebuild(self):
        cur = self.selected()
        self.lw.blockSignals(True)
        self.lw.clear()
        for d in self.mgr.items:
            it = QListWidgetItem()
            it.setSizeHint(QSize(100, ROW_H))
            self.lw.addItem(it)
            self.lw.setItemWidget(it, RowWidget(d, self.mgr))
        if cur in self.mgr.items:
            self.lw.setCurrentRow(self.mgr.items.index(cur))
        self.lw.blockSignals(False)
        self.lw._sync()
        self.stack.setCurrentIndex(0 if self.mgr.items else 1)

    def focus(self):
        d = self.selected()
        if d:
            return d
        for x in self.mgr.items:
            if x.status == "running":
                return x
        return self.mgr.items[-1] if self.mgr.items else None

    def refresh(self):
        for i in range(self.lw.count()):
            w = self.lw.itemWidget(self.lw.item(i))
            if w:
                w.update()
        d = self.focus()
        mode = int(self.S["scene_mode"])
        idx = mode if 0 <= mode < len(SCENES) else (d.scene if d else self.win.runner.idx)
        self.win.runner.idx = idx
        self.panel.update_info(d, SCENES[idx].name)

    # ---- actions
    def quick_add(self):
        ents = parse_links(self.url.text())
        if not ents:
            return
        self.mgr.add_many(ents, self.S["download_dir"])
        self.url.clear()
        self.rebuild()

    def act_start(self):
        d = self.selected()
        if d and d.status in ("queued", "paused", "error"):
            d.start()
            self.mgr.queue_on = True
            self.win.sync_queue_btn()

    def act_pause(self):
        d = self.selected()
        if d and d.status in ("running", "verifying"):
            d.pause()
        elif d and d.status == "queued":
            d.status = "paused"

    def act_move(self, delta):
        d = self.selected()
        if d:
            self.mgr.move(d, delta)
            self.rebuild()

    def act_sort(self):
        self.mgr.sort_natural()
        self.rebuild()

    def act_remove(self):
        d = self.selected()
        if not d:
            return
        if d.status in ("running", "paused", "error", "queued") and d.got > 0:
            if QMessageBox.question(self, "Remove", f"Remove '{d.name}' and delete the partial data?") != QMessageBox.StandardButton.Yes:
                return
        self.mgr.remove(d)
        self.rebuild()

    def act_open(self):
        d = self.selected()
        if d and d.status == "done":
            open_path(d.path)

    def act_folder(self):
        d = self.selected()
        if d:
            reveal(d.path) if d.path else open_path(d.dir)

    def act_clear(self):
        self.mgr.clear_done()
        self.rebuild()

    def act_double(self, _):
        d = self.selected()
        if not d:
            return
        if d.status == "done":
            open_path(d.path)
        elif d.status in ("running", "verifying"):
            self.act_pause()
        else:
            self.act_start()


class AddPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.S = win, win.S
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        lay.addWidget(Rule(tr("add_title")))
        h = QLabel(tr("add_hint"))
        h.setObjectName("dim")
        lay.addWidget(h)
        self.te = QPlainTextEdit()
        self.te.setObjectName("drop")
        self.te.setFont(mono(12))
        self.te.setPlaceholderText("╭╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╮\n╎   drop or paste links here  ↑          ╎\n╰╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╯\n\nhttps://example.com/files/part1.zip\nhttps://example.com/files/part2.zip")
        self.te.textChanged.connect(self.count)
        self.te.setAcceptDrops(True)
        lay.addWidget(self.te, 1)
        self.cnt = QLabel("0 " + tr("valid_links"))
        self.cnt.setObjectName("dim")
        lay.addWidget(self.cnt)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        self.dest = QLineEdit(self.S["download_dir"])
        bb = QPushButton(tr("browse"))
        bb.clicked.connect(self.browse)
        g.addWidget(QLabel(tr("save_to")), 0, 0)
        g.addWidget(self.dest, 0, 1)
        g.addWidget(bb, 0, 2)
        self.mode = QComboBox()
        self.mode.addItems([tr("mode_ordered"), tr("mode_parallel")])
        self.mode.setCurrentIndex(0 if int(self.S["max_parallel"]) == 1 else 1)
        g.addWidget(QLabel(tr("mode")), 1, 0)
        g.addWidget(self.mode, 1, 1, 1, 2)
        self.pos = QComboBox()
        self.pos.addItems([tr("pos_end"), tr("pos_top")])
        g.addWidget(QLabel(tr("position")), 2, 0)
        g.addWidget(self.pos, 2, 1, 1, 2)
        self.nat = QCheckBox(tr("nat"))
        self.go = QCheckBox(tr("go"))
        self.go.setChecked(True)
        g.addWidget(self.nat, 3, 1, 1, 2)
        g.addWidget(self.go, 4, 1, 1, 2)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        row = QHBoxLayout()
        for t, fn in ((tr("paste"), self.paste), (tr("clear"), self.te.clear)):
            b = QPushButton(t)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        ab = QPushButton(tr("add_queue"))
        ab.clicked.connect(self.add)
        row.addWidget(ab)
        lay.addLayout(row)

    def count(self):
        self.cnt.setText(f"{len(parse_links(self.te.toPlainText()))} {tr('valid_links')}")

    def paste(self):
        self.te.appendPlainText(QApplication.clipboard().text())

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save to", self.dest.text())
        if d:
            self.dest.setText(d)

    def add(self):
        ents = parse_links(self.te.toPlainText())
        if not ents:
            return
        if self.nat.isChecked():
            ents.sort(key=lambda e: natural_key(e[0]))
        if self.mode.currentIndex() == 0:
            self.S["max_parallel"] = 1
        elif int(self.S["max_parallel"]) == 1:
            self.S["max_parallel"] = 3
        self.S.save()
        self.win.mgr.add_many(ents, self.dest.text().strip() or self.S["download_dir"], top=self.pos.currentIndex() == 1)
        if self.go.isChecked():
            self.win.mgr.queue_on = True
            self.win.sync_queue_btn()
        self.te.clear()
        self.win.pages["downloads"].rebuild()
        self.win.show_page(0)
        self.win.settings_page.load()


class FilesPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.S = win, win.S
        self.open_dirs = set()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 8)
        lay.setSpacing(8)
        lay.addWidget(Rule(tr("files_title")))
        self.path = QLabel()
        self.path.setObjectName("dim")
        lay.addWidget(self.path)
        tb = QHBoxLayout()
        for t, fn in ((tr("open"), self.act_open), (tr("folder"), self.act_folder), (tr("delete"), self.act_delete), (tr("refresh"), self.rebuild)):
            b = QPushButton(t)
            b.clicked.connect(fn)
            tb.addWidget(b)
        tb.addStretch(1)
        lay.addLayout(tb)
        self.lw = QListWidget()
        self.lw.setObjectName("files")
        self.lw.setFont(mono(13))
        self.lw.itemClicked.connect(self.on_click)
        self.lw.itemDoubleClicked.connect(self.on_dbl)
        lay.addWidget(self.lw, 1)
        self.info = QLabel()
        self.info.setObjectName("dim")
        lay.addWidget(self.info)

    def rebuild(self):
        root = self.S["download_dir"]
        self.path.setText(root)
        rows = []
        self.open_dirs.add(root)

        def walk(d, prefix, depth):
            try:
                ents = sorted(os.scandir(d), key=lambda e: (not e.is_dir(), e.name.lower()))
            except OSError:
                return
            ents = [e for e in ents if not e.name.endswith(".part.json")]
            for i, e in enumerate(ents):
                if len(rows) > 600:
                    return
                last = i == len(ents) - 1
                isd = e.is_dir()
                op = e.path in self.open_dirs
                label = prefix + ("└─ " if last else "├─ ") + (("▼ " if op else "▶ ") + e.name + "/" if isd else "• " + e.name)
                try:
                    size = "" if isd else fmt_size(e.stat().st_size)
                except OSError:
                    size = ""
                rows.append((f"{label:<58.58}{size:>10}", e.path, isd))
                if isd and op and depth < 6:
                    walk(e.path, prefix + ("   " if last else "│  "), depth + 1)

        rname = os.path.basename(root.rstrip("/" + chr(92))) or root
        rows.append((f"▼ {rname}/", root, True))
        walk(root, "", 0)
        self.lw.clear()
        for text, path, isd in rows:
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, (path, isd))
            self.lw.addItem(it)
        self.info.setText(f"{len(rows) - 1} items")

    def cur(self):
        it = self.lw.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else (None, False)

    def on_click(self, it):
        path, isd = it.data(Qt.ItemDataRole.UserRole)
        if isd and path != self.S["download_dir"]:
            self.open_dirs ^= {path}
            self.rebuild()
        try:
            st = os.stat(path)
            self.info.setText(f"{os.path.basename(path)}  ·  {fmt_size(st.st_size) if not isd else 'folder'}  ·  {time.strftime('%Y-%m-%d %H:%M', time.localtime(st.st_mtime))}")
        except OSError:
            pass

    def on_dbl(self, it):
        path, isd = it.data(Qt.ItemDataRole.UserRole)
        if not isd:
            open_path(path)

    def act_open(self):
        p, _ = self.cur()
        if p:
            open_path(p)

    def act_folder(self):
        p, _ = self.cur()
        reveal(p) if p else open_path(self.S["download_dir"])

    def act_delete(self):
        p, isd = self.cur()
        if not p or isd or p == self.S["download_dir"]:
            return
        if QMessageBox.question(self, "Delete", f"Delete '{os.path.basename(p)}' permanently?") == QMessageBox.StandardButton.Yes:
            try:
                os.remove(p)
            except OSError as e:
                QMessageBox.warning(self, "Delete", str(e))
            self.rebuild()


class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.S = win, win.S
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        lay.addWidget(Rule(tr("settings_title")))
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(7)
        self.w = {}
        r = 0

        def row(key, label, widget, hint=""):
            nonlocal r
            g.addWidget(QLabel(label), r, 0)
            g.addWidget(widget, r, 1)
            if hint:
                h = QLabel(hint)
                h.setObjectName("dim")
                g.addWidget(h, r, 2)
            self.w[key] = widget
            r += 1

        def spin(lo, hi, suffix=""):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setSuffix(suffix)
            return s

        dl = QWidget()
        dh = QHBoxLayout(dl)
        dh.setContentsMargins(0, 0, 0, 0)
        e = QLineEdit()
        bb = QPushButton(tr("browse"))
        bb.clicked.connect(self.browse)
        dh.addWidget(e, 1)
        dh.addWidget(bb)
        g.addWidget(QLabel(tr("s_dir")), r, 0)
        g.addWidget(dl, r, 1)
        self.w["download_dir"] = e
        r += 1
        row("connections", tr("s_conn"), spin(1, 32), "8 is a good start; lower it on unstable links")
        row("chunk_mb", tr("s_chunk"), spin(1, 64, " MB"), "small chunks = faster recovery from drops")
        row("max_parallel", tr("s_par"), spin(1, 10), "1 = strictly ordered queue")
        row("speed_limit_kb", tr("s_speed"), spin(0, 10_000_000, " KB/s"), "0 = unlimited")
        row("retries", tr("s_retries"), spin(1, 100))
        row("timeout", tr("s_timeout"), spin(5, 180, " s"))
        row("proxy", tr("s_proxy"), QLineEdit(), "http://127.0.0.1:2080  or  socks5://127.0.0.1:1080")
        row("user_agent", tr("s_ua"), QLineEdit())
        row("verify_ssl", tr("s_ssl"), QCheckBox())
        row("stop_on_error", tr("s_stop"), QCheckBox())
        row("auto_start", tr("s_auto"), QCheckBox())
        row("scene_enabled", tr("s_scene"), QCheckBox())
        row("scene_fps", tr("s_fps"), spin(4, 30))
        cb = QComboBox()
        cb.addItem(tr("s_random"), -1)
        for i, sc in enumerate(SCENES):
            cb.addItem(sc.name, i)
        row("scene_mode", tr("s_scene_mode"), cb)
        lc = QComboBox()
        for code, nm in (("en", "English"), ("fa", "فارسی"), ("ar", "العربية")):
            lc.addItem(nm, code)
        row("language", tr("s_lang"), lc)
        g.setColumnStretch(1, 1)
        lay.addLayout(g)
        lay.addStretch(1)
        row2 = QHBoxLayout()
        row2.addStretch(1)
        sv = QPushButton(tr("save"))
        sv.clicked.connect(self.save)
        row2.addWidget(sv)
        lay.addLayout(row2)
        self.load()

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, tr("s_dir"), self.w["download_dir"].text())
        if d:
            self.w["download_dir"].setText(d)

    def load(self):
        for k, w in self.w.items():
            v = self.S[k]
            if isinstance(w, QSpinBox):
                w.setValue(int(v))
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(v)))
            else:
                w.setText(str(v))

    def save(self):
        old_lang = self.S["language"]
        for k, w in self.w.items():
            if isinstance(w, QSpinBox):
                self.S[k] = w.value()
            elif isinstance(w, QCheckBox):
                self.S[k] = w.isChecked()
            elif isinstance(w, QComboBox):
                self.S[k] = w.currentData()
            else:
                self.S[k] = w.text().strip()
        self.S.save()
        self.win.apply_settings()
        if self.S["language"] != old_lang:
            QMessageBox.information(self, "NEO·DL", tr("restart_note"))


class TitleBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setFixedHeight(34)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(0)
        t = QLabel("◼ NEO·DL")
        t.setFont(mono(13))
        sub = QLabel("   " + tr("subtitle"))
        sub.setObjectName("dim")
        lay.addWidget(t)
        lay.addWidget(sub)
        lay.addStretch(1)
        for txt, fn in (("—", win.showMinimized), ("✕", win.close)):
            b = QPushButton(txt)
            b.setObjectName("win")
            b.setFixedHeight(34)
            b.clicked.connect(fn)
            lay.addWidget(b)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.win.windowHandle():
            self.win.windowHandle().startSystemMove()


class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowMinimizeButtonHint)
        self.setWindowTitle("NEO·DL")
        self.setMinimumSize(920, 580)
        self.S = Settings()
        self.resize(int(self.S["win_w"]), int(self.S["win_h"]))
        self.mgr = Manager(self.S)
        self.runner = SceneRunner(self.S)
        self.runner.start()
        self.me = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QWidget()
        root.setObjectName("root")
        outer.addWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)
        v.addWidget(TitleBar(self))
        nav = QHBoxLayout()
        nav.setContentsMargins(8, 0, 8, 0)
        nav.setSpacing(0)
        self.navs = []
        for i, t in enumerate((tr("nav_dl"), tr("nav_add"), tr("nav_files"), tr("nav_set"))):
            b = QPushButton(t)
            b.setObjectName("nav")
            b.setCheckable(True)
            b.clicked.connect(lambda _, i=i: self.show_page(i))
            nav.addWidget(b)
            self.navs.append(b)
        nav.addStretch(1)
        self.qbtn = QPushButton()
        self.qbtn.clicked.connect(self.toggle_queue)
        nav.addWidget(self.qbtn)
        v.addLayout(nav)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#2a2a2a;")
        v.addWidget(line)

        self.pages_stack = QStackedWidget()
        self.pages = {}
        self.pages["downloads"] = DownloadsPage(self)
        self.add_page = AddPage(self)
        self.files_page = FilesPage(self)
        self.settings_page = SettingsPage(self)
        for w in (self.pages["downloads"], self.add_page, self.files_page, self.settings_page):
            self.pages_stack.addWidget(w)
        v.addWidget(self.pages_stack, 1)

        sb = QHBoxLayout()
        sb.setContentsMargins(12, 4, 0, 0)
        self.s_me, self.s_speed, self.s_cnt = QLabel("YOU  …"), QLabel(), QLabel()
        self.s_me.setObjectName("dim")
        self.s_cnt.setObjectName("dim")
        sb.addWidget(self.s_me)
        sb.addStretch(1)
        sb.addWidget(self.s_speed)
        sb.addSpacing(18)
        sb.addWidget(self.s_cnt)
        sb.addWidget(QSizeGrip(self), 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        v.addLayout(sb)

        self.sync_queue_btn()
        self.show_page(int(self.S["last_page"]))
        self.tick_t = QTimer(self)
        self.tick_t.timeout.connect(self.on_tick)
        self.tick_t.start(250)
        self.frame_t = QTimer(self)
        self.frame_t.timeout.connect(self.on_frame)
        self.apply_settings()
        threading.Thread(target=self._whoami, daemon=True).start()

    def _whoami(self):
        ip, loc, isp = geo_lookup("")
        self.me = f"YOU  {ip}" + (f"  ·  {loc}" if loc else "") if ip else "YOU  offline?"

    def show_page(self, i):
        self.S["last_page"] = i
        self.pages_stack.setCurrentIndex(i)
        for j, b in enumerate(self.navs):
            b.setChecked(j == i)
        if i == 2:
            self.files_page.rebuild()
        if i == 3:
            self.settings_page.load()

    def sync_queue_btn(self):
        self.qbtn.setText(tr("q_on") if self.mgr.queue_on else tr("q_off"))

    def toggle_queue(self):
        self.mgr.queue_on = not self.mgr.queue_on
        self.sync_queue_btn()

    def apply_settings(self):
        self.frame_t.start(int(1000 / max(1, int(self.S["scene_fps"]))))
        self.pages["downloads"].panel.setVisible(bool(self.S["scene_enabled"]))

    def on_tick(self):
        self.mgr.tick()
        dp = self.pages["downloads"]
        self.runner.active = self.pages_stack.currentIndex() == 0 and not self.isMinimized()
        dp.refresh()
        run = [d for d in self.mgr.items if d.status == "running"]
        self.s_speed.setText(f"↓ {fmt_speed(sum(d.speed for d in run))}")
        done = sum(1 for d in self.mgr.items if d.status == "done")
        self.s_cnt.setText(f"{len(run)} active · {done}/{len(self.mgr.items)} done")
        if self.me:
            self.s_me.setText(self.me)

    def on_frame(self):
        fr = self.runner.frame
        if fr is not None and self.runner.active:
            self.pages["downloads"].panel.view.set_frame(fr)

    def changeEvent(self, e):
        if self.windowState() & Qt.WindowState.WindowMaximized:   # no maximize / fullscreen
            self.showNormal()
        super().changeEvent(e)

    def closeEvent(self, e):
        self.S["win_w"], self.S["win_h"] = self.width(), self.height()
        self.runner.run_flag = False
        self.mgr.shutdown()
        self.S.save()
        e.accept()


def main():
    global MONO, LANG
    app = QApplication(sys.argv)
    LANG = Settings()["language"]
    if LANG not in I18N:
        LANG = "en"
    if LANG in RTL_LANGS:
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    MONO = pick_mono()
    app.setStyleSheet(QSS.replace("%MONO%", MONO))
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
