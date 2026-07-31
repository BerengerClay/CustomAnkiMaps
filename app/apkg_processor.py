import io
import os
import re
import sqlite3
import tempfile
import threading
import zipfile
import zstandard
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Callable

# ==============================================================================
# DICTIONNAIRE DES COULEURS SVG À REMPLACER ET COULEURS PAR DÉFAUT
# ==============================================================================

# Codes couleurs hexadécimaux originaux présents dans les SVG du paquet GeoQuiz.apkg :
# - "water"              : #FFFFFF / #FFF (Océan / fond de carte)
# - "other_countries"    : #CCCCCC / #CCC (Terres et pays voisins non sélectionnés)
# - "target_country"     : #59a353 (Surbrillance du pays sélectionné sur cartes)
# - "silhouette"         : #9CA3AF (Forme du pays sur cartes silhouettes)
# - "capital_map"        : #D95F5F (Épingle capitale sur cartes globe et zoomées)
# Codes couleurs hexadécimaux originaux présents dans les SVG du paquet GeoQuiz.apkg :
# - "water"              : #FFFFFF / #FFF (Océan / fond de carte)
# - "other_countries"    : #CCCCCC / #CCC (Terres et pays voisins non sélectionnés)
# - "target_country"     : #59a353 (Surbrillance du pays sélectionné sur cartes)
# - "country_borders"    : #FFFFFF / #FFF (Frontières des pays sur cartes)
# - "silhouette"         : #9CA3AF (Forme du pays sur cartes silhouettes)
# - "capital_map"        : #D95F5F (Épingle capitale sur cartes globe et zoomées)
# - "capital_silhouette" : #D95F5F (Épingle capitale sur cartes silhouettes)
# - "grid_lines"         : #D8D8D8 (Lignes de quadrillage sur cartes)
ORIGINAL_SVG_COLORS = {
    "water": ["#FFFFFF", "#FFF", "#ffffff", "#fff"],               # Couleur originale de l'eau (Océan / fond de carte)
    "other_countries": ["#CCCCCC", "#CCC", "#cccccc", "#ccc"],      # Couleur originale des pays non sélectionnés (Terres / continents)
    "target_country": ["#59a353", "#59A353"],                    # Couleur originale du pays sélectionné (Surbrillance cartes)
    "country_borders": ["#FFFFFF", "#FFF", "#ffffff", "#fff"],     # Couleur originale des frontières des pays
    "silhouette": ["#9CA3AF", "#9ca3af"],                        # Couleur originale de la forme du pays (Cartes silhouettes)
    "capital_map": ["#D95F5F", "#d95f5f"],                       # Couleur originale de la capitale (Vues cartes)
    "capital_silhouette": ["#D95F5F", "#d95f5f"],                # Couleur originale de l'épingle capitale (Vues silhouettes)
    "grid_lines": ["#D8D8D8", "#d8d8d8"]                         # Couleur originale des lignes de quadrillage
}

# Couleurs par défaut proposées dans l'interface web (Classique Anki)
DEFAULT_COLOR_PALETTE = {
    "water": "#FFFFFF",              # Couleur de l'eau
    "other_countries": "#CCCCCC",    # Autres pays (cartes)
    "target_country": "#59A353",     # Pays sélectionné (cartes)
    "country_borders": "#FFFFFF",    # Frontières des pays (cartes)
    "silhouette": "#CCCCCC",         # Couleur de la silhouette
    "capital_map": "#000000",        # Capitale (cartes)
    "capital_silhouette": "#000000", # Capitale (silhouettes)
    "grid_lines": "#D8D8D8"          # Lignes de quadrillage (cartes)
}

def ensure_svg_viewbox(svg_text: str) -> str:
    """Ensure SVG has viewBox attribute and flexible sizing so it scales perfectly in any container."""
    if 'viewBox' not in svg_text:
        w_match = re.search(r'width=[\"\'](\d+)[\"\']', svg_text)
        h_match = re.search(r'height=[\"\'](\d+)[\"\']', svg_text)
        w = w_match.group(1) if w_match else "800"
        h = h_match.group(1) if h_match else "800"
        svg_text = re.sub(
            r'<svg\b([^>]*)>',
            rf'<svg \1 viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">',
            svg_text,
            count=1
        )
    return svg_text

