import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import { ToastContainer } from '../ui/Toast'

/**
 * Shell — the persistent app chrome.
 * Used as the React Router layout route in App.tsx so all child pages
 * share the sidebar + topbar without re-mounting them on navigation.
 */
export default function Shell() {
  return (
    <div
      style={{
        display:    'flex',
        height:     '100vh',
        overflow:   'hidden',
        background: 'var(--bg-base)',
        color:      'var(--text-1)',
      }}
    >
      <Sidebar />
      <div
        style={{
          flex:          1,
          display:       'flex',
          flexDirection: 'column',
          overflow:      'hidden',
          minWidth:      0,
        }}
      >
        <TopBar />
        <main
          style={{
            flex:       1,
            overflowY:  'auto',
            padding:    '22px 24px',
            background: 'var(--bg-base)',
          }}
        >
          <Outlet />
        </main>
      </div>
      <ToastContainer />
    </div>
  )
}
