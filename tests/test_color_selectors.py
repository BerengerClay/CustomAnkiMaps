import os
import pytest
from app.apkg_processor import APKGProcessor, DEFAULT_COLOR_PALETTE, apply_color_transform

SNAPSHOTS_DIR = os.path.join(os.path.dirname(__file__), "snapshots")
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

COLOR_TEST_SPECS = [
    {
        "key": "water",
        "label": "Couleur de l'Eau",
        "test_color": "#00FFFF",  # Cyan
        "country": "FRA",
        "tab": "globe"
    },
    {
        "key": "other_countries",
        "label": "Autres Pays",
        "test_color": "#FF00FF",  # Magenta
        "country": "FRA",
        "tab": "globe"
    },
    {
        "key": "target_country",
        "label": "Pays Sélectionné",
        "test_color": "#00FF00",  # Lime Green
        "country": "FRA",
        "tab": "globe"
    },
    {
        "key": "country_borders",
        "label": "Frontières des Pays",
        "test_color": "#FF0000",  # Red
        "country": "FRA",
        "tab": "zoomed"
    },
    {
        "key": "silhouette",
        "label": "Couleur de la Silhouette",
        "test_color": "#9900FF",  # Purple
        "country": "FRA",
        "tab": "silhouette"
    },
    {
        "key": "capital_map",
        "label": "Capitale sur Cartes",
        "test_color": "#FF9900",  # Orange
        "country": "FRA",
        "tab": "zoomed"
    },
    {
        "key": "capital_silhouette",
        "label": "Capitale sur Silhouettes",
        "test_color": "#FF0066",  # Hot Pink
        "country": "FRA",
        "tab": "capitale"
    },
    {
        "key": "grid_lines",
        "label": "Lignes de Quadrillage",
        "test_color": "#0033FF",  # Deep Blue
        "country": "FRA",
        "tab": "globe"
    },
    {
        "key": "zee_map",
        "label": "Frontières Maritimes ZEE (Cartes)",
        "test_color": "#FFFF00",  # Yellow
        "country": "CPV",
        "tab": "globe"
    },
    {
        "key": "zee_silhouette",
        "label": "Frontières Maritimes ZEE (Silhouettes)",
        "test_color": "#00FFCC",  # Cyan
        "country": "CPV",
        "tab": "silhouette"
    }
]

@pytest.fixture(scope="module")
def processor():
    apkg_path = os.environ.get("APKG_PATH", "GeoQuiz.apkg")
    if not os.path.exists(apkg_path):
        alt_path = os.path.join(os.path.dirname(__file__), "..", "GeoQuiz.apkg")
        if os.path.exists(alt_path):
            apkg_path = alt_path
    return APKGProcessor(apkg_path)

@pytest.mark.parametrize("spec", COLOR_TEST_SPECS, ids=lambda s: s["key"])
def test_color_selectors(processor, spec):
    key = spec["key"]
    test_color = spec["test_color"]
    country = spec["country"]
    tab = spec["tab"]

    samples = processor.get_samples(country)
    sample = next((s for s in samples if s['id'] == tab), samples[0])

    test_colors = { **DEFAULT_COLOR_PALETTE, key: test_color }
    is_sil = (tab in ['silhouette', 'capitale'])
    actual_svg = apply_color_transform(sample['svg'], test_colors, is_silhouette=is_sil)

    assert test_color.upper() in actual_svg.upper(), f"Test color {test_color} for '{key}' not found in transformed SVG!"

    snapshot_path = os.path.join(SNAPSHOTS_DIR, f"test_{key}.svg")
    update_snapshots = os.environ.get("UPDATE_SNAPSHOTS", "").lower() in ("1", "true", "yes")

    if not os.path.exists(snapshot_path) or update_snapshots:
        with open(snapshot_path, "w", encoding="utf-8") as f:
            f.write(actual_svg)

    with open(snapshot_path, "r", encoding="utf-8") as f:
        expected_svg = f.read()

    assert actual_svg == expected_svg, (
        f"Snapshot mismatch for '{key}'!\n"
        f"Actual generated SVG does not match reference SVG snapshot '{snapshot_path}'."
    )