def apply_color_transform(svg_text: str, colors: Dict[str, str], is_silhouette: bool = False) -> str:
    """
    Applies exact semantic color transforms matching ORIGINAL_SVG_COLORS dictionary mapping:
    - water: Ocean / sea background fill
    - other_countries: Non-selected countries on Globe & Zoomed maps
    - target_country: Target country highlight on Globe & Zoomed maps
    - country_borders: Country borders stroke on Globe & Zoomed maps
    - silhouette: Country shape fill on Silhouette & Silhouette+Capitale cards
    - capital_map: Capital pin on Globe & Zoomed maps
    - capital_silhouette: Capital pin marker on Silhouette+Capitale cards
    - grid_lines: Grid lines stroke on Globe & Zoomed maps
    """
    svg_out = svg_text

    # 1. Capital pin marker replacement (<path transform="translate..." ...>)
    cap_key = "capital_silhouette" if is_silhouette else "capital_map"
    cap_val = colors.get(cap_key, DEFAULT_COLOR_PALETTE[cap_key]).upper()

    def fix_capital_pin(m):
        tag = m.group(0)
        tag = re.sub(r'stroke=[\"\'][^\"\']+[\"\']', f'stroke="{cap_val}"', tag, flags=re.IGNORECASE)
        tag = re.sub(r'fill=[\"\'](?!none)[^\"\']+[\"\']', f'fill="{cap_val}"', tag, flags=re.IGNORECASE)
        return tag

    svg_out = re.sub(r'<path\b[^>]*transform=[\"\']translate[^>]*>', fix_capital_pin, svg_out, flags=re.IGNORECASE)

    # 2. Water / Ocean background replacement
    water_val = colors.get("water", DEFAULT_COLOR_PALETTE["water"]).upper()
    for w_code in ORIGINAL_SVG_COLORS["water"]:
        pattern = re.compile(rf'fill=[\"\']{re.escape(w_code)}[\"\']', re.IGNORECASE)
        svg_out = pattern.sub(f'fill="{water_val}"', svg_out)

    # 3. Silhouette vs Map Land & Target handling
    if is_silhouette:
        # Silhouette country shape fill -> silhouette color
        sil_val = colors.get("silhouette", DEFAULT_COLOR_PALETTE["silhouette"]).upper()
        for s_code in ORIGINAL_SVG_COLORS["silhouette"]:
            pattern = re.compile(rf'fill=[\"\']{re.escape(s_code)}[\"\']', re.IGNORECASE)
            svg_out = pattern.sub(f'fill="{sil_val}"', svg_out)

        # Replace target country color codes in silhouette cards
        for t_code in ORIGINAL_SVG_COLORS["target_country"]:
            pattern = re.compile(re.escape(t_code), re.IGNORECASE)
            svg_out = pattern.sub(sil_val, svg_out)
    else:
        # Globe & Zoomed maps: Other countries land fill (#CCCCCC -> other_countries)
        other_val = colors.get("other_countries", DEFAULT_COLOR_PALETTE["other_countries"]).upper()
        for o_code in ORIGINAL_SVG_COLORS["other_countries"]:
            pattern = re.compile(rf'fill=[\"\']{re.escape(o_code)}[\"\']', re.IGNORECASE)
            svg_out = pattern.sub(f'fill="{other_val}"', svg_out)

        # Target country highlight fill (#59a353 -> target_country)
        target_val = colors.get("target_country", DEFAULT_COLOR_PALETTE["target_country"]).upper()
        for t_code in ORIGINAL_SVG_COLORS["target_country"]:
            pattern = re.compile(re.escape(t_code), re.IGNORECASE)
            svg_out = pattern.sub(target_val, svg_out)

        # Target country glow gradient stop-color update
        for g_code in ORIGINAL_SVG_COLORS["capital_map"]:
            pattern = re.compile(rf'stop-color=[\"\']{re.escape(g_code)}[\"\']', re.IGNORECASE)
            svg_out = pattern.sub(f'stop-color="{target_val}"', svg_out)

        # Grid lines stroke replacement (#D8D8D8 -> grid_lines)
        grid_val = colors.get("grid_lines", DEFAULT_COLOR_PALETTE["grid_lines"]).upper()
        for gr_code in ORIGINAL_SVG_COLORS["grid_lines"]:
            pattern = re.compile(rf'stroke=[\"\']{re.escape(gr_code)}[\"\']', re.IGNORECASE)
            svg_out = pattern.sub(f'stroke="{grid_val}"', svg_out)

        # Country borders stroke replacement (#FFFFFF -> country_borders)
        border_val = colors.get("country_borders", DEFAULT_COLOR_PALETTE["country_borders"]).upper()
        for b_code in ORIGINAL_SVG_COLORS["country_borders"]:
            pattern = re.compile(rf'stroke=[\"\']{re.escape(b_code)}[\"\']', re.IGNORECASE)
            svg_out = pattern.sub(f'stroke="{border_val}"', svg_out)

    return svg_out

