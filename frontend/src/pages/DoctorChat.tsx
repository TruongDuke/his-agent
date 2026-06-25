import { useEffect, useRef, useState } from 'react'
import { Button, List, Empty } from 'antd'
import { PlusOutlined, MessageOutlined } from '@ant-design/icons'
import ChatPanel from '../components/ChatPanel'
import type { Session } from '../api'

interface Conv { conv_id: string; session_id: string; title: string; message_count: number }
interface Current { id: string; sessionId: string; messages: { role: 'user' | 'assistant'; content: string }[] }

export default function DoctorChat({ session, prefill }: { session: Session; prefill?: string }) {
  const [convs, setConvs] = useState<Conv[]>([])
  const [current, setCurrent] = useState<Current | null>(null)
  const started = useRef(false)

  async function loadList() {
    try {
      const r = await fetch(`/session/doctor/${session.id}/conversations`)
      const d = await r.json()
      setConvs(d.conversations || [])
    } catch {}
  }

  async function newConv() {
    try {
      const r = await fetch(`/session/doctor/${session.id}/new`, { method: 'POST' })
      const d = await r.json()
      const sid: string = d.session_id
      const convId = sid.replace(`doctor_${session.id}_`, '')
      setCurrent({ id: convId, sessionId: sid, messages: [] })
      loadList()
    } catch {}
  }

  async function openConv(convId: string) {
    try {
      const r = await fetch(`/session/doctor/${session.id}/conversation/${convId}`)
      const d = await r.json()
      setCurrent({
        id: convId,
        sessionId: d.session_id,
        messages: (d.messages || []).map((m: any) => ({ role: m.role, content: m.content })),
      })
    } catch {}
  }

  useEffect(() => {
    if (started.current) return
    started.current = true
    loadList()
    newConv()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="docchat">
      <div className="docchat-side">
        <Button type="primary" icon={<PlusOutlined />} block onClick={newConv} style={{ marginBottom: 10 }}>
          Hội thoại mới
        </Button>
        <List
          size="small"
          dataSource={convs}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Chưa có hội thoại" /> }}
          renderItem={(c) => (
            <List.Item
              onClick={() => openConv(c.conv_id)}
              className={'conv-item' + (current?.id === c.conv_id ? ' active' : '')}
            >
              <MessageOutlined style={{ marginRight: 8, color: '#8d8d8d' }} />
              <span className="conv-title">{c.title || 'Hội thoại'}</span>
            </List.Item>
          )}
        />
      </div>
      <div className="docchat-main">
        {current && (
          <ChatPanel
            key={current.id}
            session={session}
            initialMessages={current.messages}
            initialSessionId={current.sessionId}
            prefillInput={prefill}
          />
        )}
      </div>
    </div>
  )
}
