"""HIS Agent API — FastAPI HTTP server."""

import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from agent import chat

app = FastAPI(title="HIS Agent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session store — đủ dùng cho demo/đồ án
# Production: thay bằng Redis hoặc PostgreSQL
_sessions: dict[str, list] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest):
    session_id = body.session_id or str(uuid.uuid4())
    history = _sessions.get(session_id, [])

    try:
        reply, updated_history = chat(body.message, history)
        _sessions[session_id] = updated_history
        return ChatResponse(reply=reply, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(_sessions)}


@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Chat UI đơn giản để test — không cần frontend riêng."""
    return """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>Trợ lý Bệnh viện Đa khoa Hà Nội</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Arial, sans-serif; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; }
    .container { width: 480px; height: 680px; background: white; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); display: flex; flex-direction: column; overflow: hidden; }
    .header { background: #0f62fe; color: white; padding: 16px 20px; }
    .header h2 { font-size: 16px; }
    .header p  { font-size: 12px; opacity: 0.8; margin-top: 2px; }
    .messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
    .msg { max-width: 80%; padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; }
    .msg.user { align-self: flex-end; background: #0f62fe; color: white; border-bottom-right-radius: 4px; }
    .msg.bot  { align-self: flex-start; background: #f4f4f4; color: #1a1a1a; border-bottom-left-radius: 4px; }
    .msg.typing { color: #888; font-style: italic; }
    .input-row { display: flex; padding: 12px; border-top: 1px solid #e0e0e0; gap: 8px; }
    .input-row input { flex: 1; padding: 10px 14px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; }
    .input-row input:focus { border-color: #0f62fe; }
    .input-row button { padding: 10px 18px; background: #0f62fe; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
    .input-row button:hover { background: #0353e9; }
    .input-row button:disabled { background: #aaa; cursor: not-allowed; }
  </style>
</head>
<body>
<div class="container">
  <div class="header">
    <h2>🏥 Trợ lý Bệnh viện Đa khoa Hà Nội</h2>
    <p>Đặt lịch khám · Triage triệu chứng · Tra cứu hồ sơ</p>
  </div>
  <div class="messages" id="messages">
    <div class="msg bot">Xin chào! Tôi có thể giúp bạn đặt lịch khám hoặc tư vấn triệu chứng. Bạn cần hỗ trợ gì?</div>
  </div>
  <div class="input-row">
    <input id="input" type="text" placeholder="Nhập tin nhắn..." autocomplete="off" />
    <button id="send">Gửi</button>
  </div>
</div>
<script>
  let sessionId = null;
  const messages = document.getElementById('messages');
  const input    = document.getElementById('input');
  const btn      = document.getElementById('send');

  function addMsg(text, role) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    return div;
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    btn.disabled = true;

    addMsg(text, 'user');
    const typing = addMsg('Đang xử lý...', 'bot typing');

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });
      const data = await res.json();
      sessionId = data.session_id;
      typing.textContent = data.reply;
      typing.classList.remove('typing');
    } catch (e) {
      typing.textContent = 'Lỗi kết nối. Vui lòng thử lại.';
    }
    btn.disabled = false;
    input.focus();
  }

  btn.addEventListener('click', send);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
</script>
</body>
</html>"""
