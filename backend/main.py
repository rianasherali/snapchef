import os
import json
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

load_dotenv()

app = FastAPI(title="SnapChef")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/key-check")
def key_check():
    return {"key_loaded": bool(os.getenv("GEMINI_API_KEY"))}

@app.post("/detect-ingredients")
async def detect_ingredients(file: UploadFile = File(...)):
    image_bytes = await file.read()

    prompt = (
        "List every food ingredient visible in this photo. "
        "Return only a JSON array of short lowercase names, "
        'like ["eggs", "milk", "spinach"]. Ignore anything that is not food.'
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=file.content_type),
                prompt,
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        ingredients = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection failed: {e}")

    return {"ingredients": ingredients}