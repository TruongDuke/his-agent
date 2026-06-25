import { useState } from 'react'
import { Modal, InputNumber, Row, Col, Alert, message, Typography } from 'antd'

const { Text } = Typography

const FIELDS: { key: string; label: string; unit: string }[] = [
  { key: 'systolic', label: 'HA tâm thu', unit: 'mmHg' },
  { key: 'diastolic', label: 'HA tâm trương', unit: 'mmHg' },
  { key: 'heart_rate', label: 'Mạch', unit: 'bpm' },
  { key: 'resp_rate', label: 'Nhịp thở', unit: 'l/phút' },
  { key: 'temp', label: 'Nhiệt độ', unit: '°C' },
  { key: 'spo2', label: 'SpO2', unit: '%' },
  { key: 'weight', label: 'Cân nặng', unit: 'kg' },
  { key: 'height', label: 'Chiều cao', unit: 'cm' },
]

export default function VitalsModal({
  open, patientId, patientName, onClose, onDone,
}: {
  open: boolean
  patientId: string
  patientName: string
  onClose: () => void
  onDone?: () => void
}) {
  const [vals, setVals] = useState<Record<string, number | null>>({})
  const [alerts, setAlerts] = useState<any[] | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    const body: any = { patient_id: patientId }
    let any = false
    for (const f of FIELDS) if (vals[f.key] != null) { body[f.key] = vals[f.key]; any = true }
    if (!any) return message.warning('Nhập ít nhất một chỉ số.')
    setSaving(true)
    try {
      const r = await fetch('/api/vitals', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error()
      setAlerts(d.alerts || [])
      message.success('Đã lưu sinh hiệu')
      onDone?.()
    } catch {
      message.error('Lưu sinh hiệu thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`Ghi sinh hiệu — ${patientName}`}
      open={open}
      onCancel={() => { setVals({}); setAlerts(null); onClose() }}
      okText="Lưu"
      confirmLoading={saving}
      onOk={submit}
      width={560}
    >
      <Row gutter={[12, 12]} style={{ marginTop: 8 }}>
        {FIELDS.map((f) => (
          <Col span={12} key={f.key}>
            <Text type="secondary" style={{ fontSize: 12 }}>{f.label}</Text>
            <InputNumber
              style={{ width: '100%' }}
              addonAfter={f.unit}
              value={vals[f.key] ?? null}
              onChange={(v) => setVals((p) => ({ ...p, [f.key]: v }))}
            />
          </Col>
        ))}
      </Row>

      {alerts && (
        <div style={{ marginTop: 16 }}>
          {alerts.length === 0 ? (
            <Alert type="success" showIcon message="Tất cả chỉ số trong giới hạn bình thường." />
          ) : (
            alerts.map((a, i) => (
              <Alert
                key={i}
                style={{ marginBottom: 8 }}
                type={a.severity === 'critical' ? 'error' : 'warning'}
                showIcon
                message={a.message}
              />
            ))
          )}
        </div>
      )}
    </Modal>
  )
}
