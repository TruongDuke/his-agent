import { useState } from 'react'
import Login from './pages/Login'
import ChatPage from './pages/ChatPage'
import DoctorDashboard from './pages/DoctorDashboard'
import type { Session } from './api'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)

  if (!session) return <Login onLogin={setSession} />
  if (session.role === 'doctor')
    return <DoctorDashboard session={session} onLogout={() => setSession(null)} />
  return <ChatPage session={session} onLogout={() => setSession(null)} />
}
