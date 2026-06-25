import { useState } from 'react'
import { Button, Tag, Typography } from 'antd'
import { LogoutOutlined, IdcardOutlined } from '@ant-design/icons'
import MyProfileDrawer from './MyProfileDrawer'
import type { Session } from '../api'

const { Text } = Typography

export default function Header({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const isDoctor = session.role === 'doctor'
  const canViewProfile = session.role === 'patient' && !session.guest && !!session.id
  const [profileOpen, setProfileOpen] = useState(false)

  return (
    <div className="app-header">
      <div className="app-header-brand">
        <div className="app-header-icon">🏥</div>
        <div>
          <div className="app-header-title">HIS Agent</div>
          <div className="app-header-sub">Bệnh viện Đa khoa</div>
        </div>
      </div>
      <div className="app-header-right">
        <Tag color={isDoctor ? 'geekblue' : 'cyan'} style={{ marginInlineEnd: 0 }}>
          {isDoctor ? 'Bác sĩ' : session.guest ? 'Khách' : 'Bệnh nhân'}
        </Tag>
        {session.name && <Text style={{ color: '#fff' }}>{session.name}</Text>}
        {canViewProfile && (
          <Button type="text" icon={<IdcardOutlined />} style={{ color: '#fff' }} onClick={() => setProfileOpen(true)}>
            Hồ sơ của tôi
          </Button>
        )}
        <Button type="text" icon={<LogoutOutlined />} style={{ color: '#fff' }} onClick={onLogout}>
          Thoát
        </Button>
      </div>
      {canViewProfile && (
        <MyProfileDrawer open={profileOpen} patientId={session.id} onClose={() => setProfileOpen(false)} />
      )}
    </div>
  )
}
