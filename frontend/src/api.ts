// API client: login + SSE streaming. Gọi lại backend FastAPI sẵn có.

export interface Session {
  role: 'patient' | 'doctor'
  id: string
  name: string
  token: string
  guest?: boolean
}

export const GUEST: Session = { role: 'patient', id: '', name: '', token: '', guest: true }

export async function loginStep(phone: string, password = ''): Promise<any> {
  const r = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, password }),
  })
  if (r.status === 404) throw new Error('Số điện thoại không có trong hệ thống bệnh viện.')
  if (r.status === 401) throw new Error('Mật khẩu không đúng.')
  if (!r.ok) throw new Error('Lỗi đăng nhập (HTTP ' + r.status + ')')
  return r.json()
}

export interface Source {
  n: number
  title: string
  url: string
  source?: string
}

export interface StreamHandlers {
  onStatus?: (t: string) => void
  onToolCall?: (label: string) => void
  onText?: (delta: string) => void
  onSources?: (items: Source[]) => void
  onError?: (msg: string) => void
  onSession?: (id: string) => void
}

export async function streamChat(body: any, token: string, h: StreamHandlers): Promise<void> {
  const res = await fetch('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Session-Token': token || '' },
    body: JSON.stringify(body),
  })
  if (!res.body) throw new Error('Không nhận được luồng phản hồi.')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() || ''
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      let ev: any
      try {
        ev = JSON.parse(line.slice(6))
      } catch {
        continue
      }
      if (ev.type === 'status') h.onStatus?.(ev.text)
      else if (ev.type === 'tool_call') h.onToolCall?.(ev.label || ev.name)
      else if (ev.type === 'text') h.onText?.(ev.delta)
      else if (ev.type === 'sources') h.onSources?.(ev.items || [])
      else if (ev.type === 'error') h.onError?.(ev.text)
      else if (ev.session_id) h.onSession?.(ev.session_id)
    }
  }
}
