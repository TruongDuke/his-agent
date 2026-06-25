import { useEffect, useState } from 'react'
import { Table, Button, Tag, Popconfirm, message, Typography, Space, Empty } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

const { Title } = Typography

interface Row {
  key: string
  appointment_id: string
  patient_name: string
  patient_email: string
  department: string
  date: string
  time: string
  symptoms: string
}

export default function Appointments({ onChange }: { onChange?: () => void }) {
  const [rows, setRows] = useState<Row[]>([])
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const r = await fetch('/api/pending-appointments')
      const d = await r.json()
      setRows((d.pending || []).map((x: any, i: number) => ({ ...x, key: x.appointment_id || String(i) })))
    } catch {
      message.error('Không tải được danh sách lịch hẹn')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function act(id: string, kind: 'confirm' | 'reject') {
    try {
      const r = await fetch(`/api/${kind}-appointment/${id}`, { method: 'POST' })
      if (!r.ok) throw new Error()
      message.success(kind === 'confirm' ? 'Đã xác nhận & gửi email cho bệnh nhân' : 'Đã từ chối, giải phóng slot')
      load()
      onChange?.()
    } catch {
      message.error(kind === 'confirm' ? 'Xác nhận thất bại' : 'Từ chối thất bại')
    }
  }

  const columns = [
    { title: 'Bệnh nhân', dataIndex: 'patient_name', render: (v: string) => <b>{v || '—'}</b> },
    { title: 'Khoa', dataIndex: 'department', render: (v: string) => (v ? <Tag color="cyan">{v}</Tag> : '—') },
    { title: 'Ngày', dataIndex: 'date', width: 110 },
    { title: 'Giờ', dataIndex: 'time', width: 80 },
    { title: 'Triệu chứng / Ghi chú', dataIndex: 'symptoms', ellipsis: true, render: (v: string) => v || '—' },
    { title: 'Email', dataIndex: 'patient_email', ellipsis: true, render: (v: string) => v || '—' },
    {
      title: 'Thao tác',
      key: 'act',
      fixed: 'right' as const,
      width: 210,
      render: (_: any, row: Row) => (
        <Space>
          <Popconfirm
            title="Xác nhận lịch hẹn này?"
            okText="Xác nhận"
            cancelText="Huỷ"
            onConfirm={() => act(row.appointment_id, 'confirm')}
          >
            <Button type="primary" size="small">
              Xác nhận
            </Button>
          </Popconfirm>
          <Popconfirm
            title="Từ chối lịch hẹn này?"
            okText="Từ chối"
            okType="danger"
            cancelText="Huỷ"
            onConfirm={() => act(row.appointment_id, 'reject')}
          >
            <Button danger size="small">
              Từ chối
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="dash-panel">
      <div className="dash-head">
        <Title level={4} style={{ margin: 0 }}>
          Lịch hẹn chờ duyệt {rows.length > 0 && <Tag color="orange">{rows.length}</Tag>}
        </Title>
        <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
          Làm mới
        </Button>
      </div>
      <Table
        columns={columns}
        dataSource={rows}
        loading={loading}
        scroll={{ x: 980 }}
        pagination={{ pageSize: 8, hideOnSinglePage: true }}
        locale={{ emptyText: <Empty description="Không có lịch hẹn chờ duyệt" /> }}
      />
    </div>
  )
}
