"""A2A protocol layer — exposes this HIS agent over the Agent-to-Agent protocol.

Thin wrapper around the existing ``agent.chat()``: serves an Agent Card and a
JSON-RPC ``message/send`` endpoint so other A2A-compliant agents (e.g. the
Sphinx platform) can call this agent without hard-coding its HTTP API.

Routes (mounted at /a2a):
  GET  /a2a/.well-known/agent-card.json   → Agent Card (discovery)
  POST /a2a/                              → JSON-RPC message/send
"""

import asyncio
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agent import chat

router = APIRouter()


_AGENT_CARD = {
    "name": "HIS Agent — Bệnh viện Đa khoa",
    "description": (
        "Trợ lý y tế của Bệnh viện Đa khoa: tư vấn y tế, tra cứu khoa/bác sĩ/lịch khám, "
        "đặt lịch hẹn, xem hồ sơ và kết quả xét nghiệm bệnh nhân."
    ),
    "version": "1.0.0",
    "protocolVersion": "0.3.0",
    "preferredTransport": "JSONRPC",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "medical_chat",
            "name": "Tư vấn & tra cứu y tế",
            "description": (
                "Trả lời câu hỏi y tế, tra cứu khoa/bác sĩ/lịch khám, đặt lịch hẹn, "
                "hồ sơ và kết quả xét nghiệm."
            ),
            "tags": ["medical", "hospital", "chat", "appointments"],
        }
    ],
}


def _text_from_parts(parts: list) -> str:
    """Concatenate all text parts of an A2A message (handles wrapped/plain)."""
    out = []
    for part in parts or []:
        actual = part.get("root", part) if isinstance(part, dict) else {}
        if actual.get("kind") == "text" or "text" in actual:
            txt = actual.get("text", "")
            if txt:
                out.append(txt)
    return "".join(out)


@router.get("/a2a/.well-known/agent-card.json")
def a2a_agent_card(request: Request):
    """Serve the Agent Card for discovery."""
    base = str(request.base_url).rstrip("/")
    card = dict(_AGENT_CARD)
    card["url"] = f"{base}/a2a/"
    return JSONResponse(card)


@router.post("/a2a/")
@router.post("/a2a")
async def a2a_rpc(request: Request):
    """Handle A2A JSON-RPC requests (message/send)."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None,
             "error": {"code": -32700, "message": "Parse error"}}
        )

    req_id = payload.get("id")
    method = payload.get("method")

    if method != "message/send":
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id,
             "error": {"code": -32601, "message": f"Method not supported: {method}"}}
        )

    message = (payload.get("params") or {}).get("message") or {}
    user_text = _text_from_parts(message.get("parts", []))
    if not user_text:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id,
             "error": {"code": -32602, "message": "No text content in message"}}
        )

    # Run the (synchronous, LLM-bound) agent off the event loop.
    try:
        reply, _ = await asyncio.get_event_loop().run_in_executor(
            None, lambda: chat(user_text, [], role="patient")
        )
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(
            {"jsonrpc": "2.0", "id": req_id,
             "error": {"code": -32603, "message": f"Agent error: {exc}"}}
        )

    result = {
        "kind": "message",
        "messageId": str(uuid.uuid4()),
        "role": "agent",
        "parts": [{"kind": "text", "text": reply}],
    }
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result})
