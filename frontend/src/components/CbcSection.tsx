import { useEffect, useState } from 'react'
import { Segmented, Select, Alert, Table, Empty, Spin } from 'antd'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

const CBC_PARAMS = [
  'Tiểu cầu (PLT)', 'Bạch cầu (WBC)', 'Hemoglobin', 'Hematocrit',
  'Hồng cầu (RBC)', 'MCV', 'MCH', 'MCHC',
]

const DENGUE: Record<string, { label: string; type: 'error' | 'warning' | 'success' | 'info' }> = {
  very_likely: { label: 'Rất có thể SXHD', type: 'error' },
  likely: { label: 'Có thể SXHD', type: 'warning' },
  possible: { label: 'Nghi ngờ SXHD', type: 'warning' },
  unlikely: { label: 'Ít khả năng SXHD', type: 'success' },
}

export default function CbcSection({ patientId }: { patientId: string }) {
  const [obs, setObs] = useState<any[]>([])
  const [dengue, setDengue] = useState<any>(null)
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const [param, setParam] = useState('Tiểu cầu (PLT)')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!patientId) return
    setLoading(true)
    Promise.all([
      fetch(`/api/observations?patient_id=${patientId}&category=laboratory&_count=100`).then((r) => r.json()),
      fetch(`/api/dengue/${patientId}`).then((r) => r.json()).catch(() => null),
    ])
      .then(([o, d]) => {
        setObs((o.observations || []).filter((x: any) => CBC_PARAMS.includes(x.name)))
        setDengue(d)
      })
      .finally(() => setLoading(false))
  }, [patientId])

  if (loading) return <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
  if (!obs.length) return <Empty description="Chưa có dữ liệu CBC" />

  // Nhóm theo ngày
  const byDate: Record<string, Record<string, number>> = {}
  const present = new Set<string>()
  for (const o of obs) {
    byDate[o.date] = byDate[o.date] || {}
    const num = parseFloat(o.value)
    if (!isNaN(num)) byDate[o.date][o.name] = num
    present.add(o.name)
  }
  const dates = Object.keys(byDate).sort()
  const chartData = dates.map((d) => ({ date: d.slice(5), ...byDate[d] }))
  const availParams = CBC_PARAMS.filter((p) => present.has(p))

  // Bảng: cột ngày
  const columns = [
    { title: 'Chỉ số', dataIndex: 'name', fixed: 'left' as const, width: 130 },
    ...dates.map((d) => ({ title: d.slice(5), dataIndex: d, render: (v: any) => (v ?? '—') })),
  ]
  const tableData = availParams.map((p, i) => ({
    key: i, name: p, ...Object.fromEntries(dates.map((d) => [d, byDate[d][p]])),
  }))

  const s = dengue?.screening || {}
  const dg = DENGUE[s.dengue_likelihood]

  return (
    <div>
      {dg && (
        <Alert
          style={{ marginBottom: 12 }}
          type={dg.type}
          showIcon
          message={<>Sàng lọc SXHD: <b>{dg.label}</b></>}
          description={(s.findings || []).slice(0, 2).join('; ') || s.interpretation}
        />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10, gap: 8 }}>
        <Segmented
          options={[{ label: 'Biểu đồ', value: 'chart' }, { label: 'Bảng', value: 'table' }]}
          value={view}
          onChange={(v) => setView(v as any)}
        />
        {view === 'chart' && (
          <Select
            value={param}
            style={{ width: 180 }}
            onChange={setParam}
            options={availParams.map((p) => ({ label: p, value: p }))}
          />
        )}
      </div>

      {view === 'chart' ? (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={chartData} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Line type="monotone" dataKey={param} stroke="#005d5d" strokeWidth={2} dot={{ r: 3 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <Table size="small" columns={columns} dataSource={tableData} pagination={false} scroll={{ x: 'max-content' }} />
      )}
    </div>
  )
}
