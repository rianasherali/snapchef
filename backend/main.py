import os
import json
import time
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from typing import List
from pydantic import BaseModel

load_dotenv()
MODEL = "gemini-3.8-flash"

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
            model=MODEL,
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

def call_gemini(contents, config, tries=4):
    for attempt in range(tries):
        try:
            return client.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
        except Exception as e:
            # Retry only when Google is busy
            if "503" in str(e) and attempt < tries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise

class RecipeRequest(BaseModel):
    ingredients: List[str]
    time_limit_minutes: int = 30
    restrictions: List[str] = []


@app.post("/generate-recipe")
def generate_recipe(req: RecipeRequest):
    restrictions_text = ", ".join(req.restrictions) if req.restrictions else "none"

    prompt = f"""
Create ONE recipe for a college student.

Ingredients they have: {", ".join(req.ingredients)}
Max total cooking time: {req.time_limit_minutes} minutes
Dietary restrictions (must follow strictly): {restrictions_text}

Rules:
- Use mostly the ingredients they have.
- You may add common pantry items (salt, oil, pepper) without listing them as missing.
- List anything else they need to buy under "missing_items".
- The recipe MUST follow every dietary restriction.

Return ONLY JSON in exactly this shape:
{{
  "title": "string",
  "total_time_minutes": 0,
  "ingredients_used": ["string"],
  "missing_items": ["string"],
  "steps": ["string"],
  "follows_restrictions": true
}}
"""

    try:
        response = call_gemini(
            prompt,
            types.GenerateContentConfig(response_mime_type="application/json"),
        )
        recipe = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {e}")

    return recipe
MEALDB = "https://www.themealdb.com/api/json/v1/1"

MEAT_WORDS = ["chicken", "beef", "pork", "lamb", "bacon", "ham", "sausage",
              "fish", "salmon", "tuna", "prawn", "shrimp", "anchov",
              "gelatin", "turkey", "mince", "goat"]
ANIMAL_PRODUCTS = ["egg", "milk", "cheese", "butter", "cream", "yogurt",
                   "yoghurt", "honey", "mayonnaise"]

BLOCKED = {
    "vegetarian": MEAT_WORDS,
    "vegan": MEAT_WORDS + ANIMAL_PRODUCTS,
    "halal": ["pork", "bacon", "ham", "wine", "beer", "rum", "gelatin", "lard"],
    "gluten-free": ["flour", "bread", "pasta", "noodle", "spaghetti", "soy sauce",
                    "couscous", "breadcrumb", "tortilla", "pastry"],
    "dairy-free": ["milk", "cheese", "butter", "cream", "yogurt", "yoghurt"],
    "nut-free": ["peanut", "almond", "walnut", "cashew", "pecan", "hazelnut", "pistachio"],
}
MEAT_CATEGORIES = {"Beef", "Chicken", "Lamb", "Pork", "Seafood", "Goat"}
PANTRY = ["salt", "pepper", "water", "oil"]


def get_meal_ingredients(meal):
    names = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip().lower()
        if name:
            names.append(name)
    return names


def breaks_restriction(meal, ings, restrictions):
    for r in restrictions:
        r = r.lower()
        if r in ("vegetarian", "vegan") and meal.get("strCategory") in MEAT_CATEGORIES:
            return True
        for word in BLOCKED.get(r, []):
            if any(word in ing for ing in ings):
                return True
    return False


@app.post("/find-recipes")
def find_recipes(req: RecipeRequest):
    mine = [i.lower().strip() for i in req.ingredients]

    # 1. Collect candidate meal IDs from TheMealDB
    ids = []
    for item in mine:
        try:
            r = requests.get(f"{MEALDB}/filter.php",
                             params={"i": item.replace(" ", "_")}, timeout=10)
            for m in (r.json().get("meals") or []):
                if m["idMeal"] not in ids:
                    ids.append(m["idMeal"])
        except Exception:
            continue
    ids = ids[:20]

    # 2. Get full details, filter, score
    results = []
    for meal_id in ids:
        try:
            r = requests.get(f"{MEALDB}/lookup.php", params={"i": meal_id}, timeout=10)
            meal = r.json()["meals"][0]
        except Exception:
            continue

        ings = get_meal_ingredients(meal)

        # Hard filter
        if breaks_restriction(meal, ings, req.restrictions):
            continue

        needed = [i for i in ings if not any(p in i for p in PANTRY)]
        if not needed:
            continue
        owned = [i for i in needed if any(m in i or i in m for m in mine)]
        missing = [i for i in needed if i not in owned]

        results.append({
            "title": meal["strMeal"],
            "category": meal.get("strCategory"),
            "image": meal.get("strMealThumb"),
            "percent_owned": round(100 * len(owned) / len(needed)),
            "missing_items": missing,
            "steps": meal.get("strInstructions"),
        })

    # 3. Rank: highest % of ingredients owned first
    results.sort(key=lambda x: x["percent_owned"], reverse=True)
    if not results:
        return {
            "recipes": [],
            "message": "No recipes matched. Try different ingredients, or check that they fit your dietary restrictions.",
        }
    return {"recipes": results[:5]}