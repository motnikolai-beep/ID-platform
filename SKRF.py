from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import os
import re
import sqlite3
import ssl
import threading
import time

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import flet as ft
import requests

from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

try:
    import winsound
except ImportError:
    winsound = None


# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

APP_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(
    os.environ.get("SKRF_DATA_DIR")
    or os.environ.get("FLET_APP_STORAGE_DATA")
    or APP_DIR
)
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "rt_cache.db"
LOG_PATH = DATA_DIR / "skrf.log"

logging.basicConfig(
    filename=str(LOG_PATH),
    level=logging.INFO,
    encoding="utf-8",
    format="%(asctime)s %(levelname)s %(message)s",
)

HOST = "стройкомплекс.рф".encode("idna").decode("ascii")
BASE_URL = f"https://{HOST}/api/visary"

PAGE_SIZE = 25
HTTP_TIMEOUT = 20

# Как в вашем рабочем приложении.
# Для включения проверки можно поставить True и при
# необходимости указать путь к доверенному CA-файлу.
VERIFY_TLS = False
CA_BUNDLE = ""

BG = "#0B0618"
PANEL = "#190F2E"
PANEL_DARK = "#110A20"
PINK = "#FF2D95"
CYAN = "#00E5FF"
GOLD = "#FFD54F"
MUTED = "#B8AACC"
WHITE = "#FFFFFF"
RED = "#FF6B80"

ALL = "__ALL__"
OTHER = "__OTHER__"

RAINBOW = [
    "#FF2D95",
    "#FF8A00",
    "#FFD54F",
    "#00E5A0",
    "#00C8FF",
    "#9254FF",
]

REQ_STATUS = {
    40: "Включён",
    50: "Архив недействующий",
    60: "Недействующий исключён",
}

DOC_STATUS = {
    40: "Действует",
    50: "Заменён",
    60: "Отменён",
}


def section(number, short, title, query="", alias=""):
    return {
        "number": number,
        "short": short,
        "alias": alias,
        "title": title,
        "query": query,
    }


# Это навигационные подборки.
# Поиск по словам не является нормативным определением
# полного состава применимых требований.
WHEEL = [
    {
        "code": "ОСР",
        "title": "ОСР",
        "colors": [PINK, "#7733FF"],
        "sections": [
            section(
                "2", "ПЗУ",
                "Схема планировочной организации земельного участка",
                "земельн",
            ),
            section(
                "3", "АР",
                "Объёмно-планировочные и архитектурные решения",
                "архитектур",
            ),
            section(
                "4", "КР",
                "Конструктивные решения",
                "конструкц",
            ),
            section(
                "7", "ПОС",
                "Проект организации строительства",
                "строительств",
            ),
            section(
                "9", "ПБ",
                "Мероприятия по обеспечению пожарной безопасности",
                "пожар",
            ),
            section(
                "10", "ТБЭ",
                "Требования к безопасной эксплуатации",
                "эксплуатац",
            ),
            section(
                "11", "ОДИ",
                "Мероприятия по обеспечению доступа инвалидов",
                "инвалид",
            ),
        ],
    },
    {
        "code": "ЭМР",
        "title": "ЭМР",
        "colors": ["#FFD200", "#FF6A00"],
        "sections": [
            section(
                "5.а", "ИОС1",
                "Электроснабжение",
                "электро",
                "ЭС",
            ),
            section(
                "5.д", "ИОС5",
                "Сети связи",
                "связ",
                "СС",
            ),
            section(
                "6", "ТХ",
                "Технологические решения: электротехническая часть",
                "электрооборуд",
            ),
            section(
                "9", "ПБ",
                "Пожарная безопасность: электрические системы",
                "пожар",
            ),
            section(
                "10", "ТБЭ",
                "Безопасная эксплуатация электроустановок",
                "электробезопас",
            ),
        ],
    },
    {
        "code": "СВМР",
        "title": "СВМР",
        "colors": ["#00F5D4", "#0072FF"],
        "sections": [
            section(
                "5.б", "ИОС2",
                "Водоснабжение",
                "водоснабж",
                "В",
            ),
            section(
                "5.в", "ИОС3",
                "Водоотведение",
                "водоотвед",
                "К",
            ),
            section(
                "5.г", "ИОС4",
                "Отопление, вентиляция, кондиционирование и тепловые сети",
                "вентиляц",
                "ОВ",
            ),
            section(
                "5.е", "ИОС6",
                "Газоснабжение",
                "газ",
                "ГС",
            ),
            section(
                "6", "ТХ",
                "Технологические решения",
                "технолог",
            ),
            section(
                "8", "ООС",
                "Мероприятия по охране окружающей среды",
                "окружающ",
            ),
        ],
    },
    {
        "code": "ОБЩ",
        "title": "Общее",
        "colors": ["#38EF7D", "#11998E"],
        "sections": [
            section("1", "ПЗ", "Пояснительная записка"),
            section(
                "8", "ООС",
                "Мероприятия по охране окружающей среды",
                "окружающ",
            ),
            section("12", "СМ", "Смета", "смет"),
            section("13", "ИД", "Иная документация"),
        ],
    },
    {
        "code": "ЛИН",
        "title": "Линейные",
        "colors": ["#F857A6", "#FF5858"],
        "sections": [
            section("1", "ПЗ", "Пояснительная записка"),
            section(
                "2", "ППО",
                "Проект полосы отвода",
                "полос",
            ),
            section(
                "3", "ТКР",
                "Технологические и конструктивные решения",
                "сооружен",
            ),
            section(
                "4", "ИЛО",
                "Здания и сооружения инфраструктуры линейного объекта",
                "инфраструктур",
            ),
            section(
                "5", "ПОС",
                "Проект организации строительства",
                "строительств",
            ),
            section(
                "6", "ООС",
                "Мероприятия по охране окружающей среды",
                "окружающ",
            ),
            section(
                "7", "ПБ",
                "Мероприятия по обеспечению пожарной безопасности",
                "пожар",
            ),
            section(
                "8", "ТБЭ",
                "Безопасная эксплуатация линейного объекта",
                "эксплуатац",
            ),
            section("9", "СМ", "Смета", "смет"),
            section("10", "ИД", "Иная документация"),
        ],
    },
]

SEGMENTS = {item["code"]: item for item in WHEEL}
FILTERS = {ALL, OTHER, *SEGMENTS}

SECTION_INDEX = {
    (segment["code"], item["number"]): item
    for segment in WHEEL
    for item in segment["sections"]
}


