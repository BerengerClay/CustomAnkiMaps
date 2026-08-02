import io
import os
import sqlite3
import tempfile
import zipfile
import zstandard
from typing import Optional

def extract_and_decompress_db(apkg_path: str, temp_dir: str, prefix: str) -> str:
    """Extrait et décompresse la base SQLite (collection.anki21b ou collection.anki2) d'un APKG."""
    dctx = zstandard.ZstdDecompressor()
    with zipfile.ZipFile(apkg_path, 'r') as z:
        db_key = 'collection.anki21b' if 'collection.anki21b' in z.namelist() else 'collection.anki2'
        raw_db = z.read(db_key)

        # Vérification compression zstd
        if len(raw_db) > 4 and raw_db[:4] == b'\x28\xb5\x2f\xfd':
            db_bytes = dctx.stream_reader(io.BytesIO(raw_db)).read()
        else:
            db_bytes = raw_db

        output_path = os.path.join(temp_dir, f"{prefix}_{db_key}.sqlite")
        with open(output_path, 'wb') as f:
            f.write(db_bytes)
        
        return output_path, db_key

def merge_deck_progress(old_apkg_path: str, new_apkg_path: str, output_apkg_path: str):
    """
    Transfère les révisions, statistiques, options et état d'apprentissage 
    de old_apkg vers new_apkg.
    """
    dctx = zstandard.ZstdDecompressor()
    cctx = zstandard.ZstdCompressor()

    with tempfile.TemporaryDirectory() as temp_dir:
        print("📦 Extraction des bases de données...")
        old_db_path, _ = extract_and_decompress_db(old_apkg_path, temp_dir, "old")
        new_db_path, db_key = extract_and_decompress_db(new_apkg_path, temp_dir, "new")

        # Connexion SQLite à la nouvelle base et ATTACH de l'ancienne
        conn = sqlite3.connect(new_db_path)
        cursor = conn.cursor()
        cursor.execute(f"ATTACH DATABASE '{old_db_path}' AS old_db")

        print("🔄 Copie du journal de révisions (revlog)...")
        # Transfère l'historique complet des réponses/révisions
        cursor.execute("INSERT OR REPLACE INTO revlog SELECT * FROM old_db.revlog")

        print("🧠 Synchronisation de l'état des cartes (cards) & notes...")
        
        # 1. Correspondance exacte par ID de note (si les IDs sont conservés)
        cursor.execute("""
            UPDATE cards 
            SET type = old_c.type,
                queue = old_c.queue,
                due = old_c.due,
                ivl = old_c.ivl,
                factor = old_c.factor,
                reps = old_c.reps,
                lapses = old_c.lapses,
                left = old_c.left,
                odue = old_c.odue,
                odid = old_c.odid
            FROM old_db.cards AS old_c
            WHERE cards.id = old_c.id
        """)

        # 2. Correspondance de secours par nom du pays (sfld) au cas où les IDs ont changé
        cursor.execute("""
            UPDATE cards
            SET type = old_c.type,
                queue = old_c.queue,
                due = old_c.due,
                ivl = old_c.ivl,
                factor = old_c.factor,
                reps = old_c.reps,
                lapses = old_c.lapses,
                left = old_c.left,
                odue = old_c.odue,
                odid = old_c.odid
            FROM old_db.cards AS old_c
            JOIN old_db.notes AS old_n ON old_c.nid = old_n.id
            JOIN notes AS new_n ON new_n.sfld = old_n.sfld
            WHERE cards.nid = new_n.id AND cards.ord = old_c.ord
        """)

        print("⚙️ Restauration des configurations du paquet (decks & dconf)...")
        # Restaure les options de decks (intervalles, cartes/jour, etc.)
        try:
            cursor.execute("UPDATE dconf SET config = (SELECT config FROM old_db.dconf WHERE id = dconf.id) WHERE id IN (SELECT id FROM old_db.dconf)")
            cursor.execute("UPDATE decks SET conf = (SELECT conf FROM old_db.decks WHERE id = decks.id) WHERE id IN (SELECT id FROM old_db.decks)")
        except sqlite3.OperationalError:
            # Anki v3/v2 comptabilité selon le schéma de base
            pass

        conn.commit()
        conn.close()

        # Re-lecture du fichier SQLite modifié
        with open(new_db_path, 'rb') as f:
            updated_db_bytes = f.read()

        # Re-compression si la base était originellement compressée en ZStandard
        with zipfile.ZipFile(new_apkg_path, 'r') as z_in:
            raw_db_orig = z_in.read(db_key)
            is_compressed = len(raw_db_orig) > 4 and raw_db_orig[:4] == b'\x28\xb5\x2f\xfd'

        if is_compressed:
            final_db_bytes = cctx.compress(updated_db_bytes)
        else:
            final_db_bytes = updated_db_bytes

        print("💾 Reconstitution du fichier .apkg final...")
        with zipfile.ZipFile(new_apkg_path, 'r') as z_in, zipfile.ZipFile(output_apkg_path, 'w', zipfile.ZIP_DEFLATED) as z_out:
            for item in z_in.infolist():
                if item.filename == db_key:
                    z_out.writestr(db_key, final_db_bytes)
                else:
                    z_out.writestr(item, z_in.read(item.filename))

        print(f"✅ Fusion réussie ! Paquet final généré : {output_apkg_path}")

# ==============================================================================
# EXÉCUTION DU SCRIPT
# ==============================================================================
if __name__ == "__main__":
    OLD_DECK = "GeoQuiz_bak.apkg"
    NEW_DECK = "GeoQuiz_Personnalise(17).apkg"
    OUTPUT_DECK = "GeoQuiz_Final_Avec_Progression.apkg"

    if os.path.exists(OLD_DECK) and os.path.exists(NEW_DECK):
        merge_deck_progress(OLD_DECK, NEW_DECK, OUTPUT_DECK)
    else:
        print("❌ Assurez-vous d'indiquer les bons noms de fichiers pour OLD_DECK et NEW_DECK.")