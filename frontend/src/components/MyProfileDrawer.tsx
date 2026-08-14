import { useEffect, useState } from 'react'
import { Drawer, Descriptions, Tabs, Table, Tag, Empty, Spin, List, Typography, Card } from 'antd'
import CbcSection from './CbcSection'
import MedRemindersSection from './MedRemindersSection'

const { Text } = Typography

const STATUS_VI: Record<string, string> = {
  booked: 'Đã xác nhận', fulfilled: 'Đã khám', cancelled: 'Đã huỷ',
  proposed: 'Chờ xác nhận', pending: 'Chờ xác nhận', noshow: 'Vắng mặt',
}

export default function MyProfileDrawer({
  open, patientId, onClose,
}: {
  open: boolean
  patientId: string
  onClose: () => void
}) {
  const [detail, setDetail] = useState<any>(null)
  const [allergies, setAllergies] = useState<any[]>([])
  const [prescriptions, setPrescriptions] = useState<any[]>([])
  const [notes, setNotes] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open || !patientId) return
    setLoading(true)
    Promise.all([
      fetch('/api/patient/' + patientId).then((r) => r.json()),
      fetch('/api/allergies/' + patientId).then((r) => r.json()).catch(() => ({})),
      fetch('/api/prescriptions/' + patientId).then((r) => r.json()).catch(() => ({})),
      fetch('/api/patient/' + patientId + '/clinical-impressions').then((r) => r.json()).catch(() => ({})),
    ])
      .then(([p, a, rx, ci]) => {
        setDetail(p)
        setAllergies(a.allergies || [])
        setPrescriptions(rx.prescriptions || [])
        setNotes(ci.impressions || [])
      })
      .finally(() => setLoading(false))
  }, [open, patientId])

  const obsCols = [
    { title: 'Chỉ số', dataIndex: 'name' },
    { title: 'Giá trị', dataIndex: 'value', render: (v: string, r: any) => <b>{v} {r.unit}</b> },
    { title: 'Ngày', dataIndex: 'date', width: 110 },
  ]

  // rootClassName "profile-drawer": CSS ép width 100% khi ≤768px, vì 520px cứng
  // rộng hơn bề ngang điện thoại.
  return (
    <Drawer title="Hồ sơ của tôi" open={open} onClose={onClose} width={520} rootClassName="profile-drawer">
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
      ) : detail ? (
        <>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="Họ tên">{detail.name}</Descriptions.Item>
            <Descriptions.Item label="Giới tính">{detail.gender || '—'}</Descriptions.Item>
            <Descriptions.Item label="Tuổi">{detail.age || '—'}</Descriptions.Item>
            <Descriptions.Item label="SĐT">{detail.phone || '—'}</Descriptions.Item>
            <Descriptions.Item label="Email">{detail.email || '—'}</Descriptions.Item>
          </Descriptions>
          <Tabs
            size="small"
            style={{ marginTop: 16 }}
            items={[
              {
                key: 'obs', label: 'Sức khỏe',
                children: (
                  <>
                    <Text strong>Xét nghiệm</Text>
                    <Table size="small" columns={obsCols} dataSource={(detail.labs || []).map((x: any, i: number) => ({ ...x, key: i }))} pagination={false} locale={{ emptyText: 'Chưa có' }} scroll={{ x: 'max-content' }} style={{ marginBottom: 16 }} />
                    <Text strong>Diễn tiến CBC & sàng lọc SXHD</Text>
                    <div style={{ marginTop: 8 }}><CbcSection patientId={patientId} /></div>
                  </>
                ),
              },
              {
                key: 'allergy', label: `Dị ứng (${allergies.length})`,
                children: allergies.length ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {allergies.map((a, i) => (
                      <Tag key={i} color={a.criticality === 'high' ? 'red' : 'orange'} style={{ padding: '4px 10px' }}>
                        <b>{a.substance}</b>{a.severity_vi ? ` — ${a.severity_vi}` : ''}
                      </Tag>
                    ))}
                  </div>
                ) : <Empty description="Không có dị ứng ghi nhận" />,
              },
              {
                key: 'remind', label: 'Nhắc uống thuốc',
                children: <MedRemindersSection patientId={patientId} />,
              },
              {
                key: 'rx', label: `Đơn thuốc (${prescriptions.length})`,
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
              {
                key: 'appts', label: `Lịch hẹn (${(detail.appointments || []).length})`,
                children: (detail.appointments || []).length ? (
                  <List
                    dataSource={detail.appointments}
                    renderItem={(a: any) => (
                      <List.Item>
                        <List.Item.Meta
                          title={a.start}
                          description={<><Tag color="cyan">{a.department || '—'}</Tag><Tag>{STATUS_VI[a.status] || a.status}</Tag></>}
                        />
                      </List.Item>
                    )}
                  />
                ) : <Empty description="Không có lịch hẹn sắp tới" />,
              },
              {
                key: 'notes', label: `Ghi chú khám (${notes.length})`,
                children: notes.length ? (
                  notes.map((ci: any, i: number) => (
                    <Card key={i} size="small" style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>📅 {ci.date || '—'}</div>
                      {ci.diagnosis && <div><Text type="secondary">Chẩn đoán: </Text>{ci.diagnosis}</div>}
                      {ci.notes && <div><Text type="secondary">Ghi chú: </Text>{ci.notes}</div>}
                      {ci.plan && <div><Text type="secondary">Kế hoạch: </Text>{ci.plan}</div>}
                    </Card>
                  ))
                ) : <Empty description="Chưa có ghi chú khám" />,
              },
            ]}
          />
        </>
      ) : (
        <Empty description="Không tải được hồ sơ" />
      )}
    </Drawer>
  )
}
