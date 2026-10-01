import trimesh
import qrcode
import numpy as np
from shapely.geometry import Polygon, Point
from PIL import Image, ImageDraw, ImageFont

# --- USTAWIENIA PARTII ---
PREFIKS = "BE"           # przedrostek numeru – wchodzi do QR i do tekstu na spodzie zawieszki
CYFRY_NUMERU = 5         # ile cyfr ma numer po przedrostku (np. 5 -> BE01261)
NUMER_STARTOWY = 2041    # Skonczyłem na 1981, następna partija zaczyna się od 981
ILE_SZTUK = 60          # Bambu P2S 256x256 – siatka 10x8 = 80 miejsc, 76 dostepnych

# --- PARAMETRY GEOMETRII W MILIMETRACH (DLA DYSZY 0.4) ---
GRUBOSC_WARSTWY = 0.2
GRUBOSC_BAZY = 2.6

# Wysokość czarnych obszarów = 2 warstwy (0.4 mm)
ZAGLEBIENIE_KODU = 2 * GRUBOSC_WARSTWY   # 0.4 mm
Z_KODU_TOP    = GRUBOSC_BAZY - ZAGLEBIENIE_KODU   # 2.2 mm (QR na górze)
Z_KODU_BOTTOM = 0.0                               # 0.0 mm (tekst na dole)
PROMIEN_ZAOKRAGLENIA = 2.0

# --- OTWÓR NA SZNUREK (górna część zawieszki) ---
SREDNICA_OTWORU = 3.0                      # średnica otworu w mm
PROMIEN_OTWORU = SREDNICA_OTWORU / 2.0     # promień wyliczany automatycznie
SRODEK_OTWORU = (9.6, 20.8)                # środek otworu (X, Y) w mm

# --- UKŁAD NA PŁYCIE (Bambu P2S 256x256) ---
ROZMIAR_STOLU_X = 256.0
ROZMIAR_STOLU_Y = 256.0
ODSTEP_X = 21.0            # raster kolumn
ODSTEP_Y = 29.0            # raster wierszy
MAX_ROWS = 8
MAX_COLS = 10
MARGINES_LEWY = 10.0       # zapas od lewej krawędzi stołu
MARGINES_DOLNY = 6.0       # zapas od przedniej krawędzi stołu (5-7 mm)

# --- KOTWICA CENTRUJĄCA ---
# Bambu Studio po imporcie centruje obiekt na stole i ignoruje pozycję z pliku STL.
# Mały znacznik w prawym tylnym rogu rozszerza bounding box tak, żeby stał się
# symetryczny względem środka stołu – wtedy centrowanie NIC nie przesuwa,
# a siatka ląduje dokładnie na MARGINES_LEWY / MARGINES_DOLNY.
# Znacznik jest drukowany: kwadracik, który po prostu zdejmuje się z płyty.
# UWAGA: kotwica stoi za kolumną, więc pilnuje TYLKO osi Y (odstęp od przodu stołu).
# W osi X Bambu Studio nadal wycentruje siatkę po swojemu.
UZYJ_KOTWICY = False       # True = dodaj kotwicę; False = same zawieszki, bez nic ekstra
KOTWICA_ROZMIAR = 5.0      # bok kwadratu w mm
KOTWICA_WYSOKOSC = 0.6     # 3 warstwy – trzyma się płyty, łatwo oderwać
KOTWICA_KOLUMNA = 2        # nr kolumny (od 0), za którą stoi kotwica – 3. od lewej, pełna (8 sztuk)


def stworz_baze():
    """Pełna bryła podstawy (bez otworów na tekst/QR)"""
    punkty = [
        (2.0,  2.0),
        (17.2, 2.0),
        (17.2, 18.8),
        (9.6,  23.3),
        (2.0,  18.8),
    ]
    szkielet = Polygon(punkty)
    zewnetrzny = szkielet.buffer(PROMIEN_ZAOKRAGLENIA)
    srodek_otworu = Point(*SRODEK_OTWORU)
    otwor = srodek_otworu.buffer(PROMIEN_OTWORU)
    return trimesh.creation.extrude_polygon(zewnetrzny.difference(otwor), height=GRUBOSC_BAZY)


def stworz_qr_3d(tekst):
    """QR jako płaski zestaw prostopadłościanów (nie lustrzany)"""
    qr = qrcode.QRCode(version=1, box_size=1, border=0)
    qr.add_data(tekst)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    rozmiar_kostki = 0.8   # 2 ścieżki × 0.4 mm
    kostki = [
        trimesh.creation.box(extents=[rozmiar_kostki, rozmiar_kostki, ZAGLEBIENIE_KODU])
        .apply_transform(trimesh.transformations.translation_matrix([
            c * rozmiar_kostki + rozmiar_kostki / 2,
            -r * rozmiar_kostki - rozmiar_kostki / 2,
            ZAGLEBIENIE_KODU / 2
        ]))
        for r, wiersz in enumerate(matrix)
        for c, v in enumerate(wiersz) if v
    ]
    return trimesh.util.concatenate(kostki), 16.8


