import { useState } from "react";

const API = "http://127.0.0.1:8002";
const RESTRICTIONS = ["vegetarian", "vegan", "halal", "gluten-free", "dairy-free", "nut-free"];

export default function App() {
  const [file, setFile] = useState(null);
  const [ingredients, setIngredients] = useState([]);
  const [newItem, setNewItem] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [detectError, setDetectError] = useState("");

  const [timeLimit, setTimeLimit] = useState(30);
  const [restrictions, setRestrictions] = useState([]);

  const [recipes, setRecipes] = useState(null);
  const [message, setMessage] = useState("");
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState("");

  async function detect() {
    if (!file) return;
    setDetecting(true);
    setDetectError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/detect-ingredients`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Detection failed");
      setIngredients(data.ingredients);
    } catch (e) {
      setDetectError(e.message);
    }
    setDetecting(false);
  }

  function removeItem(item) {
    setIngredients(ingredients.filter((i) => i !== item));
  }

  function addItem() {
    const v = newItem.trim().toLowerCase();
    if (v && !ingredients.includes(v)) setIngredients([...ingredients, v]);
    setNewItem("");
  }

  function toggleRestriction(r) {
    setRestrictions(
      restrictions.includes(r) ? restrictions.filter((x) => x !== r) : [...restrictions, r]
    );
  }

  async function generate() {
    setGenerating(true);
    setGenError("");
    setRecipes(null);
    setMessage("");
    try {
      const res = await fetch(`${API}/generate-recipes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ingredients,
          time_limit_minutes: Number(timeLimit),
          restrictions,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Recipe generation failed");
      setRecipes(data.recipes);
      setMessage(data.message || "");
    } catch (e) {
      setGenError(e.message);
    }
    setGenerating(false);
  }

  const box = { border: "1px solid #ccc", borderRadius: 8, padding: 14, marginBottom: 16 };

  return (
    <div style={{ maxWidth: 600, margin: "40px auto", fontFamily: "sans-serif", padding: "0 12px" }}>
      <h1>SnapChef</h1>

      {/* 1. Upload */}
      <h3>1. Upload a photo</h3>
      <input type="file" accept="image/*" onChange={(e) => setFile(e.target.files[0])} />
      {file && (
        <img
          src={URL.createObjectURL(file)}
          alt="preview"
          style={{ width: "100%", marginTop: 10, borderRadius: 8 }}
        />
      )}
      <div>
        <button onClick={detect} disabled={!file || detecting} style={{ marginTop: 10 }}>
          {detecting ? "Detecting... (can take up to 30 seconds)" : "Detect ingredients"}
        </button>
      </div>
      {detectError && <p style={{ color: "red" }}>{detectError}</p>}

      {/* 2. Confirm ingredients */}
      {ingredients.length > 0 && (
        <>
          <h3>2. Confirm your ingredients</h3>
          <ul>
            {ingredients.map((i) => (
              <li key={i}>
                {i} <button onClick={() => removeItem(i)}>remove</button>
              </li>
            ))}
          </ul>
          <input
            value={newItem}
            onChange={(e) => setNewItem(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addItem()}
            placeholder="add an ingredient"
          />
          <button onClick={addItem}>Add</button>

          {/* 3. Preferences */}
          <h3>3. Your preferences</h3>
          <div style={box}>
            <label>
              Time to cook (minutes):{" "}
              <input
                type="number"
                min="5"
                max="240"
                value={timeLimit}
                onChange={(e) => setTimeLimit(e.target.value)}
                style={{ width: 70 }}
              />
            </label>
            <p style={{ marginBottom: 4 }}>Dietary restrictions:</p>
            {RESTRICTIONS.map((r) => (
              <label key={r} style={{ display: "block" }}>
                <input
                  type="checkbox"
                  checked={restrictions.includes(r)}
                  onChange={() => toggleRestriction(r)}
                />{" "}
                {r}
              </label>
            ))}
          </div>

          <button onClick={generate} disabled={generating || ingredients.length === 0}>
            {generating ? "Generating... (can take up to 30 seconds)" : "Get recipes"}
          </button>
          {genError && <p style={{ color: "red" }}>{genError}</p>}
        </>
      )}

      {/* 4. Results */}
      {message && <p>{message}</p>}
      {recipes && recipes.length > 0 && <h3>4. Your recipes</h3>}
      {recipes &&
        recipes.map((r) => (
          <div key={r.title} style={box}>
            <h3 style={{ marginTop: 0 }}>{r.title}</h3>
            <p>
              {r.total_time_minutes} min · you own {r.percent_owned}% of the ingredients · score{" "}
              {r.score}
            </p>

            {r.missing_items.length > 0 ? (
              <p style={{ color: "#b45309" }}>
                <b>Missing:</b> {r.missing_items.join(", ")}
              </p>
            ) : (
              <p style={{ color: "green" }}>You have everything!</p>
            )}

            <b>Ingredients</b>
            <ul>
              {r.ingredients.map((i) => (
                <li key={i.name}>
                  {i.name} ({Math.round(i.grams)} g)
                </li>
              ))}
            </ul>

            <b>Steps</b>
            <ol>
              {r.steps.map((s, idx) => (
                <li key={idx}>{s}</li>
              ))}
            </ol>

            <b>Nutrition (estimate)</b>
            {r.nutrition ? (
              <p>
                {r.nutrition.calories} kcal · {r.nutrition.protein_g} g protein ·{" "}
                {r.nutrition.carbs_g} g carbs · {r.nutrition.fat_g} g fat
              </p>
            ) : (
              <p>Nutrition unavailable</p>
            )}

            <b>Allergens (from Open Food Facts)</b>
            <p>{r.allergens && r.allergens.length > 0 ? r.allergens.join(", ") : "None found"}</p>
          </div>
        ))}
    </div>
  );
}