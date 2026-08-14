import { Layout } from 'antd'
import Header from '../components/Header'
import ChatPanel from '../components/ChatPanel'
import type { Session } from '../api'

export default function ChatPage({ session, onLogout }: { session: Session; onLogout: () => void }) {
  return (
    <Layout className="app-shell">
      <Header session={session} onLogout={onLogout} />
      <ChatPanel session={session} autoInit={session.role === 'patient' && !session.guest && !!session.id} />
    </Layout>
  )
}
