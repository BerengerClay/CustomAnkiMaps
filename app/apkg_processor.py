import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
import zipfile
import zstandard
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Callable

# ==============================================================================
# DICTIONNAIRE DES COULEURS SVG À REMPLACER ET COULEURS PAR DÉFAUT
# ==============================================================================

# Codes couleurs hexadécimaux originaux présents dans les SVG du paquet GeoQuiz.apkg
ORIGINAL_SVG_COLORS = {
    "water": ["#FFFFFF", "#FFF", "#ffffff", "#fff"],               # Couleur originale de l'eau (Océan / fond de carte)
    "other_countries": ["#CCCCCC", "#CCC", "#cccccc", "#ccc"],      # Couleur originale des pays non sélectionnés (Terres / continents)
    "target_country": ["#59a353", "#59A353"],                    # Couleur originale du pays sélectionné (Surbrillance cartes)
    "country_borders": ["#FFFFFF", "#FFF", "#ffffff", "#fff"],     # Couleur originale des frontières des pays
    "silhouette": ["#CCCCCC", "#CCC", "#cccccc", "#ccc", "#9CA3AF", "#9ca3af"], # Couleur originale de la forme du pays (Cartes silhouettes)
    "capital_map": ["#D95F5F", "#d95f5f"],                       # Couleur originale de la capitale (Vues cartes)
    "capital_silhouette": ["#D95F5F", "#d95f5f"],                # Couleur originale de l'épingle capitale (Vues silhouettes)
    "grid_lines": ["#D8D8D8", "#d8d8d8"],                        # Couleur originale des lignes de quadrillage
    "zee_map": ["#D95F5F", "#d95f5f"],                           # Couleur originale des frontières ZEE (Vues cartes)
    "zee_silhouette": ["#D95F5F", "#d95f5f"],                    # Couleur originale des frontières ZEE (Vues silhouettes)
    "zee_border": ["#D95F5F", "#d95f5f"]                         # Rétrocompatibilité
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
    "grid_lines": "#D8D8D8",         # Lignes de quadrillage (cartes)
    "zee_map": "#D95F5F",            # Frontières maritimes ZEE (cartes)
    "zee_silhouette": "#D95F5F",     # Frontières maritimes ZEE (silhouettes)
    "zee_border": "#D95F5F"          # Rétrocompatibilité
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

def is_map_svg(filename: str) -> bool:
    """Vérifie strictement si le fichier SVG est une carte et NON un drapeau."""
    if not filename or not filename.lower().endswith('.svg'):
        return False
    fname_lower = filename.lower()
    return any(k in fname_lower for k in ['_zoomed_', '_globe_', '_silhouette_'])

def apply_color_transform(svg_text: str, colors: Dict[str, str], is_silhouette: bool = False) -> str:
    """
    Applies exact semantic color transforms matching ORIGINAL_SVG_COLORS dictionary mapping
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

    # 2. Target country glow gradient stop-color update
    target_val = colors.get("target_country", DEFAULT_COLOR_PALETTE["target_country"]).upper()
    for g_code in ORIGINAL_SVG_COLORS["capital_map"]:
        pattern = re.compile(rf'stop-color=[\"\']{re.escape(g_code)}[\"\']', re.IGNORECASE)
        svg_out = pattern.sub(f'stop-color="{target_val}"', svg_out)

    # 3. ZEE / Maritime Exclusive Economic Zone borders replacement
    zee_key = "zee_silhouette" if is_silhouette else "zee_map"
    zee_val = colors.get(zee_key, colors.get("zee_border", DEFAULT_COLOR_PALETTE.get(zee_key, "#D95F5F"))).upper()
    zee_codes = ORIGINAL_SVG_COLORS.get(zee_key, ORIGINAL_SVG_COLORS["zee_border"])
    for z_code in zee_codes:
        pattern = re.compile(re.escape(z_code), re.IGNORECASE)
        svg_out = pattern.sub(zee_val, svg_out)

    # 4. Water / Ocean background replacement
    water_val = colors.get("water", DEFAULT_COLOR_PALETTE["water"]).upper()
    for w_code in ORIGINAL_SVG_COLORS["water"]:
        pattern = re.compile(rf'fill=[\"\']{re.escape(w_code)}[\"\']', re.IGNORECASE)
        svg_out = pattern.sub(f'fill="{water_val}"', svg_out)

    # 5. Silhouette vs Map Land & Target handling
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
        for t_code in ORIGINAL_SVG_COLORS["target_country"]:
            pattern = re.compile(re.escape(t_code), re.IGNORECASE)
            svg_out = pattern.sub(target_val, svg_out)

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

def get_palette_hash(colors: Dict[str, str]) -> str:
    """Generate a deterministic 8-character hex hash from the active color palette."""
    sorted_pairs = sorted((k, str(v).upper().strip()) for k, v in colors.items())
    hash_str = "_".join(f"{k}:{v}" for k, v in sorted_pairs)
    return hashlib.md5(hash_str.encode('utf-8')).hexdigest()[:8]

def rename_svg_filename(fname: str, palette_hash: str) -> str:
    """
    Remplace les 8 derniers caractères par le hash de la palette
    UNIQUEMENT pour les cartes SVG, pour conserver strictly la même longueur de nom.
    """
    if not is_map_svg(fname):
        return fname

    name_part = fname[:-4]  # Enlève '.svg'
    hash_len = len(palette_hash)  # 8 caractères

    if len(name_part) > hash_len:
        new_name_part = name_part[:-hash_len] + palette_hash
    else:
        new_name_part = palette_hash[:len(name_part)]

    return f"{new_name_part}.svg"

def encode_anki_media_protobuf(media_dict: Dict[str, str]) -> bytes:
    """
    Encode un dictionnaire {zip_index: filename} au format Protobuf 'MediaEntries' d'Anki V3.
    """
    def write_varint(val: int) -> bytearray:
        buf = bytearray()
        while True:
            tobw = val & 0x7f
            val >>= 7
            if val:
                buf.append(tobw | 0x80)
            else:
                buf.append(tobw)
                break
        return buf

    output = bytearray()
    sorted_items = sorted(media_dict.items(), key=lambda x: int(x[0]))

    for zip_id_str, filename in sorted_items:
        zip_id = int(zip_id_str)
        fname_bytes = filename.encode('utf-8')
        
        entry_bytes = bytearray()
        entry_bytes.append(0x0A)
        entry_bytes.extend(write_varint(len(fname_bytes)))
        entry_bytes.extend(fname_bytes)
        
        entry_bytes.append(0x10)
        entry_bytes.extend(write_varint(zip_id))
        
        output.append(0x0A)
        output.extend(write_varint(len(entry_bytes)))
        output.extend(entry_bytes)

    return bytes(output)

class APKGProcessor:
    def __init__(self, apkg_path: str):
        self.apkg_path = apkg_path
        self._cached_countries = None
        self._filename_to_zip = None

    def _get_media_raw_bytes(self, z: zipfile.ZipFile, dctx: zstandard.ZstdDecompressor) -> bytes:
        """Extrait les octets bruts du fichier 'media' en gérant la compression zstd optionnelle."""
        raw = z.read('media')
        if len(raw) > 4 and raw[:4] == b'\x28\xb5\x2f\xfd':
            return dctx.stream_reader(io.BytesIO(raw)).read()
        return raw

    def _get_media_index(self, z: zipfile.ZipFile, dctx: zstandard.ZstdDecompressor) -> Dict[str, str]:
        """Build mapping of original filename -> numeric zip entry name."""
        if self._filename_to_zip is not None:
            return self._filename_to_zip

        media_bytes = self._get_media_raw_bytes(z, dctx)

        # 1. Essai de lecture au format JSON (généré par genanki)
        try:
            parsed_json = json.loads(media_bytes.decode('utf-8'))
            mapping = {v: k for k, v in parsed_json.items()}
            self._filename_to_zip = mapping
            return mapping
        except Exception:
            pass

        # 2. Essai de lecture binaire/regex (Anki V3 Protobuf ou texte)
        raw_str = media_bytes.decode('latin1', errors='ignore')
        entries = re.findall(r'([A-Za-z0-9_\-]+\.(?:svg|png|jpg))', raw_str)
        mapping = {}
        for idx, fname in enumerate(entries):
            mapping[fname] = str(idx)
        self._filename_to_zip = mapping
        return mapping

    def get_countries(self) -> List[Dict[str, Any]]:
        """Extract complete list of countries/territories from collection database."""
        if self._cached_countries:
            return self._cached_countries

        dctx = zstandard.ZstdDecompressor()
        with zipfile.ZipFile(self.apkg_path, 'r') as z:
            db_key = 'collection.anki21b' if 'collection.anki21b' in z.namelist() else 'collection.anki2'
            raw_db = z.read(db_key)

            if len(raw_db) > 4 and raw_db[:4] == b'\x28\xb5\x2f\xfd':
                db_bytes = dctx.stream_reader(io.BytesIO(raw_db)).read()
            else:
                db_bytes = raw_db

            with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
                f.write(db_bytes)
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

                        globe_m = re.search(r'([A-Za-z0-9_\-]*_globe(?:_[0-9a-fA-F]{8})?\.svg)', flds)
                        zoomed_m = re.search(r'([A-Za-z0-9_\-]*_zoomed(?:_[0-9a-fA-F]{8})?\.svg)', flds)
                        silhouette_m = re.search(r'([A-Za-z0-9_\-]*_silhouette(?:_[0-9a-fA-F]{8})?\.svg)', flds)
                        capitale_m = re.search(r'([A-Za-z0-9_\-]*_silhouette_capitale(?:_[0-9a-fA-F]{8})?\.svg)', flds)

                        code = ''
                        if globe_m:
                            raw_fn = re.sub(r'_[0-9a-fA-F]{8}\.svg$', '.svg', globe_m.group(1), flags=re.IGNORECASE)
                            code = raw_fn.replace('_globe.svg', '')
                        elif zoomed_m:
                            raw_fn = re.sub(r'_[0-9a-fA-F]{8}\.svg$', '.svg', zoomed_m.group(1), flags=re.IGNORECASE)
                            code = raw_fn.replace('_zoomed.svg', '')

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
                        else:
                            decomp = raw_data

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
        Decompresses GeoQuiz.apkg, replaces colors in map SVG files according to color_map,
        renames media files with a palette hash to force Anki refresh, and repacks into a new .apkg zip file.
        """
        output_buffer = io.BytesIO()
        dctx = zstandard.ZstdDecompressor()
        cctx = zstandard.ZstdCompressor()

        palette_hash = get_palette_hash(color_map)

        with zipfile.ZipFile(self.apkg_path, 'r') as z_in:
            media_map = self._get_media_index(z_in, dctx)
            zip_to_fname = {v: k for k, v in media_map.items()}

            infolist = z_in.infolist()
            total_files = len(infolist)
            file_data = {item.filename: z_in.read(item.filename) for item in infolist}

        # Dictionnaire des nouveaux noms (Uniquement pour les cartes SVG, pas les drapeaux)
        rename_map = {
            orig_f: rename_svg_filename(orig_f, palette_hash)
            for orig_f in media_map.keys()
            if is_map_svg(orig_f)
        }

        # 1. Mise à jour de la base de données SQLite (collection.anki21b ou collection.anki2)
        db_key = 'collection.anki21b' if 'collection.anki21b' in file_data else ('collection.anki2' if 'collection.anki2' in file_data else None)

        if db_key:
            try:
                raw_db = file_data[db_key]
                if len(raw_db) > 4 and raw_db[:4] == b'\x28\xb5\x2f\xfd':
                    db_bytes = dctx.stream_reader(io.BytesIO(raw_db)).read()
                    is_db_compressed = True
                else:
                    db_bytes = raw_db
                    is_db_compressed = False

                with tempfile.NamedTemporaryFile(suffix='.sqlite', delete=False) as f:
                    f.write(db_bytes)
                    tmp_db_path = f.name

                conn = sqlite3.connect(tmp_db_path)
                cursor = conn.cursor()
                current_time = int(time.time())

                for orig_f, new_f in rename_map.items():
                    if orig_f != new_f:
                        cursor.execute(
                            'UPDATE notes SET flds = replace(flds, ?, ?), mod = ? WHERE flds LIKE ?', 
                            (orig_f, new_f, current_time, f'%{orig_f}%')
                        )

                conn.commit()
                conn.close()

                with open(tmp_db_path, 'rb') as f:
                    new_db_bytes = f.read()

                if is_db_compressed:
                    file_data[db_key] = cctx.compress(new_db_bytes)
                else:
                    file_data[db_key] = new_db_bytes

            except Exception as e:
                print(f"❌ Erreur lors de la mise à jour SQLite : {e}", flush=True)
            finally:
                if 'tmp_db_path' in locals() and os.path.exists(tmp_db_path):
                    os.remove(tmp_db_path)

        # 2. Mise à jour du fichier 'media'
        if 'media' in file_data:
            try:
                raw_media = file_data['media']
                is_media_compressed = len(raw_media) > 4 and raw_media[:4] == b'\x28\xb5\x2f\xfd'

                if is_media_compressed:
                    media_bytes = dctx.stream_reader(io.BytesIO(raw_media)).read()
                else:
                    media_bytes = raw_media

                try:
                    parsed_json = json.loads(media_bytes.decode('utf-8'))
                    new_json = {}
                    for zip_id, orig_f in parsed_json.items():
                        new_json[zip_id] = rename_map.get(orig_f, orig_f)
                    new_media_bytes = json.dumps(new_json).encode('utf-8')
                except Exception:
                    new_media_bytes = media_bytes
                    for orig_f, new_f in rename_map.items():
                        if orig_f != new_f:
                            new_media_bytes = new_media_bytes.replace(orig_f.encode('utf-8'), new_f.encode('utf-8'))

                if is_media_compressed:
                    file_data['media'] = cctx.compress(new_media_bytes)
                else:
                    file_data['media'] = new_media_bytes

            except Exception as e:
                print(f"❌ Erreur lors de la mise à jour du fichier media : {e}", flush=True)

        # 3. Traitement multithread des fichiers SVG
        completed_count = 0
        lock = threading.Lock()

        def process_file(item):
            nonlocal completed_count
            raw_data = file_data[item.filename]
            res_data = raw_data

            orig_fname = zip_to_fname.get(item.filename, '')

            # CONDITION STRICTE : Si ce n'est PAS une carte (ex: drapeau comme FRA.svg), on passe directement !
            if not is_map_svg(orig_fname):
                with lock:
                    completed_count += 1
                    if progress_callback:
                        try:
                            progress_callback(completed_count, total_files)
                        except Exception:
                            pass
                return (item, res_data)

            # Décompression si nécessaire
            decompressed = None
            was_compressed = False
            if len(raw_data) > 4 and raw_data[:4] == b'\x28\xb5\x2f\xfd':
                try:
                    local_dctx = zstandard.ZstdDecompressor()
                    decompressed = local_dctx.stream_reader(io.BytesIO(raw_data)).read()
                    was_compressed = True
                except Exception:
                    pass
            elif b'<svg' in raw_data:
                decompressed = raw_data
                was_compressed = False

            if decompressed and b'<svg' in decompressed:
                try:
                    local_cctx = zstandard.ZstdCompressor()
                    svg_text = decompressed.decode('utf-8', errors='ignore')
                    svg_text = ensure_svg_viewbox(svg_text)

                    is_silhouette = 'silhouette' in orig_fname.lower()
                    svg_text = apply_color_transform(svg_text, color_map, is_silhouette=is_silhouette)

                    if was_compressed:
                        res_data = local_cctx.compress(svg_text.encode('utf-8'))
                    else:
                        res_data = svg_text.encode('utf-8')
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

        # 4. Reconstruction du fichier ZIP final sans doublons
        with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for item, data in results:
                if item.filename != 'media' and item.filename != db_key:
                    z_out.writestr(item, data)

            if db_key and db_key in file_data:
                z_out.writestr(db_key, file_data[db_key])

            if 'media' in file_data:
                z_out.writestr('media', file_data['media'])

        return output_buffer.getvalue()