def stworz_tekst_pixelowy(tekst):
    """Tekst 'PREFIKS\nxxxxx' jako płaskie prostopadłościany – z odbiciem lustrzanym (dla dolnej strony)"""
    litery = f"{PREFIKS}\n{tekst[len(PREFIKS):]}"
    try:
        font = ImageFont.truetype("arialbd.ttf", 16)
    except:
        font = ImageFont.load_default()

    img_test = Image.new('1', (100, 100), color=0)
    draw_test = ImageDraw.Draw(img_test)
    bbox = draw_test.multiline_textbbox((0, 0), litery, font=font, align="center")
    w = int(bbox[2] - bbox[0])
    h = int(bbox[3] - bbox[1])

    img = Image.new('1', (w + 2, h + 2), color=0)
    ImageDraw.Draw(img).multiline_text(
        (int(1 - bbox[0]), int(1 - bbox[1])), litery, font=font, fill=1, align="center"
    )

    # ZWIERCIADŁO (odbicie poziome) – TYLKO DLA TEKSTU NA DOLNEJ STRONIE
    img = img.transpose(Image.FLIP_LEFT_RIGHT)

    max_rozmiar = 16.8
    rozmiar_kostki = min(max_rozmiar / (w + 2), max_rozmiar / (h + 2))

    kostki = [
        trimesh.creation.box(extents=[rozmiar_kostki, rozmiar_kostki, ZAGLEBIENIE_KODU])
        .apply_transform(trimesh.transformations.translation_matrix([
            c * rozmiar_kostki + rozmiar_kostki / 2,
            -r * rozmiar_kostki - rozmiar_kostki / 2,
            ZAGLEBIENIE_KODU / 2
        ]))
        for r, wiersz in enumerate(np.array(img))
        for c, v in enumerate(wiersz) if v
    ]
    return trimesh.util.concatenate(kostki), (w + 2) * rozmiar_kostki, (h + 2) * rozmiar_kostki


# --- GENEROWANIE POZYCJI NA PŁYCIE ---
NUMER_KONCOWY = NUMER_STARTOWY + ILE_SZTUK - 1
print(f"Generowanie partii dla dyszy 0.4mm: {PREFIKS}{NUMER_STARTOWY:0{CYFRY_NUMERU}d} "
      f"do {PREFIKS}{NUMER_KONCOWY:0{CYFRY_NUMERU}d} ({ILE_SZTUK} sztuk)")

pozycje = []
col, row = 0, 0
while len(pozycje) < ILE_SZTUK:
    if not ((col == 0 or col == 1) and row >= 6):
        pozycje.append((col, row))
    row += 1
    if row >= MAX_ROWS:
        row = 0
        col += 1
        if col >= MAX_COLS and len(pozycje) < ILE_SZTUK:
            break

wszystkie_bazy = []
wszystkie_kody = []

for idx, i in enumerate(range(NUMER_STARTOWY, NUMER_KONCOWY + 1)):
    numer = f"{PREFIKS}{i:0{CYFRY_NUMERU}d}"
    if idx % 10 == 0:
        print(f"  -> Modelowanie: {numer}")

    baza = stworz_baze()

    # QR na górnej powierzchni (NIE lustrzany)
    q, qr_size = stworz_qr_3d(numer)
    q.apply_transform(trimesh.transformations.translation_matrix([1.2, 1.2 + qr_size, Z_KODU_TOP]))

    # Tekst na dolnej powierzchni (lustrzany – funkcja już zawiera odbicie)
    t_mod, tw, th = stworz_tekst_pixelowy(numer)
    t_x = 1.2 + (16.8 - tw) / 2.0
    t_y = 1.2 + 16.8 - (16.8 - th) / 2.0
    t_mod.apply_transform(trimesh.transformations.translation_matrix([t_x, t_y, Z_KODU_BOTTOM]))

    kody = trimesh.util.concatenate([q, t_mod])

    col, row = pozycje[idx]
    translacja = trimesh.transformations.translation_matrix([
        col * ODSTEP_X + MARGINES_LEWY,
        row * ODSTEP_Y + MARGINES_DOLNY,
        0
    ])

    wszystkie_bazy.append(baza.apply_transform(translacja))
    wszystkie_kody.append(kody.apply_transform(translacja))

nazwa_bazy  = f"1_Bazy_{NUMER_STARTOWY:0{CYFRY_NUMERU}d}-{NUMER_KONCOWY:0{CYFRY_NUMERU}d}_Dysza04.stl"
nazwa_kodow = f"2_Kody_{NUMER_STARTOWY:0{CYFRY_NUMERU}d}-{NUMER_KONCOWY:0{CYFRY_NUMERU}d}_Dysza04.stl"

