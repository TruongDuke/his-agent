import { useEffect, useState } from 'react'
import { Layout, Menu, Badge } from 'antd'
import {
  MessageOutlined, CalendarOutlined, FileSearchOutlined, ScheduleOutlined,
  DashboardOutlined, ExperimentOutlined,
} from '@ant-design/icons'
import Header from '../components/Header'
import Dashboard from './Dashboard'
import DoctorChat from './DoctorChat'
import Appointments from './Appointments'
import PatientLookup from './PatientLookup'
import TodaySchedule from './TodaySchedule'
import Lab from './Lab'
import type { Session } from '../api'

const { Sider, Content } = Layout

export default function DoctorDashboard({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [tab, setTab] = useState('dashboard')
  const [pending, setPending] = useState(0)
  const [prefill, setPrefill] = useState('')

  async function loadPending() {
    try {
      const d = await fetch('/api/pending-appointments').then((r) => r.json())
      setPending((d.pending || []).length)
    } catch {}
  }
  useEffect(() => { loadPending() }, [tab])

  return (
    <Layout style={{ height: '100vh' }}>
      <Header session={session} onLogout={onLogout} />
      <Layout style={{ flex: 1, minHeight: 0 }}>
        <Sider theme="light" width={232} style={{ borderRight: '1px solid var(--ui-03)' }}>
          <Menu
            mode="inline"
            selectedKeys={[tab]}
            onClick={(e) => setTab(e.key)}
            style={{ borderInlineEnd: 'none', marginTop: 8 }}
            items={[
              { key: 'dashboard', icon: <DashboardOutlined />, label: 'Tổng quan' },
              { key: 'chat', icon: <MessageOutlined />, label: 'Trợ lý lâm sàng' },
              { key: 'patients', icon: <FileSearchOutlined />, label: 'Hồ sơ bệnh nhân' },
              { key: 'today', icon: <ScheduleOutlined />, label: 'Lịch hẹn hôm nay' },
              { key: 'lab', icon: <ExperimentOutlined />, label: 'Xét nghiệm' },
              {
                key: 'appointments',
                icon: <CalendarOutlined />,
                label: (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                    Lịch hẹn chờ duyệt
                    {pending > 0 && <Badge count={pending} size="small" />}
                  </span>
                ),
              },
            ]}
          />
        </Sider>
        <Content style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {tab === 'dashboard' && <Dashboard session={session} />}
          {tab === 'chat' && <DoctorChat session={session} prefill={prefill} />}
          {tab === 'patients' && (
            <PatientLookup
              session={session}
              onAskAI={(name) => { setPrefill('Tóm tắt hồ sơ bệnh nhân ' + name); setTab('chat') }}
            />
          )}
          {tab === 'today' && <TodaySchedule session={session} />}
          {tab === 'lab' && <Lab />}
          {tab === 'appointments' && <Appointments onChange={loadPending} />}
        </Content>
      </Layout>
    </Layout>
  )
}
