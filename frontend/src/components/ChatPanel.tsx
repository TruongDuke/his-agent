import { useRef, useState, useEffect } from 'react'
import { Button, Avatar, Input } from 'antd'
import {
  SendOutlined, RobotOutlined, UserOutlined, PaperClipOutlined, CloseCircleFilled,
} from '@ant-design/icons'
import { marked } from 'marked'
import DengueForm from './DengueForm'
import { streamChat } from '../api'
import type { Session, Source } from '../api'

function isDengueChecklist(text: string) {
  return text.includes('A. Dịch tễ') && text.includes('B. Triệu chứng') && text.includes('C. Dấu hiệu cảnh báo')
}

interface Msg {
  role: 'user' | 'assistant'
  content: string
  image?: string
  sources?: Source[]
  status?: string
}

function escAttr(s: string) {
  return String(s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')
}

function sourceCardsHTML(sources: Source[]) {
  const cards = sources
    .map(
      (s) => `
    <a class="source-card" href="${escAttr(s.url)}" target="_blank" rel="noopener">
      <span class="source-card-n">${s.n}</span>
      <span class="source-card-main">
        <span class="source-card-title">${escAttr(s.title)}</span>
        <span class="source-card-src">${escAttr(s.source || 'Nguồn')}</span>
      </span>
    </a>`,
    )
    .join('')
  return `<div class="source-cards"><div class="source-cards-label">📚 Nguồn tham khảo (${sources.length})</div><div class="source-cards-row">${cards}</div></div>`
}

function renderAssistant(md: string, sources?: Source[]) {
  if (!sources || !sources.length) return marked.parse(md) as string
  const body = md.replace(/\n+(?:[-*_]{3,}\s*\n+)?#{0,4}\s*Ngu[ồo]n[^\n]*\n[\s\S]*?(?=\n\s*⚠|$)/i, '\n')
  let html = marked.parse(body) as string
  html = html.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_m, grp) =>
    grp
      .split(',')
      .map((x: string) => {
        const n = x.trim()
        const s = sources[parseInt(n, 10) - 1]
        return s
          ? `<a class="cite-chip" href="${escAttr(s.url)}" target="_blank" rel="noopener" title="${escAttr(s.title)}">${n}</a>`
          : `[${n}]`
      })
      .join(''),
  )
  return sourceCardsHTML(sources) + html
}

