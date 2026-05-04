"""
matrix_image.py — Генерация картинки «Матрица судьбы» (метод Натальи Ладини)
Использует только Pillow.

ИНТЕГРАЦИЯ В main.py:
  1. Положи этот файл рядом с main.py
  2. В начало main.py добавь: from matrix_image import build_matrix_image
  3. Замени вызов старого build_matrix_image на новый — сигнатура та же:
       image_path = build_matrix_image(user)   # user — словарь из БД

АЛГОРИТМ (метод Ладини / Фадеева):
  A = день рождения          → Левая точка (Личность)
  B = месяц рождения         → Верхняя точка (Дух)
  C = год (сумма цифр)       → Правая точка (Материя)
  D = reduce(A+B+C)          → Нижняя точка (Кармический хвост)
  E = reduce(A+B+C+D)        → Центр (Зона комфорта)

  Родовой квадрат:
  F = reduce(A+B)  — верхний левый  (Отец × Дух)
  G = reduce(B+C)  — верхний правый (Мать × Материя)
  H = reduce(C+D)  — нижний правый  (Деньги)
  K = reduce(D+A)  — нижний левый   (Любовь/Отношения)

  Промежуточные (центры рёбер родового квадрата):
  FG = reduce(F+G), GH = reduce(G+H), HK = reduce(H+K), KF = reduce(K+F)

  Линии рода:
    Мужская (отцовская):  A → F → B
    Женская (материнская): B → G → C

  Правило: если число > 22 — складываем цифры числа, пока не будет <= 22.
"""

import io
import math
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ─── Шрифты ──────────────────────────────────────────────────────────────────
_FONT_BOLD   = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_FONT_NORMAL = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def _f(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_FONT_BOLD if bold else _FONT_NORMAL, size)
    except Exception:
        return ImageFont.load_default()

# ─── Палитра ─────────────────────────────────────────────────────────────────
BG_TOP     = (15,  12,  35)
BG_BOT     = (28,  18,  60)
GOLD       = (212, 175,  55)
WHITE      = (255, 255, 255)
GRAY_LIGHT = (200, 200, 220)
GRAY_MID   = (130, 130, 160)

NODE_COLORS = {
    "A": (130,  80, 220),
    "B": (210,  60, 140),
    "C": (230, 130,  30),
    "D": (210,  45,  45),
    "E": (230, 195,  40),
    "F": ( 55, 130, 220),
    "G": ( 50, 180, 120),
    "H": (220, 100,  40),
    "K": (100, 180, 230),
}
MALE_COLOR   = (230,  80,  80)
FEMALE_COLOR = (180,  80, 220)

# ─── Размеры ─────────────────────────────────────────────────────────────────
IMG_W   = 960
IMG_H   = 1060
CX      = 480
CY      = 490
R_BIG   = 310
R_SMALL = int(R_BIG * 0.707)
NODE_R  = 36
MID_R   = 20

# ─── Вспомогательные функции ─────────────────────────────────────────────────

def _reduce(n: int) -> int:
    n = abs(int(n))
    while n > 22:
        n = sum(int(ch) for ch in str(n))
    return max(1, n)


def _pretty_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return date_str


