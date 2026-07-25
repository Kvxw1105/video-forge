import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { Check, FileText, FilmSlate, GitBranch, Play, Robot, UploadSimple, WarningCircle } from '@phosphor-icons/react'
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
  const [projects, setProjects] = useState<any[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [selectedProject, setSelectedProject] = useState<any>(null)
  const [srtFileName, setSrtFileName] = useState('')
  const [intakeNotice, setIntakeNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const approval = useMemo(() => (run?.approvals || []).find((item: any) => item.status === 'pending'), [run])
  const subtitleCount = Array.isArray(selectedProject?.subtitles) ? selectedProject.subtitles.length : 0
  const projectScript = String(selectedProject?.script || '').trim()

  const load = async (runId: string) => {
    const result = await Promise.all([api.getDirectorRun(runId), api.getDirectorRunEvents(runId)])
    setRun(result[0])
    setEvents(result[1].events || [])
  }

  useEffect(() => {
    api.getVersion().then(setVersion).catch(() => undefined)
    api.listProjects().then(setProjects).catch(() => undefined)
    api.listDirectorRuns().then((runs: any[]) => {
      if (runs[0]?.runId) load(runs[0].runId).catch(() => undefined)
    }).catch(() => undefined)
  }, [])

  const selectProject = async (projectId: string) => {
    setSelectedProjectId(projectId)
    setSelectedProject(null)
    setSrtFileName('')
    setIntakeNotice('')
    if (!projectId) return
    setBusy('project')
    setError('')
    try {
      setSelectedProject(await api.getProject(projectId))
    } catch (requestError: any) {
      setError(requestError.message || '读取项目失败')
    } finally {
      setBusy('')
    }
  }

  const importSrt = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !selectedProjectId) return
    setBusy('srt')
    setError('')
    setIntakeNotice('')
    try {
      const result = await api.importSrt(selectedProjectId, file)
      setSelectedProject(result.project)
      setSrtFileName(file.name)
      setIntakeNotice(`已导入 ${result.subtitleCount} 条字幕${result.ignoredCount ? `，忽略 ${result.ignoredCount} 条无效片段` : ''}`)
    } catch (requestError: any) {
      setError(requestError.message || '导入 SRT 失败')
    } finally {
      setBusy('')
    }
  }

  const createRun = async () => {
    setBusy('create')
    setError('')
    try {
      const created = await api.createDirectorRun({ task, recipeId: 'structured-knowledge-video', projectId: selectedProject?.id || undefined })
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
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="label-cinematic">输入资料</p>
                {busy === 'project' && <span className="text-xs" style={{ color: 'var(--text-muted)' }}>读取项目...</span>}
              </div>
              <select className="input-cinematic w-full text-sm" value={selectedProjectId} onChange={event => selectProject(event.target.value)} disabled={busy === 'project'}>
                <option value="">不绑定项目（仅任务说明）</option>
                {projects.map(project => <option key={project.id} value={project.id}>{project.name || project.id}</option>)}
              </select>
              {selectedProject && <div className="rounded-lg p-3 text-xs space-y-2" style={{ background: 'var(--bg-elevated)' }}>
                <div className="flex items-center gap-2"><FilmSlate size={14} /><b>{selectedProject.name}</b></div>
                <div style={{ color: 'var(--text-muted)' }}>{subtitleCount} 条字幕 · {projectScript.length} 字文案{selectedProject.structuredContent ? ' · 已结构化' : ''}</div>
                <label className="btn-cinematic inline-flex items-center gap-2 cursor-pointer">
                  <UploadSimple size={15} /> {busy === 'srt' ? '导入中...' : '导入 SRT'}
                  <input className="sr-only" type="file" accept=".srt,application/x-subrip,text/plain" onChange={importSrt} disabled={busy === 'srt'} />
                </label>
                {srtFileName && <div className="flex items-center gap-2 break-all"><FileText size={14} />{srtFileName}</div>}
                {intakeNotice && <div style={{ color: 'var(--accent)' }}>{intakeNotice}</div>}
              </div>}
              {!selectedProject && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>选择项目后可导入 SRT；字幕会写入项目时间轴，并作为 Director 的结构化上下文。</p>}
            </div>
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
