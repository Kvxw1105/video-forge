import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

export function useProject(id: string) {
  const [project, setProject] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const p = await api.getProject(id)
      setProject(p)
    } catch (e: any) {
      const msg = e?.message || '加载项目失败'
      console.error(msg, e)
      setError(e?.status ? `${e.status}: ${msg}` : msg)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const update = useCallback(async (data: any) => {
    try {
      const updated = await api.updateProject(id, data)
      setProject(updated)
      return updated
    } catch (e: any) {
      const msg = e?.message || '保存失败'
      console.error(msg, e)
      throw e  // re-throw so callers can handle if needed
    }
  }, [id])

  const refresh = useCallback(async () => {
    const latest = await api.getProject(id)
    setProject(latest)
    return latest
  }, [id])

  return { project, loading, error, reload: load, refresh, update }
}
