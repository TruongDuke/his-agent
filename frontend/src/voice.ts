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


/* ────────────── HỘI THOẠI LIÊN TỤC ──────────────
 * ASR chỉ nhận trọn câu, không nhận luồng — nên phải tự biết lúc nào người dùng nói
 * xong rồi mới gửi đi. Dò bằng mức năng lượng của khung âm thanh: có tiếng thì thu,
 * im quá lâu thì chốt một lượt.
 */

const SILENCE_MS = 900      // im bao lâu thì coi là nói xong
const MIN_SPEECH_MS = 300   // ngắn hơn thì coi là tiếng động, bỏ
const RMS_SPEECH = 0.015    // ngưỡng coi là có tiếng nói

// Trong lúc agent đang đọc, micro vẫn thu được chính tiếng loa. Nếu dùng ngưỡng
// thường thì agent tự cắt lời mình sau 1-2 giây. Nên lúc đó đòi tiếng TO HƠN HẲN và
// phải kéo dài, mới coi là người dùng thực sự chen vào.
const RMS_BARGE = 0.06
const BARGE_MIN_MS = 400
// Nghỉ một nhịp sau khi agent dứt lời, tránh thu phải đuôi tiếng vọng.
const COOLDOWN_MS = 350

export interface VoiceSession {
  stop: () => void
  /** Báo cho vòng nghe biết agent đang phát tiếng, để nhận ra khi bị cắt lời. */
  setSpeaking: (v: boolean) => void
}

export interface VoiceHandlers {
  onListening: () => void
  onThinking: () => void
  onUtterance: (wav: Blob) => Promise<void>
  onBargeIn?: () => void
  onError: (msg: string) => void
}

/**
 * Mở micro và chạy vòng: nghe → thấy nói xong → gọi onUtterance → nghe tiếp.
 * Trong lúc onUtterance chạy (nhận dạng + hỏi agent + đọc trả lời) vẫn tiếp tục
 * nghe, để người dùng cắt lời được.
 */
export async function startConversation(h: VoiceHandlers): Promise<VoiceSession> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  })
  const ctx = new AudioContext()
  const source = ctx.createMediaStreamSource(stream)
  const node = ctx.createScriptProcessor(4096, 1, 1)

  let chunks: Float32Array[] = []
  let speaking = false          // người dùng đang nói
  let speechMs = 0
  let silenceMs = 0
  let handling = false          // đang xử lý một lượt
  let stopped = false
  let busySpeaking = false      // agent đang phát tiếng
  let bargeMs = 0               // đã nghe tiếng chen vào bao lâu
  let cooldownMs = 0            // nghỉ sau khi agent dứt lời

  const frameMs = (4096 / ctx.sampleRate) * 1000

  node.onaudioprocess = async (e) => {
    if (stopped) return
    const buf = e.inputBuffer.getChannelData(0)
    let sum = 0
    for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
    const rms = Math.sqrt(sum / buf.length)

    // Agent đang đọc: KHÔNG thu gì cả, chỉ rình xem người dùng có chen vào thật không.
    // Trước đây chỉ cần một khung tiếng to là cắt — mà tiếng loa vọng vào cũng đủ to,
    // nên agent tự ngắt lời mình ngay sau 1-2 giây.
    if (busySpeaking) {
      if (rms > RMS_BARGE) {
        bargeMs += frameMs
        if (bargeMs >= BARGE_MIN_MS) {
          bargeMs = 0
          busySpeaking = false
          speaking = false
          chunks = []
          h.onBargeIn?.()
        }
      } else {
        bargeMs = 0
      }
      return
    }

    if (cooldownMs > 0) { cooldownMs -= frameMs; return }

    const loud = rms > RMS_SPEECH
    if (loud) {
      if (!speaking) { speaking = true; chunks = []; speechMs = 0; h.onListening() }
      silenceMs = 0
      speechMs += frameMs
      chunks.push(new Float32Array(buf))
    } else if (speaking) {
      silenceMs += frameMs
      chunks.push(new Float32Array(buf))   // giữ đuôi để khỏi cụt chữ cuối
      if (silenceMs >= SILENCE_MS) {
        speaking = false
        const captured = chunks
        const ms = speechMs
        chunks = []
        if (ms >= MIN_SPEECH_MS && !handling) {
          handling = true
          h.onThinking()
          try {
            await h.onUtterance(mergeToWav(captured, ctx.sampleRate))
          } catch (err: any) {
            h.onError(err?.message || 'Lỗi xử lý giọng nói')
          } finally {
            handling = false
          }
        }
      }
    }
  }

  source.connect(node)
  node.connect(ctx.destination)

  return {
    setSpeaking: (v: boolean) => {
      busySpeaking = v
      bargeMs = 0
      if (!v) cooldownMs = COOLDOWN_MS   // vừa dứt lời → nghỉ một nhịp
    },
    stop: () => {
      stopped = true
      node.disconnect(); source.disconnect()
      stream.getTracks().forEach((t) => t.stop())
      ctx.close().catch(() => {})
    },
  }
}

