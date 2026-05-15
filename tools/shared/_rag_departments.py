"""
RAG-based department retrieval using sentence-transformers + cosine similarity.
Lazy-loads on first call; subsequent calls use cached embeddings.
"""
import os
import json
import numpy as np
from pathlib import Path
from typing import Optional

os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TF", "0")

_KNOWLEDGE_FILE = Path(__file__).parent.parent / "knowledge_base" / "symptoms_departments.json"
_EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
_TOP_K = 10
_THRESHOLD = 0.30

_model = None
_documents: list[dict] = []
_embeddings: Optional[np.ndarray] = None
_initialized = False


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_EMBEDDING_MODEL)
    return _model


def _build_documents(data: list[dict]) -> list[dict]:
    docs = []
    for dept in data:
        code = dept.get("code", dept["department"])
        name = dept["department"]
        desc = dept.get("description", "")
        symptoms = dept.get("symptoms", [])
        keywords = dept.get("keywords", [])

        # Overview document
        overview = (
            f"{name}: {desc}\n"
            f"Các triệu chứng: {', '.join(symptoms)}\n"
            f"Từ khóa: {', '.join(keywords)}"
        )
        docs.append({"text": overview, "code": code, "name": name, "type": "overview"})

        # One document per symptom phrase
        for symptom in symptoms:
            docs.append({
                "text": f"Triệu chứng: {symptom}. Khoa khám phù hợp: {name}.",
                "code": code,
                "name": name,
                "type": "symptom",
            })
    return docs


def _ensure_loaded():
    global _documents, _embeddings, _initialized
    if _initialized:
        return
    if not _KNOWLEDGE_FILE.exists():
        return
    with open(_KNOWLEDGE_FILE, encoding="utf-8") as f:
        data = json.load(f)
    _documents = _build_documents(data)
    model = _get_model()
    texts = [d["text"] for d in _documents]
    _embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    _initialized = True


def retrieve_departments(query: str, top_k: int = 3) -> list[dict]:
    """
    Returns list of dicts: {code, name, score} sorted by relevance desc.
    Uses weighted-voting: sums cosine scores per department across top-K docs.
    """
    _ensure_loaded()
    if _embeddings is None or not _documents:
        return []

    model = _get_model()
    q_emb = model.encode(query, convert_to_numpy=True, normalize_embeddings=True)
    sims = np.dot(_embeddings, q_emb)

    top_indices = np.argsort(sims)[::-1][:_TOP_K]
    dept_scores: dict[str, dict] = {}

    for idx in top_indices:
        sim = float(sims[idx])
        if sim < _THRESHOLD:
            continue
        doc = _documents[idx]
        code = doc["code"]
        if code not in dept_scores:
            dept_scores[code] = {"code": code, "name": doc["name"], "score": 0.0}
        dept_scores[code]["score"] += sim

    ranked = sorted(dept_scores.values(), key=lambda d: d["score"], reverse=True)
    return ranked[:top_k]
