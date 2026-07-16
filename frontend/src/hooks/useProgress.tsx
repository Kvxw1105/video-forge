import { useState, useRef, useCallback, useEffect } from 'react'

export function useProgress() {
  const [active, setActive] = useState(false)
  const [progress, setProgress] = useState(0)
  const [label, setLabel] = useState('')
  const [failed, setFailed] = useState(false)
  const rafRef = useRef<number>(0)
  const startRef = useRef(0)

  const tick = useCallback(() => {
    const elapsed = Date.now() - startRef.current
    const p = 1 - Math.exp(-elapsed / 4000)
    const capped = Math.min(p * 99, 99)
    setProgress(capped)
    if (capped < 99) {
      rafRef.current = requestAnimationFrame(tick)
    }
  }, [])

  const start = useCallback((msg?: string) => {
    cancelAnimationFrame(rafRef.current)
    setActive(true)
    setFailed(false)
    setProgress(0)
    setLabel(msg || '处理中...')
    startRef.current = Date.now()
    rafRef.current = requestAnimationFrame(tick)
  }, [tick])

  const set = useCallback((nextProgress: number, msg?: string) => {
    cancelAnimationFrame(rafRef.current)
    setActive(true)
    setFailed(false)
    setProgress(Math.max(0, Math.min(100, nextProgress)))
    if (msg) setLabel(msg)
  }, [])

  const finish = useCallback((msg?: string) => {
    cancelAnimationFrame(rafRef.current)
    setFailed(false)
    setProgress(100)
    if (msg) setLabel(msg)
    setTimeout(() => { setActive(false); setProgress(0) }, 800)
  }, [])

  const fail = useCallback((msg?: string) => {
    cancelAnimationFrame(rafRef.current)
    setFailed(true)
    setLabel(msg || '操作失败')
    setTimeout(() => { setActive(false); setProgress(0); setFailed(false) }, 3000)
  }, [])

  useEffect(() => () => cancelAnimationFrame(rafRef.current), [])

  return { active, progress, label, failed, start, set, finish, fail }
}

export function LoadingProgress({ active, progress, label, failed }: {
  active: boolean; progress: number; label: string; failed?: boolean
}) {
  if (!active) return null
  return (
    <div className="w-full overflow-hidden rounded-md" style={{ height: 28, background: 'var(--bg-elevated)' }}>
      <div className="h-full flex items-center px-3 gap-2">
        <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border-subtle)' }}>
          <div
            className="h-full rounded-full transition-all duration-300 ease-out"
            style={{
              width: failed ? '100%' : `${progress}%`,
              background: failed
                ? '#a0674a'
                : 'linear-gradient(90deg, var(--accent), var(--accent-light, var(--accent)))',
            }}
          />
        </div>
        <span className="text-[10px] font-mono whitespace-nowrap" style={{ color: failed ? '#a0674a' : 'var(--text-muted)' }}>
          {failed ? '失败' : progress < 100 ? `${Math.round(progress)}%` : '完成'}
        </span>
        <span className="text-[10px] whitespace-nowrap truncate max-w-[220px]" style={{ color: 'var(--text-secondary)' }}>
          {label}
        </span>
      </div>
    </div>
  )
}
