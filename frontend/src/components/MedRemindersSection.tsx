import { useEffect, useState } from 'react'
import { Input, Switch, Select, Button, Card, Empty, Spin, message, Typography, Space, Popconfirm } from 'antd'
import { BellOutlined, DeleteOutlined, SendOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Item {
  id: string
  drug_name: string
  dose_text: string
  instruction: string
  times: string[]
  start_date: string
  end_date: string
  enabled: boolean
  sent_log?: string[]
}
interface Doc {
  patient_name: string
  email: string
  items: Item[]
}

export default function MedRemindersSection({ patientId }: { patientId: string }) {
  const [doc, setDoc] = useState<Doc>({ patient_name: '', email: '', items: [] })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!patientId) return
    setLoading(true)
    fetch(`/api/med-reminders/${patientId}`)
      .then((r) => r.json())
      .then((d) => setDoc({ patient_name: d.patient_name || '', email: d.email || '', items: d.items || [] }))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [patientId])

  function patchItem(id: string, patch: Partial<Item>) {
    setDoc((prev) => ({ ...prev, items: prev.items.map((it) => (it.id === id ? { ...it, ...patch } : it)) }))
  }

  async function save(): Promise<boolean> {
    setSaving(true)
    try {
      const r = await fetch(`/api/med-reminders/${patientId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(doc),
      })
      if (!r.ok) throw new Error()
      const saved = await r.json()
      setDoc({ patient_name: saved.patient_name || '', email: saved.email || '', items: saved.items || [] })
      return true
    } catch {
      message.error('Lưu lịch nhắc thất bại')
      return false
    } finally {
      setSaving(false)
    }
  }

  async function onSaveClick() {
    if (await save()) message.success('Đã lưu lịch nhắc uống thuốc')
  }

  async function sendTest(itemId: string) {
    if (!(await save())) return
    try {
      const r = await fetch(`/api/med-reminders/${patientId}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_id: itemId }),
      })
      const d = await r.json()
      if (r.ok && d.sent) message.success(`Đã gửi email thử tới ${doc.email}`)
      else message.error(d.detail || d.error || 'Gửi thử thất bại')
    } catch {
      message.error('Gửi thử thất bại')
    }
  }

  if (loading) return <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>

  return (
    <div>
      <Text strong>Email nhận nhắc</Text>
      <Input
        style={{ margin: '6px 0 14px' }}
        placeholder="Email nhận nhắc uống thuốc"
        value={doc.email}
        onChange={(e) => setDoc({ ...doc, email: e.target.value })}
      />

      {doc.items.length === 0 ? (
        <Empty description="Chưa có lịch nhắc uống thuốc" />
      ) : (
        doc.items.map((it) => (
          <Card key={it.id} size="small" style={{ marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <BellOutlined style={{ color: it.enabled ? '#005d5d' : '#bbb' }} />
                <b>{it.drug_name}</b>
              </Space>
              <Space>
                <Switch size="small" checked={it.enabled} onChange={(v) => patchItem(it.id, { enabled: v })} />
                <Popconfirm
                  title="Xoá lịch nhắc này?"
                  onConfirm={() => setDoc((p) => ({ ...p, items: p.items.filter((x) => x.id !== it.id) }))}
                  okText="Xoá" cancelText="Huỷ"
                >
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            </div>
            {it.dose_text && <div><Text type="secondary" style={{ fontSize: 12 }}>{it.dose_text}{it.instruction ? ` — ${it.instruction}` : ''}</Text></div>}
            <div style={{ marginTop: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>Giờ nhắc: </Text>
              <Select
                mode="tags"
                style={{ width: '100%', marginTop: 4 }}
                placeholder="Thêm giờ (HH:MM)"
                value={it.times}
                onChange={(v) => patchItem(it.id, { times: v })}
                tokenSeparators={[',', ' ']}
              />
            </div>
            {/* flex + wrap thay cho float: trên điện thoại nút "Gửi thử" xuống hàng
                thay vì đè lên khoảng ngày. */}
            <div style={{
              marginTop: 6, display: 'flex', flexWrap: 'wrap',
              alignItems: 'center', justifyContent: 'space-between', gap: 4,
            }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {it.start_date} → {it.end_date || 'không giới hạn'}
              </Text>
              <Button
                size="small" type="link" icon={<SendOutlined />}
                onClick={() => sendTest(it.id)} disabled={!doc.email}
                style={{ padding: 0 }}
              >
                Gửi thử
              </Button>
            </div>
          </Card>
        ))
      )}

      <Button type="primary" block onClick={onSaveClick} loading={saving} style={{ marginTop: 8 }}>
        Lưu lịch nhắc
      </Button>
      <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
        Hệ thống gửi email đúng giờ đã đặt trong khoảng ngày kê đơn. Tắt công tắc để tạm dừng một thuốc.
      </Text>
    </div>
  )
}
