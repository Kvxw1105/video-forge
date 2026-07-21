import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../lib/api'
import type { SystemReadinessResponse } from '../types/systemReadiness'

interface SystemReadinessState {
  data: SystemReadinessResponse | null
  loading: boolean
  refreshing: boolean
  error: Error | null
  refresh: () => Promise<void>
}

const SystemReadinessContext = createContext<SystemReadinessState | null>(null)

export function SystemReadinessProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<SystemReadinessResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const mounted = useRef(true)
  const loaded = useRef(false)

  const load = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true)
    else setLoading(true)
    try {
      const next = await api.getSystemReadiness({ refresh: manual })
      if (!mounted.current) return
      setData(next)
      setError(null)
    } catch (cause) {
      if (!mounted.current) return
      setError(cause instanceof Error ? cause : new Error('系统检查请求失败'))
    } finally {
      if (!mounted.current) return
      if (manual) setRefreshing(false)
      else setLoading(false)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    if (!loaded.current) {
      loaded.current = true
      void load(false)
    }
    return () => { mounted.current = false }
  }, [load])

  const refresh = useCallback(() => load(true), [load])
  return <SystemReadinessContext.Provider value={{ data, loading, refreshing, error, refresh }}>{children}</SystemReadinessContext.Provider>
}

export function useSystemReadiness() {
  const value = useContext(SystemReadinessContext)
  if (!value) throw new Error('useSystemReadiness must be used inside SystemReadinessProvider')
  return value
}
