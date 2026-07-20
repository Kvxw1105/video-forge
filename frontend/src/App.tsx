import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import React from 'react'
import { ArrowRight, Warning, X } from '@phosphor-icons/react'
import ErrorBoundary from './components/ui/ErrorBoundary'
import Home from './pages/Home'
import Editor from './pages/Editor'
import Library from './pages/Library'
import SystemReadiness from './pages/SystemReadiness'
import { SystemReadinessProvider, useSystemReadiness } from './contexts/SystemReadinessContext'

export default function App() {
  return (
    <ErrorBoundary>
      <SystemReadinessProvider>
        <BrowserRouter>
          <ReadinessBanner />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/editor/:id" element={<Editor />} />
            <Route path="/library" element={<Library />} />
            <Route path="/settings/system" element={<SystemReadiness />} />
          </Routes>
        </BrowserRouter>
      </SystemReadinessProvider>
    </ErrorBoundary>
  )
}

function ReadinessBanner() {
  const { data } = useSystemReadiness()
  const location = useLocation()
  const navigate = useNavigate()
  const [dismissed, setDismissed] = React.useState(false)
  const signature = data ? `${data.status}:${data.checks.filter(item => item.status !== 'pass').map(item => item.id).join(',')}` : ''

  React.useEffect(() => {
    setDismissed(signature ? sessionStorage.getItem(`vf-readiness-banner:${signature}`) === 'dismissed' : false)
  }, [signature])

  if (!data || data.status === 'ready' || dismissed || location.pathname === '/settings/system') return null
  const blocked = data.status === 'blocked'
  const dismiss = () => { sessionStorage.setItem(`vf-readiness-banner:${signature}`, 'dismissed'); setDismissed(true) }
  return <div className={`readiness-global-banner ${blocked ? 'is-blocked' : 'is-degraded'}`} role="status"><Warning size={17} weight="fill" /><div><strong>{blocked ? '运行环境存在阻塞项' : '部分功能暂时受限'}</strong><span>{blocked ? '请查看系统检查并处理必要问题。' : 'VideoForge 可以继续使用，但部分能力可能不可用。'}</span></div><button onClick={() => navigate('/settings/system')} className="readiness-banner-action">查看系统检查<ArrowRight size={14} /></button><button onClick={dismiss} className="readiness-banner-close" aria-label="关闭提示"><X size={15} /></button></div>
}
