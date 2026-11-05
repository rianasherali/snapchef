import { useState } from "react";

const API = "http://127.0.0.1:8002";

export default function App() {
  const [file, setFile] = useState(null);
  const [ingredients, setIngredients] = useState([]);
  const [newItem, setNewItem] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function detect() {
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API}/detect-ingredients`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Detection failed");
      setIngredients(data.ingredients);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  }

  function removeItem(item) {
    setIngredients(ingredients.filter((i) => i !== item));
  }

  function addItem() {
    const v = newItem.trim().toLowerCase();
    if (v && !ingredients.includes(v)) setIngredients([...ingredients, v]);
    setNewItem("");
  }

  return (
    <div style={{ maxWidth: 500, margin: "40px auto", fontFamily: "sans-serif" }}>
      <h1>SnapChef</h1>

      <h3>1. Upload a photo</h3>
      <input
        type="file"
        accept="image/*"
        onChange={(e) => setFile(e.target.files[0])}
      />
      {file && (
        <div>
          <img
            src={URL.createObjectURL(file)}
            alt="preview"
            style={{ width: "100%", marginTop: 10, borderRadius: 8 }}
          />
        </div>
      )}
      <button onClick={detect} disabled={!file || loading} style={{ marginTop: 10 }}>
        {loading ? "Detecting..." : "Detect ingredients"}
      </button>
      {error && <p style={{ color: "red" }}>{error}</p>}

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
            placeholder="add an ingredient"
          />
          <button onClick={addItem}>Add</button>
        </>
      )}
    </div>
  );
}