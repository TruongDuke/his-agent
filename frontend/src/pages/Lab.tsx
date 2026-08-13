import { useEffect, useState } from 'react'
import { Table, Select, Button, Typography, message } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

const { Title } = Typography

export default function Lab() {
  const [rows, setRows] = useState<any[]>([])
  const [cat, setCat] = useState('all')
  const [loading, setLoading] = useState(false)

  async function load() {
    setLoading(true)
    try {
      const d = await fetch(`/api/observations?category=${cat}&_count=60`).then((r) => r.json())
      setRows((d.observations || []).map((x: any, i: number) => ({ ...x, key: i })))
    } catch {
      message.error('Không tải được kết quả xét nghiệm')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [cat])

  const columns = [
    { title: 'Bệnh nhân', dataIndex: 'patient_name', render: (v: string) => <b>{v || '—'}</b> },
    { title: 'Chỉ số', dataIndex: 'name' },
    { title: 'Giá trị', dataIndex: 'value', render: (v: string, r: any) => <b>{v} {r.unit}</b> },
    { title: 'Ngày', dataIndex: 'date', width: 120 },
  ]

  return (
    <div className="dash-panel">
      <div className="dash-head">
        <Title level={4} style={{ margin: 0 }}>Xét nghiệm</Title>
        <div style={{ display: 'flex', gap: 8 }}>
          <Select
            value={cat}
            onChange={setCat}
            style={{ width: 170 }}
            options={[
              { value: 'all', label: 'Tất cả loại' },
              { value: 'laboratory', label: 'Xét nghiệm' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>Làm mới</Button>
        </div>
      </div>
      <Table columns={columns} dataSource={rows} loading={loading} pagination={{ pageSize: 12 }} />
    </div>
  )
}