# ============================================================
# ФОРМАТИРОВАНИЕ
# ============================================================

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    for _ in range(2):
        text = html.unescape(text)

    text = re.sub(
        r"<(script|style)\b[^>]*>.*?</\1\s*>",
        "",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"</(?:p|div|li|tr|h[1-6])\s*>|<br\s*/?>",
        "\n",
        text,
        flags=re.I,
    )

    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")

    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.splitlines()
    ]

    return "\n".join(line for line in lines if line)


def excel_date(value):
    if value is None:
        return "—"

    try:
        return (
            date(1899, 12, 30) + timedelta(days=int(value))
        ).strftime("%d.%m.%Y")

    except (ValueError, TypeError, OverflowError):
        return str(value)


def readable(value):
    if value is None:
        return "—"

    if isinstance(value, list):
        return "\n".join(readable(item) for item in value) or "—"

    if isinstance(value, dict):
        parts = [
            clean_text(value[key])
            for key in ("number", "title", "name", "fullname")
            if value.get(key)
        ]

        if parts:
            return " · ".join(dict.fromkeys(parts))

        return json.dumps(value, ensure_ascii=False, indent=2)

    return clean_text(value)


def normalize_segment(value):
    value = str(value or "").strip()
    return value if value in SEGMENTS else OTHER


def segment_title(code):
    if code == ALL:
        return "Все"
    if code == OTHER:
        return "Прочие"
    return SEGMENTS.get(code, {}).get("title", str(code))


def segment_color(code):
    if code == ALL:
        return GOLD
    if code == OTHER:
        return MUTED
    return SEGMENTS.get(code, {}).get("colors", [PINK])[0]


def enrich(selection):
    result = dict(selection)

    if result.get("source") == "pp87":
        item = SECTION_INDEX.get((
            result.get("segment"),
            str(result.get("number", "")),
        ))

        if item:
            result["short"] = item["short"]
            result["alias"] = item.get("alias", "")

    return result


def selection_for(code, item):
    return {
        "screen": "requirements",
        "segment": code,
        "source": "pp87",
        **item,
        "skip": 0,
        "rt_type_id": None,
    }


def short_name(selection):
    selection = enrich(selection)

    return " · ".join(filter(None, [
        selection.get("short"),
        selection.get("alias"),
    ]))


def label(selection, compact=False):
    selection = enrich(selection)

    if selection.get("screen") == "sections":
        return f"{selection.get('segment', '')} / Разделы"

    parts = [
        selection.get("segment", ""),
        short_name(selection),
    ]

    if selection.get("number"):
        parts.append(f"р. {selection['number']}")

    if not compact or not short_name(selection):
        parts.append(selection.get("title") or "Все требования")

    return " / ".join(filter(None, parts))


def glow(color, blur=18):
    return ft.BoxShadow(
        color=color,
        blur_radius=blur,
        spread_radius=1,
        offset=ft.Offset(0, 0),
    )


# ============================================================
# БАЗА ДАННЫХ
# ============================================================

class Storage:
    def __init__(self, path):
        self.path = str(path)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row

        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self):
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")

            db.execute("""
                CREATE TABLE IF NOT EXISTS c (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL,
                    t REAL NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS saved_sections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    section_key TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    selection_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    segment TEXT NOT NULL DEFAULT ''
                )
            """)

            columns = {
                row["name"]
                for row in db.execute(
                    "PRAGMA table_info(saved_sections)"
                ).fetchall()
            }

            if "segment" not in columns:
                db.execute("""
                    ALTER TABLE saved_sections
                    ADD COLUMN segment TEXT NOT NULL DEFAULT ''
                """)

            rows = db.execute("""
                SELECT id, selection_json
                FROM saved_sections
            """).fetchall()

            for row in rows:
                try:
                    value = json.loads(row["selection_json"])

                    if not isinstance(value, dict):
                        raise ValueError("Некорректный JSON")

                    selection = enrich(value)

                    db.execute("""
                        UPDATE saved_sections
                        SET segment = ?,
                            selection_json = ?,
                            label = ?
                        WHERE id = ?
                    """, (
                        normalize_segment(selection.get("segment")),
                        dump(selection),
                        label(selection),
                        row["id"],
                    ))

                except (ValueError, TypeError):
                    db.execute("""
                        UPDATE saved_sections
                        SET segment = ?
                        WHERE id = ?
                    """, (OTHER, row["id"]))

            db.execute("""
                CREATE INDEX IF NOT EXISTS idx_saved_segment
                ON saved_sections(segment, updated_at DESC)
            """)

    def set_state(self, key, value):
        with self.connection() as db:
            db.execute("""
                INSERT INTO app_state(key, value_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
            """, (key, dump(value), now()))

    def get_state(self, key, default=None):
        with self.connection() as db:
            row = db.execute("""
                SELECT value_json
                FROM app_state
                WHERE key = ?
            """, (key,)).fetchone()

        if row:
            try:
                return json.loads(row["value_json"])
            except (ValueError, TypeError):
                pass

        return default

    def save_section(self, selection):
        selection = enrich(selection)

        key = dump({
            "segment": selection.get("segment"),
            "source": selection.get("source"),
            "number": selection.get("number"),
            "rt_type_id": selection.get("rt_type_id"),
        })

        stamp = now()

        with self.connection() as db:
            db.execute("""
                INSERT INTO saved_sections(
                    section_key, label, selection_json,
                    created_at, updated_at, segment
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(section_key) DO UPDATE SET
                    label = excluded.label,
                    selection_json = excluded.selection_json,
                    updated_at = excluded.updated_at,
                    segment = excluded.segment
            """, (
                key,
                label(selection),
                dump(selection),
                stamp,
                stamp,
                normalize_segment(selection.get("segment")),
            ))

    def saved_snapshot(self, segment=ALL):
        with self.connection() as db:
            grouped = db.execute("""
                SELECT segment, COUNT(*) AS total
                FROM saved_sections
                GROUP BY segment
            """).fetchall()

            if segment == ALL:
                rows = db.execute("""
                    SELECT *
                    FROM saved_sections
                    ORDER BY updated_at DESC, id DESC
                """).fetchall()
            else:
                rows = db.execute("""
                    SELECT *
                    FROM saved_sections
                    WHERE segment = ?
                    ORDER BY updated_at DESC, id DESC
                """, (segment,)).fetchall()

        counts = {
            ALL: 0,
            OTHER: 0,
            **{code: 0 for code in SEGMENTS},
        }

        for row in grouped:
            code = normalize_segment(row["segment"])
            counts[code] += row["total"]
            counts[ALL] += row["total"]

        items = []

        for row in rows:
            item = dict(row)

            try:
                value = json.loads(item["selection_json"])
                item["selection"] = (
                    enrich(value)
                    if isinstance(value, dict)
                    else None
                )
            except (ValueError, TypeError):
                item["selection"] = None

            items.append(item)

        return counts, items

    def delete_section(self, saved_id):
        with self.connection() as db:
            db.execute(
                "DELETE FROM saved_sections WHERE id = ?",
                (saved_id,),
            )

    def get_cache(self, key):
        with self.connection() as db:
            row = db.execute(
                "SELECT v, t FROM c WHERE k = ?",
                (key,),
            ).fetchone()

        if row:
            try:
                return json.loads(row["v"]), row["t"]
            except (ValueError, TypeError):
                pass

        return None

    def put_cache(self, key, data):
        with self.connection() as db:
            db.execute("""
                INSERT OR REPLACE INTO c(k, v, t)
                VALUES (?, ?, ?)
            """, (key, dump(data), time.time()))


