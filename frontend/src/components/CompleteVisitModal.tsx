import { useEffect, useState } from 'react'
import {
  Modal, Input, Checkbox, message, Typography, Button, Select, InputNumber, Card, Alert, Tag, Space, Divider,
} from 'antd'
import { PlusOutlined, DeleteOutlined, BulbOutlined } from '@ant-design/icons'

const { Text } = Typography

interface Row {
  drug_id?: string
  dose_per_intake: number
  frequency_per_day: number
  duration_days?: number
  instructions: string
  override_reason: string
  check?: any
}
const newRow = (): Row => ({ dose_per_intake: 1, frequency_per_day: 2, duration_days: 5, instructions: '', override_reason: '' })

export default function CompleteVisitModal({
  open, appt, practitionerId, onClose, onDone,
}: {
  open: boolean
  appt: { id: string; patient_id: string; patient_name: string } | null
  practitionerId: string
  onClose: () => void
  onDone?: () => void
}) {
  const [diagnosis, setDiagnosis] = useState('')
  const [notes, setNotes] = useState('')
  const [plan, setPlan] = useState('')
  const [email, setEmail] = useState('')
  const [sendEmail, setSendEmail] = useState(true)
  const [remind, setRemind] = useState(true)
  const [saving, setSaving] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [allergies, setAllergies] = useState<any[]>([])
  const [catalog, setCatalog] = useState<Record<string, any[]>>({})
  const [rows, setRows] = useState<Row[]>([])

  useEffect(() => {
    if (!open || !appt) return
    setDiagnosis(''); setNotes(''); setPlan(''); setEmail(''); setSendEmail(true); setRemind(true); setRows([])
    fetch('/api/patient/' + appt.patient_id).then((r) => r.json()).then((p) => p.email && setEmail(p.email)).catch(() => {})
    fetch('/api/allergies/' + appt.patient_id).then((r) => r.json()).then((a) => setAllergies((a.allergies || []).filter((x: any) => x.category === 'medication'))).catch(() => {})
    fetch('/api/drug-catalog').then((r) => r.json()).then((d) => setCatalog(d.by_category || {})).catch(() => {})
  }, [open, appt])

  const flatDrugs = Object.values(catalog).flat()
  const options = Object.entries(catalog).map(([cat, drugs]) => ({
    label: cat,
    options: drugs.map((d) => ({ label: `${d.name} ${d.strength} (${d.form})`, value: d.id })),
  }))
  const updateRow = (i: number, patch: Partial<Row>) => setRows((p) => p.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))

  async function onDrug(i: number, drugId: string) {
    updateRow(i, { drug_id: drugId, check: null })
    try {
      const r = await fetch('/api/check-allergy', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: appt!.patient_id, drug_id: drugId }),
      })
      updateRow(i, { check: await r.json() })
    } catch {}
  }

  async function aiSuggest() {
    if (!appt) return
    setAiLoading(true)
    try {
      const r = await fetch('/api/suggest-completion', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: appt.patient_id, appointment_id: appt.id }),
      })
      const d = await r.json()
      if (d.diagnosis) setDiagnosis(d.diagnosis)
      if (d.notes) setNotes(d.notes)
      if (d.plan) setPlan(d.plan)
      if (!d.diagnosis && !d.notes && !d.plan) message.info('AI chưa có gợi ý cho ca này')
    } catch {
      message.error('Gợi ý thất bại')
    } finally {
      setAiLoading(false)
    }
  }

  async function submit() {
    if (!appt) return
    if (!diagnosis.trim()) return message.warning('Vui lòng nhập chẩn đoán.')
    const meds = rows.filter((r) => r.drug_id)
    if (meds.some((r) => r.check?.verdict === 'block'))
      return message.error('Có thuốc bị CHẶN do dị ứng — hãy bỏ hoặc đổi thuốc.')
    if (meds.some((r) => r.check?.verdict === 'warn' && !r.override_reason.trim()))
      return message.warning('Thuốc có cảnh báo dị ứng — nhập lý do override để tiếp tục.')

    setSaving(true)
    try {
      // snapshot thuốc cho email
      const emailMeds = meds.map((m) => {
        const d = flatDrugs.find((x: any) => x.id === m.drug_id)
        const dur = m.duration_days ? ` × ${m.duration_days} ngày` : ''
        const instr = m.instructions ? ` (${m.instructions})` : ''
        return {
          drug_name: d ? `${d.name} ${d.strength}` : m.drug_id,
          instruction: `${m.dose_per_intake} ${d?.form || 'viên'} × ${m.frequency_per_day} lần/ngày${dur}${instr}`,
        }
      })

      const r1 = await fetch('/api/complete-appointment/' + appt.id, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          patient_id: appt.patient_id, practitioner_id: practitionerId || 'unknown',
          diagnosis, notes, plan,
          send_email: sendEmail && !!email, patient_email: email, medications: emailMeds,
        }),
      })
      const d1 = await r1.json()
      if (!r1.ok) throw new Error()

      // kê đơn thật (nếu có thuốc)
      if (meds.length) {
        const r2 = await fetch('/api/prescription', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            patient_id: appt.patient_id, practitioner_id: practitionerId || 'unknown', diagnosis,
            medications: meds.map((m) => ({
              drug_id: m.drug_id, dose_per_intake: m.dose_per_intake, frequency_per_day: m.frequency_per_day,
              duration_days: m.duration_days, instructions: m.instructions, override_reason: m.override_reason,
            })),
          }),
        })
        const d2 = await r2.json()
        if (d2.saved === false && d2.error === 'prescription_blocked') {
          message.error('Đơn thuốc bị chặn: ' + (d2.message || ''))
          return
        }

        // Bật nhắc uống thuốc — cùng cơ chế với màn Kê đơn. Thiếu đoạn này thì thuốc
        // kê qua "Hoàn tất khám" không bao giờ có lịch nhắc, dù cùng là kê đơn.
        if (remind) {
          if (!email.trim()) {
            message.warning('Đã kê đơn nhưng chưa có email BN — không bật được nhắc uống thuốc.')
          } else {
            try {
              const rr = await fetch(`/api/med-reminders/${appt.patient_id}/from-prescription`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  email: email.trim(),
                  patient_name: appt.patient_name,
                  medications: meds.map((m) => {
                    const d = flatDrugs.find((x: any) => x.id === m.drug_id)
                    return {
                      drug_name: d ? `${d.name} ${d.strength}` : m.drug_id,
                      dose_per_intake: m.dose_per_intake,
                      frequency_per_day: m.frequency_per_day,
                      duration_days: m.duration_days,
                      instructions: m.instructions,
                    }
                  }),
                }),
              })
              if (rr.ok) message.success('Đã bật nhắc uống thuốc qua email cho BN')
            } catch {
              message.warning('Đã kê đơn nhưng bật nhắc uống thuốc thất bại.')
            }
          }
        }
      }

      const emailMsg = d1.email?.success ? ' · 📧 đã gửi email' : sendEmail && !email ? ' · ⚠ chưa gửi email' : ''
      message.success(`Đã hoàn tất khám${meds.length ? ` + kê ${meds.length} thuốc` : ''}${emailMsg}`)
      onDone?.()
      onClose()
    } catch {
      message.error('Hoàn tất khám thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`Kết thúc khám — ${appt?.patient_name || ''}`}
      open={open}
      onCancel={onClose}
      okText="Lưu & Kết thúc"
      confirmLoading={saving}
      onOk={submit}
      width={680}
    >
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <Button size="small" icon={<BulbOutlined />} loading={aiLoading} onClick={aiSuggest}>✨ AI gợi ý</Button>
      </div>

      {allergies.length > 0 && (
        <Alert
          style={{ marginBottom: 12 }}
          type="warning"
          showIcon
          message="Dị ứng thuốc đã ghi nhận"
          description={allergies.map((a, i) => (
            <Tag key={i} color={a.criticality === 'high' ? 'red' : 'orange'}>{a.substance}{a.severity_vi ? ` (${a.severity_vi})` : ''}</Tag>
          ))}
        />
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Input placeholder="Chẩn đoán *" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} />
        <Input.TextArea placeholder="Ghi chú lâm sàng" value={notes} onChange={(e) => setNotes(e.target.value)} autoSize={{ minRows: 2, maxRows: 4 }} />

        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>Đơn thuốc (tùy chọn — kèm kiểm tra dị ứng)</Text>
          {rows.map((row, i) => (
            <Card key={i} size="small" style={{ marginTop: 8 }}>
              <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                <Select showSearch placeholder="Chọn thuốc" style={{ width: 260 }} options={options}
                  value={row.drug_id} optionFilterProp="label" onChange={(v) => onDrug(i, v)} />
                <Space>
                  <InputNumber min={1} value={row.dose_per_intake} onChange={(v) => updateRow(i, { dose_per_intake: v || 1 })} addonAfter="viên" />
                  <InputNumber min={1} value={row.frequency_per_day} onChange={(v) => updateRow(i, { frequency_per_day: v || 1 })} addonAfter="lần" />
                  <InputNumber min={1} value={row.duration_days} onChange={(v) => updateRow(i, { duration_days: v || undefined })} addonAfter="ngày" />
                  <Button danger type="text" icon={<DeleteOutlined />} onClick={() => setRows(rows.filter((_, idx) => idx !== i))} />
                </Space>
              </Space>
              <Input placeholder="Hướng dẫn dùng" value={row.instructions} onChange={(e) => updateRow(i, { instructions: e.target.value })} style={{ marginTop: 8 }} />
              {row.check && row.check.verdict !== 'clear' && (
                <Alert style={{ marginTop: 8 }} type={row.check.verdict === 'block' ? 'error' : 'warning'} showIcon
                  message={row.check.verdict === 'block' ? '🚫 CHẶN — dị ứng' : '⚠ Cảnh báo dị ứng'}
                  description={
                    <>
                      {(row.check.checks || []).map((c: any, j: number) => <div key={j}>{c.message}</div>)}
                      {row.check.suggested_alternatives?.length > 0 && (
                        <div style={{ marginTop: 4 }}>
                          Gợi ý thay thế:{' '}
                          {row.check.suggested_alternatives.map((a: any) => (
                            <Tag key={a.id} color="green">{a.name}</Tag>
                          ))}
                        </div>
                      )}
                      {row.check.verdict === 'warn' && (
                        <Input placeholder="Lý do override (≥5 ký tự)" value={row.override_reason}
                          onChange={(e) => updateRow(i, { override_reason: e.target.value })} style={{ marginTop: 6 }} />
                      )}
                    </>
                  }
                />
              )}
              {row.check?.verdict === 'clear' && row.drug_id && (
                <Text type="success" style={{ fontSize: 12, marginTop: 6, display: 'block' }}>✓ An toàn</Text>
              )}
            </Card>
          ))}
          <Button type="dashed" icon={<PlusOutlined />} block onClick={() => setRows([...rows, newRow()])} style={{ marginTop: 8 }}>
            Thêm thuốc
          </Button>
        </div>

        <Input placeholder="Kế hoạch / tái khám" value={plan} onChange={(e) => setPlan(e.target.value)} />

        <Divider style={{ margin: '4px 0' }} />
        <Checkbox checked={sendEmail} onChange={(e) => setSendEmail(e.target.checked)}>📧 Gửi email tóm tắt khám cho bệnh nhân</Checkbox>
        {sendEmail && <Input placeholder="Email bệnh nhân" value={email} onChange={(e) => setEmail(e.target.value)} />}
        <Checkbox checked={remind} onChange={(e) => setRemind(e.target.checked)}>
          ⏰ Nhắc bệnh nhân uống thuốc qua email
        </Checkbox>
        {remind && !sendEmail && (
          <Input placeholder="Email bệnh nhân để nhận nhắc" value={email} onChange={(e) => setEmail(e.target.value)} />
        )}
        <Text type="secondary" style={{ fontSize: 12 }}>
          Lưu ClinicalImpression + đổi trạng thái → fulfilled. Có thuốc thì kê đơn (check dị ứng). Email tóm tắt gửi tự động.
        </Text>
      </div>
    </Modal>
  )
}
