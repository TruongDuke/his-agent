"""Drug catalog cho HIS — 50 thuốc phổ biến tại VN.

Nguồn:
  - Danh mục thuốc thiết yếu BYT QĐ 1165/QĐ-BYT 2022
  - Danh mục thuốc OTC phổ biến tại nhà thuốc Việt Nam
  - British National Formulary (BNF) — phân loại drug_class

Mỗi entry:
  - id:        slug kebab-case (dùng làm khóa lookup)
  - name:      tên hoạt chất (generic name) bằng tiếng Latin
  - vi:        tên thường gọi tiếng Việt (tùy chọn)
  - strength:  hàm lượng
  - form:      dạng bào chế (viên, gói, ống, tuýp...)
  - drug_class: nhóm dược lý (key dùng cho allergy cross-reactivity)
  - category:  nhóm dùng để group trên UI dropdown
  - max_daily_dose: liều tối đa/ngày (mg, hoặc None nếu không áp dụng)
"""
from __future__ import annotations

DRUG_CATALOG: list[dict] = [
    # ── Kháng sinh: Beta-lactam — Penicillin ──
    {"id": "amoxicillin-500", "name": "Amoxicillin", "vi": "Amoxicillin",
     "strength": "500mg", "form": "viên", "drug_class": "penicillin",
     "category": "Kháng sinh", "max_daily_dose_mg": 3000},
    {"id": "ampicillin-500", "name": "Ampicillin", "vi": "Ampicillin",
     "strength": "500mg", "form": "viên", "drug_class": "penicillin",
     "category": "Kháng sinh", "max_daily_dose_mg": 4000},
    {"id": "amoxicillin-clavulanate-625", "name": "Amoxicillin/Clavulanate",
     "vi": "Augmentin", "strength": "625mg", "form": "viên",
     "drug_class": "penicillin", "category": "Kháng sinh",
     "max_daily_dose_mg": 2625},

    # ── Kháng sinh: Beta-lactam — Cephalosporin ──
    {"id": "cefuroxime-500", "name": "Cefuroxime", "vi": "Cefuroxime",
     "strength": "500mg", "form": "viên", "drug_class": "cephalosporin",
     "category": "Kháng sinh", "max_daily_dose_mg": 1000},
    {"id": "cefixime-200", "name": "Cefixime", "vi": "Cefixime",
     "strength": "200mg", "form": "viên", "drug_class": "cephalosporin",
     "category": "Kháng sinh", "max_daily_dose_mg": 400},
    {"id": "ceftriaxone-1g", "name": "Ceftriaxone", "vi": "Ceftriaxone",
     "strength": "1g", "form": "ống tiêm", "drug_class": "cephalosporin",
     "category": "Kháng sinh", "max_daily_dose_mg": 4000},

    # ── Kháng sinh: Macrolide ──
    {"id": "azithromycin-500", "name": "Azithromycin", "vi": "Azithromycin",
     "strength": "500mg", "form": "viên", "drug_class": "macrolide",
     "category": "Kháng sinh", "max_daily_dose_mg": 500},
    {"id": "clarithromycin-500", "name": "Clarithromycin",
     "vi": "Clarithromycin", "strength": "500mg", "form": "viên",
     "drug_class": "macrolide", "category": "Kháng sinh",
     "max_daily_dose_mg": 1000},
    {"id": "erythromycin-500", "name": "Erythromycin", "vi": "Erythromycin",
     "strength": "500mg", "form": "viên", "drug_class": "macrolide",
     "category": "Kháng sinh", "max_daily_dose_mg": 2000},

    # ── Kháng sinh: Quinolone ──
    {"id": "ciprofloxacin-500", "name": "Ciprofloxacin", "vi": "Ciprofloxacin",
     "strength": "500mg", "form": "viên", "drug_class": "fluoroquinolone",
     "category": "Kháng sinh", "max_daily_dose_mg": 1500},
    {"id": "levofloxacin-500", "name": "Levofloxacin", "vi": "Levofloxacin",
     "strength": "500mg", "form": "viên", "drug_class": "fluoroquinolone",
     "category": "Kháng sinh", "max_daily_dose_mg": 750},

    # ── Kháng sinh: Khác ──
    {"id": "doxycycline-100", "name": "Doxycycline", "vi": "Doxycycline",
     "strength": "100mg", "form": "viên", "drug_class": "tetracycline",
     "category": "Kháng sinh", "max_daily_dose_mg": 200},
    {"id": "metronidazole-500", "name": "Metronidazole", "vi": "Metronidazole",
     "strength": "500mg", "form": "viên", "drug_class": "nitroimidazole",
     "category": "Kháng sinh", "max_daily_dose_mg": 2000},
    {"id": "clindamycin-300", "name": "Clindamycin", "vi": "Clindamycin",
     "strength": "300mg", "form": "viên", "drug_class": "lincosamide",
     "category": "Kháng sinh", "max_daily_dose_mg": 1800},
    {"id": "co-trimoxazole-960", "name": "Sulfamethoxazole/Trimethoprim",
     "vi": "Bactrim", "strength": "960mg", "form": "viên",
     "drug_class": "sulfonamide", "category": "Kháng sinh",
     "max_daily_dose_mg": 1920},

    # ── Giảm đau - hạ sốt ──
    {"id": "paracetamol-500", "name": "Paracetamol", "vi": "Paracetamol",
     "strength": "500mg", "form": "viên", "drug_class": "paracetamol",
     "category": "Giảm đau - hạ sốt", "max_daily_dose_mg": 4000},
    {"id": "paracetamol-325", "name": "Paracetamol", "vi": "Paracetamol",
     "strength": "325mg", "form": "viên", "drug_class": "paracetamol",
     "category": "Giảm đau - hạ sốt", "max_daily_dose_mg": 4000},

    # ── NSAID ──
    {"id": "ibuprofen-400", "name": "Ibuprofen", "vi": "Ibuprofen",
     "strength": "400mg", "form": "viên", "drug_class": "nsaid",
     "category": "NSAID", "max_daily_dose_mg": 2400},
    {"id": "diclofenac-50", "name": "Diclofenac", "vi": "Diclofenac",
     "strength": "50mg", "form": "viên", "drug_class": "nsaid",
     "category": "NSAID", "max_daily_dose_mg": 150},
    {"id": "naproxen-500", "name": "Naproxen", "vi": "Naproxen",
     "strength": "500mg", "form": "viên", "drug_class": "nsaid",
     "category": "NSAID", "max_daily_dose_mg": 1000},
    {"id": "meloxicam-15", "name": "Meloxicam", "vi": "Meloxicam",
     "strength": "15mg", "form": "viên", "drug_class": "nsaid",
     "category": "NSAID", "max_daily_dose_mg": 15},
    {"id": "celecoxib-200", "name": "Celecoxib", "vi": "Celecoxib",
     "strength": "200mg", "form": "viên", "drug_class": "nsaid-cox2",
     "category": "NSAID", "max_daily_dose_mg": 400},
    {"id": "aspirin-81", "name": "Aspirin", "vi": "Aspirin",
     "strength": "81mg", "form": "viên", "drug_class": "salicylate",
     "category": "Tim mạch", "max_daily_dose_mg": 325},

    # ── Tim mạch - Tăng huyết áp ──
    {"id": "amlodipine-5", "name": "Amlodipine", "vi": "Amlodipine",
     "strength": "5mg", "form": "viên", "drug_class": "ccb-dihydropyridine",
     "category": "Tim mạch", "max_daily_dose_mg": 10},
    {"id": "amlodipine-10", "name": "Amlodipine", "vi": "Amlodipine",
     "strength": "10mg", "form": "viên", "drug_class": "ccb-dihydropyridine",
     "category": "Tim mạch", "max_daily_dose_mg": 10},
    {"id": "losartan-50", "name": "Losartan", "vi": "Losartan",
     "strength": "50mg", "form": "viên", "drug_class": "arb",
     "category": "Tim mạch", "max_daily_dose_mg": 100},
    {"id": "telmisartan-40", "name": "Telmisartan", "vi": "Telmisartan",
     "strength": "40mg", "form": "viên", "drug_class": "arb",
     "category": "Tim mạch", "max_daily_dose_mg": 80},
    {"id": "enalapril-10", "name": "Enalapril", "vi": "Enalapril",
     "strength": "10mg", "form": "viên", "drug_class": "ace-inhibitor",
     "category": "Tim mạch", "max_daily_dose_mg": 40},
    {"id": "perindopril-5", "name": "Perindopril", "vi": "Perindopril",
     "strength": "5mg", "form": "viên", "drug_class": "ace-inhibitor",
     "category": "Tim mạch", "max_daily_dose_mg": 10},
    {"id": "bisoprolol-5", "name": "Bisoprolol", "vi": "Bisoprolol",
     "strength": "5mg", "form": "viên", "drug_class": "beta-blocker",
     "category": "Tim mạch", "max_daily_dose_mg": 20},
    {"id": "metoprolol-50", "name": "Metoprolol", "vi": "Metoprolol",
     "strength": "50mg", "form": "viên", "drug_class": "beta-blocker",
     "category": "Tim mạch", "max_daily_dose_mg": 200},
    {"id": "hydrochlorothiazide-25", "name": "Hydrochlorothiazide",
     "vi": "HCTZ", "strength": "25mg", "form": "viên",
     "drug_class": "thiazide", "category": "Tim mạch",
     "max_daily_dose_mg": 50},
    {"id": "furosemide-40", "name": "Furosemide", "vi": "Lasix",
     "strength": "40mg", "form": "viên", "drug_class": "loop-diuretic",
     "category": "Tim mạch", "max_daily_dose_mg": 600},
    {"id": "spironolactone-25", "name": "Spironolactone", "vi": "Spironolactone",
     "strength": "25mg", "form": "viên", "drug_class": "potassium-sparing-diuretic",
     "category": "Tim mạch", "max_daily_dose_mg": 100},

    # ── Đái tháo đường ──
    {"id": "metformin-500", "name": "Metformin", "vi": "Metformin",
     "strength": "500mg", "form": "viên", "drug_class": "biguanide",
     "category": "Đái tháo đường", "max_daily_dose_mg": 2550},
    {"id": "metformin-850", "name": "Metformin", "vi": "Metformin",
     "strength": "850mg", "form": "viên", "drug_class": "biguanide",
     "category": "Đái tháo đường", "max_daily_dose_mg": 2550},
    {"id": "gliclazide-30", "name": "Gliclazide MR", "vi": "Gliclazide",
     "strength": "30mg", "form": "viên", "drug_class": "sulfonylurea",
     "category": "Đái tháo đường", "max_daily_dose_mg": 120},
    {"id": "insulin-mix-30-70", "name": "Insulin Mixtard 30/70",
     "vi": "Mixtard", "strength": "100UI/mL", "form": "ống",
     "drug_class": "insulin", "category": "Đái tháo đường",
     "max_daily_dose_mg": None},

    # ── Tiêu hóa ──
    {"id": "omeprazole-20", "name": "Omeprazole", "vi": "Omeprazole",
     "strength": "20mg", "form": "viên", "drug_class": "ppi",
     "category": "Tiêu hóa", "max_daily_dose_mg": 80},
    {"id": "esomeprazole-40", "name": "Esomeprazole", "vi": "Nexium",
     "strength": "40mg", "form": "viên", "drug_class": "ppi",
     "category": "Tiêu hóa", "max_daily_dose_mg": 80},
    {"id": "domperidone-10", "name": "Domperidone", "vi": "Motilium",
     "strength": "10mg", "form": "viên", "drug_class": "prokinetic",
     "category": "Tiêu hóa", "max_daily_dose_mg": 30},
    {"id": "loperamide-2", "name": "Loperamide", "vi": "Loperamide",
     "strength": "2mg", "form": "viên", "drug_class": "antidiarrheal",
     "category": "Tiêu hóa", "max_daily_dose_mg": 16},
    {"id": "ors-vn", "name": "Oresol", "vi": "ORS",
     "strength": "27.9g", "form": "gói", "drug_class": "ors",
     "category": "Tiêu hóa", "max_daily_dose_mg": None},

    # ── Hô hấp ──
    {"id": "salbutamol-mdi", "name": "Salbutamol", "vi": "Ventolin",
     "strength": "100mcg/liều", "form": "bình xịt",
     "drug_class": "beta2-agonist", "category": "Hô hấp",
     "max_daily_dose_mg": None},
    {"id": "ambroxol-30", "name": "Ambroxol", "vi": "Ambroxol",
     "strength": "30mg", "form": "viên", "drug_class": "mucolytic",
     "category": "Hô hấp", "max_daily_dose_mg": 120},
    {"id": "loratadine-10", "name": "Loratadine", "vi": "Loratadine",
     "strength": "10mg", "form": "viên", "drug_class": "antihistamine-h1-2nd",
     "category": "Hô hấp", "max_daily_dose_mg": 10},
    {"id": "cetirizine-10", "name": "Cetirizine", "vi": "Cetirizine",
     "strength": "10mg", "form": "viên", "drug_class": "antihistamine-h1-2nd",
     "category": "Hô hấp", "max_daily_dose_mg": 10},

    # ── Khác ──
    {"id": "vitamin-c-500", "name": "Acid ascorbic", "vi": "Vitamin C",
     "strength": "500mg", "form": "viên", "drug_class": "vitamin",
     "category": "Vitamin - khoáng chất", "max_daily_dose_mg": 2000},
    {"id": "vitamin-b-complex", "name": "Vitamin B complex",
     "vi": "B-complex", "strength": "1 viên", "form": "viên",
     "drug_class": "vitamin", "category": "Vitamin - khoáng chất",
     "max_daily_dose_mg": None},
    {"id": "atorvastatin-20", "name": "Atorvastatin", "vi": "Atorvastatin",
     "strength": "20mg", "form": "viên", "drug_class": "statin",
     "category": "Rối loạn lipid", "max_daily_dose_mg": 80},
    {"id": "rosuvastatin-10", "name": "Rosuvastatin", "vi": "Rosuvastatin",
     "strength": "10mg", "form": "viên", "drug_class": "statin",
     "category": "Rối loạn lipid", "max_daily_dose_mg": 40},
    {"id": "warfarin-5", "name": "Warfarin", "vi": "Warfarin",
     "strength": "5mg", "form": "viên", "drug_class": "vka-anticoagulant",
     "category": "Chống đông", "max_daily_dose_mg": 10},
]


# ── Helpers ──
_BY_ID: dict[str, dict] = {d["id"]: d for d in DRUG_CATALOG}


def get_drug(drug_id: str) -> dict | None:
    return _BY_ID.get(drug_id)


def all_drugs() -> list[dict]:
    return list(DRUG_CATALOG)


def drugs_by_category() -> dict[str, list[dict]]:
    """Group thuốc theo category cho dropdown UI."""
    out: dict[str, list[dict]] = {}
    for d in DRUG_CATALOG:
        out.setdefault(d["category"], []).append(d)
    return out
