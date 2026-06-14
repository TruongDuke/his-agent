"""Allergy rules: aliases (free-text → drug_class) + cross-reactivity.

Nguồn:
  - Stockley's Drug Interactions, 13th ed (2022) — cross-reactivity tables
  - British National Formulary (BNF) 86 — drug class taxonomy
  - WHO Pharmacovigilance guidelines — ADR severity
  - QĐ 1088/QĐ-BYT 2013 — Hướng dẫn theo dõi phản ứng có hại của thuốc

Cấu trúc:
  ALLERGY_ALIASES: free-text bệnh nhân nói → list drug_class bị ảnh hưởng
    VD: "penicillin" → ["penicillin"] (cấm tất cả penicillin)
         "kháng sinh" → tất cả các nhóm kháng sinh (mơ hồ, warning)

  CROSS_REACTIVITY: (allergy_class, prescribed_class) → severity + rationale
    - "critical": cùng nhóm hoặc phản ứng chéo nguy hiểm — CHẶN
    - "warning":  có nguy cơ phản ứng chéo — cảnh báo, cho qua nếu bác sĩ confirm
"""
from __future__ import annotations

# ── ALLERGY ALIASES ─────────────────────────────────────────────
# Mapping từ free-text bệnh nhân nói → drug_class trong catalog.
# Match case-insensitive, không dấu (sẽ normalize trong code).
ALLERGY_ALIASES: dict[str, list[str]] = {
    # Kháng sinh — Penicillin
    "penicillin":      ["penicillin"],
    "pen":             ["penicillin"],
    "amoxicillin":     ["penicillin"],
    "ampicillin":      ["penicillin"],
    "augmentin":       ["penicillin"],

    # Cephalosporin
    "cephalosporin":   ["cephalosporin"],
    "cefuroxime":      ["cephalosporin"],
    "ceftriaxone":     ["cephalosporin"],
    "cefixime":        ["cephalosporin"],

    # Macrolide
    "macrolide":       ["macrolide"],
    "azithromycin":    ["macrolide"],
    "clarithromycin":  ["macrolide"],
    "erythromycin":    ["macrolide"],

    # Quinolone
    "quinolone":       ["fluoroquinolone"],
    "fluoroquinolone": ["fluoroquinolone"],
    "ciprofloxacin":   ["fluoroquinolone"],
    "levofloxacin":    ["fluoroquinolone"],

    # Sulfa
    "sulfa":           ["sulfonamide"],
    "sulfonamide":     ["sulfonamide"],
    "bactrim":         ["sulfonamide"],
    "co-trimoxazole":  ["sulfonamide"],
    "sulfamethoxazole":["sulfonamide"],

    # Tetracycline
    "tetracycline":    ["tetracycline"],
    "doxycycline":     ["tetracycline"],

    # NSAID
    "nsaid":           ["nsaid", "nsaid-cox2", "salicylate"],
    "ibuprofen":       ["nsaid"],
    "diclofenac":      ["nsaid"],
    "naproxen":        ["nsaid"],
    "aspirin":         ["salicylate", "nsaid"],
    "salicylate":      ["salicylate"],

    # Paracetamol — chỉ chính nó
    "paracetamol":     ["paracetamol"],
    "acetaminophen":   ["paracetamol"],

    # Tim mạch
    "ace-inhibitor":   ["ace-inhibitor"],
    "ace":             ["ace-inhibitor"],
    "enalapril":       ["ace-inhibitor"],
    "captopril":       ["ace-inhibitor"],
    "perindopril":     ["ace-inhibitor"],
    "arb":             ["arb"],
    "losartan":        ["arb"],
    "telmisartan":     ["arb"],
    "beta-blocker":    ["beta-blocker"],
    "bisoprolol":      ["beta-blocker"],
    "metoprolol":      ["beta-blocker"],

    # Statin
    "statin":          ["statin"],
    "atorvastatin":    ["statin"],
    "rosuvastatin":    ["statin"],

    # Tiêu hóa
    "ppi":             ["ppi"],
    "omeprazole":      ["ppi"],

    # Khác
    "warfarin":        ["vka-anticoagulant"],
    "insulin":         ["insulin"],
    "iod":             ["iodine-contrast"],  # Cản quang iod (không có trong catalog hiện tại)
    "iodine":          ["iodine-contrast"],
    "cản quang":       ["iodine-contrast"],
}


# ── CROSS-REACTIVITY ───────────────────────────────────────────
# Key: (allergy_class_BN, prescribed_drug_class)
# Value: (severity, message_vi, alternative_drug_classes_to_suggest)
#
# Lưu ý: rule cùng class được tự sinh trong code (allergy_class == prescribed_class → critical),
# không cần hardcode ở đây. File này CHỈ chứa cross-class.

