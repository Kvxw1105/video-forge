import { useEffect, useMemo, useState } from 'react'
import { Check, FilmSlate, GitBranch, Play, Robot, WarningCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'

const DEFAULT_TASK = '把这篇文案生成一个可预览、可导入剪映的视频草稿。'

function shortPath(value: string) {
  const parts = value.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || value
}

export default function DirectorDesk() {
  const [task, setTask] = useState(DEFAULT_TASK)
  const [run, setRun] = useState<any>(null)
  const [events, setEvents] = useState<any[]>([])
  const [version, setVersion] = useState<any>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const approval = useMemo(() => (run?.approvals || []).find((item: any) => item.status === 'pending'), [run])

  const load = async (runId: string) => {
    const result = await Promise.all([api.getDirectorRun(runId), api.getDirectorRunEvents(runId)])
    setRun(result[0])
    setEvents(result[1].events || [])
  }

  useEffect(() => {
    api.getVersion().then(setVersion).catch(() => undefined)
    api.listDirectorRuns().then((runs: any[]) => {
      if (runs[0]?.runId) load(runs[0].runId).catch(() => undefined)
    }).catch(() => undefined)
  }, [])

  const createRun = async () => {
    setBusy('create')
    setError('')
    try {
      const created = await api.createDirectorRun({ task, recipeId: 'structured-knowledge-video' })
      await load(created.runId)
    } catch (requestError: any) {
      setError(requestError.message || '创建 Director Run 失败')
    } finally {
      setBusy('')
    }
  }

  const resolveApproval = async () => {
    if (!run?.runId || !approval?.approvalId) return
    setBusy('approval')
    setError('')
    try {
      await api.approveDirectorRun(run.runId, approval.approvalId, 'replace')
      await load(run.runId)
    } catch (requestError: any) {
      setError(requestError.message || '审批恢复失败')
    } finally {
      setBusy('')
    }
  }

  return (
    <main className="min-h-[100dvh] workbench-shell p-4 md:p-6">
      <div className="max-w-7xl mx-auto space-y-4">
        <header className="card-cinematic p-5 flex flex-wrap items-center gap-4">
          <div className="home-brand-mark"><Robot size={20} weight="fill" /></div>
          <div className="flex-1 min-w-[240px]">
            <p className="section-index">PI VIDEO DIRECTOR / LITE</p>
            <h1 className="text-2xl font-heading">Director Desk</h1>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>创建任务、查看真实事件、处理审批、取得候选工件。</p>
          </div>
          <div className="text-xs grid gap-1" style={{ color: 'var(--text-secondary)' }}>
            <span><GitBranch size={13} className="inline mr-1" />{version?.branch || 'unknown'}</span>
            <span>{String(version?.commit || '').slice(0, 8) || 'no-sha'} / {version?.environment || 'local'}</span>
          </div>
        </header>

        <section className="grid lg:grid-cols-[380px_minmax(0,1fr)] gap-4">
          <aside className="card-cinematic p-5 space-y-4">
            <div>
              <p className="label-cinematic">任务</p>
              <textarea className="input-cinematic w-full min-h-[180px] mt-2 text-sm" value={task} onChange={event => setTask(event.target.value)} />
            </div>
            {error && <div className="operation-error">{error}</div>}
            <button className="btn-gold w-full justify-center" disabled={!task.trim() || busy === 'create'} onClick={createRun}>
              <Play size={16} /> {busy === 'create' ? '正在创建...' : '创建 Director Run'}
            </button>
            {run && <div className="rounded-lg p-3 text-xs space-y-2" style={{ background: 'var(--bg-elevated)' }}>
              <div>Run: <b>{run.runId}</b></div>
              <div>Status: <b>{run.status}</b></div>
              <div>Mock: {String(run.mockTransport)} / Network: {run.networkCalls}</div>
              <div>Live Call: {String(run.liveCallPerformed)}</div>
            </div>}
            {approval && <div className="rounded-lg border p-4 space-y-3" style={{ borderColor: 'var(--accent)', background: 'var(--bg-surface)' }}>
              <div className="flex items-center gap-2 text-sm"><WarningCircle size={16} />审批：{approval.operation}</div>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{approval.message}</p>
              <button className="btn-gold w-full justify-center" disabled={busy === 'approval'} onClick={resolveApproval}>
                <Check size={15} /> replace 并恢复执行
              </button>
            </div>}
          </aside>

          <div className="grid xl:grid-cols-2 gap-4">
            <section className="card-cinematic p-5 space-y-3">
              <p className="label-cinematic">Run Timeline</p>
              <div className="space-y-2 max-h-[560px] overflow-auto pr-1">
                {events.map(event => <div key={event.sequence} className="rounded-lg p-3 text-xs" style={{ background: 'var(--bg-elevated)' }}>
                  <div className="flex justify-between gap-3"><b>#{event.sequence} {event.type}</b><span>{String(event.time || '').slice(11, 19)}</span></div>
                  {event.toolName && <div className="mt-1">Tool: {event.toolName}</div>}
                  {event.sceneId && <div>Scene: {event.sceneId}</div>}
                </div>)}
                {!events.length && <div className="empty-state"><FilmSlate size={28} /><span>暂无事件</span></div>}
              </div>
            </section>
            <section className="card-cinematic p-5 space-y-3">
              <p className="label-cinematic">Artifacts</p>
              <div className="space-y-2">
                {(run?.artifacts || []).map((artifact: any) => <div key={artifact.artifactId + ':' + artifact.path} className="rounded-lg p-3 text-xs" style={{ background: 'var(--bg-elevated)' }}>
                  <b>{artifact.artifactType}</b>
                  <div className="break-all mt-1">{shortPath(artifact.path || '')}</div>
                  <div className="mt-1" style={{ color: 'var(--text-muted)' }}>{artifact.source?.plugin || artifact.artifactId}</div>
                </div>)}
                {!run?.artifacts?.length && <div className="empty-state"><FilmSlate size={28} /><span>暂无工件</span></div>}
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  )
}