# --- KOTWICA: symetryzuje bounding box w osi Y względem środka stołu ---
if UZYJ_KOTWICY:
    siatka_bounds = trimesh.util.concatenate(wszystkie_bazy + wszystkie_kody).bounds
    sx0, sy0 = siatka_bounds[0][0], siatka_bounds[0][1]
    sx1, sy1 = siatka_bounds[1][0], siatka_bounds[1][1]

    # tylna krawędź kotwicy = lustrzane odbicie przedniej krawędzi siatki
    ky1 = ROZMIAR_STOLU_Y - sy0

    if ky1 <= sy1:
        raise SystemExit(
            f"BŁĄD: siatka jest za głęboka – kotwica musiałaby stanąć za Y={sy1:.1f}, "
            f"a wypada na Y={ky1:.1f}.\n"
            f"Zmniejsz ILE_SZTUK, ODSTEP_Y albo MARGINES_DOLNY."
        )

    # kotwica stoi za kolumną nr KOTWICA_KOLUMNA (licząc od 0, od lewej)
    szer_metki = stworz_baze().bounds[1][0]
    kx_srodek = MARGINES_LEWY + KOTWICA_KOLUMNA * ODSTEP_X + szer_metki / 2

    kotwica = trimesh.creation.box(
        extents=[KOTWICA_ROZMIAR, KOTWICA_ROZMIAR, KOTWICA_WYSOKOSC]
    ).apply_transform(trimesh.transformations.translation_matrix([
        kx_srodek,
        ky1 - KOTWICA_ROZMIAR / 2,
        KOTWICA_WYSOKOSC / 2
    ]))
    wszystkie_bazy.append(kotwica)
    print(f"\nKotwica (oś Y): kwadrat {KOTWICA_ROZMIAR}x{KOTWICA_ROZMIAR}x{KOTWICA_WYSOKOSC} mm "
          f"za kolumną {KOTWICA_KOLUMNA + 1}. od lewej – środek X={kx_srodek:.1f}, tylna krawędź Y={ky1:.1f}")

plyta_bazy = trimesh.util.concatenate(wszystkie_bazy)
plyta_kody = trimesh.util.concatenate(wszystkie_kody)

plyta_bazy.export(nazwa_bazy)
plyta_kody.export(nazwa_kodow)

# --- KONTROLA POŁOŻENIA NA STOLE ---
(bx0, by0, _), (bx1, by1, _) = trimesh.util.concatenate([plyta_bazy, plyta_kody]).bounds
print(f"\nStół {ROZMIAR_STOLU_X:.0f}x{ROZMIAR_STOLU_Y:.0f} mm")
if UZYJ_KOTWICY:
    print(f"  Same zawieszki:  X {sx0:.1f}..{sx1:.1f}, Y {sy0:.1f}..{sy1:.1f} mm")
print(f"  Bounding box:    X {bx0:.1f}..{bx1:.1f}, Y {by0:.1f}..{by1:.1f} mm")
print(f"  Środek bounding boxa: X={(bx0+bx1)/2:.1f}, Y={(by0+by1)/2:.1f} mm "
      f"(środek stołu: {ROZMIAR_STOLU_X/2:.1f}, {ROZMIAR_STOLU_Y/2:.1f})")
print(f"\n  >>> Jeśli Bambu Studio wycentruje siatkę, wpisz w panelu 'Manipulacja obiektem':")
print(f"      Pozycja X = {(bx0+bx1)/2:.1f} mm,  Pozycja Y = {(by0+by1)/2:.1f} mm")

print(f"\nGotowe! Wyeksportowano pliki:")
print(f"  - {nazwa_bazy} (biała podstawa)")
print(f"  - {nazwa_kodow} (czarne napisy i QR)")
print("\nINSTRUKCJA DO BAMBU STUDIO:")
print("1. File → Import → Import STL → zaznacz oba pliki jednocześnie.")
print("2. Włącz opcję 'Load as multiple parts' (wczytaj jako wiele części).")
print("3. W oknie 'Objects' przypisz:")
print("   - '1_Bazy...' → biały filament")
print("   - '2_Kody...' → czarny filament")
print("4. NIE używaj 'Auto arrange' / klawisza 'A'. Kotwica pilnuje osi Y (odstęp od przodu),")
print("   w osi X Bambu Studio przesunie siatkę na środek stołu – to jest OK.")
print("5. Slajsuj – czarne obszary zostaną wydrukowane jako część białej bryły (bez wgłębień).")
print(f"6. Po wydruku oderwij kwadracik-kotwicę stojący za {KOTWICA_KOLUMNA + 1}. kolumną od lewej.")
print(f"   Dolny tekst jest lustrzany (będzie czytelny po odwróceniu gotowej zawieszki).")