# ============================================================
# СЕТЬ — ОСНОВА ИЗ ВАШЕГО РАБОЧЕГО ПРИЛОЖЕНИЯ
# ============================================================

class UnverifiedSslAdapter(HTTPAdapter):
    @staticmethod
    def create_context():
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        return context

    def init_poolmanager(
        self,
        connections,
        maxsize,
        block=False,
        **pool_kwargs,
    ):
        pool_kwargs["ssl_context"] = self.create_context()

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs["ssl_context"] = self.create_context()
        return super().proxy_manager_for(proxy, **proxy_kwargs)


class Api:
    def __init__(self, storage):
        self.storage = storage
        self.local = threading.local()

    def session(self):
        session = getattr(self.local, "session", None)

        if session is None:
            session = requests.Session()

            if not VERIFY_TLS:
                session.mount(
                    "https://",
                    UnverifiedSslAdapter(max_retries=0),
                )

            session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "Stroykompleks-Neon/5.0"
                ),
                "Accept": "application/json, text/plain, */*",
            })

            self.local.session = session

        return session

    def call(self, method, path, params=None, body=None):
        key = dump([method, path, params, body])

        verify = (
            CA_BUNDLE or True
            if VERIFY_TLS
            else False
        )

        try:
            with self.session().request(
                method=method,
                url=BASE_URL.rstrip("/") + "/" + path.lstrip("/"),
                params=params,
                json=body,
                timeout=(8, HTTP_TIMEOUT),
                verify=verify,
                allow_redirects=False,
            ) as response:

                if 300 <= response.status_code < 400:
                    raise RuntimeError(
                        "Портал вернул перенаправление "
                        f"HTTP {response.status_code}. "
                        "Проверьте адрес API."
                    )

                response.raise_for_status()

                data = (
                    {}
                    if response.status_code == 204
                    else response.json()
                )

                if not isinstance(data, dict):
                    raise ValueError(
                        "Ожидался JSON-объект в ответе API"
                    )

        except (
            requests.RequestException,
            ValueError,
            RuntimeError,
            OSError,
        ) as error:
            logging.exception("Ошибка запроса API %s", path)

            cached = self.storage.get_cache(key)

            if cached is not None:
                data, stamp = cached

                date_text = datetime.fromtimestamp(stamp).strftime(
                    "%d.%m.%Y %H:%M"
                )

                return data, f"КЭШ · {date_text}"

            if isinstance(error, requests.exceptions.Timeout):
                message = (
                    "Превышено время ожидания портала. "
                    "Повторите запрос или уточните поиск."
                )
            else:
                message = str(error)

            raise RuntimeError(
                message + "\n\nПодходящего ответа в кэше нет."
            ) from error

        try:
            self.storage.put_cache(key, data)
            cache_note = ""
        except Exception:
            logging.exception("Ошибка записи кэша")
            cache_note = " · кэш не записан"

        mode = (
            "TLS-проверка включена"
            if VERIFY_TLS
            else "TLS-сертификат не проверяется"
        )

        return data, f"ОНЛАЙН · {mode}{cache_note}"

    def search(self, selection):
        body = {
            "statuses": [40],
            "isStrict": False,
            "lastVersion": False,
            "sort": {"title": "id", "order": "asc"},
        }

        query = str(selection.get("query") or "").strip()

        if query:
            body["content"] = query

        if selection.get("rt_type_id") is not None:
            body["documentTypeIds"] = [selection["rt_type_id"]]

        return self.call(
            "POST",
            "/PublicNtdRequirement/Search",
            params={
                "take": PAGE_SIZE,
                "skip": max(0, int(selection.get("skip", 0))),
            },
            body=body,
        )


# ============================================================
# ПРИЛОЖЕНИЕ НА НОВОМ FLET
# ============================================================

