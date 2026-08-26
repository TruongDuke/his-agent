import { useRef, useState, useEffect } from 'react'
import { Button, Avatar, Input, message, Tooltip } from 'antd'
import {
  SendOutlined, RobotOutlined, UserOutlined, PaperClipOutlined, CloseCircleFilled, PlusOutlined,
  SettingOutlined, AudioOutlined, AudioMutedOutlined, SoundOutlined,
  PhoneOutlined, PhoneFilled,
} from '@ant-design/icons'
import { marked } from 'marked'
import DengueForm from './DengueForm'
import CbcConfigModal from './CbcConfigModal'
import { streamChat } from '../api'
import {
  startRecording, transcribe, startConversation, splitForSpeech, speakStream,
  type Recorder, type VoiceSession,
} from '../voice'
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
  const [cfgOpen, setCfgOpen] = useState(false)
  const [recording, setRecording] = useState(false)
  const [sttBusy, setSttBusy] = useState(false)
  const recorder = useRef<Recorder | null>(null)
  const [callState, _setCallState] = useState<'off' | 'listening' | 'thinking' | 'speaking'>('off')
  const callStateRef = useRef<'off' | 'listening' | 'thinking' | 'speaking'>('off')
  const setCallState = (v: 'off' | 'listening' | 'thinking' | 'speaking') => {
    callStateRef.current = v
    _setCallState(v)
  }
  const call = useRef<VoiceSession | null>(null)
  const stopSpeak = useRef<(() => void) | null>(null)
  const [speakingId, _setSpeakingId] = useState<number | null>(null)
  const speakingIdRef = useRef<number | null>(null)
  const setSpeakingId = (v: number | null) => { speakingIdRef.current = v; _setSpeakingId(v) }
  const sessionId = useRef(initialSessionId || '')
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const initRan = useRef(false)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  // Lời chào chủ động (__init__): nhắc chẩn đoán/kế hoạch tái khám lần trước.
  // Tách thành hàm để dùng lại cho cả lần đăng nhập lẫn nút "Cuộc trò chuyện mới".
  function runInit() {
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
  }

  // Bắt đầu cuộc trò chuyện mới: quên session_id (backend sẽ cấp id mới) + xóa lịch sử hiển thị.
  function newChat() {
    if (busy) return
    sessionId.current = ''
    setInput('')
    setImg(null)
    if (autoInit) runInit()   // bệnh nhân đã đăng nhập → chào lại + nhận session mới
    else setMessages([])      // khách → chỉ xóa
  }

  // Lời chào chủ động khi đăng nhập lần đầu (backend xử lý qua tin "__init__").
  useEffect(() => {
    if (!autoInit || initRan.current || messages.length) return
    initRan.current = true
    runInit()
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

  // Ghi âm → chữ. CỐ Ý đổ vào ô nhập thay vì gửi thẳng: nhận dạng giọng nói có thể
  // nghe nhầm ("đặt lịch" thành "lại lịch"), mà đây là bối cảnh y tế nên phải cho
  // người dùng đọc lại trước khi gửi.
  async function toggleMic() {
    if (busy || sttBusy) return
    if (callState !== 'off') {
      message.info('Đang trong cuộc gọi — cứ nói, không cần bấm micro.')
      return
    }
    if (recording) {
      const rec = recorder.current
      recorder.current = null
      setRecording(false)
      if (!rec) return
      setSttBusy(true)
      try {
        const { text, empty } = await transcribe(await rec.stop())
        if (empty) message.info('Không nghe thấy gì — thử nói to và rõ hơn.')
        else setInput((prev) => (prev ? prev + ' ' : '') + text)
      } catch (e: any) {
        message.error('Không nhận dạng được giọng nói: ' + e.message)
      } finally {
        setSttBusy(false)
      }
    } else {
      try {
        recorder.current = await startRecording()
        setRecording(true)
      } catch {
        message.error('Không truy cập được micro — kiểm tra quyền trong trình duyệt.')
      }
    }
  }

  /**
   * Đọc một câu trả lời. Dùng chung đường với chế độ gọi: bóc markdown, cắt câu,
   * phát nối tiếp — nghe tiếng sau ~1 giây thay vì chờ sinh hết cả đoạn (5-6 giây).
   *
   * Chốt cờ speakingId NGAY khi bấm, không đợi await: trước đây chỉ kiểm sau khi
   * TTS sinh xong nên trong lúc chờ, bấm thêm lần nữa (hoặc bấm ở câu trả lời khác)
   * là mở thêm một luồng phát — bao nhiêu lần bấm là bấy nhiêu giọng chồng nhau.
   */
  async function readAloud(text: string, id: number) {
    if (stopSpeak.current) {          // đang đọc thì bấm nữa là tắt
      stopSpeak.current()
      stopSpeak.current = null
      const same = speakingId === id
      setSpeakingId(null)
      if (same) return                // bấm lại đúng câu đó → chỉ tắt
    }
    setSpeakingId(id)
    try {
      const sentences = await splitForSpeech(text)
      if (speakingIdRef.current !== id) return   // đã bấm sang câu khác trong lúc chờ
      stopSpeak.current = speakStream(
        sentences,
        () => { stopSpeak.current = null; setSpeakingId(null) },
        (msg) => message.error(msg),
      )
    } catch (e: any) {
      setSpeakingId(null)
      message.error('Không đọc được: ' + e.message)
    }
  }

  /** Bật/tắt chế độ gọi: nghe liên tục, tự gửi khi nói xong, tự đọc câu trả lời. */
  async function toggleCall() {
    // Chặn mở cuộc gọi khi micro tay đang bật hoặc đang gửi tin — hai luồng micro
    // cùng lúc sẽ tranh nhau thiết bị.
    if (!call.current && (recording || sttBusy || busy)) {
      message.info('Đợi xử lý xong rồi hãy gọi.')
      return
    }
    if (call.current) {
      stopSpeak.current?.()
      call.current.stop()
      call.current = null
      setCallState('off')
      return
    }
    try {
      const session = await startConversation({
        onListening: () => setCallState('listening'),
        onThinking: () => setCallState('thinking'),
        // Người dùng lên tiếng giữa lúc agent đang đọc → cắt lời ngay
        onBargeIn: () => { stopSpeak.current?.(); stopSpeak.current = null },
        onError: (m) => message.error(m),
        onUtterance: async (wav) => {
          const { text, empty } = await transcribe(wav)
          if (empty || !text.trim()) { setCallState('listening'); return }
          const reply = await sendAndGetReply(text)
          // Nói rõ hỏng ở khâu nào thay vì im lặng quay về nghe tiếp — im lặng làm
          // không phân biệt được "agent không trả lời" với "trả lời rồi mà không phát".
          if (!reply.trim()) {
            message.warning('Agent không trả về nội dung để đọc.')
            setCallState('listening'); return
          }
          setCallState('speaking')
          call.current?.setSpeaking(true)
          const sentences = await splitForSpeech(reply)
          if (!sentences.length) {
            message.warning('Không cắt được câu nào để đọc.')
            call.current?.setSpeaking(false)
            setCallState('listening'); return
          }
          stopSpeak.current = speakStream(
            sentences,
            () => {
              call.current?.setSpeaking(false)
              stopSpeak.current = null
              setCallState('listening')
            },
            (msg) => message.error(msg),
          )
        },
      })
      call.current = session
      setCallState('listening')
      message.info('Đang nghe — cứ nói, ngừng khoảng 1 giây là mình trả lời.')
    } catch {
      message.error('Không truy cập được micro — kiểm tra quyền trong trình duyệt.')
    }
  }

  async function send(override?: string): Promise<string> {
    const text = (override ?? input).trim()
    if ((!text && !img) || busy) return ''
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
      // Đang gọi → agent trả lời ngắn để đọc lên nghe được (xem VOICE_EXTRA ở backend)
      // Đọc qua ref: callState trong closure bị đóng băng ở lần render lúc bấm Gọi
      // (khi đó vẫn là 'off'), nên đọc thẳng state sẽ luôn ra false.
      voice_mode: callStateRef.current !== 'off',
    }

    // Gom song song với việc đổ ra màn hình: chế độ gọi cần nguyên văn câu trả lời
    // để đưa sang TTS, mà state của React thì không đọc lại ngay được.
    let full = ''
    try {
      await streamChat(body, session.token, {
        onStatus: (t) => patch((m) => { if (!m.content) m.status = t }),
        onToolCall: (label) => patch((m) => { if (!m.content) m.status = label }),
        onText: (delta) => { full += delta; patch((m) => { m.content += delta; m.status = undefined }) },
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
    return full
  }

  /** Dùng cho chế độ gọi — gửi câu vừa nghe được và lấy lại câu trả lời để đọc. */
  async function sendAndGetReply(text: string): Promise<string> {
    return send(text)
  }

  const isDoctor = session.role === 'doctor'

  return (
    <div className="chat-panel">
      {session.role === 'patient' && (
        <div
          style={{
            display: 'flex', justifyContent: 'flex-end',
            padding: '8px 12px', borderBottom: '1px solid #f0f0f0', background: '#fff',
          }}
        >
          <Button size="small" icon={<PlusOutlined />} onClick={newChat} disabled={busy}>
            Cuộc trò chuyện mới
          </Button>
        </div>
      )}
      {isDoctor && (
        <div
          style={{
            display: 'flex', justifyContent: 'flex-end',
            padding: '8px 12px', borderBottom: '1px solid #f0f0f0', background: '#fff',
          }}
        >
          <Button size="small" icon={<SettingOutlined />} onClick={() => setCfgOpen(true)}>
            Cấu hình báo cáo CBC
          </Button>
        </div>
      )}
      {isDoctor && (
        <CbcConfigModal open={cfgOpen} doctorId={session.id} onClose={() => setCfgOpen(false)} />
      )}
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
                  <>
                    <div
                      className="md"
                      dangerouslySetInnerHTML={{ __html: renderAssistant(m.content, m.sources) }}
                    />
                    <Button
                      type="text"
                      size="small"
                      icon={<SoundOutlined />}
                      onClick={() => readAloud(m.content, i)}
                      style={{ marginTop: 4, color: speakingId === i ? '#005d5d' : '#888' }}
                    >
                      {speakingId === i ? 'Dừng' : 'Nghe'}
                    </Button>
                  </>
                ) : (
                  m.content
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="chat-footer">
        {callState !== 'off' && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
            background: '#e6f4f1', borderRadius: 6, marginBottom: 8, fontSize: 13, color: '#005d5d',
          }}>
            <span className="dots"><i /><i /><i /></span>
            {callState === 'listening' && 'Đang nghe — cứ nói, ngừng khoảng 1 giây là mình trả lời'}
            {callState === 'thinking' && 'Đang xử lý...'}
            {callState === 'speaking' && 'Đang trả lời — bạn cứ nói để ngắt lời'}
          </div>
        )}
        <div className="chat-input-wrap">
          {/* Đính kèm ảnh phiếu xét nghiệm chỉ dành cho bác sĩ (phân tích CBC) */}
          {isDoctor && (
            <>
              <input ref={fileRef} type="file" accept="image/*,application/pdf" hidden onChange={onFile} />
              <Button
                size="large"
                icon={<PaperClipOutlined />}
                onClick={() => fileRef.current?.click()}
                title="Đính kèm ảnh phiếu xét nghiệm"
              />
            </>
          )}
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
          <Tooltip title={callState === 'off' ? 'Gọi — nói chuyện liên tục với trợ lý' : 'Kết thúc cuộc gọi'}>
            <Button
              size="large"
              type={callState === 'off' ? 'default' : 'primary'}
              danger={callState !== 'off'}
              icon={callState === 'off' ? <PhoneOutlined /> : <PhoneFilled />}
              onClick={toggleCall}
            />
          </Tooltip>
          <Tooltip title={recording ? 'Bấm để dừng và chuyển thành chữ' : 'Nói thay vì gõ'}>
            <Button
              size="large"
              danger={recording}
              loading={sttBusy}
              icon={recording ? <AudioMutedOutlined /> : <AudioOutlined />}
              onClick={toggleMic}
            />
          </Tooltip>
          <Button type="primary" size="large" icon={<SendOutlined />} loading={busy} onClick={() => send()} />
        </div>
      </div>
    </div>
  )
}
