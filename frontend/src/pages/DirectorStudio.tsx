import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowCounterClockwise, ArrowLeft, Check, CheckCircle, DownloadSimple, FileText, FloppyDisk, Package, Play, Plus, Robot, Trash, UploadSimple, WarningCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'

const EXAMPLE_GPT_DISCUSSION = `我要做低饱和纪录片风格的知识视频。
字幕一句对应一个画面，不做花哨转场。
重点观点用暖棕和金色信息卡，优先使用真实素材。
缺少素材时再提出生成建议；替换已有素材和付费生成必须先问我。`

type Tab = 'import' | 'skills' | 'packs'

function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export default function DirectorStudio() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<Tab>('import')
  const [skills, setSkills] = useState<any[]>([])
  const [packs, setPacks] = useState<any[]>([])
  const [selectedSkill, setSelectedSkill] = useState<any>(null)
  const [gptText, setGptText] = useState('')
  const [importName, setImportName] = useState('')
  const [packName, setPackName] = useState('')
  const [packDescription, setPackDescription] = useState('')
  const [packSkillIds, setPackSkillIds] = useState<string[]>([])
  const [packStyle, setPackStyle] = useState({ name: '', palette: '', mood: '', layout: '' })
  const [packDocument, setPackDocument] = useState('')
  const [trial, setTrial] = useState<any>(null)
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [feedback, setFeedback] = useState<{ tone: 'ok' | 'danger' | 'warn', title: string, detail: string } | null>(null)
  const [busy, setBusy] = useState('')

  const publishedSkills = useMemo(() => skills.filter(skill => skill.status === 'published'), [skills])

  const refresh = async () => {
    setCatalogLoading(true)
    try {
      const [skillResult, packResult] = await Promise.all([api.listDirectorStudioSkills(), api.listDirectorPacks()])
      setSkills(skillResult.skills || [])
      setPacks(packResult.packs || [])
    } finally { setCatalogLoading(false) }
  }

  useEffect(() => { refresh().catch(error => setFeedback({ tone: 'danger', title: '读取私有工作台失败', detail: error.message })) }, [])

  const importDraft = async () => {
    setBusy('import'); setFeedback(null)
    try {
      const result = await api.importGptSkill(gptText, importName || undefined)
      setSelectedSkill(result.skill); setTab('skills'); setTrial(null)
      setFeedback({ tone: 'ok', title: '已生成 Skill 草稿', detail: '现在检查规则、试跑 Scene Plan，确认后再发布。' })
      await refresh()
    } catch (error: any) { setFeedback({ tone: 'danger', title: '无法生成草稿', detail: error.message || '请检查讨论文本。' }) } finally { setBusy('') }
  }

  const chooseSkill = async (skill: any) => {
    setBusy(`skill:${skill.skillId}`); setTrial(null)
    try { const result = await api.getDirectorStudioSkill(skill.skillId); setSelectedSkill(result.skill); setTab('skills') }
    catch (error: any) { setFeedback({ tone: 'danger', title: '读取 Skill 失败', detail: error.message }) }
    finally { setBusy('') }
  }

  const saveSkill = async () => {
    if (!selectedSkill) return
    setBusy('save-skill')
    try {
      const result = await api.updateDirectorStudioSkill(selectedSkill.skillId, {
        name: selectedSkill.name,
        description: selectedSkill.description,
        directives: selectedSkill.directives,
        requiredCapabilities: selectedSkill.requiredCapabilities,
      })
      setSelectedSkill(result.skill); setFeedback({ tone: 'ok', title: 'Skill 草稿已保存', detail: `当前版本 v${result.skill.version}。` }); await refresh()
    } catch (error: any) { setFeedback({ tone: 'danger', title: '保存 Skill 失败', detail: error.message }) } finally { setBusy('') }
  }

  const validateOrTrial = async (mode: 'validate' | 'trial') => {
    if (!selectedSkill) return
    setBusy(mode)
    try {
      const result = mode === 'validate' ? await api.validateDirectorStudioSkill(selectedSkill.skillId) : await api.trialDirectorStudioSkill(selectedSkill.skillId)
      if (mode === 'validate') setFeedback(result.ok ? { tone: 'ok', title: 'Skill 校验通过', detail: '它只会使用已注册的 VideoForge 能力。' } : { tone: 'danger', title: 'Skill 校验未通过', detail: (result.errors || []).join('；') })
      else { setTrial(result.scenePlan); setFeedback({ tone: 'ok', title: '试跑完成', detail: '下面是合成字幕得到的 Scene Plan；试跑不会改项目或调用付费服务。' }) }
    } catch (error: any) { setFeedback({ tone: 'danger', title: mode === 'trial' ? '试跑失败' : '校验失败', detail: error.message }) } finally { setBusy('') }
  }

  const publishSkill = async () => {
    if (!selectedSkill) return
    setBusy('publish')
    try { const result = await api.publishDirectorStudioSkill(selectedSkill.skillId); setSelectedSkill(result.skill); setFeedback({ tone: 'ok', title: 'Skill 已发布到你的私有库', detail: `版本 v${result.skill.version} 可被 Director Pack 固定使用。` }); await refresh() }
    catch (error: any) { setFeedback({ tone: 'danger', title: '发布失败', detail: error.message }) } finally { setBusy('') }
  }

  const changeSkillDirective = (key: string, value: string) => setSelectedSkill((current: any) => ({ ...current, directives: { ...(current?.directives || {}), [key]: value } }))

  const createPack = async () => {
    setBusy('pack'); setFeedback(null)
    try {
      const skillPins = packSkillIds.map(skillId => { const skill = publishedSkills.find(row => row.skillId === skillId); return { skillId, version: skill?.version } })
      const result = await api.saveDirectorPack({ name: packName, description: packDescription, recipeId: 'structured-knowledge-video', skillPins, style: packStyle, capabilityIds: ['review_visual_scene_plan', 'prepare_visual_generation_pack', 'bind_scene_assets'] })
      setFeedback({ tone: 'ok', title: '导演包已安装', detail: '回到 Director 时可以选择它，并固定使用当前 Skill 版本。' })
      setPackName(''); setPackDescription(''); setPackSkillIds([]); setPackStyle({ name: '', palette: '', mood: '', layout: '' }); await refresh()
      setTab('packs')
    } catch (error: any) { setFeedback({ tone: 'danger', title: '创建导演包失败', detail: error.message }) } finally { setBusy('') }
  }

  const exportPack = async (pack: any) => {
    setBusy(`export:${pack.packId}`)
    try { const document = await api.exportDirectorPack(pack.packId); downloadJson(`${pack.name || pack.packId}.videoforge-pack.json`, document); setFeedback({ tone: 'ok', title: '导演包已导出', detail: '文件包含固定版本的 Skill 与 Pack manifest。' }) }
    catch (error: any) { setFeedback({ tone: 'danger', title: '导出失败', detail: error.message }) } finally { setBusy('') }
  }

  const importPack = async () => {
    setBusy('import-pack')
    try { const document = JSON.parse(packDocument); await api.importDirectorPack(document); setPackDocument(''); setFeedback({ tone: 'ok', title: '导演包已导入', detail: '导入的 Skill 会作为私有版本保留。' }); await refresh() }
    catch (error: any) { setFeedback({ tone: 'danger', title: '导入失败', detail: error.message || '请检查 JSON 文件。' }) } finally { setBusy('') }
  }

  const readPackFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; event.target.value = ''
    if (!file) return
    const reader = new FileReader(); reader.onload = () => setPackDocument(String(reader.result || '')); reader.readAsText(file)
  }

  const removePack = async (pack: any) => {
    setBusy(`delete:${pack.packId}`)
    try { await api.uninstallDirectorPack(pack.packId); setFeedback({ tone: 'warn', title: '导演包已卸载', detail: 'Skill 仍保留在你的私有库，可用于其他导演包。' }); await refresh() }
    catch (error: any) { setFeedback({ tone: 'danger', title: '卸载失败', detail: error.message }) } finally { setBusy('') }
  }

  return <main className="min-h-[100dvh] workbench-shell p-4 md:p-6"><div className="max-w-7xl mx-auto space-y-4">
    <header className="card-cinematic p-5 flex flex-wrap items-center gap-4"><button className="icon-button" title="返回智能助手" onClick={() => navigate('/director')}><ArrowLeft size={18}/></button><div className="home-brand-mark"><Robot size={20} weight="fill"/></div><div className="flex-1 min-w-[240px]"><p className="section-index">PRIVATE DIRECTOR STUDIO</p><h1 className="text-2xl font-heading">我的视频制作方案</h1><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>先把 GPT 讨论变成“导演方法”，再把方法、风格和流程组合成可直接使用的视频制作方案。</p></div><button className="btn-gold text-xs" onClick={() => { setTab('import'); setGptText(EXAMPLE_GPT_DISCUSSION) }}><Plus size={15}/> 从 GPT 讨论开始</button></header>

    <div className="grid md:grid-cols-3 gap-2"><button className={tab === 'import' ? 'btn-gold justify-center' : 'btn-cinematic justify-center'} onClick={() => setTab('import')}><FileText size={16}/> 1. 导入 GPT 讨论</button><button className={tab === 'skills' ? 'btn-gold justify-center' : 'btn-cinematic justify-center'} onClick={() => setTab('skills')}><Robot size={16}/> 2. 我的导演方法 ({catalogLoading ? '读取中' : skills.length})</button><button className={tab === 'packs' ? 'btn-gold justify-center' : 'btn-cinematic justify-center'} onClick={() => setTab('packs')}><Package size={16}/> 3. 我的制作方案 ({catalogLoading ? '读取中' : packs.length})</button></div>

    {feedback && <div className="status-pill p-4 flex items-start gap-3 animate-surface-in" data-tone={feedback.tone === 'ok' ? 'ok' : feedback.tone === 'danger' ? 'danger' : 'warn'}>{feedback.tone === 'ok' ? <CheckCircle size={21} weight="fill"/> : <WarningCircle size={21} weight="fill"/>}<div><b>{feedback.title}</b><p className="text-xs mt-1">{feedback.detail}</p></div></div>}

    {tab === 'import' && <section className="card-cinematic p-5 grid lg:grid-cols-[minmax(0,1fr)_320px] gap-5"><div className="space-y-3"><div><h2 className="text-lg font-heading">粘贴 GPT 讨论成果</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>可以是风格讨论、镜头规则、素材策略或审批要求。系统会先生成草稿，绝不会直接改项目。</p></div><textarea className="input-cinematic w-full min-h-[360px] text-sm" value={gptText} onChange={event => setGptText(event.target.value)} placeholder={EXAMPLE_GPT_DISCUSSION}/><div className="flex flex-wrap gap-2"><button className="btn-cinematic text-xs" onClick={() => setGptText(EXAMPLE_GPT_DISCUSSION)}><FileText size={14}/> 填入示例</button><button className="btn-gold ml-auto" disabled={gptText.trim().length < 24 || !!busy} onClick={importDraft}><Robot size={16}/>{busy === 'import' ? '正在整理...' : '生成 Skill 草稿'}</button></div></div><aside className="space-y-3 border-l pl-5" style={{ borderColor: 'var(--border)' }}><p className="label-cinematic">会提取什么</p>{['镜头与字幕规则', '视觉风格与素材策略', '审批边界', '需要的已注册能力', '可试跑的 Scene Plan'].map(item => <div className="flex items-center gap-2 text-sm" key={item}><Check size={15} style={{ color: 'var(--success)' }}/>{item}</div>)}<label className="label-cinematic pt-3">给 Skill 起名（可选）<input className="input-cinematic w-full mt-2" value={importName} onChange={event => setImportName(event.target.value)} placeholder="例如：我的纪录片导演"/></label></aside></section>}

    {tab === 'skills' && <section className="grid xl:grid-cols-[300px_minmax(0,1fr)_340px] gap-4"><aside className="card-cinematic p-4 space-y-2"><div className="flex items-center justify-between"><div><p className="label-cinematic">导演方法</p><p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>它决定字幕如何变镜头、画面是什么风格、哪些动作需确认。</p></div><button className="icon-button" title="导入 GPT 讨论成果" onClick={() => setTab('import')}><Plus size={16}/></button></div>{catalogLoading && <div className="status-pill text-xs" data-tone="warn">正在读取你的导演方法...</div>}{skills.map(skill => <button key={skill.skillId} onClick={() => chooseSkill(skill)} className="w-full text-left p-3 border rounded transition-colors" style={{ borderColor: selectedSkill?.skillId === skill.skillId ? 'var(--accent)' : 'var(--border)', background: selectedSkill?.skillId === skill.skillId ? 'var(--bg-elevated)' : 'var(--bg-surface)' }}><div className="flex justify-between gap-2"><b className="truncate">{skill.name}</b><span className="status-pill text-[10px]" data-tone={skill.status === 'published' ? 'ok' : skill.status === 'disabled' ? 'danger' : 'warn'}>{skill.status}</span></div><p className="text-[11px] mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>v{skill.version} · {skill.description}</p></button>)}{!catalogLoading && !skills.length && <p className="text-xs p-3" style={{ color: 'var(--text-muted)' }}>还没有导演方法。先导入一段 GPT 讨论成果。</p>}</aside>
      <section className="card-cinematic p-5 space-y-4">{selectedSkill ? <><div className="flex flex-wrap items-start gap-3"><div className="flex-1"><p className="label-cinematic">编辑 Skill 草稿</p><input className="input-cinematic w-full mt-2 text-lg" value={selectedSkill.name || ''} onChange={event => setSelectedSkill({ ...selectedSkill, name: event.target.value })}/><textarea className="input-cinematic w-full min-h-[72px] mt-2 text-sm" value={selectedSkill.description || ''} onChange={event => setSelectedSkill({ ...selectedSkill, description: event.target.value })}/></div><span className="status-pill" data-tone={selectedSkill.status === 'published' ? 'ok' : selectedSkill.status === 'disabled' ? 'danger' : 'warn'}>v{selectedSkill.version} · {selectedSkill.status}</span></div><div className="grid md:grid-cols-2 gap-3">{Object.entries(selectedSkill.directives || {}).map(([key, value]) => <label className="label-cinematic" key={key}>{({ sceneRule: '镜头与字幕规则', visualStyle: '视觉风格', assetStrategy: '素材策略', approvalRule: '审批规则' } as any)[key] || key}<textarea className="input-cinematic w-full min-h-[88px] mt-2 text-sm" value={String(value)} onChange={event => changeSkillDirective(key, event.target.value)}/></label>)}</div><div><p className="label-cinematic">允许使用的 VideoForge 能力</p><div className="flex flex-wrap gap-2 mt-2">{(selectedSkill.requiredCapabilities || []).map((item: string) => <span className="status-pill text-xs" key={item}>{item}</span>)}</div></div><div className="flex flex-wrap gap-2"><button className="btn-cinematic" disabled={!!busy} onClick={saveSkill}><FloppyDisk size={16}/> 保存草稿</button><button className="btn-cinematic" disabled={!!busy} onClick={() => validateOrTrial('validate')}><Check size={16}/> 校验</button><button className="btn-cinematic" disabled={!!busy} onClick={() => validateOrTrial('trial')}><Play size={16}/> 试跑 Scene Plan</button>{selectedSkill.status !== 'published' && <button className="btn-gold ml-auto" disabled={!!busy} onClick={publishSkill}><CheckCircle size={16}/> 发布到我的 Skill 库</button>}{selectedSkill.status === 'published' && <button className="btn-cinematic" disabled={!!busy} onClick={async () => { await api.disableDirectorStudioSkill(selectedSkill.skillId); await chooseSkill(selectedSkill); await refresh() }}><Trash size={16}/> 禁用</button>}{selectedSkill.version > 1 && <button className="btn-cinematic" disabled={!!busy} onClick={async () => { const result = await api.rollbackDirectorStudioSkill(selectedSkill.skillId, selectedSkill.version - 1); setSelectedSkill(result.skill); await refresh(); setFeedback({ tone: 'warn', title: '已回滚当前版本', detail: `现在固定到 v${result.skill.version}。` }) }}><ArrowCounterClockwise size={16}/> 回滚到 v{selectedSkill.version - 1}</button>}</div></> : <div className="empty-state min-h-[360px]"><Robot size={32}/><span>从左侧选择一个 Skill，或导入 GPT 讨论成果。</span></div>}</section>
      <aside className="card-cinematic p-4 space-y-3"><p className="label-cinematic">试跑结果</p>{trial ? <><div className="status-pill" data-tone="ok"><CheckCircle size={15}/> {trial.scenes?.length || 0} 个 Scene，不会改项目</div><p className="text-xs" style={{ color: 'var(--text-muted)' }}>{trial.styleSignature || '无风格签名'}</p><div className="space-y-2 max-h-[420px] overflow-auto">{(trial.scenes || []).map((scene: any) => <div className="p-3 rounded text-xs" style={{ background: 'var(--bg-elevated)' }} key={scene.sceneId}><b>{scene.sceneId}</b><p className="mt-1">{scene.start}s → {scene.end}s · {scene.text}</p><p className="mt-1" style={{ color: 'var(--text-muted)' }}>{scene.direction}</p></div>)}</div></> : <p className="text-xs" style={{ color: 'var(--text-muted)' }}>校验后点击“试跑 Scene Plan”。此处只展示合成字幕的确定性结果。</p>}</aside></section>}

    {tab === 'packs' && <section className="grid xl:grid-cols-[minmax(0,1fr)_360px] gap-4"><div className="space-y-4"><section className="card-cinematic p-5 space-y-4"><div><h2 className="text-lg font-heading">组装我的导演包</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>导演包会固定选中的已发布 Skill 版本，并组合 Recipe、风格参数、模板和受控能力。</p></div><div className="grid md:grid-cols-2 gap-3"><label className="label-cinematic">包名称<input className="input-cinematic w-full mt-2" value={packName} onChange={event => setPackName(event.target.value)} placeholder="例如：我的纪录片知识视频"/></label><label className="label-cinematic">描述<input className="input-cinematic w-full mt-2" value={packDescription} onChange={event => setPackDescription(event.target.value)} placeholder="这个包适合什么内容"/></label></div><div><p className="label-cinematic">选择已发布 Skill</p><div className="grid sm:grid-cols-2 gap-2 mt-2">{publishedSkills.map(skill => <label className="p-3 border rounded text-sm flex gap-2" style={{ borderColor: 'var(--border)' }} key={skill.skillId}><input type="checkbox" checked={packSkillIds.includes(skill.skillId)} onChange={event => setPackSkillIds(current => event.target.checked ? [...current, skill.skillId] : current.filter(id => id !== skill.skillId))}/><span><b>{skill.name}</b><small className="block mt-1" style={{ color: 'var(--text-muted)' }}>固定 v{skill.version}</small></span></label>)}{!publishedSkills.length && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>先发布至少一个 Skill。</p>}</div></div><div className="grid md:grid-cols-2 gap-3">{Object.entries(packStyle).map(([key, value]) => <label className="label-cinematic" key={key}>{({ name: '风格名', palette: '色彩', mood: '情绪', layout: '画面布局' } as any)[key]}<input className="input-cinematic w-full mt-2" value={value} onChange={event => setPackStyle(current => ({ ...current, [key]: event.target.value }))}/></label>)}</div><button className="btn-gold ml-auto" disabled={!packName.trim() || !packSkillIds.length || !!busy} onClick={createPack}><Package size={16}/>{busy === 'pack' ? '正在组装...' : '安装到我的导演包'}</button></section>
        <section className="card-cinematic p-5"><div><p className="label-cinematic">已安装视频制作方案</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>选择“去使用”会直接带着这套方案回到 Director。</p></div><div className="grid md:grid-cols-2 gap-3 mt-3">{catalogLoading && <div className="status-pill text-xs" data-tone="warn">正在读取你的制作方案...</div>}{packs.map(pack => <div className="border p-4 rounded space-y-3" style={{ borderColor: 'var(--border)' }} key={pack.packId}><div><b>{pack.name}</b><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{pack.description || '未写描述'}</p></div><div className="text-xs" style={{ color: 'var(--text-secondary)' }}>{(pack.skillPins || []).map((pin: any) => `${pin.skillId} v${pin.version}`).join(' · ')}</div><div className="flex gap-2"><button className="btn-cinematic text-xs" onClick={() => exportPack(pack)} disabled={!!busy}><DownloadSimple size={14}/> 导出</button><button className="btn-cinematic text-xs" onClick={() => removePack(pack)} disabled={!!busy}><Trash size={14}/> 卸载</button><button className="btn-gold text-xs ml-auto" onClick={() => navigate(`/director?pack=${encodeURIComponent(pack.packId)}`)}><Robot size={14}/> 用这套方案</button></div></div>)}{!catalogLoading && !packs.length && <p className="text-xs" style={{ color: 'var(--text-muted)' }}>还没有视频制作方案。将已发布导演方法组合起来即可创建。</p>}</div></section></div>
      <aside className="card-cinematic p-5 space-y-3"><p className="label-cinematic">导入他人的导演包</p><p className="text-xs" style={{ color: 'var(--text-muted)' }}>只导入 manifest 与版本化 Skill，不会执行包内任意代码。</p><label className="btn-cinematic inline-flex cursor-pointer"><UploadSimple size={15}/> 选择 .json 文件<input hidden type="file" accept="application/json,.json" onChange={readPackFile}/></label><textarea className="input-cinematic w-full min-h-[230px] text-xs font-mono" value={packDocument} onChange={event => setPackDocument(event.target.value)} placeholder="也可以粘贴导出的 Director Pack JSON"/><button className="btn-gold w-full justify-center" disabled={!packDocument.trim() || !!busy} onClick={importPack}><UploadSimple size={16}/> 导入导演包</button></aside></section>}
  </div></main>
}