class APKGProcessor:
    def __init__(self, apkg_path: str):
        self.apkg_path = apkg_path
        self._cached_countries = None
        self._filename_to_zip = None

    def _get_media_index(self, z: zipfile.ZipFile, dctx: zstandard.ZstdDecompressor) -> Dict[str, str]:
        """Build mapping of original filename -> numeric zip entry name."""
        if self._filename_to_zip is not None:
            return self._filename_to_zip

        media_bytes = dctx.stream_reader(z.open('media')).read()
        raw_str = media_bytes.decode('latin1', errors='ignore')
        entries = re.findall(r'([A-Za-z0-9_\-]+\.(?:svg|png|jpg))', raw_str)
        mapping = {}
        for idx, fname in enumerate(entries):
            mapping[fname] = str(idx)
        self._filename_to_zip = mapping
        return mapping

    def get_countries(self) -> List[Dict[str, Any]]:
        """Extract complete list of countries/territories from collection.anki21b."""
        if self._cached_countries:
            return self._cached_countries

        dctx = zstandard.ZstdDecompressor()
        with zipfile.ZipFile(self.apkg_path, 'r') as z:
            anki21_bytes = dctx.stream_reader(z.open('collection.anki21b')).read()

            with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
                f.write(anki21_bytes)
                tmp_path = f.name

            try:
                conn = sqlite3.connect(tmp_path)
                cursor = conn.cursor()
                cursor.execute('SELECT sfld, flds FROM notes')

                countries = []
                for sfld, flds in cursor.fetchall():
                    country_name = sfld.strip()
                    if country_name and not country_name.startswith('Merci de'):
                        fields = flds.split('\x1f')
                        region = fields[11] if len(fields) > 11 else 'Autre'

                        globe_m = re.search(r'([A-Za-z0-9_\-]*_globe\.svg)', flds)
                        zoomed_m = re.search(r'([A-Za-z0-9_\-]*_zoomed\.svg)', flds)
                        silhouette_m = re.search(r'([A-Za-z0-9_\-]*_silhouette\.svg)', flds)
                        capitale_m = re.search(r'([A-Za-z0-9_\-]*_silhouette_capitale\.svg)', flds)

                        code = ''
                        if globe_m:
                            code = globe_m.group(1).replace('_globe.svg', '')
                        elif zoomed_m:
                            code = zoomed_m.group(1).replace('_zoomed.svg', '')

                        sil_file = silhouette_m.group(1) if silhouette_m else None
                        if sil_file and 'capitale' in sil_file:
                            sil_file = sil_file.replace('_capitale', '')

                        countries.append({
                            'code': code,
                            'name': country_name,
                            'region': region or 'Autre',
                            'svgs': {
                                'globe': globe_m.group(1) if globe_m else None,
                                'zoomed': zoomed_m.group(1) if zoomed_m else None,
                                'silhouette': sil_file,
                                'capitale': capitale_m.group(1) if capitale_m else None
                            }
                        })

                countries.sort(key=lambda x: x['name'])
                self._cached_countries = countries
                return countries
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    def get_samples(self, country_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract sample SVGs for live preview in frontend for a given country."""
        countries = self.get_countries()

        target = None
        if country_code:
            target = next((c for c in countries if c['code'].upper() == country_code.upper()), None)

        if not target:
            target = next((c for c in countries if c['code'] == 'FRA'), None) or \
                     next((c for c in countries if c['code'] == 'DEU'), None) or \
                     countries[0]

        dctx = zstandard.ZstdDecompressor()
        samples = []

        with zipfile.ZipFile(self.apkg_path, 'r') as z:
            media_map = self._get_media_index(z, dctx)

            categories = [
                ("globe", "Vue Globe 🌍", f"Globe terrestre - {target['name']}", target['svgs'].get('globe')),
                ("zoomed", "Vue Zoomée 🔍", f"Carte régionale zoomée - {target['name']}", target['svgs'].get('zoomed')),
                ("silhouette", "Silhouette 👤", f"Silhouette du pays - {target['name']}", target['svgs'].get('silhouette')),
                ("capitale", "Silhouette + Capitale 🏛️", f"Silhouette avec la capitale - {target['name']}", target['svgs'].get('capitale'))
            ]

            for cat_id, title, desc, filename in categories:
                svg_content = None
                if filename and filename in media_map:
                    zip_name = media_map[filename]
                    try:
                        raw_data = z.read(zip_name)
                        if len(raw_data) > 4 and raw_data[:4] == b'\x28\xb5\x2f\xfd':
                            decomp = dctx.stream_reader(io.BytesIO(raw_data)).read()
                            if b'<svg' in decomp:
                                svg_content = ensure_svg_viewbox(decomp.decode('utf-8', errors='ignore'))
                    except Exception:
                        pass

                if svg_content:
                    samples.append({
                        "id": cat_id,
                        "title": title,
                        "description": desc,
                        "filename": filename,
                        "country_name": target['name'],
                        "country_code": target['code'],
                        "svg": svg_content
                    })

        return samples

    def process_and_repack(self, color_map: Dict[str, str], progress_callback: Optional[Callable[[int, int], None]] = None) -> bytes:
        """
        Decompresses GeoQuiz.apkg, replaces colors in all SVG files according to color_map,
        and repacks into a new .apkg zip file in memory using multi-threading.
        """
        output_buffer = io.BytesIO()
        dctx = zstandard.ZstdDecompressor()

        with zipfile.ZipFile(self.apkg_path, 'r') as z_in:
            media_map = self._get_media_index(z_in, dctx)
            zip_to_fname = {v: k for k, v in media_map.items()}

            infolist = z_in.infolist()
            total_files = len(infolist)
            file_data = {item.filename: z_in.read(item.filename) for item in infolist}

        completed_count = 0
        lock = threading.Lock()

        def process_file(item):
            nonlocal completed_count
            raw_data = file_data[item.filename]
            res_data = raw_data

            if item.filename.isdigit() and len(raw_data) > 4 and raw_data[:4] == b'\x28\xb5\x2f\xfd':
                try:
                    local_dctx = zstandard.ZstdDecompressor()
                    local_cctx = zstandard.ZstdCompressor()
                    decompressed = local_dctx.stream_reader(io.BytesIO(raw_data)).read()
                    if b'<svg' in decompressed:
                        svg_text = decompressed.decode('utf-8', errors='ignore')
                        svg_text = ensure_svg_viewbox(svg_text)

                        orig_fname = zip_to_fname.get(item.filename, '')
                        is_silhouette = 'silhouette' in orig_fname.lower() or ('<path' in svg_text and '<rect' not in svg_text and '<circle' not in svg_text)
                        svg_text = apply_color_transform(svg_text, color_map, is_silhouette=is_silhouette)

                        res_data = local_cctx.compress(svg_text.encode('utf-8'))
                except Exception:
                    pass

            with lock:
                completed_count += 1
                if progress_callback:
                    try:
                        progress_callback(completed_count, total_files)
                    except Exception:
                        pass

            return (item, res_data)

        max_workers = min(32, (os.cpu_count() or 4) * 2)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_file, infolist))

        with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for item, data in results:
                z_out.writestr(item, data)

        return output_buffer.getvalue()