def _tc(draw, x, y, text, font, fill):
    """Text centered at (x, y)."""
    bb = draw.textbbox((0, 0), text, font=font)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((x - w // 2, y - h // 2), text, font=font, fill=fill)


# ─── Расчёт матрицы ──────────────────────────────────────────────────────────

def calc_matrix(date_str: str) -> dict:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    A = _reduce(d.day)
    B = _reduce(d.month)
    C = _reduce(sum(int(ch) for ch in str(d.year)))
    D = _reduce(A + B + C)
    E = _reduce(A + B + C + D)
    F  = _reduce(A + B)
    G  = _reduce(B + C)
    H  = _reduce(C + D)
    K  = _reduce(D + A)
    FG = _reduce(F + G)
    GH = _reduce(G + H)
    HK = _reduce(H + K)
    KF = _reduce(K + F)
    return dict(
        A=A, B=B, C=C, D=D, E=E,
        F=F, G=G, H=H, K=K,
        FG=FG, GH=GH, HK=HK, KF=KF,
        male_line=[A, F, B],
        female_line=[B, G, C],
    )


# ─── Координаты узлов ────────────────────────────────────────────────────────

def _nodes():
    A  = (CX - R_BIG,  CY)
    B  = (CX,          CY - R_BIG)
    C  = (CX + R_BIG,  CY)
    D  = (CX,          CY + R_BIG)
    F  = (CX - R_SMALL, CY - R_SMALL)
    G  = (CX + R_SMALL, CY - R_SMALL)
    H  = (CX + R_SMALL, CY + R_SMALL)
    K  = (CX - R_SMALL, CY + R_SMALL)
    FG = ((F[0]+G[0])//2, (F[1]+G[1])//2)
    GH = ((G[0]+H[0])//2, (G[1]+H[1])//2)
    HK = ((H[0]+K[0])//2, (H[1]+K[1])//2)
    KF = ((K[0]+F[0])//2, (K[1]+F[1])//2)
    E  = (CX, CY)
    return dict(A=A, B=B, C=C, D=D, E=E,
                F=F, G=G, H=H, K=K,
                FG=FG, GH=GH, HK=HK, KF=KF)


# ─── Возрастная шкала ────────────────────────────────────────────────────────

def _age_labels(nodes):
    """Список (x, y, text) для меток возраста снаружи октаграммы."""
    OFFSET = 42
    result = []

    def push(key, age):
        x, y = nodes[key]
        dx, dy = x - CX, y - CY
        ln = math.hypot(dx, dy) or 1
        ox = x + int(dx / ln * OFFSET)
        oy = y + int(dy / ln * OFFSET)
        result.append((ox, oy, f"{age} лет"))

    def push_mid(k1, k2, age):
        x1, y1 = nodes[k1]
        x2, y2 = nodes[k2]
        mx, my = (x1+x2)//2, (y1+y2)//2
        dx, dy = mx - CX, my - CY
        ln = math.hypot(dx, dy) or 1
        ox = mx + int(dx / ln * OFFSET)
        oy = my + int(dy / ln * OFFSET)
        result.append((ox, oy, f"{age} лет"))

    # вершины (по часовой от верха)
    push("B", 0)
    push("G", 10)
    push("C", 20)
    push("H", 30)
    push("D", 40)
    push("K", 50)
    push("A", 60)
    push("F", 70)

    # середины рёбер
    push_mid("B", "G",  5)
    push_mid("G", "C", 15)
    push_mid("C", "H", 25)
    push_mid("H", "D", 35)
    push_mid("D", "K", 45)
    push_mid("K", "A", 55)
    push_mid("A", "F", 65)
    push_mid("F", "B", 75)

    return result


# ─── Рисование ───────────────────────────────────────────────────────────────

def _gradient_bg(img):
    draw = ImageDraw.Draw(img)
    for y in range(IMG_H):
        t = y / IMG_H
        r = int(BG_TOP[0] + (BG_BOT[0]-BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1]-BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2]-BG_TOP[2]) * t)
        draw.line([(0, y), (IMG_W, y)], fill=(r, g, b))


def _node(draw, cx, cy, r, color, value, fnt):
    # тень
    draw.ellipse([cx-r+3, cy-r+3, cx+r+3, cy+r+3], fill=(5, 5, 20))
    # свечение (3 кольца)
    for i in (3, 2, 1):
        gr = r + i * 5
        gc = tuple(min(255, c + 20*i) for c in color)
        draw.ellipse([cx-gr, cy-gr, cx+gr, cy+gr], outline=gc, width=1)
    # заливка
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color, outline=GOLD, width=2)
    # блик
    br = r // 4
    bx, by = cx - r//3, cy - r//3
    lc = tuple(min(255, c+90) for c in color)
    draw.ellipse([bx-br, by-br, bx+br, by+br], fill=lc)
    # число
    _tc(draw, cx, cy, str(value), fnt, WHITE)


def _small_node(draw, cx, cy, r, value, fnt):
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(235, 230, 255), outline=(100, 90, 170), width=2)
    _tc(draw, cx, cy, str(value), fnt, (40, 30, 80))


def _arrow_line(draw, p1, p2, color, w=3):
    draw.line([p1, p2], fill=color, width=w)
    dx, dy = p2[0]-p1[0], p2[1]-p1[1]
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx/ln, dy/ln
    px, py = -uy, ux
    al, aw = 14, 6
    tip = p2
    a1 = (int(tip[0]-ux*al+px*aw), int(tip[1]-uy*al+py*aw))
    a2 = (int(tip[0]-ux*al-px*aw), int(tip[1]-uy*al-py*aw))
    draw.polygon([tip, a1, a2], fill=color)


# ─── Главная функция ─────────────────────────────────────────────────────────

def generate_matrix_image(date_str: str, name: str = "") -> bytes:
    """
    Генерирует PNG матрицы судьбы.
    date_str: 'YYYY-MM-DD'
    name:     имя пользователя (необязательно)
    Возвращает bytes (PNG).
    """
    m  = calc_matrix(date_str)
    nd = _nodes()

    img = Image.new("RGB", (IMG_W, IMG_H))
    _gradient_bg(img)
    draw = ImageDraw.Draw(img)

    # шрифты
    F_TITLE  = _f(32, True)
    F_SUB    = _f(18, False)
    F_NODE   = _f(26, True)
    F_MID    = _f(16, True)
    F_AGE    = _f(11, False)
    F_LEG    = _f(14, False)
    F_LBL    = _f(12, False)

    # ── Заголовок ─────────────────────────────────────────────────────────
    _tc(draw, IMG_W//2, 36, "✦  Матрица Судьбы  ✦", F_TITLE, GOLD)
    parts = ([name] if name else []) + [_pretty_date(date_str)]
    _tc(draw, IMG_W//2, 70, "  •  ".join(parts), F_SUB, GRAY_LIGHT)
    draw.line([(IMG_W//2-200, 88), (IMG_W//2+200, 88)], fill=GOLD, width=1)

    # ── Рёбра родового квадрата ───────────────────────────────────────────
    sq = ["F","G","H","K"]
    for i in range(4):
        draw.line([nd[sq[i]], nd[sq[(i+1)%4]]], fill=(90, 80, 150), width=2)

    # ── Диагонали родового квадрата ───────────────────────────────────────
    draw.line([nd["F"], nd["H"]], fill=(60, 55, 110), width=1)
    draw.line([nd["G"], nd["K"]], fill=(60, 55, 110), width=1)

    # ── Рёбра диагонального квадрата (ромб) ──────────────────────────────
    dia = ["A","B","C","D"]
    for i in range(4):
        draw.line([nd[dia[i]], nd[dia[(i+1)%4]]], fill=(150, 140, 200), width=2)

    # ── Оси ───────────────────────────────────────────────────────────────
    draw.line([nd["B"], nd["D"]], fill=(150, 140, 200), width=2)
    draw.line([nd["A"], nd["C"]], fill=(150, 140, 200), width=2)

    # ── Лучи от центра к углам родового квадрата ─────────────────────────
    for k in ["F","G","H","K"]:
        draw.line([nd["E"], nd[k]], fill=(60, 55, 110), width=1)

    # ── Мужская линия: A → F → B ─────────────────────────────────────────
    _arrow_line(draw, nd["A"], nd["F"], MALE_COLOR, 3)
    _arrow_line(draw, nd["F"], nd["B"], MALE_COLOR, 3)
    lmx = (nd["A"][0]+nd["F"][0])//2 - 72
    lmy = (nd["A"][1]+nd["F"][1])//2 + 4
    draw.text((lmx, lmy), "линия\nмужского рода", font=F_LBL, fill=MALE_COLOR)

    # ── Женская линия: B → G → C ─────────────────────────────────────────
    _arrow_line(draw, nd["B"], nd["G"], FEMALE_COLOR, 3)
    _arrow_line(draw, nd["G"], nd["C"], FEMALE_COLOR, 3)
    lfx = (nd["C"][0]+nd["G"][0])//2 + 8
    lfy = (nd["C"][1]+nd["G"][1])//2 - 32
    draw.text((lfx, lfy), "линия\nженского рода", font=F_LBL, fill=FEMALE_COLOR)

    # ── Символы $ и ♥ ─────────────────────────────────────────────────────
    ex, ey = nd["E"]
    hx, hy = nd["H"]
    kx, ky = nd["K"]
    _tc(draw, (ex+hx)//2+14, (ey+hy)//2,    "$", _f(22,True), (80,200,100))
    _tc(draw, (ex+kx)//2-14, (ey+ky)//2+4,  "♥", _f(20,True), (220,80,80))

    # ── Возрастная шкала ──────────────────────────────────────────────────
    for ax, ay, age_text in _age_labels(nd):
        bb = draw.textbbox((0,0), age_text, font=F_AGE)
        aw = bb[2]-bb[0]
        draw.text((ax-aw//2, ay-7), age_text, font=F_AGE, fill=GRAY_MID)

    # ── Маленькие узлы ────────────────────────────────────────────────────
    for k in ["FG","GH","HK","KF"]:
        px, py = nd[k]
        _small_node(draw, px, py, MID_R, m[k], F_MID)

    # ── Большие узлы ─────────────────────────────────────────────────────
    node_labels = {
        "A":"Личность","B":"Дух","C":"Материя","D":"Карма",
        "E":"Центр","F":"Отец×Дух","G":"Мать×Мат","H":"Деньги","K":"Любовь",
    }
    for key in ["A","B","C","D","F","G","H","K","E"]:
        px, py = nd[key]
        r = NODE_R + 5 if key == "E" else NODE_R
        _node(draw, px, py, r, NODE_COLORS[key], m[key], F_NODE)
        lbl = node_labels[key]
        bb = draw.textbbox((0,0), lbl, font=F_LBL)
        lw = bb[2]-bb[0]
        draw.text((px-lw//2, py+r+6), lbl, font=F_LBL, fill=GRAY_MID)

    # ── Блок внизу ───────────────────────────────────────────────────────
    bot_y = CY + R_BIG + 70
    draw.line([(40, bot_y-10), (IMG_W-40, bot_y-10)], fill=(80,70,130), width=1)

    male_str   = "  ·  ".join(str(x) for x in m["male_line"])
    female_str = "  ·  ".join(str(x) for x in m["female_line"])
    draw.text((50, bot_y),
              f"♂  Родовые программы (мужская линия):   {male_str}",
              font=F_LEG, fill=MALE_COLOR)
    draw.text((50, bot_y+24),
              f"♀  Родовые программы (женская линия):    {female_str}",
              font=F_LEG, fill=FEMALE_COLOR)

    legend_items = [
        ("A", m["A"], "Личность (день)",      NODE_COLORS["A"]),
        ("B", m["B"], "Дух (месяц)",           NODE_COLORS["B"]),
        ("C", m["C"], "Материя (год)",          NODE_COLORS["C"]),
        ("D", m["D"], "Кармич. хвост",          NODE_COLORS["D"]),
        ("E", m["E"], "Зона комфорта",          NODE_COLORS["E"]),
        ("F", m["F"], "Отец × Дух",             NODE_COLORS["F"]),
        ("G", m["G"], "Мать × Материя",         NODE_COLORS["G"]),
        ("H", m["H"], "Деньги / здоровье",      NODE_COLORS["H"]),
        ("K", m["K"], "Любовь / отношения",     NODE_COLORS["K"]),
    ]
    leg_y = bot_y + 56
    cols, col_w = 3, IMG_W // 3
    for i, (lbl, val, desc, col) in enumerate(legend_items):
        ci, ri = i % cols, i // cols
        lx = ci*col_w + 50
        ly = leg_y + ri*24
        draw.ellipse([lx, ly+3, lx+14, ly+17], fill=col)
        draw.text((lx+20, ly+1), f"{lbl} = {val}  —  {desc}", font=F_LEG, fill=GRAY_LIGHT)

    # ── Рамка ────────────────────────────────────────────────────────────
    draw.rectangle([4, 4, IMG_W-5, IMG_H-5], outline=GOLD, width=2)
    draw.rectangle([8, 8, IMG_W-9, IMG_H-9], outline=(80,70,130), width=1)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.read()


# ─── Совместимость с main.py ─────────────────────────────────────────────────

def build_matrix_image(user: dict) -> "str | None":
    """
    Принимает словарь user из БД (как в твоём main.py).
    Сохраняет PNG во временный файл, возвращает путь к файлу.
    Возвращает None при ошибке или отсутствии birth_date.
    """
    date_str = user.get("birth_date")
    if not date_str:
        return None
    try:
        png = generate_matrix_image(date_str, user.get("name", ""))
        path = Path(tempfile.gettempdir()) / f"matrix_{user.get('telegram_id','tmp')}.png"
        path.write_bytes(png)
        return str(path)
    except Exception as e:
        print(f"[matrix_image] Ошибка: {e}")
        return None


# ─── Тест из командной строки ────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    date = sys.argv[1] if len(sys.argv) > 1 else "1990-06-15"
    name = sys.argv[2] if len(sys.argv) > 2 else "Иван Иванов"
    png  = generate_matrix_image(date, name)
    out  = "/tmp/matrix_preview.png"
    with open(out, "wb") as f:
        f.write(png)
    m = calc_matrix(date)
    print(f"Матрица для {name} ({date}):")
    for k in ["A","B","C","D","E","F","G","H","K"]:
        print(f"  {k} = {m[k]}")
    print(f"  Мужская: {m['male_line']}")
    print(f"  Женская: {m['female_line']}")
    print(f"Сохранено: {out}")
