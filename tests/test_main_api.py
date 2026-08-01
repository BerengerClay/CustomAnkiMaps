import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)

def test_get_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Anki Map Customizer" in response.text

def test_get_defaults(client):
    response = client.get("/api/defaults")
    assert response.status_code == 200
    data = response.json()
    assert "palette" in data
    assert "original_colors" in data
    assert data["palette"]["water"] == "#FFFFFF"

def test_get_countries(client):
    response = client.get("/api/countries")
    assert response.status_code == 200
    data = response.json()
    assert "countries" in data
    assert len(data["countries"]) > 0

def test_get_samples(client):
    response = client.get("/api/samples?country=FRA")
    assert response.status_code == 200
    data = response.json()
    assert "samples" in data
    assert len(data["samples"]) > 0

def test_generate_apkg(client):
    payload = {
        "colors": {
            "water": "#FFFFFF",
            "other_countries": "#CCCCCC",
            "target_country": "#59A353",
            "country_borders": "#FFFFFF",
            "silhouette": "#CCCCCC",
            "capital_map": "#000000",
            "capital_silhouette": "#000000",
            "grid_lines": "#D8D8D8",
            "zee_border": "#D95F5F"
        }
    }
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert len(response.content) > 0
