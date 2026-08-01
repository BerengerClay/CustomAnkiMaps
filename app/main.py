import os
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Dict, Optional

from app.apkg_processor import APKGProcessor, DEFAULT_COLOR_PALETTE, ORIGINAL_SVG_COLORS

APKG_PATH = os.environ.get("APKG_PATH", "GeoQuiz.apkg")

if not os.path.exists(APKG_PATH):
    alt_path = os.path.join(os.path.dirname(__file__), "..", "GeoQuiz.apkg")
    if os.path.exists(alt_path):
        APKG_PATH = alt_path

processor = APKGProcessor(APKG_PATH)

app = FastAPI(
    title="Anki Map Color Customizer",
    description="Personnalisation des couleurs des cartes Anki pour le paquet GeoQuiz",
    version="1.2.0"
)

# Mount static files directory and set up Jinja2 templates
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=static_dir)

class ColorMapRequest(BaseModel):
    colors: Dict[str, str]

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "umami_script_url": os.environ.get("UMAMI_SCRIPT_URL", "https://stats.beclay.fr/script.js").strip(),
            "umami_website_id": os.environ.get("UMAMI_WEBSITE_ID", "").strip(),
        }
    )

@app.get("/api/defaults")
async def get_defaults():
    return JSONResponse(content={
        "palette": DEFAULT_COLOR_PALETTE,
        "original_colors": ORIGINAL_SVG_COLORS
    })

@app.get("/api/countries")
async def get_countries():
    try:
        countries = processor.get_countries()
        return JSONResponse(content={"countries": countries})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la récupération des pays: {str(e)}")

@app.get("/api/samples")
async def get_samples(country: Optional[str] = Query(None, description="Code ISO/prefix du pays")):
    try:
        samples = processor.get_samples(country_code=country)
        return JSONResponse(content={"samples": samples})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur d'extraction des cartes: {str(e)}")

import asyncio
import json
import uuid
from fastapi.responses import HTMLResponse, Response, JSONResponse, StreamingResponse

generated_jobs: Dict[str, bytes] = {}

@app.post("/api/generate-stream")
async def generate_stream(req: ColorMapRequest):
    if not req.colors:
        raise HTTPException(status_code=400, detail="Aucun dictionnaire de couleurs fourni.")

    async def event_generator():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def progress_cb(current, total):
            percent = int((current / total) * 100)
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "progress", "percent": percent, "current": current, "total": total})

        job_id = str(uuid.uuid4())

        def run_processing():
            try:
                apkg_bytes = processor.process_and_repack(req.colors, progress_callback=progress_cb)
                generated_jobs[job_id] = apkg_bytes
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "complete", "job_id": job_id})
            except Exception as ex:
                loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(ex)})

        asyncio.create_task(asyncio.to_thread(run_processing))

        while True:
            item = await queue.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/download/{job_id}")
async def download_job(job_id: str):
    if job_id not in generated_jobs:
        raise HTTPException(status_code=404, detail="Fichier expiré ou non trouvé.")
    
    apkg_bytes = generated_jobs.pop(job_id)
    filename = "GeoQuiz_Personnalise.apkg"
    return Response(
        content=apkg_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )

@app.post("/api/generate")
async def generate_custom_apkg(req: ColorMapRequest):
    if not req.colors:
        raise HTTPException(status_code=400, detail="Aucun dictionnaire de couleurs fourni.")

    try:
        apkg_bytes = processor.process_and_repack(req.colors)
        filename = "GeoQuiz_Personnalise.apkg"
        return Response(
            content=apkg_bytes,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de génération du paquet Anki: {str(e)}")
