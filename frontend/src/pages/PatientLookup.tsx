import { useState, useEffect } from 'react'
import {
  Input, List, Card, Descriptions, Tabs, Table, Tag, Empty, Spin, Typography, message, Avatar, Button, Space, Segmented,
} from 'antd'
import {
  UserOutlined, SearchOutlined, MedicineBoxOutlined, WarningOutlined, UserAddOutlined, ExperimentOutlined,
} from '@ant-design/icons'
import PrescriptionModal from '../components/PrescriptionModal'
import AllergyModal from '../components/AllergyModal'
import RegisterPatientModal from '../components/RegisterPatientModal'
import CbcModal from '../components/CbcModal'
import CbcSection from '../components/CbcSection'
import type { Session } from '../api'

const { Title, Text } = Typography

interface PatientRow { id: string; name: string; gender: string; birth_date: string; phone: string }

export default function PatientLookup({ session, onAskAI }: { session: Session; onAskAI?: (name: string) => void }) {
  const [rxOpen, setRxOpen] = useState(false)
  const [allergyOpen, setAllergyOpen] = useState(false)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [cbcOpen, setCbcOpen] = useState(false)
  const [results, setResults] = useState<PatientRow[]>([])
  const [searching, setSearching] = useState(false)
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'mine' | 'all'>('mine')
  const [browse, setBrowse] = useState<any[]>([])
  const [browseLoading, setBrowseLoading] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [allergies, setAllergies] = useState<any[]>([])
  const [prescriptions, setPrescriptions] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  async function search(q: string) {
    setQuery(q)
    if (!q.trim()) return
    setSearching(true)
    try {
      const r = await fetch('/api/patients?q=' + encodeURIComponent(q.trim()))
      const d = await r.json()
      setResults(d.patients || [])
    } catch {
      message.error('Không tìm được bệnh nhân')
    } finally {
      setSearching(false)
    }
  }

  async function loadBrowse() {
    setBrowseLoading(true)
    try {
      const url = mode === 'mine'
        ? `/api/doctor/${session.id}/patients`
        : '/api/patients?_count=30'
      const d = await fetch(url).then((r) => r.json())
      setBrowse(d.patients || [])
    } catch {
      setBrowse([])
    } finally {
      setBrowseLoading(false)
    }
  }
  useEffect(() => { loadBrowse() }, [mode])

  const displayList = query.trim() ? results : browse

  async function open(id: string) {
    setSelected(id)
    setLoading(true)
    try {
      const [p, a, rx] = await Promise.all([
        fetch('/api/patient/' + id).then((r) => r.json()),
        fetch('/api/allergies/' + id).then((r) => r.json()).catch(() => ({})),
        fetch('/api/prescriptions/' + id).then((r) => r.json()).catch(() => ({})),
      ])
      setDetail(p)
      setAllergies(a.allergies || [])
      setPrescriptions(rx.prescriptions || [])
    } catch {
      message.error('Không tải được hồ sơ')
    } finally {
      setLoading(false)
    }
  }

  const obsCols = [
    { title: 'Chỉ số', dataIndex: 'name' },
    { title: 'Giá trị', dataIndex: 'value', render: (v: string, r: any) => <b>{v} {r.unit}</b> },
    { title: 'Ngày', dataIndex: 'date', width: 120 },
  ]

  return (
    <div className="dash-panel">
      <Title level={4} style={{ marginTop: 0 }}>Hồ sơ bệnh nhân</Title>
      <div className="lookup-grid">
        {/* Cột tìm kiếm */}
        <div className="lookup-list">
          <Input.Search
            placeholder="Tìm theo tên hoặc SĐT..."
            enterButton={<SearchOutlined />}
            onSearch={search}
            loading={searching}
            allowClear
          />
          <Button block icon={<UserAddOutlined />} style={{ marginTop: 8 }} onClick={() => setRegisterOpen(true)}>
            Đăng ký bệnh nhân mới
          </Button>
          {!query.trim() && (
            <Segmented
              block
              style={{ marginTop: 10 }}
              value={mode}
              onChange={(v) => setMode(v as 'mine' | 'all')}
              options={[{ label: 'Của tôi', value: 'mine' }, { label: 'Tất cả', value: 'all' }]}
            />
          )}
          <List
            style={{ marginTop: 12 }}
            loading={query.trim() ? searching : browseLoading}
            dataSource={displayList}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={query.trim() ? 'Không tìm thấy' : 'Chưa có bệnh nhân'} /> }}
            renderItem={(p: any) => (
              <List.Item
                onClick={() => open(p.id)}
                className={'lookup-item' + (selected === p.id ? ' active' : '')}
              >
                <List.Item.Meta
                  avatar={<Avatar icon={<UserOutlined />} style={{ background: '#005d5d' }} />}
                  title={
                    <>
                      {p.name}{' '}
                      {p.plt_display && p.plt_display !== '—' && (
                        <Tag color={p.plt_status === 'critical' ? 'red' : p.plt_status === 'warning' ? 'orange' : 'green'}>
                          PLT {p.plt_display}
                        </Tag>
                      )}
                    </>
                  }
                  description={`${p.gender || ''}${p.birth_date ? ' · ' + p.birth_date : ''}${p.phone ? ' · ' + p.phone : ''}`}
                />
              </List.Item>
            )}
          />
        </div>

        {/* Cột chi tiết */}
        <div className="lookup-detail">
          {!selected ? (
            <Card><Empty description="Chọn một bệnh nhân để xem hồ sơ" /></Card>
          ) : loading ? (
            <Card><div style={{ textAlign: 'center', padding: 40 }}><Spin /></div></Card>
          ) : detail ? (
            <Card
              title={detail.name}
              extra={
                <Space wrap>
                  {onAskAI && (
                    <Button type="dashed" onClick={() => onAskAI(detail.name)}>🤖 Hỏi AI</Button>
                  )}
                  <Button icon={<ExperimentOutlined />} onClick={() => setCbcOpen(true)}>CBC</Button>
                  <Button icon={<WarningOutlined />} onClick={() => setAllergyOpen(true)}>Dị ứng</Button>
                  <Button type="primary" icon={<MedicineBoxOutlined />} onClick={() => setRxOpen(true)}>Kê đơn</Button>
                </Space>
              }
            >
              <Descriptions column={2} size="small" bordered>
                <Descriptions.Item label="Giới tính">{detail.gender || '—'}</Descriptions.Item>
                <Descriptions.Item label="Tuổi">{detail.age || '—'}</Descriptions.Item>
                <Descriptions.Item label="Ngày sinh">{detail.birth_date || '—'}</Descriptions.Item>
                <Descriptions.Item label="SĐT">{detail.phone || '—'}</Descriptions.Item>
                <Descriptions.Item label="Email" span={2}>{detail.email || '—'}</Descriptions.Item>
              </Descriptions>

              <Tabs
                style={{ marginTop: 16 }}
                items={[
                  {
                    key: 'overview',
                    label: 'Tổng quan',
                    children: (
                      <>
                        <Text strong>Xét nghiệm gần nhất</Text>
                        <Table size="small" columns={obsCols} dataSource={(detail.labs || []).map((x: any, i: number) => ({ ...x, key: i }))}
                          pagination={false} locale={{ emptyText: 'Chưa có' }} style={{ marginBottom: 16 }} />
                        <Text strong>Diễn tiến CBC & sàng lọc SXHD</Text>
                        <div style={{ marginTop: 8 }}><CbcSection patientId={selected!} /></div>
                      </>
                    ),
                  },
                  {
                    key: 'allergies',
                    label: `Dị ứng (${allergies.length})`,
                    children: allergies.length ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {allergies.map((a, i) => (
                          <Tag key={i} color={a.criticality === 'high' ? 'red' : 'orange'} style={{ padding: '4px 10px' }}>
                            <b>{a.substance}</b>
                            {a.severity_vi ? ` — ${a.severity_vi}` : ''}
                            {a.reaction ? ` (${a.reaction})` : ''}
                          </Tag>
                        ))}
                      </div>
                    ) : <Empty description="Không có dị ứng ghi nhận" />,
                  },
                  {
                    key: 'rx',
                    label: `Đơn thuốc (${prescriptions.length})`,
                    children: prescriptions.length ? (
                      <List
                        dataSource={prescriptions}
                        renderItem={(p: any) => (
                          <List.Item>
                            <List.Item.Meta
                              title={
                                <>
                                  {p.prescription_date} {p.diagnosis && <Tag color="blue">{p.diagnosis}</Tag>}
                                  {p.has_override && <Tag color="warning">⚠ Có override</Tag>}
                                </>
                              }
                              description={
                                <ul style={{ margin: 0, paddingLeft: 18 }}>
                                  {(p.medications || []).map((m: any, j: number) => (
                                    <li key={j}>
                                      {m.drug_name} {m.instruction && <Text type="secondary">— {m.instruction}</Text>}
                                      {/* Lý do bác sĩ vẫn kê dù có cảnh báo dị ứng — bắt buộc hiện để audit được */}
                                      {m.override_note && (
                                        <div style={{ color: '#d46b08', fontSize: 12, marginTop: 2 }}>
                                          {m.override_note}
                                        </div>
                                      )}
                                    </li>
                                  ))}
                                </ul>
                              }
                            />
                          </List.Item>
                        )}
                      />
                    ) : <Empty description="Chưa có đơn thuốc" />,
                  },
                ]}
              />
            </Card>
          ) : (
            <Card><Empty description="Không tải được hồ sơ" /></Card>
          )}
        </div>
      </div>

      {selected && detail && (
        <>
          <PrescriptionModal
            open={rxOpen}
            patientId={selected}
            patientName={detail.name}
            practitionerId={session.id}
            onClose={() => setRxOpen(false)}
            onDone={() => open(selected)}
          />
          <AllergyModal
            open={allergyOpen}
            patientId={selected}
            patientName={detail.name}
            onClose={() => setAllergyOpen(false)}
            onDone={() => open(selected)}
          />
          <CbcModal
            open={cbcOpen}
            patientId={selected}
            patientName={detail.name}
            onClose={() => setCbcOpen(false)}
            onDone={() => open(selected)}
          />
        </>
      )}

      <RegisterPatientModal
        open={registerOpen}
        onClose={() => setRegisterOpen(false)}
        onDone={(id) => open(id)}
      />
    </div>
  )
}
