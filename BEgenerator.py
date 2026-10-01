import uuid
import zipfile
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

# --- EKSPORT ---
# Plik 3MF: każda zawieszka to OSOBNY obiekt (2 części: biała baza + czarny kod).
# Dzięki temu w Bambu Studio / na drukarce można pominąć ("Skip objects")
# pojedynczą uszkodzoną zawieszkę w trakcie wydruku.
# 3MF zapamiętuje też pozycje, więc Bambu Studio niczego nie centruje.
FILAMENT_BAZY = 1          # nr filamentu (slot AMS) dla białej podstawy
FILAMENT_KODOW = 2         # nr filamentu (slot AMS) dla czarnych kodów
EKSPORTUJ_STL = False      # True = dodatkowo stare 2 pliki STL (cała płyta jako jeden obiekt)


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


def _siatka_xml(mesh, obj_id):
    """Jeden obiekt <object> z siatką trójkątów w formacie 3MF"""
    wierzcholki = "".join(
        f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in mesh.vertices
    )
    trojkaty = "".join(
        f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces
    )
    return (f'  <object id="{obj_id}" p:UUID="{uuid.uuid4()}" type="model">\n'
            f'   <mesh><vertices>{wierzcholki}</vertices>'
            f'<triangles>{trojkaty}</triangles></mesh>\n'
            f'  </object>\n')


