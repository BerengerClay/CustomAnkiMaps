import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_index():
    response = client.get("/")
    assert response.status_code == 200

def test_get_defaults():
    response = client.get("/api/defaults")
    assert response.status_code == 200
    data = response.json()
    assert "palette" in data

def test_get_countries():
    response = client.get("/api/countries")
    assert response.status_code == 200
    data = response.json()
    assert "countries" in data

def test_get_samples():
    response = client.get("/api/samples?country=FRA")
    assert response.status_code == 200
    data = response.json()
    assert "samples" in data

def test_generate_apkg():
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
            "zee_map": "#D95F5F",
            "zee_silhouette": "#D95F5F"
        }
    }
    response = client.post("/api/generate", json=payload)
    assert response.status_code == 200
