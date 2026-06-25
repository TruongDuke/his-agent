import { useState } from 'react'
import { Input, Button, Typography, Divider, Alert, Space } from 'antd'
import { loginStep, GUEST } from '../api'
import type { Session } from '../api'

const { Title, Text } = Typography

export default function Login({ onLogin }: { onLogin: (s: Session) => void }) {
  const [step, setStep] = useState<1 | 2>(1)
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  async function checkPhone() {
    setErr('')
    if (!phone.trim()) return setErr('Vui lòng nhập số điện thoại.')
    setLoading(true)
    try {
      const res = await loginStep(phone)
      if (res.status === 'need_password') {
        setName(res.name || '')
        setStep(2)
      } else if (res.status === 'ok') {
        onLogin({ role: res.role, id: res.id, name: res.name, token: res.token })
      }
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function doLogin() {
    setErr('')
    setLoading(true)
    try {
      const res = await loginStep(phone, password)
      if (res.status === 'ok') {
        onLogin({ role: res.role, id: res.id, name: res.name, token: res.token })
      }
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-screen">
      <div className="login-brand">
        <div className="login-brand-icon">🏥</div>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            HIS Agent
          </Title>
          <Text type="secondary">Bệnh viện Đa khoa</Text>
        </div>
      </div>

      <div className="login-card">
        {step === 1 ? (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Text strong>Đăng nhập bằng số điện thoại</Text>
            <Input
              size="large"
              placeholder="Số điện thoại (VD: 0912345678)"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              onPressEnter={checkPhone}
              maxLength={11}
            />
            {err && <Alert type="error" message={err} showIcon />}
            <Button type="primary" size="large" block loading={loading} onClick={checkPhone}>
              Tiếp tục
            </Button>
          </Space>
        ) : (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Text>
              Xin chào <Text strong>{name}</Text>, nhập mật khẩu để đăng nhập.
            </Text>
            <Input.Password
              size="large"
              placeholder="Mật khẩu"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onPressEnter={doLogin}
              autoFocus
            />
            {err && <Alert type="error" message={err} showIcon />}
            <Button type="primary" size="large" block loading={loading} onClick={doLogin}>
              Đăng nhập
            </Button>
            <Button type="link" block onClick={() => { setStep(1); setErr(''); setPassword('') }}>
              ← Đổi số điện thoại
            </Button>
          </Space>
        )}

        <Divider plain style={{ color: '#a8a8a8', fontSize: 12 }}>
          hoặc
        </Divider>
        <Button block onClick={() => onLogin(GUEST)}>
          Tiếp tục với tư cách khách
        </Button>
      </div>
    </div>
  )
}