function mergeToWav(chunks: Float32Array[], rate: number): Blob {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const merged = new Float32Array(total)
  let off = 0
  for (const c of chunks) { merged.set(c, off); off += c.length }
  return encodeWav(downsample(merged, rate, TARGET_RATE), TARGET_RATE)
}

/** Bóc markdown + cắt câu ở backend, để đọc nối tiếp cho đỡ chờ. */
export async function splitForSpeech(text: string): Promise<string[]> {
  const r = await fetch('/api/voice/split', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!r.ok) return [text]
  return (await r.json()).sentences || [text]
}

/**
 * Đọc lần lượt từng câu. Sinh câu kế trong lúc đang phát câu trước nên người nghe
 * chỉ chờ đúng câu đầu (~1 giây) thay vì chờ cả đoạn (5-6 giây).
 * Trả về hàm dừng để cắt ngang khi người dùng lên tiếng.
 */
export function speakStream(
  sentences: string[],
  onDone?: () => void,
  onError?: (msg: string) => void,
  rate = 1.15,
) {
  let cancelled = false
  let current: HTMLAudioElement | null = null

  const fetchOne = async (s: string): Promise<Blob | null> => {
    try {
      const r = await fetch('/api/voice/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: s, clean: false }),
      })
      if (!r.ok) {
        onError?.(`TTS lỗi ${r.status}: ${(await r.text()).slice(0, 80)}`)
        return null
      }
      return await r.blob()
    } catch (e: any) {
      onError?.('Không gọi được TTS: ' + (e?.message || e))
      return null
    }
  }

  ;(async () => {
    let next = sentences.length ? fetchOne(sentences[0]) : null
    for (let i = 0; i < sentences.length && !cancelled; i++) {
      const blob = await next
      next = i + 1 < sentences.length ? fetchOne(sentences[i + 1]) : null  // sinh trước câu sau
      if (!blob || cancelled) continue
      await new Promise<void>((resolve) => {
        const a = new Audio(URL.createObjectURL(blob))
        a.playbackRate = rate     // giọng gốc đọc hơi thong thả, nhanh nhẹ cho gọn
        current = a
        a.onended = () => resolve()
        a.onerror = () => { onError?.('Không phát được đoạn tiếng'); resolve() }
        // Trình duyệt chặn tự phát thì play() văng lỗi — trước đây nuốt luôn nên
        // im ru mà không ai biết vì sao.
        a.play().catch((e) => {
          onError?.('Trình duyệt chặn phát tiếng: ' + (e?.name || e))
          resolve()
        })
      })
    }
    current = null
    if (!cancelled) onDone?.()
  })()

  return () => {
    cancelled = true
    if (current) { current.pause(); current = null }
  }
}
