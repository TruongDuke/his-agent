/**
 * Ghi âm micro và mã hoá thành WAV 16kHz mono.
 *
 * Không dùng MediaRecorder vì nó cho ra webm/opus, mà server nhận dạng giọng nói chỉ
 * ghi rõ là nhận wav/mp3 — không kiểm chứng được webm nên chọn đường chắc chắn.
 * Tự lấy PCM từ Web Audio rồi ghép header WAV, khỏi phụ thuộc codec của trình duyệt.
 */

const TARGET_RATE = 16000

export interface Recorder {
  stop: () => Promise<Blob>
  cancel: () => void
}

/** Hạ tần số lấy mẫu bằng cách lấy trung bình từng cụm — đủ tốt cho tiếng nói. */
function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input
  const ratio = fromRate / toRate
  const out = new Float32Array(Math.floor(input.length / ratio))
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(Math.floor((i + 1) * ratio), input.length)
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    out[i] = end > start ? sum / (end - start) : 0
  }
  return out
}

function encodeWav(samples: Float32Array, rate: number): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buf)
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
  }
  writeStr(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeStr(8, 'WAVE')
  writeStr(12, 'fmt ')
  view.setUint32(16, 16, true)          // kích thước khối fmt
  view.setUint16(20, 1, true)           // PCM
  view.setUint16(22, 1, true)           // mono
  view.setUint32(24, rate, true)
  view.setUint32(28, rate * 2, true)    // byte/giây
  view.setUint16(32, 2, true)           // byte/mẫu
  view.setUint16(34, 16, true)          // bit/mẫu
  writeStr(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let off = 44
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([view], { type: 'audio/wav' })
}

export async function startRecording(): Promise<Recorder> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  })
  const ctx = new AudioContext()
  const source = ctx.createMediaStreamSource(stream)
  const node = ctx.createScriptProcessor(4096, 1, 1)
  const chunks: Float32Array[] = []

  node.onaudioprocess = (e) => {
    chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
  }
  source.connect(node)
  node.connect(ctx.destination)

  const teardown = () => {
    node.disconnect()
    source.disconnect()
    stream.getTracks().forEach((t) => t.stop())
    ctx.close().catch(() => {})
  }

  return {
    cancel: teardown,
    stop: async () => {
      const rate = ctx.sampleRate
      teardown()
      const total = chunks.reduce((n, c) => n + c.length, 0)
      const merged = new Float32Array(total)
      let off = 0
      for (const c of chunks) { merged.set(c, off); off += c.length }
      return encodeWav(downsample(merged, rate, TARGET_RATE), TARGET_RATE)
    },
  }
}

/** Gửi bản ghi lên backend, nhận lại chữ. */
export async function transcribe(wav: Blob): Promise<{ text: string; empty: boolean }> {
  const fd = new FormData()
  fd.append('file', wav, 'mic.wav')
  fd.append('language', 'vi')
  const r = await fetch('/api/voice/stt', { method: 'POST', body: fd })
  if (!r.ok) throw new Error((await r.text()).slice(0, 120))
  return r.json()
}

/** Đọc một đoạn chữ thành tiếng. Trả về hàm dừng để bấm lần nữa là tắt. */
export async function speak(text: string): Promise<HTMLAudioElement> {
  const r = await fetch('/api/voice/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!r.ok) throw new Error((await r.text()).slice(0, 120))
  const audio = new Audio(URL.createObjectURL(await r.blob()))
  await audio.play()
  return audio
}
