import { useEffect, useState } from 'react'
import { Modal, Form, Radio, Switch, Input, message, Divider, Typography, Spin } from 'antd'

const { Text } = Typography

export interface CbcConfig {
  length: 'full' | 'concise'
  audience: 'doctor' | 'patient'
  show_citations: boolean
  show_recommended_tests: boolean
  show_aspirin_warning: boolean
  show_scores: boolean
  custom_note: string
}

const DEFAULTS: CbcConfig = {
  length: 'full',
  audience: 'doctor',
  show_citations: true,
  show_recommended_tests: true,
  show_aspirin_warning: true,
  show_scores: false,
  custom_note: '',
}

export default function CbcConfigModal({
  open, doctorId, onClose,
}: {
  open: boolean
  doctorId: string
  onClose: () => void
}) {
  const [form] = Form.useForm<CbcConfig>()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !doctorId) return
    setLoading(true)
    fetch(`/api/doctor/${doctorId}/cbc-config`)
      .then((r) => r.json())
      .then((cfg) => form.setFieldsValue({ ...DEFAULTS, ...cfg }))
      .catch(() => form.setFieldsValue(DEFAULTS))
      .finally(() => setLoading(false))
  }, [open, doctorId, form])

  async function submit() {
    const v = await form.validateFields()
    setSaving(true)
    try {
      const r = await fetch(`/api/doctor/${doctorId}/cbc-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(v),
      })
      if (!r.ok) throw new Error()
      message.success('Đã lưu cấu hình báo cáo CBC')
      onClose()
    } catch {
      message.error('Lưu cấu hình thất bại')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="Cấu hình báo cáo CBC / sàng lọc SXHD"
      open={open}
      onCancel={onClose}
      okText="Lưu cấu hình"
      cancelText="Đóng"
      onOk={submit}
      confirmLoading={saving}
      width={520}
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 32 }}><Spin /></div>
      ) : (
        <Form form={form} layout="vertical" initialValues={DEFAULTS}>
          <Form.Item name="length" label="Độ dài báo cáo">
            <Radio.Group
              optionType="button"
              buttonStyle="solid"
              options={[
                { value: 'full', label: 'Đầy đủ' },
                { value: 'concise', label: 'Gọn' },
              ]}
            />
          </Form.Item>
          <Form.Item name="audience" label="Đối tượng đọc">
            <Radio.Group
              optionType="button"
              buttonStyle="solid"
              options={[
                { value: 'doctor', label: 'Bác sĩ' },
                { value: 'patient', label: 'Bệnh nhân' },
              ]}
            />
          </Form.Item>

          <Divider style={{ margin: '8px 0 16px' }} />

          <Form.Item name="show_citations" label="Trích dẫn nguồn (QĐ 2760)" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="show_recommended_tests" label="Khuyến nghị xét nghiệm tiếp theo" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="show_aspirin_warning" label="Cảnh báo aspirin/NSAID" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="show_scores" label="Hiển thị điểm kỹ thuật (cbc_score/warning_score)" valuePropName="checked">
            <Switch />
          </Form.Item>

          <Form.Item
            name="custom_note"
            label="Hướng dẫn riêng (tùy chọn)"
            extra={<Text type="secondary">VD: "Nhấn mạnh xu hướng PLT giữa các lần xét nghiệm", "Viết ngắn cho tuyến dưới".</Text>}
          >
            <Input.TextArea rows={3} maxLength={2000} placeholder="Hướng dẫn thêm về cách trình bày báo cáo CBC..." />
          </Form.Item>

          <Text type="secondary" style={{ fontSize: 12 }}>
            Cấu hình chỉ đổi CÁCH TRÌNH BÀY. Ngưỡng và kết quả sàng lọc do công cụ tính vẫn giữ nguyên.
          </Text>
        </Form>
      )}
    </Modal>
  )
}
