import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { Check, ClipboardText, FileText, FilmSlate, GearSix, GitBranch, Play, Robot, UploadSimple, WarningCircle, X } from '@phosphor-icons/react'
import { api } from '../lib/api'

const DEFAULT_TASK = '把这篇文案生成一个可预览、可导入剪映的视频草稿。'
const TEST_TASK = `把这份内容制作成一条 9:16 的知识短视频草稿。

要求：
- 以字幕时间轴为唯一时长依据，不跨字幕块安排画面。
- 每个场景只表达一个明确观点，优先复用已有素材。
- 缺少素材时，为 Scene 001 生成一张简洁的矢量信息卡。
- 在替换 Scene 001 现有素材前，说明替换原因并等待我的审批。`

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
  const [provider, setProvider] = useState<any>(null)
  const [inputMode, setInputMode] = useState<'srt' | 'project'>('srt')
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [selectedProject, setSelectedProject] = useState<any>(null)
  const [srtFileName, setSrtFileName] = useState('')
  const [standaloneSrtIntake, setStandaloneSrtIntake] = useState<any>(null)
  const [intakeNotice, setIntakeNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const approval = useMemo(() => (run?.approvals || []).find((item: any) => item.status === 'pending'), [run])
  const providerReady = Boolean(provider?.enabled && provider?.baseUrl && provider?.model)
  const inputReady = inputMode === 'srt' ? Boolean(standaloneSrtIntake) : Boolean(selectedProject?.id)
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
    api.getAgentProviderSettings().then(setProvider).catch(() => undefined)
    api.listDirectorRuns().then((runs: any[]) => {
      if (runs[0]?.runId) load(runs[0].runId).catch(() => undefined)
    }).catch(() => undefined)
  }, [])

  const selectProject = async (projectId: string) => {
    setSelectedProjectId(projectId)
    setSelectedProject(null)
    setSrtFileName('')
    setStandaloneSrtIntake(null)
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

  const chooseInputMode = (mode: 'srt' | 'project') => {
    setInputMode(mode)
    setError('')
    if (mode === 'srt') {
      setSelectedProjectId('')
      setSelectedProject(null)
    } else {
      setStandaloneSrtIntake(null)
      setSrtFileName('')
    }
    setIntakeNotice('')
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

  const importStandaloneSrt = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setBusy('standalone-srt')
    setError('')
    setIntakeNotice('')
    try {
      const result = await api.uploadDirectorSrtIntake(file)
      setSelectedProjectId('')
      setSelectedProject(null)
      setSrtFileName(file.name)
      setStandaloneSrtIntake(result.intake)
      const readiness = result.intake?.readiness || {}
      setIntakeNotice(`已读取 ${readiness.subtitleCount || 0} 条字幕，时长 ${readiness.durationSeconds || 0} 秒；不会修改任何项目。`)
    } catch (requestError: any) {
      setError(requestError.message || '读取 SRT 失败')
    } finally {
      setBusy('')
    }
  }

  const createRun = async () => {
    setBusy('create')
    setError('')
    try {
      const created = await api.createDirectorRun({
        task,
        recipeId: 'structured-knowledge-video',
        projectId: selectedProject?.id || undefined,
        intake: standaloneSrtIntake || undefined,
      })
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

  const rejectApproval = async () => {
    if (!run?.runId || !approval?.approvalId) return
    setBusy('approval')
    setError('')
    try {
      await api.approveDirectorRun(run.runId, approval.approvalId, 'reject')
      await load(run.runId)
    } catch (requestError: any) {
      setError(requestError.message || '拒绝建议失败')
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
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>选输入，写要求，确认素材替换，再取得预览与剪映草稿。</p>
          </div>
          <div className="text-xs grid gap-1" style={{ color: 'var(--text-secondary)' }}>
            <span><GitBranch size={13} className="inline mr-1" />{version?.branch || 'unknown'}</span>
            <span>{String(version?.commit || '').slice(0, 8) || 'no-sha'} / {version?.environment || 'local'}</span>
          </div>
          <a className="btn-cinematic icon-button" href="/settings/agent" title="模型与上游服务设置" aria-label="模型与上游服务设置">
            <GearSix size={18} />
          </a>
        </header>

        <section className="grid sm:grid-cols-2 xl:grid-cols-4 gap-2 text-xs" aria-label="Director 操作步骤">
          {[
            ['1', '选择输入', inputReady ? '已就绪' : '选择 SRT 或项目'],
            ['2', '确认模型', providerReady ? `已启用：${provider.model}` : '当前使用本地模拟流程'],
            ['3', '创建任务', run ? `Run ${run.status}` : '写入制作要求'],
            ['4', '处理审批', approval ? '等待你的决定' : '有建议时再确认'],
          ].map(([step, title, detail]) => <div key={step} className="flex items-center gap-3 px-3 py-2 border rounded" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
            <span className="w-6 h-6 shrink-0 inline-flex items-center justify-center rounded-full text-xs" style={{ background: 'var(--bg-elevated)', color: 'var(--accent)' }}>{step}</span>
            <div className="min-w-0"><b>{title}</b><div className="truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>{detail}</div></div>
          </div>)}
        </section>

        <section className="grid lg:grid-cols-[380px_minmax(0,1fr)] gap-4">
          <aside className="card-cinematic p-5 space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <p className="label-cinematic">第一步：选择输入</p>
                {busy === 'project' && <span className="text-xs" style={{ color: 'var(--text-muted)' }}>读取项目...</span>}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <button className={inputMode === 'srt' ? 'btn-gold justify-center text-xs' : 'btn-cinematic justify-center text-xs'} onClick={() => chooseInputMode('srt')}><FileText size={15} /> 从 SRT 开始</button>
                <button className={inputMode === 'project' ? 'btn-gold justify-center text-xs' : 'btn-cinematic justify-center text-xs'} onClick={() => chooseInputMode('project')}><FilmSlate size={15} /> 使用已有项目</button>
              </div>
              {inputMode === 'srt' && <div className="border-l-2 pl-3 text-xs space-y-2" style={{ borderColor: 'var(--accent)' }}>
                <p style={{ color: 'var(--text-muted)' }}>适合第一次测试。读取字幕时间轴创建 Run，不会修改任何项目。</p>
                <label className="btn-cinematic inline-flex items-center gap-2 cursor-pointer">
                  <UploadSimple size={15} /> {busy === 'standalone-srt' ? '正在读取...' : '选择 SRT 文件'}
                  <input className="sr-only" type="file" accept=".srt,application/x-subrip,text/plain" onChange={importStandaloneSrt} disabled={busy === 'standalone-srt'} />
                </label>
                {standaloneSrtIntake && <div style={{ color: 'var(--accent)' }}>已读取：{srtFileName} · {standaloneSrtIntake.readiness?.subtitleCount || 0} 条字幕 / {standaloneSrtIntake.readiness?.durationSeconds || 0} 秒</div>}
              </div>}
              {inputMode === 'project' && <>
                <select className="input-cinematic w-full text-sm" value={selectedProjectId} onChange={event => selectProject(event.target.value)} disabled={busy === 'project'}>
                  <option value="">选择要读取的项目</option>
                  {projects.map(project => <option key={project.id} value={project.id}>{project.name || project.id}</option>)}
                </select>
              {selectedProject && <div className="border-l-2 pl-3 text-xs space-y-2" style={{ borderColor: 'var(--accent)' }}>
                <div className="flex items-center gap-2"><FilmSlate size={14} /><b>{selectedProject.name}</b></div>
                <div style={{ color: 'var(--text-muted)' }}>{subtitleCount} 条字幕 · {projectScript.length} 字文案{selectedProject.structuredContent ? ' · 已结构化' : ''}</div>
                <label className="btn-cinematic inline-flex items-center gap-2 cursor-pointer">
                  <UploadSimple size={15} /> {busy === 'srt' ? '导入中...' : '导入 SRT'}
                  <input className="sr-only" type="file" accept=".srt,application/x-subrip,text/plain" onChange={importSrt} disabled={busy === 'srt'} />
                </label>
                {srtFileName && <div className="flex items-center gap-2 break-all"><FileText size={14} />{srtFileName}</div>}
                {intakeNotice && <div style={{ color: 'var(--accent)' }}>{intakeNotice}</div>}
              </div>}
              {!selectedProject && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>选择项目后可以额外导入 SRT；这会写入该项目的字幕时间轴。</p>}
              </>}
            </div>
            <div>
              <div className="flex items-center justify-between gap-2"><p className="label-cinematic">第二步：告诉 Director 要做什么</p><button className="btn-cinematic text-xs py-1.5" onClick={() => setTask(TEST_TASK)}><ClipboardText size={14} /> 填入测试指令</button></div>
              <textarea className="input-cinematic w-full min-h-[180px] mt-2 text-sm" value={task} onChange={event => setTask(event.target.value)} />
            </div>
            <div className="border-l-2 pl-3 text-xs space-y-2" style={{ borderColor: providerReady ? 'var(--accent)' : 'var(--warning)' }}>
              <b>{providerReady ? `模型已启用：${provider.model}` : '尚未启用真实模型'}</b>
              <p style={{ color: 'var(--text-muted)' }}>{providerReady ? '本次新 Run 会尝试调用该模型；事件区会显示实际运行状态。' : '现在仍可演示完整流程，但不会发起模型调用。配置好后，新 Run 才会使用真实 Pi。'}</p>
              {!providerReady && <a className="btn-cinematic inline-flex text-xs" href="/settings/agent"><GearSix size={14} /> 去配置模型</a>}
            </div>
            {error && <div className="operation-error">{error}</div>}
            <button className="btn-gold w-full justify-center" disabled={!task.trim() || !inputReady || busy === 'create'} title={!inputReady ? '请先上传 SRT 或选择项目' : ''} onClick={createRun}>
              <Play size={16} /> {busy === 'create' ? '正在创建...' : inputReady ? '第三步：创建 Director Run' : '请先完成第一步'}
            </button>
            {run && <div className="rounded-lg p-3 text-xs space-y-2" style={{ background: 'var(--bg-elevated)' }}>
              <div>Run: <b>{run.runId}</b></div>
              <div>状态：<b>{run.status}</b></div>
              <div>{run.mockTransport ? '当前为本地模拟流程，未调用模型。' : run.liveCallPerformed ? '已发起真实模型调用。' : '等待 Pi 返回。'}</div>
            </div>}
            {approval && <div className="rounded-lg border p-4 space-y-3" style={{ borderColor: 'var(--accent)', background: 'var(--bg-surface)' }}>
              <div className="flex items-center gap-2 text-sm"><WarningCircle size={16} />审批：{approval.operation}</div>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{approval.message}</p>
              {approval.actionProposal?.reason && <div className="text-xs p-3 rounded" style={{ background: 'var(--bg-elevated)' }}>
                <b>Pi 建议依据</b>
                <p className="mt-1" style={{ color: 'var(--text-muted)' }}>{approval.actionProposal.reason}</p>
              </div>}
              <div className="grid grid-cols-2 gap-2"><button className="btn-cinematic justify-center" disabled={busy === 'approval'} onClick={rejectApproval}><X size={15} /> 拒绝建议</button><button className="btn-gold justify-center" disabled={busy === 'approval'} onClick={resolveApproval}><Check size={15} /> 同意并继续</button></div>
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