def zapisz_3mf(nazwa_pliku, zawieszki):
    """
    Zapisuje płytę jako projekt 3MF w układzie Bambu Studio.
    zawieszki: lista (nazwa, baza, kody, (x, y)) – siatki w układzie lokalnym zawieszki,
    (x, y) = położenie zawieszki na stole.
    Każda zawieszka = osobny obiekt złożony z 2 części (baza + kody).
    """
    NS = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
          'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
          'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
          'requiredextensions="p"')
    JEDNOSTKOWA = "1 0 0 0 1 0 0 0 1 0 0 0"

    zasoby_glowne, budowa, relacje, config_obiekty, config_plyta = [], [], [], [], []
    pliki_obiektow = {}

    for k, (nazwa, baza, kody, (x, y)) in enumerate(zawieszki):
        id_bazy, id_kodow, id_obiektu = 3 * k + 1, 3 * k + 2, 3 * k + 3
        sciezka = f"/3D/Objects/zawieszka_{k + 1}.model"

        pliki_obiektow[sciezka[1:]] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<model unit="millimeter" xml:lang="en-US" {NS}>\n'
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
            ' <resources>\n'
            + _siatka_xml(baza, id_bazy)
            + _siatka_xml(kody, id_kodow)
            + ' </resources>\n <build/>\n</model>\n'
        )
        relacje.append(
            f' <Relationship Target="{sciezka}" Id="rel-{k + 1}" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        )
        zasoby_glowne.append(
            f'  <object id="{id_obiektu}" p:UUID="{uuid.uuid4()}" type="model">\n'
            '   <components>\n'
            f'    <component p:path="{sciezka}" objectid="{id_bazy}" '
            f'p:UUID="{uuid.uuid4()}" transform="{JEDNOSTKOWA}"/>\n'
            f'    <component p:path="{sciezka}" objectid="{id_kodow}" '
            f'p:UUID="{uuid.uuid4()}" transform="{JEDNOSTKOWA}"/>\n'
            '   </components>\n'
            '  </object>\n'
        )
        budowa.append(
            f'  <item objectid="{id_obiektu}" p:UUID="{uuid.uuid4()}" '
            f'transform="1 0 0 0 1 0 0 0 1 {x:.4f} {y:.4f} 0" printable="1"/>\n'
        )

        def czesc(id_czesci, nazwa_czesci, filament):
            return (f'    <part id="{id_czesci}" subtype="normal_part">\n'
                    f'      <metadata key="name" value="{nazwa_czesci}"/>\n'
                    '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>\n'
                    f'      <metadata key="extruder" value="{filament}"/>\n'
                    '    </part>\n')

        config_obiekty.append(
            f'  <object id="{id_obiektu}">\n'
            f'    <metadata key="name" value="{nazwa}"/>\n'
            f'    <metadata key="extruder" value="{FILAMENT_BAZY}"/>\n'
            + czesc(id_bazy, f"{nazwa}_baza", FILAMENT_BAZY)
            + czesc(id_kodow, f"{nazwa}_kod", FILAMENT_KODOW)
            + '  </object>\n'
        )
        config_plyta.append(
            '    <model_instance>\n'
            f'      <metadata key="object_id" value="{id_obiektu}"/>\n'
            '      <metadata key="instance_id" value="0"/>\n'
            f'      <metadata key="identify_id" value="{100 + k}"/>\n'
            '    </model_instance>\n'
        )

    model_glowny = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<model unit="millimeter" xml:lang="en-US" {NS}>\n'
        ' <metadata name="Application">BambuStudio-02.00.00.00</metadata>\n'
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
        ' <metadata name="Title">Zawieszki QR</metadata>\n'
        ' <resources>\n' + "".join(zasoby_glowne) + ' </resources>\n'
        f' <build p:UUID="{uuid.uuid4()}">\n' + "".join(budowa) + ' </build>\n'
        '</model>\n'
    )
    model_settings = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n'
        + "".join(config_obiekty)
        + '  <plate>\n'
        '    <metadata key="plater_id" value="1"/>\n'
        '    <metadata key="plater_name" value=""/>\n'
        '    <metadata key="locked" value="false"/>\n'
        + "".join(config_plyta)
        + '  </plate>\n</config>\n'
    )

    with zipfile.ZipFile(nazwa_pliku, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
                   ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
                   ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
                   ' <Default Extension="config" ContentType="text/xml"/>\n'
                   '</Types>\n')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                   ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
                   'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
                   '</Relationships>\n')
        z.writestr("3D/3dmodel.model", model_glowny)
        z.writestr("3D/_rels/3dmodel.model.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>\n'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                   + "".join(relacje) + '</Relationships>\n')
        for sciezka, tresc in pliki_obiektow.items():
            z.writestr(sciezka, tresc)
        z.writestr("Metadata/model_settings.config", model_settings)


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

if len(pozycje) < ILE_SZTUK:
    raise SystemExit(f"BŁĄD: na stole mieści się tylko {len(pozycje)} sztuk – zmniejsz ILE_SZTUK.")

zawieszki = []   # (nazwa, baza, kody, (x, y)) – siatki w układzie lokalnym zawieszki

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
    kody.merge_vertices()

    # Układ lokalny zawieszki: środek bazy w XY, spód na Z=0.
    # Pozycja na stole trafia do transformacji obiektu w 3MF.
    (x0, y0, _), (x1, y1, _) = baza.bounds
    srodek = np.array([(x0 + x1) / 2, (y0 + y1) / 2, 0.0])
    baza.apply_translation(-srodek)
    kody.apply_translation(-srodek)

    col, row = pozycje[idx]
    x = col * ODSTEP_X + MARGINES_LEWY + srodek[0]
    y = row * ODSTEP_Y + MARGINES_DOLNY + srodek[1]
    zawieszki.append((numer, baza, kody, (x, y)))

zakres = f"{NUMER_STARTOWY:0{CYFRY_NUMERU}d}-{NUMER_KONCOWY:0{CYFRY_NUMERU}d}"
nazwa_3mf = f"Zawieszki_{PREFIKS}{zakres}_Dysza04.3mf"
zapisz_3mf(nazwa_3mf, zawieszki)

if EKSPORTUJ_STL:
    def na_stole(mesh, x, y):
        return mesh.copy().apply_translation([x, y, 0])
    trimesh.util.concatenate([na_stole(b, x, y) for _, b, _, (x, y) in zawieszki]).export(
        f"1_Bazy_{zakres}_Dysza04.stl")
    trimesh.util.concatenate([na_stole(k, x, y) for _, _, k, (x, y) in zawieszki]).export(
        f"2_Kody_{zakres}_Dysza04.stl")

# --- KONTROLA POŁOŻENIA NA STOLE ---
bx0 = min(x + b.bounds[0][0] for _, b, _, (x, y) in zawieszki)
by0 = min(y + b.bounds[0][1] for _, b, _, (x, y) in zawieszki)
bx1 = max(x + b.bounds[1][0] for _, b, _, (x, y) in zawieszki)
by1 = max(y + b.bounds[1][1] for _, b, _, (x, y) in zawieszki)
print(f"\nStół {ROZMIAR_STOLU_X:.0f}x{ROZMIAR_STOLU_Y:.0f} mm")
print(f"  Zawieszki zajmują: X {bx0:.1f}..{bx1:.1f}, Y {by0:.1f}..{by1:.1f} mm")
if bx1 > ROZMIAR_STOLU_X or by1 > ROZMIAR_STOLU_Y:
    print("  UWAGA: siatka wychodzi poza stół!")

print("\nGotowe! Wyeksportowano plik:")
print(f"  - {nazwa_3mf} ({ILE_SZTUK} osobnych obiektów, każdy = baza + kod)")
if EKSPORTUJ_STL:
    print(f"  - 1_Bazy_{zakres}_Dysza04.stl, 2_Kody_{zakres}_Dysza04.stl (stary format)")
print("\nINSTRUKCJA DO BAMBU STUDIO:")
print("1. File → Open Project (lub przeciągnij plik .3mf do okna).")
print(f"2. Każda zawieszka jest osobnym obiektem ({PREFIKS}...) z dwiema częściami:")
print(f"   '_baza' → filament {FILAMENT_BAZY} (biały), '_kod' → filament {FILAMENT_KODOW} (czarny).")
print("   Sprawdź tylko, czy w AMS sloty filamentów odpowiadają kolorom.")
print("3. Pozycje są zapisane w pliku – NIE używaj 'Auto arrange' / klawisza 'A'.")
print("4. Slajsuj i drukuj. W razie problemu z jedną zawieszką: na drukarce lub w Bambu")
print("   Handy/Studio wybierz 'Skip objects' i zaznacz uszkodzony obiekt (nazwa = numer).")
print("   Dolny tekst jest lustrzany (będzie czytelny po odwróceniu gotowej zawieszki).")
