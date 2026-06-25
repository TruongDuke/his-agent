import { Modal, Form, Input, Select, message } from 'antd'

export default function AllergyModal({
  open, patientId, patientName, onClose, onDone,
}: {
  open: boolean
  patientId: string
  patientName: string
  onClose: () => void
  onDone?: () => void
}) {
  const [form] = Form.useForm()

  async function submit() {
    const v = await form.validateFields()
    try {
      const r = await fetch('/api/allergy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ patient_id: patientId, ...v }),
      })
      if (!r.ok) throw new Error()
      message.success('Đã ghi nhận dị ứng')
      form.resetFields()
      onDone?.()
      onClose()
    } catch {
      message.error('Ghi nhận dị ứng thất bại')
    }
  }

  return (
    <Modal title={`Ghi nhận dị ứng — ${patientName}`} open={open} onCancel={onClose} okText="Lưu" onOk={submit}>
      <Form form={form} layout="vertical" initialValues={{ category: 'medication', severity: 'moderate', verification: 'confirmed' }}>
        <Form.Item name="substance" label="Chất gây dị ứng" rules={[{ required: true, message: 'Nhập chất gây dị ứng' }]}>
          <Input placeholder="VD: Penicillin, Tôm cua..." />
        </Form.Item>
        <Form.Item name="category" label="Nhóm">
          <Select
            options={[
              { value: 'medication', label: 'Thuốc' },
              { value: 'food', label: 'Thức ăn' },
              { value: 'environment', label: 'Môi trường' },
            ]}
          />
        </Form.Item>
        <Form.Item name="severity" label="Mức độ">
          <Select
            options={[
              { value: 'mild', label: 'Nhẹ' },
              { value: 'moderate', label: 'Vừa' },
              { value: 'severe', label: 'Nặng' },
            ]}
          />
        </Form.Item>
        <Form.Item name="reaction" label="Phản ứng (tùy chọn)">
          <Input placeholder="VD: nổi mề đay, khó thở..." />
        </Form.Item>
      </Form>
    </Modal>
  )
}
