import { useEffect, useState } from 'react'
import { Table, Button, Tag, Typography, message, Empty, DatePicker, Input, Select, Space, Popconfirm } from 'antd'
import { ReloadOutlined, CheckCircleOutlined } from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import CompleteVisitModal from '../components/CompleteVisitModal'
import type { Session } from '../api'

const { Title } = Typography

const STATUS_VI: Record<string, { text: string; color: string }> = {
  proposed: { text: 'Chờ duyệt', color: 'orange' },
  booked: { text: 'Đã xác nhận', color: 'blue' },
  fulfilled: { text: 'Đã khám', color: 'green' },
  cancelled: { text: 'Đã huỷ', color: 'default' },
  noshow: { text: 'Vắng mặt', color: 'gold' },
}

export default function TodaySchedule({ session }: { session: Session }) {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState<any>(null)
  const [date, setDate] = useState<Dayjs>(dayjs())
  const [nameQ, setNameQ] = useState('')
  const [status, setStatus] = useState('')

  async function load() {
    setLoading(true)
    try {
      const ds = date.format('YYYY-MM-DD')
      const r = await fetch(`/api/appointments?date_str=${ds}&practitioner_id=${session.id}`)
      const d = await r.json()
      setRows((d.appointments || []).map((x: any, i: number) => ({ ...x, key: x.id || i })))
    } catch {
      message.error('Không tải được lịch khám')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [date])

  async function act(id: string, kind: 'confirm' | 'reject') {
    try {
      const r = await fetch(`/api/${kind}-appointment/${id}`, { method: 'POST' })
      if (!r.ok) throw new Error()
      message.success(kind === 'confirm' ? 'Đã xác nhận lịch hẹn' : 'Đã từ chối lịch hẹn')
      load()
    } catch {
      message.error('Thao tác thất bại')
    }
  }

  const filtered = rows.filter(
    (r) =>
      (!nameQ || (r.patient_name || '').toLowerCase().includes(nameQ.toLowerCase())) &&
      (!status || r.status === status),
  )

  const columns = [
    { title: 'Giờ', dataIndex: 'start', width: 130, render: (v: string) => v?.slice(11) || v },
    { title: 'Bệnh nhân', dataIndex: 'patient_name', render: (v: string) => <b>{v || '—'}</b> },
    { title: 'Khoa', dataIndex: 'department', render: (v: string) => (v ? <Tag color="cyan">{v}</Tag> : '—') },
    { title: 'Lý do', dataIndex: 'reason', ellipsis: true, render: (v: string) => v || '—' },
    {
      title: 'Trạng thái', dataIndex: 'status', width: 130,
      render: (s: string) => {
        const m = STATUS_VI[s] || { text: s, color: 'default' }
        return <Tag color={m.color}>{m.text}</Tag>
      },
    },
    {
      title: 'Thao tác', key: 'act', fixed: 'right' as const, width: 230,
      render: (_: any, row: any) => {
        if (row.status === 'fulfilled')
          return <Tag color="green" icon={<CheckCircleOutlined />}>Đã khám</Tag>
        if (row.status === 'proposed')
          return (
            <Space>
              <Popconfirm title="Xác nhận lịch này?" okText="Xác nhận" cancelText="Huỷ" onConfirm={() => act(row.id, 'confirm')}>
                <Button type="primary" size="small">Duyệt</Button>
              </Popconfirm>
              <Popconfirm title="Từ chối lịch này?" okText="Từ chối" okType="danger" cancelText="Huỷ" onConfirm={() => act(row.id, 'reject')}>
                <Button danger size="small">Từ chối</Button>
              </Popconfirm>
            </Space>
          )
        // booked / khác → cho kết thúc khám
        return <Button type="primary" size="small" onClick={() => setActive(row)}>Kết thúc khám</Button>
      },
    },
  ]

  return (
    <div className="dash-panel">
      <div className="dash-head">
        <Title level={4} style={{ margin: 0 }}>Lịch hẹn</Title>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>Làm mới</Button>
      </div>

      <Space wrap style={{ marginBottom: 14 }}>
        <DatePicker value={date} onChange={(d) => d && setDate(d)} format="DD/MM/YYYY" allowClear={false} />
        <Button onClick={() => setDate(dayjs())}>Hôm nay</Button>
        <Input.Search placeholder="Lọc theo tên bệnh nhân..." allowClear style={{ width: 240 }} onChange={(e) => setNameQ(e.target.value)} />
        <Select
          value={status}
          onChange={setStatus}
          style={{ width: 170 }}
          options={[
            { value: '', label: 'Tất cả trạng thái' },
            { value: 'booked', label: 'Đã xác nhận' },
            { value: 'fulfilled', label: 'Đã khám' },
            { value: 'proposed', label: 'Chờ duyệt' },
            { value: 'cancelled', label: 'Đã huỷ' },
          ]}
        />
      </Space>

      <Table
        columns={columns}
        dataSource={filtered}
        loading={loading}
        scroll={{ x: 880 }}
        pagination={{ pageSize: 10, hideOnSinglePage: true }}
        locale={{ emptyText: <Empty description="Không có lịch hẹn" /> }}
      />
      <CompleteVisitModal
        open={!!active}
        appt={active}
        practitionerId={session.id}
        onClose={() => setActive(null)}
        onDone={load}
      />
    </div>
  )
}