CROSS_REACTIVITY: dict[tuple[str, str], dict] = {
    # ── Beta-lactam cross-reactivity ──
    # Penicillin → Cephalosporin: nguy cơ phản ứng chéo 5-10%
    # (Stockley's 13th ed, p. 234)
    ("penicillin", "cephalosporin"): {
        "severity": "warning",
        "message": "BN dị ứng Penicillin — Cephalosporin có nguy cơ phản ứng chéo 5-10% (cùng nhóm β-lactam). Cân nhắc test da hoặc đổi nhóm khác.",
        "alternatives": ["macrolide", "fluoroquinolone", "tetracycline", "lincosamide"],
    },
    ("cephalosporin", "penicillin"): {
        "severity": "warning",
        "message": "BN dị ứng Cephalosporin — Penicillin có nguy cơ phản ứng chéo (cùng nhóm β-lactam).",
        "alternatives": ["macrolide", "fluoroquinolone", "tetracycline", "lincosamide"],
    },

    # ── NSAID cross-reactivity ──
    # NSAID → Aspirin và ngược lại: AERD (aspirin-exacerbated respiratory disease)
    ("nsaid", "salicylate"): {
        "severity": "critical",
        "message": "BN dị ứng NSAID — Aspirin (salicylate) có nguy cơ AERD (hen do aspirin), có thể gây co thắt phế quản nặng.",
        "alternatives": ["paracetamol"],
    },
    ("salicylate", "nsaid"): {
        "severity": "critical",
        "message": "BN dị ứng Aspirin — NSAID khác có nguy cơ AERD.",
        "alternatives": ["paracetamol"],
    },
    # COX-2 selective an toàn hơn nhưng vẫn warning
    ("nsaid", "nsaid-cox2"): {
        "severity": "warning",
        "message": "BN dị ứng NSAID thông thường — COX-2 selective (Celecoxib) có nguy cơ phản ứng chéo ~7%. Có thể thử với theo dõi.",
        "alternatives": ["paracetamol"],
    },
    ("salicylate", "nsaid-cox2"): {
        "severity": "warning",
        "message": "BN dị ứng Aspirin — COX-2 selective có nguy cơ phản ứng chéo thấp hơn (~5%) nhưng vẫn có thể xảy ra.",
        "alternatives": ["paracetamol"],
    },

    # ── Sulfonamide cross-reactivity ──
    # Sulfa kháng sinh ↔ Sulfa không kháng sinh (HCTZ, Furosemide):
    # Tranh cãi nhưng FDA labeling vẫn cảnh báo
    ("sulfonamide", "thiazide"): {
        "severity": "warning",
        "message": "BN dị ứng Sulfonamide kháng sinh — Thiazide (HCTZ) chứa nhóm sulfa, nguy cơ phản ứng chéo thấp nhưng có ghi nhận.",
        "alternatives": ["ccb-dihydropyridine", "arb", "ace-inhibitor"],
    },
    ("sulfonamide", "loop-diuretic"): {
        "severity": "warning",
        "message": "BN dị ứng Sulfonamide kháng sinh — Furosemide chứa nhóm sulfa, có ghi nhận phản ứng chéo.",
        "alternatives": ["potassium-sparing-diuretic"],
    },

    # ── ACE-inhibitor → ARB ──
    # Phù mạch do ACE-I, ARB thường an toàn nhưng warning nhẹ
    ("ace-inhibitor", "arb"): {
        "severity": "warning",
        "message": "BN dị ứng ACE-inhibitor — ARB là lựa chọn thay thế phổ biến, nhưng cũng có nguy cơ phù mạch (thấp hơn ACE-I).",
        "alternatives": ["ccb-dihydropyridine", "beta-blocker"],
    },

    # ── Macrolide cross-class ──
    ("macrolide", "macrolide"): {  # placeholder — handled by same-class rule, ghi để rõ ràng
        "severity": "critical",
        "message": "BN dị ứng Macrolide — không nên kê thuốc cùng nhóm.",
        "alternatives": ["fluoroquinolone", "tetracycline", "lincosamide"],
    },
}


# ── HELPERS ─────────────────────────────────────────────────────
def _normalize(s: str) -> str:
    """Lowercase + strip dấu tiếng Việt + bỏ khoảng trắng thừa."""
    import unicodedata
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip().lower()


def match_allergy_classes(allergy_text: str) -> list[str]:
    """Free-text từ BN ("Penicillin", "Sulfa", "Bactrim") → list drug_class.

    Trả về list rỗng nếu không match (warning UI để bác sĩ verify thủ công).
    """
    norm = _normalize(allergy_text)
    # Exact match trước
    if norm in ALLERGY_ALIASES:
        return ALLERGY_ALIASES[norm]
    # Substring match (vd: "dị ứng penicillin")
    matched: list[str] = []
    for alias, classes in ALLERGY_ALIASES.items():
        if alias in norm:
            for c in classes:
                if c not in matched:
                    matched.append(c)
    return matched


def check_cross_reactivity(allergy_class: str, prescribed_class: str) -> dict | None:
    """Trả về dict cảnh báo, hoặc None nếu không có rule."""
    # Same class — luôn critical
    if allergy_class == prescribed_class:
        return {
            "severity": "critical",
            "message": f"BN dị ứng nhóm {allergy_class} — thuốc kê CÙNG nhóm dược lý, KHÔNG được kê.",
            "alternatives": [],
        }
    return CROSS_REACTIVITY.get((allergy_class, prescribed_class))
