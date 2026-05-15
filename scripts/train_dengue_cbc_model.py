"""
Train dengue CBC prediction model.

Dataset: DengueFeverHematologicalDataset1523.csv
Features: PLT, WBC, HCT, HGB (+ neutrophils, lymphocytes, monocytes, MPV, RDW nếu có)
Target: Result (positive/negative)

Usage:
    python scripts/train_dengue_cbc_model.py

Output:
    tools/knowledge_base/dengue_cbc_model.joblib
    tools/knowledge_base/dengue_cbc_model_meta.json
"""

import json
import os
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import (
    classification_report, roc_auc_score,
    confusion_matrix, ConfusionMatrixDisplay
)
from sklearn.preprocessing import LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import numpy as np

# ── Config ──────────────────────────────────────────────────────────────────

DATASET_CANDIDATES = [
    "/Users/duc/Downloads/DengueFeverHematologicalDataset1523.csv",
    "/Users/duc/Downloads/Dengue Fever Hematological Dataset Clinical Insights for Improved Diagnosis and Patient Management/Dengue Fever Hematological Dataset.csv",
]

OUT_DIR = Path(__file__).parent.parent / "tools" / "knowledge_base"
MODEL_PATH = OUT_DIR / "dengue_cbc_model.joblib"
META_PATH  = OUT_DIR / "dengue_cbc_model_meta.json"

# Mapping: tên cột trong dataset → tên feature chuẩn của tool
COL_MAP = {
    "Total Platelet Count(/cumm)": "plt_raw",   # ÷1000 → K/mcL
    "Total WBC count(/cumm)":      "wbc_raw",   # ÷1000 → K/mcL
    "HCT(%)":                      "hct",
    "Hemoglobin(g/dl)":            "hgb",
    "Neutrophils(%)":              "neutrophils",
    "Lymphocytes(%)":              "lymphocytes",
    "Monocytes(%)":                "monocytes",
    "MPV(fl)":                     "mpv",
    "RDW-CV(%)":                   "rdw",
    "Result":                      "label",
}

# Features dùng để train (theo thứ tự — phải khớp lúc predict)
CORE_FEATURES    = ["plt", "wbc", "hct", "hgb"]
EXTRA_FEATURES   = ["neutrophils", "lymphocytes", "monocytes", "mpv", "rdw"]
ALL_FEATURES     = CORE_FEATURES + EXTRA_FEATURES


def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df.rename(columns={k: v for k, v in COL_MAP.items() if k in df.columns})

    # Convert units
    df["plt"] = df["plt_raw"] / 1000.0   # /cumm → K/mcL
    df["wbc"] = df["wbc_raw"] / 1000.0

    # Encode label
    df["label"] = (df["label"].str.strip().str.lower() == "positive").astype(int)

    return df


def build_feature_matrix(df: pd.DataFrame, features: list) -> pd.DataFrame:
    return df[features].copy()


def main():
    # ── Load data ──
    data_path = None
    for p in DATASET_CANDIDATES:
        if os.path.exists(p):
            data_path = p
            break
    if not data_path:
        print("[ERROR] Không tìm thấy dataset. Đặt file vào một trong các đường dẫn sau:")
        for p in DATASET_CANDIDATES:
            print(f"  {p}")
        sys.exit(1)

    print(f"[INFO] Loading dataset: {data_path}")
    df = load_data(data_path)
    print(f"[INFO] Samples: {len(df)} | Positive: {df['label'].sum()} | Negative: {(df['label']==0).sum()}")

    available_features = [f for f in ALL_FEATURES if f in df.columns]
    print(f"[INFO] Features available: {available_features}")

    X = build_feature_matrix(df, available_features)
    y = df["label"]

    # ── Train model ──
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    )

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_auc = cross_val_score(clf, X, y, cv=cv, scoring="roc_auc")
    cv_f1  = cross_val_score(clf, X, y, cv=cv, scoring="f1")
    print(f"\n[CV] ROC-AUC: {cv_auc.mean():.3f} ± {cv_auc.std():.3f}")
    print(f"[CV] F1:      {cv_f1.mean():.3f} ± {cv_f1.std():.3f}")

    # Final fit on all data
    clf.fit(X, y)

    # Feature importance
    fi = sorted(zip(available_features, clf.feature_importances_), key=lambda x: -x[1])
    print("\n[Feature Importance]")
    for feat, imp in fi:
        bar = "█" * int(imp * 40)
        print(f"  {feat:<15} {imp:.3f}  {bar}")

    # ── Save model ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    print(f"\n[SAVED] Model → {MODEL_PATH}")

    meta = {
        "features":       available_features,
        "cv_auc_mean":    round(float(cv_auc.mean()), 4),
        "cv_auc_std":     round(float(cv_auc.std()), 4),
        "cv_f1_mean":     round(float(cv_f1.mean()), 4),
        "n_samples":      len(df),
        "n_positive":     int(df["label"].sum()),
        "n_negative":     int((df["label"] == 0).sum()),
        "dataset":        str(data_path),
        "unit_note":      "plt và wbc đã được chia 1000 (từ /cumm → K/mcL) trước khi train",
    }
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(f"[SAVED] Meta  → {META_PATH}")
    print(f"\n✅ Done. ROC-AUC: {cv_auc.mean():.3f}")


if __name__ == "__main__":
    main()