export default function ChatPanel({
  session, initialMessages, initialSessionId, autoInit, prefillInput,
}: {
  session: Session
  initialMessages?: Msg[]
  initialSessionId?: string
  autoInit?: boolean
  prefillInput?: string
}) {
  const [messages, setMessages] = useState<Msg[]>(initialMessages || [])
  const [input, setInput] = useState(prefillInput || '')
  const [busy, setBusy] = useState(false)
  const [img, setImg] = useState<{ data: string; mime: string; url: string } | null>(null)
  const sessionId = useRef(initialSessionId || '')
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const initRan = useRef(false)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // Lời chào chủ động khi đăng nhập: nhắc chẩn đoán/kế hoạch tái khám lần trước
  // (backend xử lý qua tin "__init__" ở endpoint /chat non-stream).
  useEffect(() => {
    if (!autoInit || initRan.current || messages.length) return
    initRan.current = true
    setMessages([{ role: 'assistant', content: '', status: 'Đang tải...' }])
    fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-Token': session.token || '' },
      body: JSON.stringify({
        message: '__init__',
        session_id: sessionId.current,
        role: session.role,
        patient_name: session.role === 'patient' ? session.name : '',
        patient_id: session.role === 'patient' ? session.id : '',
        doctor_name: session.role === 'doctor' ? session.name : '',
        doctor_id: session.role === 'doctor' ? session.id : '',
        image_base64: '', image_mime: 'image/jpeg',
      }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.session_id) sessionId.current = d.session_id
        setMessages(d.reply ? [{ role: 'assistant', content: d.reply }] : [])
      })
      .catch(() => setMessages([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function patch(updater: (m: Msg) => void) {
    setMessages((prev) => {
      const next = [...prev]
      const last = { ...next[next.length - 1] }
      updater(last)
      next[next.length - 1] = last
      return next
    })
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      const url = reader.result as string
      setImg({ data: url.split(',')[1] || '', mime: f.type || 'image/jpeg', url })
    }
    reader.readAsDataURL(f)
    e.target.value = ''
  }

  async function send(override?: string) {
    const text = (override ?? input).trim()
    if ((!text && !img) || busy) return
    if (!override) setInput('')
    const attached = override ? null : img
    if (!override) setImg(null)
    setBusy(true)
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text || (attached ? '[Ảnh xét nghiệm]' : ''), image: attached?.url },
      { role: 'assistant', content: '', status: 'Đang xử lý...' },
    ])

    const isDoctor = session.role === 'doctor'
    const body = {
      message: text,
      session_id: sessionId.current,
      role: session.role,
      doctor_name: isDoctor ? session.name : '',
      doctor_id: isDoctor ? session.id : '',
      patient_name: !isDoctor ? session.name : '',
      patient_id: !isDoctor ? session.id : '',
      image_base64: attached?.data || '',
      image_mime: attached?.mime || 'image/jpeg',
    }

    try {
      await streamChat(body, session.token, {
        onStatus: (t) => patch((m) => { if (!m.content) m.status = t }),
        onToolCall: (label) => patch((m) => { if (!m.content) m.status = label }),
        onText: (delta) => patch((m) => { m.content += delta; m.status = undefined }),
        onSources: (items) => patch((m) => { m.sources = items }),
        onError: (msg) => patch((m) => { m.content = '⚠ Lỗi: ' + msg; m.status = undefined }),
        onSession: (id) => { sessionId.current = id },
      })
    } catch (e: any) {
      patch((m) => { m.content = '⚠ Lỗi kết nối: ' + e.message; m.status = undefined })
    } finally {
      patch((m) => { m.status = undefined })
      setBusy(false)
    }
  }

  const isDoctor = session.role === 'doctor'

  return (
    <div className="chat-panel">
      <div className="chat-content" ref={scrollRef}>
        <div className="chat-inner">
          {messages.length === 0 && (
            <div className="chat-empty">
              <RobotOutlined style={{ fontSize: 40, color: '#005d5d' }} />
              <h2>Xin chào{session.name ? `, ${session.name}` : ''} 👋</h2>
              <p>
                {isDoctor
                  ? 'Tra cứu hồ sơ, phân tích CBC (tải ảnh phiếu xét nghiệm), kê đơn, tra cứu thuốc...'
                  : 'Đặt lịch khám, hỏi triệu chứng, sàng lọc sốt xuất huyết, tra cứu thuốc...'}
              </p>
              <div className="suggest-chips">
                {(isDoctor
                  ? ['Tra cứu thuốc amoxicillin', 'Tình hình sốt xuất huyết TP.HCM', 'Danh sách khoa khám']
                  : ['Tôi muốn đặt lịch khám', 'Đau bụng nên khám khoa nào?', 'Kiểm tra lịch hẹn của tôi', 'Liều paracetamol']
                ).map((s) => (
                  <button key={s} className="suggest-chip" onClick={() => send(s)}>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`msg-row ${m.role}`}>
              <Avatar
                className={`msg-avatar ${m.role}`}
                icon={m.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
              />
              <div className={`bubble ${m.role}`}>
                {m.image && <img className="msg-img" src={m.image} alt="ảnh" />}
                {m.status ? (
                  <span className="status-line">
                    <span className="dots"><i /><i /><i /></span> {m.status}
                  </span>
                ) : m.role === 'assistant' && isDengueChecklist(m.content) ? (
                  <DengueForm onSubmit={(t) => send(t)} />
                ) : m.role === 'assistant' ? (
                  <div
                    className="md"
                    dangerouslySetInnerHTML={{ __html: renderAssistant(m.content, m.sources) }}
                  />
                ) : (
                  m.content
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="chat-footer">
        <div className="chat-input-wrap">
          <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden onChange={onFile} />
          <Button
            size="large"
            icon={<PaperClipOutlined />}
            onClick={() => fileRef.current?.click()}
            title="Đính kèm ảnh phiếu xét nghiệm"
          />
          <div style={{ flex: 1 }}>
            {img && (
              <div className="img-preview">
                <img src={img.url} alt="preview" />
                <CloseCircleFilled onClick={() => setImg(null)} />
              </div>
            )}
            <Input.TextArea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={img ? 'Thêm mô tả (tùy chọn) rồi gửi...' : 'Nhập tin nhắn...'}
              autoSize={{ minRows: 1, maxRows: 4 }}
              onPressEnter={(e) => {
                if (!e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
          </div>
          <Button type="primary" size="large" icon={<SendOutlined />} loading={busy} onClick={send} />
        </div>
      </div>
    </div>
  )
}
