import { Modal, Form, Input, Select, DatePicker, message } from 'antd'

export default function RegisterPatientModal({
  open, onClose, onDone,
}: {
  open: boolean
  onClose: () => void
  onDone?: (id: string, name: string) => void
}) {
  const [form] = Form.useForm()

  async function submit() {
    const v = await form.validateFields()
    try {
      const r = await fetch('/api/register-patient', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: v.name,
          gender: v.gender,
          birth_date: v.birth_date ? v.birth_date.format('YYYY-MM-DD') : '',
          phone: v.phone || '',
          address: v.address || '',
        }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error()
      message.success('Đã tạo hồ sơ bệnh nhân')
      form.resetFields()
      onDone?.(d.patient_id, d.name)
      onClose()
    } catch {
      message.error('Đăng ký bệnh nhân thất bại')
    }
  }

  return (
    <Modal title="Đăng ký bệnh nhân mới" open={open} onCancel={onClose} okText="Tạo hồ sơ" onOk={submit}>
      <Form form={form} layout="vertical" initialValues={{ gender: 'male' }}>
        <Form.Item name="name" label="Họ tên" rules={[{ required: true, message: 'Nhập họ tên' }]}>
          <Input placeholder="VD: Nguyễn Văn An" />
        </Form.Item>
        <Form.Item name="gender" label="Giới tính">
          <Select options={[{ value: 'male', label: 'Nam' }, { value: 'female', label: 'Nữ' }]} />
        </Form.Item>
        <Form.Item name="birth_date" label="Ngày sinh">
          <DatePicker style={{ width: '100%' }} format="DD/MM/YYYY" />
        </Form.Item>
        <Form.Item name="phone" label="Số điện thoại">
          <Input placeholder="09..." />
        </Form.Item>
        <Form.Item name="address" label="Địa chỉ (tùy chọn)">
          <Input />
        </Form.Item>
      </Form>
    </Modal>
  )
}
