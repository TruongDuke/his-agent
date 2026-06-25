import { useState } from 'react'
import { Radio, InputNumber, Button, Switch } from 'antd'

const SYMPTOMS: [string, string][] = [
  ['s3', 'Buồn nôn hoặc nôn ói'],
  ['s4', 'Phát ban, nổi mẩn đỏ trên da'],
  ['s5', 'Đau cơ, đau khớp, nhức hai hố mắt'],
  ['s6', 'Chấm đỏ dưới da hoặc bầm tím không rõ nguyên nhân'],
]
const WARNINGS: [string, string][] = [
  ['w7', 'Đau bụng nhiều hoặc đau vùng gan'],
  ['w8', 'Nôn ói liên tục nhiều lần'],
  ['w9', 'Chảy máu chân răng, chảy máu mũi, phân đen'],
  ['w10', 'Đi tiểu ít hoặc nước tiểu sẫm màu'],
  ['w11', 'Vật vã, lờ đờ, mệt lả nhiều'],
]

function YesNo({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
  return (
    <Radio.Group
      size="small"
      optionType="button"
      buttonStyle="solid"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      options={[{ label: 'Có', value: true }, { label: 'Không', value: false }]}
    />
  )
}

export default function DengueForm({ onSubmit }: { onSubmit: (text: string) => void }) {
  const [epi, setEpi] = useState(false)
  const [fever, setFever] = useState<number>(0)
  const [ans, setAns] = useState<Record<string, boolean>>({})
  const [done, setDone] = useState(false)
  const set = (k: string, v: boolean) => setAns((p) => ({ ...p, [k]: v }))

  function submit() {
    const yn = (b?: boolean) => (b ? 'Có' : 'Không')
    const lines = [
      `1. Đang ở/đến vùng có dịch: ${yn(epi)}`,
      `2. Sốt: ${fever} ngày`,
      ...SYMPTOMS.map(([k, l], i) => `${i + 3}. ${l}: ${yn(ans[k])}`),
      ...WARNINGS.map(([k, l], i) => `${i + 7}. ${l}: ${yn(ans[k])}`),
    ]
    setDone(true)
    onSubmit(lines.join('\n'))
  }

  const Row = ({ k, label }: { k: string; label: string }) => (
    <div className="dgf-q">
      <span className="dgf-label">{label}</span>
      <YesNo value={!!ans[k]} onChange={(v) => set(k, v)} />
    </div>
  )

  return (
    <div className="dengue-form">
      <div className="dgf-title">🦟 Phiếu sàng lọc Sốt xuất huyết</div>

      <div className="dgf-section">A. Dịch tễ</div>
      <div className="dgf-q">
        <span className="dgf-label">Đang sống/vừa đến vùng có dịch?</span>
        <Switch checkedChildren="Có" unCheckedChildren="Không" checked={epi} onChange={setEpi} />
      </div>
      <div className="dgf-q">
        <span className="dgf-label">Sốt mấy ngày rồi? (0 = không sốt)</span>
        <InputNumber min={0} max={30} value={fever} onChange={(v) => setFever(v || 0)} style={{ width: 90 }} />
      </div>

      <div className="dgf-section">B. Triệu chứng</div>
      {SYMPTOMS.map(([k, l]) => <Row key={k} k={k} label={l} />)}

      <div className="dgf-section">C. Dấu hiệu cảnh báo</div>
      {WARNINGS.map(([k, l]) => <Row key={k} k={k} label={l} />)}

      <Button type="primary" block onClick={submit} disabled={done} style={{ marginTop: 12 }}>
        {done ? 'Đã gửi' : 'Gửi kết quả sàng lọc'}
      </Button>
    </div>
  )
}
