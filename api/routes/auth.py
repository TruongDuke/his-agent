"""Auth routes — login."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.deps import _aidbox
from db import get_user, create_user, verify_password

router = APIRouter()


class LoginRequest(BaseModel):
    phone: str
    password: str = ""


def _normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "").replace("-", "")


DEFAULT_PASSWORD = "123456"


async def _find_in_aidbox(phone: str) -> dict | None:
    url, auth = _aidbox()
    if not url:
        return None

    async with httpx.AsyncClient(timeout=10, auth=auth) as client:
        for resource, role in [("Practitioner", "doctor"), ("Patient", "patient")]:
            r = await client.get(f"{url}/fhir/{resource}",
                                 params={"telecom": phone, "_count": "1"})
            entries = r.json().get("entry") or []
            if entries:
                res = entries[0]["resource"]
                name_obj = (res.get("name") or [{}])[0]
                given  = " ".join(name_obj.get("given", []))
                family = name_obj.get("family", "")
                return {
                    "fhir_id": res["id"],
                    "role":    role,
                    "name":    f"{given} {family}".strip(),
                }
    return None


@router.post("/api/login")
async def login(body: LoginRequest):
    phone = _normalize_phone(body.phone)
    user  = get_user(phone)

    if user:
        # Tài khoản đã có — bắt buộc nhập mật khẩu
        if not body.password:
            return {"status": "need_password", "name": user["name"]}
        if not verify_password(body.password, user["password"]):
            raise HTTPException(401, "Mật khẩu không đúng.")
        return {
            "status": "ok",
            "role":   user["role"],
            "id":     user["fhir_id"],
            "name":   user["name"],
        }

    # Chưa có tài khoản — tìm trong Aidbox
    fhir = await _find_in_aidbox(phone)
    if not fhir:
        raise HTTPException(404, "Số điện thoại không có trong hệ thống bệnh viện.")

    # Tự tạo tài khoản với mật khẩu mặc định
    create_user(phone, DEFAULT_PASSWORD, fhir["fhir_id"], fhir["role"], fhir["name"])
    return {
        "status": "ok",
        "role":   fhir["role"],
        "id":     fhir["fhir_id"],
        "name":   fhir["name"],
    }
