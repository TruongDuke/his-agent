import { useEffect, useState } from 'react'
import {
  Modal, Input, Select, InputNumber, Button, Alert, Space, Card, Tag, message, Typography, Divider,
} from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Row {
  drug_id?: string
  dose_per_intake: number
  frequency_per_day: number
  duration_days?: number
  instructions: string
  override_reason: string
  check?: any
  checking?: boolean
}

const newRow = (): Row => ({
  dose_per_intake: 1,
  frequency_per_day: 2,
  duration_days: 5,
  instructions: '',
  override_reason: '',
})

export default function PrescriptionModal({
  open, patientId, patientName, practitionerId, onClose, onDone,
}: {
  open: boolean
  patientId: string
  patientName: string
  practitionerId: string
  onClose: () => void
  onDone?: () => void
}) {
  const [diagnosis, setDiagnosis] = useState('')
  const [rows, setRows] = useState<Row[]>([newRow()])
  const [catalog, setCatalog] = useState<Record<string, any[]>>({})
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!open) return
    setDiagnosis('')
    setRows([newRow()])
    fetch('/api/drug-catalog')
      .then((r) => r.json())
      .then((d) => setCatalog(d.by_category || {}))
      .catch(() => {})
  }, [open])

  const options = Object.entries(catalog).map(([cat, drugs]) => ({
    label: cat,
    options: drugs.map((d) => ({ label: `${d.name} ${d.strength} (${d.form})`, value: d.id })),
  }))

  function update(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  }

  async function onDrug(i: number, drugId: string) {
    update(i, { drug_id: drugId, check: null, checking: true })
    try {
      const r = await fetch('/api/check-allergy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: patientId, drug_id: drugId }),
      })
      update(i, { check: await r.json(), checking: false })
    } catch {
      update(i, { checking: false })
    }
  }

  async function submit() {
    if (!diagnosis.trim()) return message.warning('Vui lòng nhập chẩn đoán.')
    const meds = rows.filter((r) => r.drug_id)
    if (!meds.length) return message.warning('Thêm ít nhất một thuốc.')
    if (meds.some((r) => r.check?.verdict === 'block'))
      return message.error('Có thuốc bị CHẶN do dị ứng — hãy bỏ hoặc đổi thuốc.')
    const needOverride = meds.find((r) => r.check?.verdict === 'warn' && !r.override_reason.trim())
    if (needOverride)
      return message.warning('Thuốc có cảnh báo dị ứng — nhập lý do override (≥5 ký tự) để tiếp tục.')

    setSubmitting(true)
    try {
      const r = await fetch('/api/prescription', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: patientId,
          practitioner_id: practitionerId || 'unknown',
          diagnosis,
          medications: meds.map((m) => ({
            drug_id: m.drug_id,
            dose_per_intake: m.dose_per_intake,
            frequency_per_day: m.frequency_per_day,
            duration_days: m.duration_days,
            instructions: m.instructions,
            override_reason: m.override_reason,
          })),
        }),
      })
      const d = await r.json()
      if (d.saved === false && d.error === 'prescription_blocked') {
        message.error('Đơn bị server chặn do dị ứng: ' + (d.message || ''))
        return
      }
      if (!r.ok) throw new Error()
      message.success(`Đã kê đơn ${meds.length} thuốc cho ${patientName}`)
      onDone?.()
      onClose()
    } catch {
      message.error('Kê đơn thất bại.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title={`Kê đơn — ${patientName}`}
      open={open}
      onCancel={onClose}
      width={760}
      okText="Kê đơn"
      confirmLoading={submitting}
      onOk={submit}
    >
      <Input
        placeholder="Chẩn đoán *"
        value={diagnosis}
        onChange={(e) => setDiagnosis(e.target.value)}
        style={{ margin: '8px 0 16px' }}
      />

      {rows.map((row, i) => (
        <Card key={i} size="small" style={{ marginBottom: 12 }}>
          <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
            <Select
              showSearch
              placeholder="Chọn thuốc"
              style={{ width: 320 }}
              options={options}
              value={row.drug_id}
              optionFilterProp="label"
              onChange={(v) => onDrug(i, v)}
              loading={row.checking}
            />
            <Space>
              <InputNumber min={1} value={row.dose_per_intake} onChange={(v) => update(i, { dose_per_intake: v || 1 })} addonAfter="viên" />
              <InputNumber min={1} value={row.frequency_per_day} onChange={(v) => update(i, { frequency_per_day: v || 1 })} addonAfter="lần/ngày" />
              <InputNumber min={1} value={row.duration_days} onChange={(v) => update(i, { duration_days: v || undefined })} addonAfter="ngày" />
              {rows.length > 1 && (
                <Button danger type="text" icon={<DeleteOutlined />} onClick={() => setRows(rows.filter((_, idx) => idx !== i))} />
              )}
            </Space>
          </Space>

          <Input
            placeholder="Hướng dẫn dùng (vd: uống sau ăn)"
            value={row.instructions}
            onChange={(e) => update(i, { instructions: e.target.value })}
            style={{ marginTop: 8 }}
          />

          {row.check && row.check.verdict !== 'clear' && (
            <Alert
              style={{ marginTop: 8 }}
              type={row.check.verdict === 'block' ? 'error' : 'warning'}
              showIcon
              message={row.check.verdict === 'block' ? '🚫 CHẶN — dị ứng' : '⚠ Cảnh báo dị ứng'}
              description={
                <>
                  {(row.check.checks || []).map((c: any, j: number) => (
                    <div key={j}>{c.message}</div>
                  ))}
                  {row.check.suggested_alternatives?.length > 0 && (
                    <div style={{ marginTop: 4 }}>
                      Gợi ý thay thế:{' '}
                      {row.check.suggested_alternatives.map((a: any) => (
                        <Tag key={a.id} color="green">{a.name}</Tag>
                      ))}
                    </div>
                  )}
                  {row.check.verdict === 'warn' && (
                    <Input
                      placeholder="Lý do vẫn kê (override, ≥5 ký tự)"
                      value={row.override_reason}
                      onChange={(e) => update(i, { override_reason: e.target.value })}
                      style={{ marginTop: 6 }}
                    />
                  )}
                </>
              }
            />
          )}
          {row.check && row.check.verdict === 'clear' && row.drug_id && (
            <Text type="success" style={{ fontSize: 12, marginTop: 6, display: 'block' }}>
              ✓ An toàn — không có dị ứng ghi nhận
            </Text>
          )}
        </Card>
      ))}

      <Button type="dashed" icon={<PlusOutlined />} block onClick={() => setRows([...rows, newRow()])}>
        Thêm thuốc
      </Button>
      <Divider style={{ margin: '12px 0 0' }} />
      <Text type="secondary" style={{ fontSize: 12 }}>
        Hệ thống tự kiểm tra dị ứng 4 lớp khi chọn thuốc (Stockley's, BNF). Thuốc bị chặn phải đổi; cảnh báo cần lý do override.
      </Text>
    </Modal>
  )
}
