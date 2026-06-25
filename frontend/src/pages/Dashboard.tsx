import { useEffect, useState } from 'react'
import { Card, Row, Col, Statistic, Spin } from 'antd'
import { CalendarOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons'
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import type { Session } from '../api'

const STATUS: Record<string, { label: string; color: string }> = {
  booked: { label: 'Đã xác nhận', color: '#198038' },
  fulfilled: { label: 'Đã khám', color: '#8d8d8d' },
  cancelled: { label: 'Đã huỷ', color: '#da1e28' },
  noshow: { label: 'Vắng mặt', color: '#b28600' },
  proposed: { label: 'Chờ duyệt', color: '#0f62fe' },
  pending: { label: 'Chờ duyệt', color: '#0f62fe' },
}
const DAY_VI = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']

export default function Dashboard({ session }: { session: Session }) {
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ today: 0, waiting: 0, total: 0 })
  const [bar, setBar] = useState<any[]>([])
  const [pie, setPie] = useState<any[]>([])

  useEffect(() => {
    ;(async () => {
      try {
        const today = new Date()
        const dfrom = today.toISOString().slice(0, 10)
        const dto = new Date(today.getTime() + 6 * 864e5).toISOString().slice(0, 10)
        const [r, p] = await Promise.all([
          fetch(`/api/appointments?date_from=${dfrom}&date_to=${dto}&practitioner_id=${session.id}`).then((x) => x.json()),
          fetch('/api/patients?_count=1').then((x) => x.json()),
        ])
        const appts = r.appointments || []
        const todayA = appts.filter((a: any) => a.start?.startsWith(dfrom))
        setStats({ today: todayA.length, waiting: todayA.filter((a: any) => a.status === 'booked').length, total: p.total ?? 0 })

        const barData = []
        for (let i = 0; i < 7; i++) {
          const d = new Date(today.getTime() + i * 864e5)
          const ds = d.toISOString().slice(0, 10)
          barData.push({ day: (i === 0 ? 'Hôm nay' : DAY_VI[d.getDay()]) + ' ' + ds.slice(5), count: appts.filter((a: any) => a.start?.startsWith(ds)).length })
        }
        setBar(barData)

        const sc: Record<string, number> = {}
        appts.forEach((a: any) => { sc[a.status] = (sc[a.status] || 0) + 1 })
        setPie(Object.entries(sc).map(([s, v]) => ({ name: STATUS[s]?.label || s, value: v, color: STATUS[s]?.color || '#c6c6c6' })))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  if (loading) return <div className="dash-panel" style={{ textAlign: 'center', paddingTop: 60 }}><Spin /></div>

  return (
    <div className="dash-panel">
      <Row gutter={16}>
        <Col span={8}><Card><Statistic title="Lịch hẹn hôm nay" value={stats.today} prefix={<CalendarOutlined />} valueStyle={{ color: '#005d5d' }} /></Card></Col>
        <Col span={8}><Card><Statistic title="Đang chờ khám" value={stats.waiting} prefix={<ClockCircleOutlined />} valueStyle={{ color: '#b28600' }} /></Card></Col>
        <Col span={8}><Card><Statistic title="Tổng bệnh nhân" value={stats.total} prefix={<TeamOutlined />} /></Card></Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={14}>
          <Card title="Lịch hẹn 7 ngày tới" size="small">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={bar} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="day" fontSize={11} />
                <YAxis allowDecimals={false} fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" name="Lịch hẹn" fill="#005d5d" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </Col>
        <Col span={10}>
          <Card title="Phân bố trạng thái" size="small">
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={pie} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90}>
                  {pie.map((e, i) => <Cell key={i} fill={e.color} />)}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
