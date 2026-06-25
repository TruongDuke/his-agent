import { useState } from 'react'
import { Modal, InputNumber, Row, Col, Alert, message, Typography, Tag } from 'antd'

const { Text } = Typography

const FIELDS: { key: string; label: string; unit: string; required?: boolean }[] = [
  { key: 'plt', label: 'PLT (Tiểu cầu)', unit: 'K/μL', required: true },
  { key: 'wbc', label: 'WBC (Bạch cầu)', unit: 'K/μL' },
  { key: 'hct', label: 'HCT (Hematocrit)', unit: '%' },
  { key: 'hgb', label: 'HGB (Hemoglobin)', unit: 'g/dL' },
  { key: 'ast', label: 'AST', unit: 'U/L' },
  { key: 'alt', label: 'ALT', unit: 'U/L' },
  { key: 'fever_day', label: 'Ngày sốt thứ', unit: 'ngày' },
]

const COLOR_MAP: Record<string, string> = { red: 'error', orange: 'warning', yellow: 'warning', green: 'success' }

export default function CbcModal({
  open, patientId, patientName, onClose, onDone,
}: {
  open: boolean
  patientId: string
  patientName: string
  onClose: () => void
  onDone?: () => void
}) {
  const [vals, setVals] = useState<Record<string, number | null>>({})
  const [result, setResult] = useState<any>(null)
  const [saving, setSaving] = useState(false)

  async function submit() {
    if (vals.plt == null) return message.warning('PLT (tiểu cầu) là bắt buộc.')
    const body: any = { patient_id: patientId }
    for (const f of FIELDS) if (vals[f.key] != null) body[f.key] = vals[f.key]
    setSaving(true)
    try {
      const r = await fetch('/api/cbc', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      const d = await r.json()
      if (!r.ok) throw new Error()
      setResult(d.dengue_screening || null)
      message.success('Đã lưu CBC + sàng lọc SXHD')
      onDone?.()
    } catch {
      message.error('Lưu CBC thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`Nhập CBC — ${patientName}`}
      open={open}
      onCancel={() => { setVals({}); setResult(null); onClose() }}
      okText="Lưu & Sàng lọc"
      confirmLoading={saving}
      onOk={submit}
      width={600}
    >
      <Row gutter={[12, 12]} style={{ marginTop: 8 }}>
        {FIELDS.map((f) => (
          <Col span={12} key={f.key}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {f.label} {f.required && <Text type="danger">*</Text>}
            </Text>
            <InputNumber
              style={{ width: '100%' }}
              addonAfter={f.unit}
              value={vals[f.key] ?? null}
              onChange={(v) => setVals((p) => ({ ...p, [f.key]: v }))}
            />
          </Col>
        ))}
      </Row>

      {result && (
        <div style={{ marginTop: 16 }}>
          <Alert
            type={(COLOR_MAP[result.color] as any) || 'info'}
            showIcon
            message={<>Sàng lọc SXHD: <b>{result.likelihood_label}</b> <Tag>{result.color}</Tag></>}
            description={
              <>
                {(result.findings || []).slice(0, 6).map((f: string, i: number) => (
                  <div key={i}>{f}</div>
                ))}
                {result.next_action && <div style={{ marginTop: 6 }}><b>Khuyến nghị:</b> {result.next_action}</div>}
              </>
            }
          />
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
            Công cụ sàng lọc theo QĐ 2760/QĐ-BYT 2023. Không thay thế chẩn đoán lâm sàng.
          </Text>
        </div>
      )}
    </Modal>
  )
}