class NeonApp:
    def __init__(self, page):
        self.page = page
        self.storage = Storage(DB_PATH)
        self.api = Api(self.storage)

        self.history = []
        self.revision = 0
        self.effects = None
        self.animation_task = None

        self.sound_enabled = True
        self.animations_enabled = True
        self.sound_lock = threading.Lock()

        self.body = ft.Column(expand=True, spacing=10)

        self.title = ft.Text(
            "СТРОЙКОМПЛЕКС · NEON",
            color=PINK,
            size=24,
            weight=ft.FontWeight.W_900,
        )

        self.crumbs = ft.Text(
            "Главная",
            color=CYAN,
            size=12,
        )

        self.status = ft.Text(
            "Готово",
            color=GOLD,
            size=11,
        )

    async def db(self, method, *args):
        return await asyncio.to_thread(method, *args)

    def notify(self, text):
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(str(text)),
                bgcolor="#35204F",
            )
        )

    def sound(self, kind="click"):
        if not winsound or not self.sound_enabled:
            return

        def worker():
            if not self.sound_lock.acquire(blocking=False):
                return

            try:
                tones = {
                    "hover": [(1300, 20)],
                    "click": [(750, 25), (1100, 25), (1500, 25)],
                    "save": [(1000, 45), (1500, 45), (1900, 60)],
                }

                for frequency, duration in tones.get(
                    kind, tones["click"]
                ):
                    winsound.Beep(frequency, duration)

            except Exception:
                pass
            finally:
                self.sound_lock.release()

        threading.Thread(target=worker, daemon=True).start()

    def button(self, text, callback, color=PINK, disabled=False):
        async def clicked(event):
            self.sound()
            await callback(event)

        control = ft.Container(
            content=ft.Text(
                text,
                color=WHITE,
                size=12,
                weight=ft.FontWeight.BOLD,
            ),
            padding=ft.Padding.symmetric(
                horizontal=14,
                vertical=10,
            ),
            border_radius=16,
            gradient=ft.LinearGradient(
                colors=[color, "#37204D"]
            ),
            border=ft.Border.all(1, color),
            shadow=glow(color, 9),
            animate_scale=ft.Animation(
                duration=150,
                curve=ft.AnimationCurve.EASE_OUT,
            ),
            disabled=disabled,
            opacity=0.35 if disabled else 1,
            on_click=clicked if not disabled else None,
            ink=True,
        )

        def hovered(event):
            if disabled:
                return

            entered = bool(event.data)

            control.scale = (
                1.035
                if entered and self.animations_enabled
                else 1
            )

            if entered:
                self.sound("hover")

            control.update()

        control.on_hover = hovered
        return control

    def card(self, content, callback=None, color=PINK):
        async def clicked(event):
            self.sound()

            if callback:
                await callback(event)

        return ft.Container(
            content=content,
            padding=14,
            bgcolor=PANEL,
            border_radius=15,
            border=ft.Border.all(1, color),
            shadow=glow(color, 7),
            on_click=clicked if callback else None,
            ink=callback is not None,
        )

    def scroll(self, controls):
        return ft.Column(
            controls=controls,
            expand=True,
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

    def action(self, route, replace=False):
        async def handler(event):
            await self.navigate(route, replace)
        return handler

    def badge(self, selection, color):
        selection = enrich(selection)

        controls = [
            ft.Text(
                selection.get("short") or "РТ",
                size=19,
                color=WHITE,
                weight=ft.FontWeight.W_900,
                text_align=ft.TextAlign.CENTER,
            )
        ]

        if selection.get("alias"):
            controls.append(
                ft.Text(
                    selection["alias"],
                    size=11,
                    color=GOLD,
                    text_align=ft.TextAlign.CENTER,
                )
            )

        return ft.Container(
            width=100,
            padding=12,
            border_radius=12,
            alignment=ft.Alignment.CENTER,
            gradient=ft.LinearGradient(
                colors=[color, "#302048"]
            ),
            content=ft.Column(
                controls=controls,
                spacing=3,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def project_heading(self, selection, color):
        selection = enrich(selection)
        number = selection.get("number")

        return ft.Row(
            controls=[
                self.badge(selection, color),
                ft.Column(
                    controls=[
                        ft.Text(
                            f"Раздел {number}"
                            if number
                            else "Раздел реестра",
                            color=GOLD,
                            size=11,
                        ),
                        ft.Text(
                            selection.get("title") or "",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    expand=True,
                    spacing=3,
                ),
            ],
            spacing=12,
        )

    async def home(self, event=None):
        await self.navigate({"screen": "home"})

    async def back(self, event=None):
        if len(self.history) > 1:
            self.history.pop()
            await self.render(self.history[-1])
        else:
            await self.home()

    async def open_saved(self, event=None):
        revision = self.revision
        current = self.history[-1] if self.history else {}
        code = current.get("segment")

        if current.get("screen") != "saved" and code in SEGMENTS:
            chosen = code
        else:
            chosen = await self.db(
                self.storage.get_state,
                "saved_segment_filter",
                ALL,
            )

            if revision != self.revision:
                return

        if chosen not in FILTERS:
            chosen = ALL

        await self.navigate({
            "screen": "saved",
            "filter_segment": chosen,
        })

    def navbar(self, *extra):
        return ft.Row(
            controls=[
                self.button("Назад", self.back, "#7744FF"),
                self.button("Колесо", self.home),
                self.button(
                    "Сохранённые",
                    self.open_saved,
                    "#008FA8",
                ),
                *extra,
            ],
            wrap=True,
            spacing=9,
            run_spacing=9,
        )

    async def navigate(self, route, replace=False):
        route = json.loads(dump(route))

        if route.get("screen") == "requirements":
            route = enrich(route)

        if replace and self.history:
            self.history[-1] = route
        else:
            self.history.append(route)

        await self.render(route)

    async def remember(self, selection):
        try:
            await self.db(
                self.storage.set_state,
                "last_selection",
                enrich(selection),
            )
        except Exception:
            logging.exception("Ошибка сохранения выбора")

    async def render(self, route):
        self.revision += 1
        revision = self.revision

        self.effects = None

        handlers = {
            "home": self.show_home,
            "sections": self.show_sections,
            "saved": self.show_saved,
            "rt_sections": self.show_rt_sections,
            "requirements": self.show_requirements,
            "requirement": self.show_requirement,
            "attributes": self.show_attributes,
            "document": self.show_document,
        }

        try:
            handler = handlers.get(route.get("screen"))

            if handler is None:
                raise ValueError("Неизвестный экран")

            await handler(route)

        except Exception as error:
            logging.exception("Ошибка экрана")

            if revision == self.revision:
                self.status.value = "ОШИБКА"

                self.body.controls = [
                    self.navbar(),
                    self.scroll([
                        self.card(
                            ft.Text(str(error), selectable=True),
                            color=RED,
                        )
                    ]),
                ]

        if revision == self.revision:
            self.page.update()

    async def fetch(self, method, *args):
        revision = self.revision

        self.body.controls = [
            self.navbar(),
            ft.Row(
                controls=[
                    ft.ProgressRing(color=PINK),
                    ft.Text("Получаем данные...", color=GOLD),
                ]
            ),
        ]

        self.page.update()

        data, message = await asyncio.to_thread(method, *args)

        if revision != self.revision:
            return None

        self.status.value = message
        return data

    # --------------------------------------------------------
    # ГЛАВНАЯ С КОЛЕСОМ
    # --------------------------------------------------------

    async def show_home(self, route):
        revision = self.revision

        counts, _ = await self.db(
            self.storage.saved_snapshot,
            ALL,
        )

        last = await self.db(
            self.storage.get_state,
            "last_selection",
        )

        if revision != self.revision:
            return

        self.crumbs.value = "Выберите вид работ"
        self.status.value = "Выбор раздела запускает поиск автоматически"

        size = 530
        center = size / 2
        layers = []
        bulbs = []

        for index in range(40):
            angle = math.tau * index / 40

            bulb = ft.Container(
                left=center + 246 * math.cos(angle) - 4,
                top=center + 246 * math.sin(angle) - 4,
                width=8,
                height=8,
                border_radius=4,
                bgcolor=RAINBOW[index % len(RAINBOW)],
            )

            bulbs.append(bulb)
            layers.append(bulb)

        layers.append(
            ft.Container(
                left=75,
                top=75,
                width=380,
                height=380,
                border_radius=190,
                border=ft.Border.all(3, "#7333BB"),
                shadow=glow("#7333BB", 30),
            )
        )

        core = ft.Container(
            left=center - 60,
            top=center - 60,
            width=120,
            height=120,
            border_radius=60,
            alignment=ft.Alignment.CENTER,
            gradient=ft.RadialGradient(
                colors=["#7434CD", "#25103F"]
            ),
            shadow=glow(PINK, 35),
            animate_scale=ft.Animation(
                duration=500,
                curve=ft.AnimationCurve.EASE_IN_OUT,
            ),
            content=ft.Column(
                controls=[
                    ft.Text(
                        "РТ",
                        size=35,
                        color=GOLD,
                        weight=ft.FontWeight.W_900,
                    ),
                    ft.Text("СТРОЙКОМПЛЕКС", size=9),
                ],
                spacing=0,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

        layers.append(core)

        for index, item in enumerate(WHEEL):
            angle = -math.pi / 2 + math.tau * index / len(WHEEL)

            control = ft.Container(
                left=center + 165 * math.cos(angle) - 52,
                top=center + 165 * math.sin(angle) - 52,
                width=104,
                height=104,
                border_radius=52,
                alignment=ft.Alignment.CENTER,
                gradient=ft.LinearGradient(
                    colors=item["colors"]
                ),
                border=ft.Border.all(2, WHITE),
                shadow=glow(item["colors"][0], 24),
                animate_scale=ft.Animation(
                    duration=180,
                    curve=ft.AnimationCurve.EASE_OUT,
                ),
                on_click=self.action({
                    "screen": "sections",
                    "segment": item["code"],
                }),
                content=ft.Column(
                    controls=[
                        ft.Text(
                            item["title"],
                            size=18,
                            weight=ft.FontWeight.W_900,
                        ),
                        ft.Text(
                            f"{len(item['sections'])} разделов",
                            size=10,
                        ),
                        ft.Text(
                            f"Сохранено: {counts.get(item['code'], 0)}",
                            size=9,
                        ),
                    ],
                    spacing=2,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
            )

            def hovered(event):
                entered = bool(event.data)

                event.control.scale = (
                    1.13
                    if entered and self.animations_enabled
                    else 1
                )

                if entered:
                    self.sound("hover")

                event.control.update()

            control.on_hover = hovered
            layers.append(control)

        controls = [
            ft.Row(
                controls=[
                    self.button(
                        f"Сохранённые · {counts[ALL]}",
                        self.open_saved,
                        "#008FA8",
                    )
                ],
                wrap=True,
            )
        ]

        if (
            isinstance(last, dict)
            and last.get("screen") in {"sections", "requirements"}
        ):
            last = enrich(last)

            controls.append(
                self.card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "ПРОДОЛЖИТЬ",
                                color=GOLD,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(label(last)),
                        ]
                    ),
                    self.action(last),
                    color=GOLD,
                )
            )

        controls.extend([
            ft.Row(
                controls=[
                    ft.Stack(
                        controls=layers,
                        width=size,
                        height=size,
                    )
                ],
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            ft.Text(
                "Подборки — навигационные. Поиск по словам "
                "не гарантирует полноту и применимость требований.",
                color=MUTED,
                size=11,
            ),
        ])

        self.body.controls = [self.scroll(controls)]
        self.effects = {"bulbs": bulbs, "core": core}

    # --------------------------------------------------------
    # СПИСОК РАЗДЕЛОВ
    # --------------------------------------------------------

    async def show_sections(self, route):
        revision = self.revision
        code = route["segment"]
        segment = SEGMENTS[code]

        await self.remember(route)

        if revision != self.revision:
            return

        self.crumbs.value = f"{segment['title']} / Разделы"
        self.status.value = "Нажмите раздел — поиск начнётся сразу"

        controls = [
            self.navbar(
                self.button(
                    "Разделы реестра РТ",
                    self.action({
                        "screen": "rt_sections",
                        "segment": code,
                    }),
                    "#008FA8",
                )
            )
        ]

        for item in segment["sections"]:
            selection = selection_for(code, item)

            controls.append(
                self.card(
                    ft.Column(
                        controls=[
                            self.project_heading(
                                selection,
                                segment["colors"][0],
                            ),
                            ft.Text(
                                "Автопоиск: "
                                + (item["query"] or "без текстового фильтра"),
                                color=MUTED,
                                size=11,
                            ),
                        ]
                    ),
                    self.action(selection),
                    color=segment["colors"][0],
                )
            )

        self.body.controls = [self.scroll(controls)]

    # --------------------------------------------------------
    # БОКОВОЕ МЕНЮ РАЗДЕЛОВ
    # --------------------------------------------------------

    def sidebar(self, selection):
        code = selection.get("segment")
        segment = SEGMENTS.get(code)

        if not segment:
            return ft.Container(width=1)

        color = segment["colors"][0]

        controls = [
            ft.Text(
                "РАЗДЕЛЫ",
                color=GOLD,
                weight=ft.FontWeight.BOLD,
            ),
            ft.Text(
                "Переключение запускает поиск",
                size=10,
                color=MUTED,
            ),
        ]

        for item in segment["sections"]:
            active = (
                selection.get("source") == "pp87"
                and str(selection.get("number")) == item["number"]
            )

            target = selection_for(code, item)

            controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text(
                                        short_name(item),
                                        color=GOLD if active else WHITE,
                                        weight=ft.FontWeight.BOLD,
                                        size=13,
                                    ),
                                    ft.Text(
                                        item["number"],
                                        color=MUTED,
                                        size=10,
                                    ),
                                ],
                                wrap=True,
                            ),
                            ft.Text(
                                item["title"],
                                size=11,
                                color=WHITE if active else MUTED,
                            ),
                        ],
                        spacing=3,
                    ),
                    padding=11,
                    border_radius=12,
                    bgcolor="#35204F" if active else PANEL_DARK,
                    border=ft.Border.all(
                        2 if active else 1,
                        color if active else "#39244C",
                    ),
                    on_click=self.action(target, replace=True),
                    ink=True,
                )
            )

        return ft.Container(
            width=235,
            padding=10,
            bgcolor=PANEL_DARK,
            border_radius=14,
            border=ft.Border.all(1, "#39244C"),
            content=self.scroll(controls),
        )

    # --------------------------------------------------------
    # АВТОМАТИЧЕСКИЙ ПОИСК ПРИ ОТКРЫТИИ РАЗДЕЛА
    # --------------------------------------------------------

    async def show_requirements(self, selection):
        revision = self.revision
        selection = enrich(selection)

        color = segment_color(selection.get("segment"))

        self.crumbs.value = label(selection, compact=True)
        self.status.value = "Автоматический поиск требований..."

        query = ft.TextField(
            value=selection.get("query", ""),
            label="Уточнить поиск",
            expand=True,
            border_color=color,
            focused_border_color=GOLD,
            border_radius=14,
        )

        results = self.scroll([
            ft.Row(
                controls=[
                    ft.ProgressRing(color=color),
                    ft.Text(
                        "Ищем требования выбранного раздела...",
                        color=GOLD,
                    ),
                ]
            )
        ])

        async def search(event):
            await self.navigate(
                {
                    **selection,
                    "query": (query.value or "").strip(),
                    "skip": 0,
                },
                replace=True,
            )

        query.on_submit = search

        async def save(event):
            updated = {
                **selection,
                "query": (query.value or "").strip(),
            }

            if updated["query"] != selection.get("query", ""):
                updated["skip"] = 0

            try:
                await self.db(
                    self.storage.save_section,
                    updated,
                )

                self.sound("save")
                self.notify(
                    "Раздел сохранён: "
                    + label(updated, compact=True)
                )

            except Exception as error:
                logging.exception("Ошибка сохранения")
                self.notify(str(error))

        self.body.controls = [
            self.navbar(
                self.button("Сохранить раздел", save, "#B87C00")
            ),
            self.card(
                self.project_heading(selection, color),
                color=color,
            ),
            ft.Row(
                controls=[
                    query,
                    self.button("Найти", search, color),
                    self.button(
                        "Обновить",
                        self.action(selection, replace=True),
                        "#6545AA",
                    ),
                ]
            ),
            ft.Row(
                controls=[
                    self.sidebar(selection),
                    ft.Container(
                        content=results,
                        expand=True,
                        padding=ft.Padding.only(left=10),
                    ),
                ],
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ]

        self.page.update()

        # Последний выбор сохраняется, но сеть не ждёт
        # дополнительных действий пользователя.
        await self.remember(selection)

        if revision != self.revision:
            return

        try:
            data, message = await asyncio.to_thread(
                self.api.search,
                selection,
            )

        except Exception as error:
            logging.exception("Ошибка автоматического поиска")

            if revision != self.revision:
                return

            self.status.value = "Ошибка поиска"

            results.controls = [
                self.card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Не удалось загрузить требования",
                                color=RED,
                                size=17,
                            ),
                            ft.Text(
                                str(error),
                                selectable=True,
                            ),
                            self.button(
                                "Повторить",
                                self.action(selection, replace=True),
                                color,
                            ),
                        ]
                    ),
                    color=RED,
                )
            ]

            return

        # Главное: старый ответ не может заменить новый раздел.
        if revision != self.revision:
            return

        items = data.get("data") or []
        total = int(data.get("total") or 0)
        skip = int(selection.get("skip", 0))

        self.status.value = (
            f"{message} · Найдено: {total}"
        )

        controls = [
            ft.Row(
                controls=[
                    ft.Text(
                        f"{skip + 1 if items else 0}"
                        f"–{skip + len(items)} из {total}",
                        color=GOLD,
                        weight=ft.FontWeight.BOLD,
                    ),
                    self.button(
                        "Назад",
                        self.action(
                            {
                                **selection,
                                "skip": max(0, skip - PAGE_SIZE),
                            },
                            replace=True,
                        ),
                        "#6545AA",
                        disabled=skip == 0,
                    ),
                    self.button(
                        "Далее",
                        self.action(
                            {
                                **selection,
                                "skip": skip + PAGE_SIZE,
                            },
                            replace=True,
                        ),
                        "#6545AA",
                        disabled=(
                            not items
                            or skip + len(items) >= total
                        ),
                    ),
                ],
                wrap=True,
            )
        ]

        if not items:
            controls.append(
                self.card(
                    ft.Text(
                        "По этой поисковой строке ничего не найдено. "
                        "Измените её или очистите и нажмите Enter."
                    ),
                    color=color,
                )
            )

        for item in items:
            text = clean_text(item.get("content"))
            document = item.get("document") or {}

            controls.append(
                self.card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                "Требование "
                                + str(
                                    item.get("number")
                                    or item["id"]
                                ),
                                color=GOLD,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                text[:500]
                                + ("…" if len(text) > 500 else "")
                            ),
                            ft.Text(
                                readable(document),
                                color=CYAN,
                                size=11,
                            ),
                            ft.Text(
                                str(
                                    REQ_STATUS.get(
                                        item.get("status"),
                                        item.get("status"),
                                    )
                                )
                                + " · Введено: "
                                + excel_date(
                                    item.get("effectiveDate")
                                ),
                                color=MUTED,
                                size=11,
                            ),
                        ]
                    ),
                    self.action({
                        "screen": "requirement",
                        "segment": selection["segment"],
                        "id": item["id"],
                        "project": selection,
                    }),
                    color=color,
                )
            )

        results.controls = controls

    # --------------------------------------------------------
    # СОХРАНЁННЫЕ
    # --------------------------------------------------------

    async def show_saved(self, route):
        revision = self.revision

        selected = route.get("filter_segment", ALL)

        if selected not in FILTERS:
            selected = ALL

        route["filter_segment"] = selected

        await self.db(
            self.storage.set_state,
            "saved_segment_filter",
            selected,
        )

        counts, items = await self.db(
            self.storage.saved_snapshot,
            selected,
        )

        if revision != self.revision:
            return

        self.crumbs.value = (
            "Сохранённые / " + segment_title(selected)
        )

        self.status.value = (
            f"Показано: {len(items)} · Всего: {counts[ALL]}"
        )

        codes = [ALL, *SEGMENTS]

        if counts[OTHER] or selected == OTHER:
            codes.append(OTHER)

        filter_controls = []

        for code in codes:
            active = code == selected
            color = segment_color(code)

            filter_controls.append(
                ft.Container(
                    content=ft.Text(
                        f"{segment_title(code)} · {counts.get(code, 0)}",
                        color=BG if active else WHITE,
                        weight=ft.FontWeight.BOLD,
                    ),
                    padding=ft.Padding.symmetric(
                        horizontal=14,
                        vertical=11,
                    ),
                    border_radius=16,
                    bgcolor=color if active else PANEL,
                    border=ft.Border.all(
                        2 if active else 1,
                        color,
                    ),
                    shadow=glow(color, 12) if active else None,
                    on_click=self.action(
                        {
                            "screen": "saved",
                            "filter_segment": code,
                        },
                        replace=True,
                    ),
                    ink=True,
                )
            )

        controls = [
            self.navbar(),
            ft.Row(
                controls=filter_controls,
                wrap=True,
                spacing=9,
                run_spacing=9,
            ),
        ]

        if not items:
            controls.append(
                self.card(
                    ft.Text(
                        "Сохранённых разделов в этой группе пока нет.",
                        color=MUTED,
                    ),
                    color=segment_color(selected),
                )
            )

        for item in items:
            selection = item["selection"]
            color = segment_color(item["segment"])
            details = []
            actions = []

            if selection:
                details.extend([
                    self.project_heading(selection, color),
                    ft.Text(
                        f"Поиск: {selection.get('query') or 'без фильтра'}",
                        color=MUTED,
                        size=12,
                    ),
                ])

                actions.append(
                    self.button(
                        "Открыть и найти",
                        self.action(selection),
                        "#008FA8",
                    )
                )
            else:
                details.append(
                    ft.Text(
                        "Повреждённая запись: " + item["label"],
                        color=RED,
                    )
                )

            actions.append(
                self.button(
                    "Удалить",
                    self.delete_action(item["id"], selected),
                    "#A53259",
                )
            )

            details.extend([
                ft.Text(
                    f"Обновлено: {item['updated_at']}",
                    color=MUTED,
                    size=11,
                ),
                ft.Row(controls=actions, wrap=True),
            ])

            controls.append(
                self.card(
                    ft.Column(controls=details),
                    color=color,
                )
            )

        self.body.controls = [self.scroll(controls)]

    def delete_action(self, saved_id, selected):
        async def handler(event):
            try:
                await self.db(
                    self.storage.delete_section,
                    saved_id,
                )

                self.notify("Раздел удалён")

                current = self.history[-1] if self.history else {}

                if (
                    current.get("screen") == "saved"
                    and current.get("filter_segment") == selected
                ):
                    await self.navigate(
                        {
                            "screen": "saved",
                            "filter_segment": selected,
                        },
                        replace=True,
                    )

            except Exception as error:
                self.notify(str(error))

        return handler

    # --------------------------------------------------------
    # РАЗДЕЛЫ РЕЕСТРА
    # --------------------------------------------------------

    async def show_rt_sections(self, route):
        self.crumbs.value = (
            f"{route['segment']} / Разделы реестра РТ"
        )

        data = await self.fetch(
            self.api.call,
            "GET",
            "/PublicNtdRequirement/GetSearchParams",
        )

        if data is None:
            return

        controls = [self.navbar()]

        for item in data.get("documentTypes") or []:
            selection = {
                "screen": "requirements",
                "segment": route["segment"],
                "source": "rt",
                "number": str(item.get("section") or ""),
                "title": item.get("title") or "Раздел РТ",
                "query": "",
                "short": "",
                "alias": "",
                "skip": 0,
                "rt_type_id": item["id"],
            }

            controls.append(
                self.card(
                    ft.Text(selection["title"], size=15),
                    self.action(selection),
                    color=CYAN,
                )
            )

        self.body.controls = [self.scroll(controls)]

    # --------------------------------------------------------
    # ТРЕБОВАНИЕ, АТРИБУТЫ И ДОКУМЕНТ
    # --------------------------------------------------------

    def context_label(self, route):
        project = route.get("project")

        if isinstance(project, dict):
            return label(project, compact=True)

        return route.get("segment", "")

    async def show_requirement(self, route):
        self.crumbs.value = (
            f"{self.context_label(route)}"
            f" / Требование #{route['id']}"
        )

        data = await self.fetch(
            self.api.call,
            "GET",
            f"/PublicNtdRequirement/GetById/{route['id']}",
        )

        if data is None:
            return

        controls = [self.navbar()]
        document = data.get("document") or {}

        if isinstance(document, dict) and document.get("id"):
            controls.append(
                self.button(
                    "Документ-источник: " + readable(document),
                    self.action({
                        "screen": "document",
                        "segment": route["segment"],
                        "id": document["id"],
                        "project": route.get("project"),
                    }),
                    "#B87C00",
                )
            )

        controls.append(
            self.card(
                ft.Column(
                    controls=[
                        ft.Text(
                            "Требование "
                            + str(data.get("number") or route["id"]),
                            color=GOLD,
                            size=21,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            clean_text(data.get("content"))
                            or "Текст отсутствует",
                            selectable=True,
                            size=16,
                        ),
                        ft.Divider(color="#513565"),
                        ft.Text(
                            "Статус: "
                            + str(
                                REQ_STATUS.get(
                                    data.get("status"),
                                    data.get("status"),
                                )
                            )
                        ),
                        ft.Text(
                            "В реестре с: "
                            + excel_date(
                                data.get("publicationDate")
                            )
                        ),
                        ft.Text(
                            "Введено: "
                            + excel_date(
                                data.get("effectiveDate")
                            )
                        ),
                        ft.Text(
                            "Прекращено: "
                            + excel_date(
                                data.get("suspensionDate")
                            )
                        ),
                        ft.Text(
                            "Аспекты безопасности: "
                            + readable(
                                data.get("securityAspects")
                            )
                        ),
                    ]
                ),
                color=CYAN,
            )
        )

        for item in data.get("versions") or []:
            if item.get("id"):
                controls.append(
                    self.button(
                        f"Версия {item.get('version', '—')}"
                        f" · ID {item['id']}",
                        self.action({
                            **route,
                            "id": item["id"],
                        }),
                        "#6545AA",
                    )
                )

        controls.append(
            self.button(
                "Все атрибуты",
                self.action({
                    **route,
                    "screen": "attributes",
                }),
                "#008FA8",
            )
        )

        self.body.controls = [self.scroll(controls)]

    async def show_attributes(self, route):
        self.crumbs.value = (
            f"{self.context_label(route)}"
            f" / Атрибуты #{route['id']}"
        )

        data = await self.fetch(
            self.api.call,
            "GET",
            f"/PublicNtdRequirement/GetViewById/{route['id']}",
        )

        if data is None:
            return

        controls = [self.navbar()]
        attributes = data.get("data") or []

        if not attributes:
            controls.append(
                self.card(
                    ft.Text("Атрибуты отсутствуют"),
                    color=CYAN,
                )
            )

        for item in sorted(
            attributes,
            key=lambda value: value.get("sortOrder") or 0,
        ):
            value = item.get("value")

            if str(item.get("type", "")).lower() == "date":
                value = excel_date(value)
            else:
                value = readable(value)

            controls.append(
                self.card(
                    ft.Column(
                        controls=[
                            ft.Text(
                                item.get("publicName")
                                or item.get("attribute")
                                or "Атрибут",
                                color=GOLD,
                            ),
                            ft.Text(
                                value,
                                selectable=True,
                            ),
                        ]
                    ),
                    color=CYAN,
                )
            )

        self.body.controls = [self.scroll(controls)]

    async def show_document(self, route):
        self.crumbs.value = (
            f"{self.context_label(route)}"
            f" / Документ #{route['id']}"
        )

        data = await self.fetch(
            self.api.call,
            "GET",
            "/PublicNtd/GetDocumentById",
            {"id": route["id"]},
        )

        if data is None:
            return

        main = data.get("main") or {}

        details = [
            ft.Text(
                clean_text(
                    data.get("title")
                    or main.get("title")
                    or "Документ"
                ),
                color=GOLD,
                size=21,
                selectable=True,
            ),
            ft.Text(
                f"Номер: {main.get('number') or '—'}"
            ),
            ft.Text(
                "Статус: "
                + str(
                    DOC_STATUS.get(
                        main.get("status"),
                        main.get("status"),
                    )
                )
            ),
            ft.Text(
                f"Вид: {main.get('kindTitle') or '—'}"
            ),
            ft.Text(
                f"Группа: {main.get('groupTitle') or '—'}"
            ),
            ft.Text(
                f"Тип: {main.get('typeTitle') or '—'}"
            ),
            ft.Text(
                "Дата: "
                + excel_date(main.get("date"))
            ),
            ft.Text(
                "Введён: "
                + excel_date(main.get("effectiveDate"))
            ),
            ft.Text(
                "Прекращён: "
                + excel_date(main.get("suspensionDate"))
            ),
        ]

        controls = [
            self.navbar(),
            self.card(
                ft.Column(controls=details),
                color=CYAN,
            ),
        ]

        for key, title in [
            ("legalAct", "Нормативный правовой акт"),
            ("extra", "Дополнительные сведения"),
            ("conn", "Связанные документы"),
            ("section", "Разделы документа"),
            ("version", "Изменения и версии"),
        ]:
            if data.get(key):
                controls.append(
                    self.card(
                        ft.Column(
                            controls=[
                                ft.Text(
                                    title,
                                    color=GOLD,
                                    size=16,
                                ),
                                ft.Text(
                                    json.dumps(
                                        data[key],
                                        ensure_ascii=False,
                                        indent=2,
                                    ),
                                    selectable=True,
                                    size=12,
                                ),
                            ]
                        ),
                        color="#7544AA",
                    )
                )

        self.body.controls = [self.scroll(controls)]

    # --------------------------------------------------------
    # НАСТРОЙКИ И АНИМАЦИЯ
    # --------------------------------------------------------

    async def toggle_sound(self, event):
        self.sound_enabled = not self.sound_enabled

        self.sound_button.icon = (
            ft.Icons.VOLUME_UP
            if self.sound_enabled
            else ft.Icons.VOLUME_OFF
        )

        self.page.update()

        try:
            await self.db(
                self.storage.set_state,
                "sound_enabled",
                self.sound_enabled,
            )
        except Exception:
            logging.exception("Ошибка сохранения звука")

    async def toggle_effects(self, event):
        self.animations_enabled = not self.animations_enabled

        self.effects_button.icon = (
            ft.Icons.PAUSE
            if self.animations_enabled
            else ft.Icons.PLAY_ARROW
        )

        if not self.animations_enabled:
            self.title.color = PINK

            if self.effects:
                self.effects["core"].scale = 1

        self.page.update()

        try:
            await self.db(
                self.storage.set_state,
                "animations_enabled",
                self.animations_enabled,
            )
        except Exception:
            logging.exception("Ошибка сохранения эффектов")

    async def animate(self):
        tick = 0

        try:
            while True:
                await asyncio.sleep(0.55)

                if not self.animations_enabled:
                    continue

                tick += 1

                self.title.color = RAINBOW[
                    tick % len(RAINBOW)
                ]

                if self.effects:
                    for index, bulb in enumerate(
                        self.effects["bulbs"]
                    ):
                        bulb.bgcolor = (
                            RAINBOW[
                                (index + tick) % len(RAINBOW)
                            ]
                            if (index + tick) % 3 == 0
                            else "#2A183C"
                        )

                    self.effects["core"].scale = (
                        1.06 if tick % 2 else 0.97
                    )

                self.page.update()

        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception("Анимация остановлена")

    async def start(self):
        self.page.title = "Стройкомплекс · NEON"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = BG
        self.page.padding = 0
        self.page.spacing = 0

        self.page.window.width = 1280
        self.page.window.height = 930
        self.page.window.min_width = 980
        self.page.window.min_height = 700

        await self.db(self.storage.initialize)

        self.sound_enabled = bool(
            await self.db(
                self.storage.get_state,
                "sound_enabled",
                True,
            )
        )

        self.animations_enabled = bool(
            await self.db(
                self.storage.get_state,
                "animations_enabled",
                True,
            )
        )

        self.sound_button = ft.IconButton(
            icon=(
                ft.Icons.VOLUME_UP
                if self.sound_enabled
                else ft.Icons.VOLUME_OFF
            ),
            icon_color=GOLD,
            tooltip="Включить или выключить звук",
            on_click=self.toggle_sound,
        )

        self.effects_button = ft.IconButton(
            icon=(
                ft.Icons.PAUSE
                if self.animations_enabled
                else ft.Icons.PLAY_ARROW
            ),
            icon_color=CYAN,
            tooltip="Включить или выключить анимацию",
            on_click=self.toggle_effects,
        )

        header = ft.Container(
            padding=ft.Padding.symmetric(
                horizontal=18,
                vertical=12,
            ),
            gradient=ft.LinearGradient(
                colors=["#32104E", BG]
            ),
            border=ft.Border(
                bottom=ft.BorderSide(
                    width=2,
                    color=PINK,
                )
            ),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=self.title,
                                expand=True,
                            ),
                            self.effects_button,
                            self.sound_button,
                        ]
                    ),
                    self.crumbs,
                    self.status,
                ],
                spacing=4,
            ),
        )

        self.page.add(
            header,
            ft.Container(
                content=self.body,
                padding=16,
                expand=True,
            ),
        )

        await self.navigate({"screen": "home"})

        self.animation_task = self.page.run_task(
            self.animate
        )

        def closed(event):
            if self.animation_task:
                self.animation_task.cancel()

        self.page.on_close = closed


# ============================================================
# ЗАПУСК
# ============================================================

async def main(page: ft.Page):
    logging.info(
        "Запуск. Flet=%s; база=%s; verify_tls=%s",
        version("flet"),
        DB_PATH,
        VERIFY_TLS,
    )

    try:
        app = NeonApp(page)
        await app.start()

    except Exception as error:
        logging.exception("Ошибка запуска")

        page.controls.clear()

        page.add(
            ft.Container(
                padding=24,
                content=ft.Column(
                    controls=[
                        ft.Text(
                            "Не удалось запустить приложение",
                            color=RED,
                            size=23,
                        ),
                        ft.Text(
                            str(error),
                            selectable=True,
                        ),
                        ft.Text(
                            f"Журнал: {LOG_PATH}",
                            selectable=True,
                        ),
                    ]
                ),
            )
        )


if __name__ == "__main__":
    ft.run(main)