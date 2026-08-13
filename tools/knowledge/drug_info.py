"""Tra cứu thông tin thuốc từ NCBI (StatPearls + PubMed) — CÓ DẪN NGUỒN.

Bản tối giản: gọi NCBI E-utilities lấy nguồn + abstract làm ngữ cảnh, rồi LLM
tổng hợp câu trả lời TIẾNG VIỆT và dẫn nguồn (markdown link ở cuối câu).
Giới hạn ngữ nghĩa quanh danh mục 52 thuốc của HIS (tools/shared/_drug_catalog.py).

⚠ Giới hạn (nói rõ khi phản biện):
  - Nội dung gốc TIẾNG ANH (StatPearls/PubMed) → trả lời lại bằng tiếng Việt.
  - KHÔNG theo chuẩn kê đơn Việt Nam. Hướng phát triển: bổ sung Dược thư QG.
  - Đây là tool KIẾN THỨC, KHÔNG dùng để kê đơn / kiểm tra dị ứng (đã có tool riêng).

Nguồn: NCBI E-utilities — https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Cho phép import _drug_catalog từ tools/shared
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

TOOL_NAME = "drug_info"
CATEGORY = "Healthcare"
DESCRIPTION = (
    "Tra cứu THÔNG TIN KIẾN THỨC về một loại thuốc (liều dùng, tác dụng phụ, "
    "tương tác, chống chỉ định, công dụng) từ nguồn NCBI (StatPearls + PubMed), "
    "có dẫn nguồn. Dùng khi người dùng HỎI VỀ một thuốc cụ thể, ví dụ: "
    "'liều amoxicillin', 'tác dụng phụ của metformin', 'paracetamol uống thế nào', "
    "'ibuprofen tương tác với thuốc gì'. "
    "KHÔNG dùng để kê đơn hay kiểm tra dị ứng của bệnh nhân (đã có tool riêng). "
    "Trả về danh sách nguồn (sources) kèm link và đoạn bằng chứng để tổng hợp. "
    "Nội dung gốc tiếng Anh — phải trả lời lại bằng tiếng Việt."
)
ARGS_SCHEMA = {
    "drug_name": (
        "string — Tên thuốc cần tra (hoạt chất hoặc tên thường gọi). "
        "Ví dụ: 'amoxicillin', 'metformin', 'paracetamol'. BẮT BUỘC."
    ),
    "aspect": (
        "string — Khía cạnh quan tâm: 'lieu' | 'tac_dung_phu' | 'tuong_tac' | "
        "'tong_quat'. Tùy chọn, mặc định 'tong_quat'."
    ),
}

_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 20

# Đồng nghĩa để mở rộng truy vấn PubMed (MeSH dùng tên khác tên thường gọi VN)
_SYNONYMS: dict[str, str] = {
    "paracetamol": "acetaminophen",
    "lasix": "furosemide",
    "augmentin": "amoxicillin clavulanate",
    "bactrim": "trimethoprim sulfamethoxazole",
    "ventolin": "salbutamol albuterol",
    "nexium": "esomeprazole",
    "motilium": "domperidone",
} #Tên VN ≠ tên PubMed


def _api_key_param() -> dict:
    k = os.getenv("NCBI_API_KEY", "").strip()
    return {"api_key": k} if k else {}


def _match_catalog(drug_name: str) -> tuple[str, str | None]: # khớp với catalog 52 thuốc
    """Khớp tên thuốc với catalog 52 thuốc.

    Trả về (canonical_name, drug_class). Nếu không khớp → (drug_name, None).
    """
    try:
        from _drug_catalog import all_drugs
    except Exception:
        return drug_name, None
    norm = drug_name.strip().lower()
    if not norm:
        return drug_name, None
    for d in all_drugs():
        candidates = [str(d.get("name", "")).lower(), str(d.get("vi", "")).lower()]
        for c in candidates:
            if not c:
                continue
            if norm == c or norm in c or c in norm:
                return d.get("name", drug_name), d.get("drug_class")
    return drug_name, None


def run(args: dict) -> dict:
    import httpx

    drug = str(args.get("drug_name") or "").strip()
    if not drug:
        return {"error": "Thiếu drug_name."}
    aspect = str(args.get("aspect") or "tong_quat").strip().lower()

    canonical, drug_class = _match_catalog(drug)
    in_catalog = drug_class is not None

    sources: list[dict] = []
    evidence: list[str] = []
    n = 0 # bộ đếm số nguồn 

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            # ── 1) StatPearls (NCBI Bookshelf) — chuyên luận thuốc ── chỉ lấy link, không trích nội dung
#             StatPearls là gì?
# Bộ chuyên luận y khoa (peer-reviewed) trên NCBI Bookshelf — kiểu "từ điển thuốc/bệnh" chuẩn quốc tế, mở miễn phí. Mỗi thuốc có 1 chương (liều, tác dụng phụ, chống chỉ định...). Đây là nguồn tổng quát, đáng tin cho thông tin thuốc.

            try:
                r = client.get(f"{_EUTILS}/esearch.fcgi", params={
                    "db": "books", "term": f"{canonical} statpearls", # tìm sách/chương có tên thuốc + "statpearls"
                    "retmax": "1", "retmode": "json", **_api_key_param(),
                })
                ids = r.json().get("esearchresult", {}).get("idlist", []) # lấy ID sách/chương
                if ids: # nếu thấy nguồn
                    # Tiêu đề chương con của StatPearls hay gây nhầm → hiển thị tên
                    # chuẩn của thuốc; link tới trang tra cứu Bookshelf (luôn hợp lệ).
                    n += 1
                    sources.append({
                        "n": n,
                        "title": f"{canonical} — StatPearls (NCBI Bookshelf)",
                        "url": f"https://www.ncbi.nlm.nih.gov/books/?term={canonical}",
                        "source": "StatPearls · NCBI",
                    })
                    # Nhãn evidence cho [n] — StatPearls là chuyên luận (chưa trích nội dung)
                    evidence.append(
                        f"[{n}] StatPearls (NCBI Bookshelf) — chuyên luận tổng quát về "
                        f"{canonical}; chưa trích nội dung. Dùng link để xem liều/chi tiết."
                    )
            except Exception:
                pass

            # ── 2) PubMed — bằng chứng (abstract) ──
            try:
                aspect_terms = { # dựng query
                    "lieu": "dosage administration",
                    "tac_dung_phu": "adverse effects",
                    "tuong_tac": "drug interactions",
                }
                syn = _SYNONYMS.get(canonical.strip().lower())
                base = f"({canonical} OR {syn})" if syn else canonical
                term = base
                if aspect in aspect_terms:
                    term = f"{base} AND {aspect_terms[aspect]}"
                r = client.get(f"{_EUTILS}/esearch.fcgi", params={ # esearch -> tìm bài viết PubMed
                    "db": "pubmed", "term": term, "retmax": "3",
                    "sort": "relevance", "retmode": "json", **_api_key_param(),
                })
                pmids = r.json().get("esearchresult", {}).get("idlist", [])
                if pmids:
                    s = client.get(f"{_EUTILS}/esummary.fcgi", params={
                        "db": "pubmed", "id": ",".join(pmids),
                        "retmode": "json", **_api_key_param(),
                    })
                    res = s.json().get("result", {})
                    pmid_to_n = {}
                    for pid in pmids:
                        doc = res.get(pid, {})
                        title = doc.get("title") or "PubMed article"
                        n += 1
                        pmid_to_n[pid] = n
                        sources.append({"n": n, "title": title,
                                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                                        "source": "PubMed"})
                    # Lấy abstract TỪNG bài và GẮN NHÃN [n] đúng số nguồn
                    # → LLM trích đúng số, chip không lệch nguồn.
                    for pid in pmids:
                        try:
                            f = client.get(f"{_EUTILS}/efetch.fcgi", params={
                                "db": "pubmed", "id": pid,
                                "rettype": "abstract", "retmode": "text", **_api_key_param(),
                            })
                            if f.status_code == 200 and f.text.strip():
                                evidence.append(
                                    f"[{pmid_to_n[pid]}] " + f.text.strip()[:1800]
                                )
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception as e:
        return {"error": f"Không gọi được NCBI: {e}"}

    if not sources:
        return {
            "error": f"Không tìm được thông tin cho '{drug}' trên NCBI.",
            "drug": canonical,
        }

    return {
        "drug": canonical,
        "in_catalog": in_catalog,
        "drug_class": drug_class,
        "aspect": aspect,
        "sources": sources,
        "evidence_en": "\n\n".join(evidence) if evidence else None,
        "note_for_llm": (
            "evidence_en được GẮN NHÃN [n] ở đầu mỗi đoạn, n khớp với sources[].n. "
            "Khi trích một ý, CHÈN ĐÚNG số [n] của đoạn evidence chứa ý đó — TUYỆT ĐỐI "
            "KHÔNG tự đánh số lại, KHÔNG đổi thứ tự. "
            "GROUNDING: chỉ nêu thông tin CÓ trong evidence_en. KHÔNG thêm số liều, phác "
            "đồ, thuốc phối hợp, chống chỉ định bằng kiến thức nền nếu không có trong "
            "evidence_en. Nếu không có liều cụ thể, nói 'Chi tiết liều xem chuyên luận "
            "StatPearls (thẻ nguồn bên trên)' — KHÔNG tự ghi mg. KHÔNG mô tả nguồn là "
            "'của Việt Nam' (đây là nguồn quốc tế tiếng Anh). Không chắc → bỏ ý đó. "
            "KHÔNG tự viết danh sách 'Nguồn:' — hệ thống tự render thẻ nguồn. Chỉ chèn [n]."
        ),
        "_citation": "NCBI · StatPearls + PubMed (nguồn tiếng Anh; chưa theo chuẩn kê đơn VN)",
        "_disclaimer": "Thông tin tham khảo — không thay thế chỉ định của bác sĩ/dược sĩ.",
    }


# ── SELF-TEST ──
if __name__ == "__main__":
    import json
    for name in ["amoxicillin", "metformin", "paracetamol"]:
        print("=" * 70)
        print(name)
        out = run({"drug_name": name, "aspect": "tong_quat"})
        if "error" in out:
            print("  ERROR:", out["error"])
            continue
        print("  drug:", out["drug"], "| in_catalog:", out["in_catalog"])
        for s in out["sources"]:
            print(f"  [{s['n']}] {s['source']}: {s['title'][:60]} -> {s['url']}")
        print("  evidence_en chars:", len(out["evidence_en"] or ""))
