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

@app.get("/health")
def health():
    return {"status": "ok"}


#detect ingredients (computer vision)
@app.post("/detect-ingredients")
async def detect_ingredients(file: UploadFile = File(...)):
    image_bytes = await file.read()
    prompt = (
        "List every food ingredient visible in this photo, using simple generic "
        "names (say 'cheese' not 'shredded cheese'). "
        "Return only a JSON array of short lowercase names, "
        'like ["eggs", "milk", "spinach"]. Ignore anything that is not food.'
    )

    try:
        response = call_gemini(
            [
                types.Part.from_bytes(data=image_bytes, mime_type=file.content_type),
                prompt,
            ],
            types.GenerateContentConfig(response_mime_type="application/json"),
        )
        ingredients = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection failed: {e}")
    return {"ingredients": ingredients}


#restriction filter
class RecipeRequest(BaseModel):
    ingredients: List[str]
    time_limit_minutes: int = 30
    restrictions: List[str] = []

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
PANTRY = {"salt", "pepper", "black pepper", "water", "oil", "olive oil",
          "vegetable oil", "cooking oil", "sugar"}

def is_pantry(name):
    return name in PANTRY

def breaks_restriction(ingredient_names, restrictions):
    for r in restrictions:
        for word in BLOCKED.get(r.lower(), []):
            if any(word in ing for ing in ingredient_names):
                return True
    return False


#open food facts for nutrition/allergen info (external API)
OFF_URL = "https://world.openfoodfacts.org/cgi/search.pl"
off_cache = {}  # ingredient name -> nutrition/allergen info (simple caching)


def lookup_off(name):
    """Looks up one ingredient. Returns per-100g nutrition and allergens."""
    if name in off_cache:
        return off_cache[name]

    info = {"kcal": None, "protein": None, "carbs": None, "fat": None, "allergens": []}
    try:
        r = requests.get(
            OFF_URL,
            params={
                "search_terms": name,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 3,
                "fields": "product_name,nutriments,allergens_tags",
            },
            headers={"User-Agent": "SnapChef/1.0 (student capstone project)"},
            timeout=8,
        )
        products = r.json().get("products", [])

        def avg(key):
            vals = [p["nutriments"][key] for p in products
                    if isinstance(p.get("nutriments", {}).get(key), (int, float))]
            return sum(vals) / len(vals) if vals else None

        info["kcal"] = avg("energy-kcal_100g")
        info["protein"] = avg("proteins_100g")
        info["carbs"] = avg("carbohydrates_100g")
        info["fat"] = avg("fat_100g")

        #keep allergen only if most matching products list it
        counts = {}
        for p in products:
            for tag in p.get("allergens_tags", []):
                counts[tag] = counts.get(tag, 0) + 1
        need = 2 if len(products) >= 2 else 1
        info["allergens"] = [t.replace("en:", "") for t, c in counts.items() if c >= need]

        off_cache[name] = info
    except Exception:
        pass  #leave empty values so it still works

    return info


def add_nutrition(recipe):
    totals = {"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}
    allergens = set()
    found = 0

    for ing in recipe["ingredients"]:
        if is_pantry(ing["name"]):
            continue
        info = lookup_off(ing["name"])
        allergens.update(info["allergens"])
        if info["kcal"] is None:
            continue
        found += 1
        factor = ing["grams"] / 100
        totals["calories"] += info["kcal"] * factor
        totals["protein_g"] += (info["protein"] or 0) * factor
        totals["carbs_g"] += (info["carbs"] or 0) * factor
        totals["fat_g"] += (info["fat"] or 0) * factor

    recipe["nutrition"] = {k: round(v) for k, v in totals.items()} if found else None
    recipe["allergens"] = sorted(allergens)


#recipe generation (AI/NLP and ranking)
@app.post("/generate-recipes")
def generate_recipes(req: RecipeRequest):
    mine = [i.lower().strip() for i in req.ingredients]
    restrictions_text = ", ".join(req.restrictions) if req.restrictions else "none"

    prompt = f"""
Create 5 different simple recipes for a college student. Each recipe serves 1 person.

Ingredients they have: {", ".join(mine)}
Max total cooking time: {req.time_limit_minutes} minutes
Dietary restrictions (must follow strictly): {restrictions_text}

Rules:
- Use mostly the ingredients they have.
- Every recipe MUST follow every dietary restriction.
- Use simple generic ingredient names (say "cheese", not "shredded cheddar").
- Give every ingredient an amount in grams (including oil and water).
- The 5 recipes must be different from each other.

Return ONLY a JSON array in exactly this shape:
[
  {{
    "title": "string",
    "total_time_minutes": 0,
    "ingredients": [{{"name": "string", "grams": 0}}],
    "steps": ["string"]
  }}
]
"""

    try:
        response = call_gemini(
            prompt,
            types.GenerateContentConfig(response_mime_type="application/json"),
        )
        candidates = json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Recipe generation failed: {e}")

    limit = max(req.time_limit_minutes, 1)
    scored = []

    for c in candidates:
        try:
            names = [i["name"].lower().strip() for i in c["ingredients"]]
            time_min = int(c["total_time_minutes"])
            for i in c["ingredients"]:
                i["grams"] = float(i["grams"])
        except Exception:
            continue  #skip badly formed recipes

        #filters 
        if breaks_restriction(names, req.restrictions):
            continue
        if time_min > limit:
            continue

        #score = % of ingredients owned + up to 20 points for short time
        needed = [n for n in names if not is_pantry(n)]
        owned = [n for n in needed if any(m in n or n in m for m in mine)]
        missing = [n for n in needed if n not in owned]
        percent_owned = round(100 * len(owned) / len(needed)) if needed else 100
        bonus = round(20 * (limit - time_min) / limit)

        scored.append({
            "title": c["title"],
            "total_time_minutes": time_min,
            "ingredients": c["ingredients"],
            "steps": c["steps"],
            "percent_owned": percent_owned,
            "missing_items": missing,
            "score": percent_owned + bonus,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:3]

    #add real nutrition and allergens (top 3 recipes bc API limtis)
    for r in top:
        add_nutrition(r)

    if not top:
        return {
            "recipes": [],
            "message": "No recipes matched. Try a longer time limit or different ingredients.",
        }
    return {"recipes": top}