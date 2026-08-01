import { ChangeEvent, useEffect, useMemo, useState } from 'react'
import { ArrowClockwise, CaretRight, CheckCircle, CircleNotch, DownloadSimple, FloppyDisk, Package, Play, Plus, Trash, UploadSimple, WarningCircle } from '@phosphor-icons/react'
import { api } from '../../lib/api'

type Section = 'overview' | 'visual' | 'archetypes' | 'runtime' | 'eval' | 'versions'

const SAMPLE_TEXT = `人之所以会陷入长期内耗，通常经过三个阶段。

第一阶段，外部评价进入自我判断。

第二阶段，人开始反复比较现实与期待。

最后，注意力被消耗，却没有形成实际行动。

另一种人会把评价拆成事实、解释和下一步。`

function fixture(text: string) {
  return text.split(/\n\s*\n/).map(value => value.trim()).filter(Boolean).map((value, index) => ({
    id: 'studio_sample_' + String(index + 1).padStart(3, '0'), start: index * 3, end: index * 3 + 2.8, text: value,
  }))
}

function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; anchor.click(); URL.revokeObjectURL(url)
}

export default function ProductionPackStudio({ packs, publishedSkills, onChanged, onUse }: { packs: any[], publishedSkills: any[], onChanged: () => Promise<void>, onUse: (packId: string) => void }) {
  const [selectedId, setSelectedId] = useState('')
  const [section, setSection] = useState<Section>('overview')
  const [registry, setRegistry] = useState<any[]>([])
  const [health, setHealth] = useState<any>(null)
  const [editing, setEditing] = useState<any>(null)
  const [compiled, setCompiled] = useState<any>(null)
  const [evaluation, setEvaluation] = useState<any>(null)
  const [sampleText, setSampleText] = useState(SAMPLE_TEXT)
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState<any>(null)
  const [importText, setImportText] = useState('')
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [createSkills, setCreateSkills] = useState<string[]>([])

  const selected = useMemo(() => packs.find(pack => pack.packId === selectedId) || null, [packs, selectedId])

  useEffect(() => { if (!selectedId && packs[0]?.packId) setSelectedId(packs[0].packId) }, [packs, selectedId])
  useEffect(() => { api.getProductionRendererRegistry().then(result => setRegistry(result.renderers || [])).catch(() => setRegistry([])) }, [])
  useEffect(() => { if (selected) inspect(selected).catch(() => undefined) }, [selectedId])

  const inspect = async (pack: any) => {
    setSelectedId(pack.packId); setEditing(JSON.parse(JSON.stringify(pack))); setCompiled(null); setEvaluation(null); setBusy('health')
    try { const result = await api.getProductionPackHealth(pack.packId); setHealth(result.health) }
    catch (error: any) { setHealth({ status: 'error', warnings: [error.message || '无法读取 Pack Health'] }) }
    finally { setBusy('') }
  }

  const compile = async () => {
    if (!selected) return
    setBusy('compile'); setNotice(null)
    try {
      const result = await api.compileProductionPack(selected.packId, { subtitles: fixture(sampleText) })
      setCompiled(result); setSection('eval')
      setNotice({ tone: 'ok', text: '已为 ' + (result.scenePlan?.scenes?.length || 0) + ' 个 Scene 生成持久化 VisualSpec。' })
    } catch (error: any) { setNotice({ tone: 'danger', text: error.message || '编译失败。' }) }
    finally { setBusy('') }
  }

  const evaluate = async (caseId?: string) => {
    if (!selected) return
    setBusy('eval'); setNotice(null)
    try {
      const result = await api.runProductionPackEval(selected.packId, caseId ? { caseId } : {})
      setEvaluation(result)
      setNotice({ tone: result.status === 'succeeded' ? 'ok' : 'warn', text: 'Eval 已完成：' + (result.cases?.length || 0) + ' 个隔离真实渲染结果已保存。' })
    } catch (error: any) { setNotice({ tone: 'danger', text: error.message || 'Eval 失败。' }) }
    finally { setBusy('') }
  }

  const save = async () => {
    if (!editing) return
    setBusy('save'); setNotice(null)
    try {
      const result = await api.saveDirectorPack(editing)
      await onChanged(); await inspect(result.pack)
      setNotice({ tone: 'ok', text: '已保存 Production Pack V' + result.pack.version + '，Fingerprint 已更新。' })
    } catch (error: any) { setNotice({ tone: 'danger', text: error.message || '保存失败。' }) }
    finally { setBusy('') }
  }

  const createCompatible = async () => {
    setBusy('create'); setNotice(null)
    try {
      const skillPins = createSkills.map(id => { const skill = publishedSkills.find(row => row.skillId === id); return { skillId: id, version: skill?.version } })
      const result = await api.saveDirectorPack({ name: createName, description: createDescription, recipeId: 'structured-knowledge-video', skillPins, style: { name: '编辑部知识视频', palette: '#171512', mood: '克制', layout: '清晰关系' }, capabilityIds: ['review_visual_scene_plan', 'prepare_visual_generation_pack', 'bind_scene_assets'] })
      setCreateName(''); setCreateDescription(''); setCreateSkills([]); await onChanged(); await inspect(result.pack)
      setNotice({ tone: 'ok', text: '兼容 Pack 已保存并迁移为 V2。' })
    } catch (error: any) { setNotice({ tone: 'danger', text: error.message || '创建失败。' }) }
    finally { setBusy('') }
  }

  const importPack = async () => {
    setBusy('import'); setNotice(null)
    try { await api.importDirectorPack(JSON.parse(importText)); setImportText(''); await onChanged(); setNotice({ tone: 'ok', text: 'Pack 已导入并经过声明式安全校验。' }) }
    catch (error: any) { setNotice({ tone: 'danger', text: error.message || '导入失败。' }) }
    finally { setBusy('') }
  }

  const importFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; event.target.value = ''
    if (!file) return
    const reader = new FileReader(); reader.onload = () => setImportText(String(reader.result || '')); reader.readAsText(file)
  }

  const updateStyle = (group: string, field: string, value: any) => setEditing((current: any) => ({ ...current, styleKit: { ...(current?.styleKit || {}), [group]: { ...(current?.styleKit?.[group] || {}), [field]: value } } }))
  const updateArchetype = (id: string, patch: any) => setEditing((current: any) => ({ ...current, sceneArchetypes: (current?.sceneArchetypes || []).map((item: any) => item.archetypeId === id ? { ...item, ...patch } : item) }))
  const currentRenderer = (binding: any) => registry.find(row => row.providerId === binding.providerId && row.rendererId === binding.rendererId)

  return <section className="space-y-4">
    <header className="card-cinematic p-5 flex flex-wrap gap-4 items-center">
      <div className="flex-1 min-w-[240px]"><p className="section-index">PRODUCTION PACK STUDIO / V2</p><h2 className="text-xl font-heading mt-1">可执行的视频生产方案</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>把导演方法、视觉系统、场景原型和真实 Renderer 组装为可复现的视频能力。</p></div>
      <button className="btn-cinematic text-xs" onClick={() => { onChanged().catch(() => undefined); api.getProductionRendererRegistry().then(result => setRegistry(result.renderers || [])) }} disabled={!!busy}><ArrowClockwise size={14}/> 刷新</button>
      <button className="btn-gold text-xs" onClick={compile} disabled={!selected || !!busy}><Play size={14}/>{busy === 'compile' ? '正在编译...' : '编译示例'}</button>
    </header>

    {notice && <div className="status-pill p-3 text-xs" data-tone={notice.tone}><span>{notice.tone === 'danger' ? <WarningCircle size={16}/> : <CheckCircle size={16}/>}</span>{notice.text}</div>}

    <div className="grid xl:grid-cols-[270px_minmax(0,1fr)_320px] gap-4">
      <aside className="card-cinematic p-3 space-y-2 self-start xl:sticky xl:top-4"><div className="px-2 py-1"><p className="label-cinematic">Pack Library</p><p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>内置、私有和导入包共享同一条 V2 编译路径。</p></div>
        {packs.map(pack => <button key={pack.packId} onClick={() => inspect(pack)} className="w-full text-left p-3 border rounded focus-visible:outline focus-visible:outline-2" style={{ borderColor: selectedId === pack.packId ? 'var(--accent)' : 'var(--border)', background: selectedId === pack.packId ? 'var(--bg-elevated)' : 'var(--bg-surface)' }}><div className="flex justify-between gap-2"><b className="truncate">{pack.name}</b><span className="status-pill text-[10px]">{pack.source?.type === 'built_in' ? '内置' : '已安装'}</span></div><p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>V{pack.version} · {pack.sceneArchetypes?.length || 0} 个 Scene 原型</p><p className="font-mono text-[10px] mt-1 truncate" style={{ color: 'var(--text-muted)' }}>{String(pack.fingerprint || '').slice(0, 12)}</p></button>)}
        {!packs.length && <div className="empty-state text-xs"><Package size={22}/><span>暂无 Pack</span></div>}
      </aside>

      <main className="space-y-4 min-w-0">{selected ? <>
        <section className="card-cinematic p-5"><div className="flex flex-wrap justify-between gap-3"><div><p className="label-cinematic">Production Track</p><h3 className="font-heading text-xl mt-1">{selected.name}</h3><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{selected.description || '尚未填写描述。'}</p></div><p className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>{String(selected.fingerprint || '').slice(0, 16)}</p></div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-2 mt-5">{[
            ['Director Method', String(selected.skillPins?.length || 0) + ' 个固定 Skill', !!selected.skillPins?.length],
            ['Visual Style', selected.styleKit?.identity?.name || '待配置', !!selected.styleKit],
            ['Scene Archetypes', String(selected.sceneArchetypes?.filter((item: any) => item.enabled !== false).length || 0) + ' 个启用', !!selected.sceneArchetypes?.length],
            ['Renderer Bindings', String(selected.rendererBindings?.length || 0) + ' 条真实 Binding', !!selected.rendererBindings?.length],
            ['Eval Bench', evaluation?.status || '未运行', !!evaluation || !!selected.evalCases?.length],
            ['Ready', health?.status === 'ready' ? '可运行' : health?.status === 'warning' ? '有警告' : '待检查', health?.status === 'ready'],
          ].map(([name, detail, ok], index) => <div className="relative p-3 border rounded min-h-[90px]" style={{ borderColor: ok ? 'var(--accent)' : 'var(--border)', background: 'var(--bg-surface)' }} key={String(name)}><span className="text-[10px]" style={{ color: 'var(--accent)' }}>0{index + 1}</span><b className="block text-xs mt-1">{name}</b><p className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>{detail}</p>{index < 5 && <CaretRight className="hidden xl:block absolute -right-3 top-8 z-10" size={14} style={{ color: 'var(--accent)' }}/>}</div>)}</div>
          {health?.warnings?.length ? <div className="status-pill mt-4 text-xs" data-tone="warn"><WarningCircle size={15}/>{health.warnings.join('；')}</div> : null}
        </section>

        <section className="card-cinematic p-3"><div className="flex gap-1 overflow-x-auto" role="tablist">{([['overview', 'Overview'], ['visual', 'Visual System'], ['archetypes', 'Scene Archetypes'], ['runtime', 'Runtime Bindings'], ['eval', 'Eval Bench'], ['versions', 'Versions']] as [Section, string][]).map(([id, label]) => <button key={id} role="tab" aria-selected={section === id} className={section === id ? 'btn-gold text-xs whitespace-nowrap' : 'btn-cinematic text-xs whitespace-nowrap'} onClick={() => setSection(id)}>{label}</button>)}</div></section>

        {section === 'overview' && <section className="card-cinematic p-5 grid md:grid-cols-2 gap-4"><div><p className="label-cinematic">运行保障</p><p className="text-sm mt-2 leading-6">同一 Pack 与同一 Scene 输入会得到相同 Fingerprint、Archetype 与 VisualSpec。缺少 Renderer 依赖时，Run 标记为可恢复并保留已有资产。</p></div><div className="p-4 rounded text-xs" style={{ background: 'var(--bg-elevated)' }}><b>Provider Policy</b><p className="mt-2" style={{ color: 'var(--text-muted)' }}>{(selected.providerPolicy?.routes || ['local_free']).join(' · ')} · 不使用真实付费 API</p><div className="flex flex-wrap gap-2 mt-3">{(selected.capabilityIds || []).map((id: string) => <span className="status-pill text-[10px]" key={id}>{id}</span>)}</div></div></section>}

        {section === 'visual' && <section className="card-cinematic p-5 space-y-4"><div><p className="label-cinematic">Visual System</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>颜色按职责配置；字体、构图与动效角色都进入每一个 VisualSpec。</p></div><div className="grid md:grid-cols-2 gap-3">{(['background', 'surface', 'primary', 'secondary', 'accent', 'text', 'muted'] as string[]).map(field => <label className="label-cinematic" key={field}>{field}<div className="flex gap-2 mt-2"><input type="color" className="w-10 h-9 p-1" value={editing?.styleKit?.palette?.[field] || '#171717'} onChange={event => updateStyle('palette', field, event.target.value)}/><input className="input-cinematic flex-1" value={editing?.styleKit?.palette?.[field] || ''} onChange={event => updateStyle('palette', field, event.target.value)}/></div></label>)}</div><div className="grid md:grid-cols-3 gap-3"><label className="label-cinematic">信息密度<input className="input-cinematic w-full mt-2" value={editing?.styleKit?.composition?.density || ''} onChange={event => updateStyle('composition', 'density', event.target.value)}/></label><label className="label-cinematic">构图对齐<input className="input-cinematic w-full mt-2" value={editing?.styleKit?.composition?.alignment || ''} onChange={event => updateStyle('composition', 'alignment', event.target.value)}/></label><label className="label-cinematic">动作节奏<input className="input-cinematic w-full mt-2" value={editing?.styleKit?.motion?.tempo || ''} onChange={event => updateStyle('motion', 'tempo', event.target.value)}/></label></div><button className="btn-gold" disabled={!!busy} onClick={save}><FloppyDisk size={15}/>{busy === 'save' ? '保存中...' : '保存 Visual System'}</button></section>}

        {section === 'archetypes' && <section className="card-cinematic p-5 space-y-3"><div><p className="label-cinematic">Archetype Board</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>关键词、Block Type、Scene Intent、优先级与 fallback 共同决定视觉路线。</p></div>{(editing?.sceneArchetypes || selected.sceneArchetypes || []).map((item: any) => <article className="border rounded p-4 grid md:grid-cols-[1fr_160px] gap-3" style={{ borderColor: item.enabled === false ? 'var(--border)' : 'var(--accent)' }} key={item.archetypeId}><div><b>{item.name}</b><span className="status-pill text-[10px] ml-2">{item.rendererBindingId}</span><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>触发：{(item.semanticTags || []).join(' · ') || '默认 fallback'}</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>fallback：{item.fallbackArchetypeId || '无'} · 目标：{(item.sceneIntents || []).join('、') || '通用'}</p></div><div className="flex gap-2 items-center"><input className="input-cinematic w-20 text-xs" type="number" value={item.priority || 0} aria-label={item.name + ' 优先级'} onChange={event => updateArchetype(item.archetypeId, { priority: Number(event.target.value) })}/><button className={item.enabled === false ? 'btn-cinematic text-xs' : 'btn-gold text-xs'} onClick={() => updateArchetype(item.archetypeId, { enabled: item.enabled === false })}>{item.enabled === false ? '启用' : '已启用'}</button></div></article>)}<button className="btn-gold" disabled={!!busy} onClick={save}><FloppyDisk size={15}/> 保存 Archetype</button></section>}

        {section === 'runtime' && <section className="card-cinematic p-5 space-y-3"><div><p className="label-cinematic">Runtime Bindings</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>这里展示的 ID 来自后端唯一 Renderer Registry，页面没有硬编码第二份能力清单。</p></div>{(selected.rendererBindings || []).map((binding: any) => { const item = currentRenderer(binding); return <article className="border rounded p-4 grid md:grid-cols-[1fr_auto] gap-3" style={{ borderColor: item?.availability === 'available' ? 'var(--accent)' : 'var(--warning)' }} key={binding.bindingId}><div><b>{binding.bindingId}</b><p className="font-mono text-xs mt-1">{binding.providerId}/{binding.rendererId}</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{binding.templateId} · {binding.outputMode} · {binding.presentationMode} · {binding.themeMode}</p></div><span className="status-pill text-xs" data-tone={item?.availability === 'available' ? 'ok' : 'warn'}>{item?.availability || '未注册'}</span></article>})}</section>}

        {section === 'eval' && <section className="card-cinematic p-5 space-y-4"><div className="flex flex-wrap justify-between gap-3"><div><p className="label-cinematic">Eval Bench</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>真实 Compile → 真实 Renderer → Artifact SHA → 代表帧。Eval 在隔离目录运行，绝不修改用户项目。</p></div><button className="btn-gold" disabled={!!busy} onClick={() => evaluate()}><Play size={15}/>{busy === 'eval' ? '正在渲染...' : '运行全部 Eval'}</button></div><label className="label-cinematic">测试文案<textarea className="input-cinematic w-full min-h-[160px] text-sm mt-2" value={sampleText} onChange={event => setSampleText(event.target.value)}/></label><div className="flex flex-wrap gap-2"><button className="btn-cinematic text-xs" disabled={!!busy} onClick={compile}><Play size={14}/> 编译 VisualSpec</button>{(selected.evalCases || []).map((item: any) => <button className="btn-cinematic text-xs" disabled={!!busy} key={item.caseId} onClick={() => evaluate(item.caseId)}>{item.name}</button>)}</div>{compiled?.scenePlan?.scenes?.length ? <div className="space-y-2">{compiled.scenePlan.scenes.map((scene: any) => <div className="p-3 rounded text-xs" style={{ background: 'var(--bg-elevated)' }} key={scene.sceneId}><div className="flex justify-between"><b>{scene.sceneId} · {scene.visualSpec?.archetypeId}</b><span className="font-mono">{scene.visualSpec?.rendererId}</span></div><p className="mt-1">{scene.text}</p><p className="mt-1" style={{ color: 'var(--text-muted)' }}>命中：{(scene.visualSpec?.selectionEvidence?.matchedTags || []).join('、') || scene.visualSpec?.selectionEvidence?.matchedSceneIntent || 'fallback'} · {scene.visualSpec?.presentationMode}</p></div>)}</div> : <div className="empty-state"><Play size={26}/><span>先编译示例，查看每一幕的 VisualSpec。</span></div>}{evaluation && <div className="border rounded p-4" style={{ borderColor: evaluation.status === 'succeeded' ? 'var(--accent)' : 'var(--warning)' }}><div className="flex justify-between text-xs"><b>Eval {evaluation.status}</b><span className="font-mono">{evaluation.runId}</span></div>{(evaluation.cases || []).map((row: any) => <div key={row.case?.caseId} className="border-t mt-3 pt-3 text-xs" style={{ borderColor: 'var(--border)' }}><b>{row.case?.name}</b><p className="mt-1" style={{ color: 'var(--text-muted)' }}>{row.artifact?.rendererId} · {row.artifact?.artifactType} · SHA {String(row.artifact?.artifactSha256 || '').slice(0, 12)}</p><p className="mt-1 break-all" style={{ color: 'var(--text-muted)' }}>{row.artifact?.artifactPath}</p>{row.warnings?.length ? <p className="mt-1" style={{ color: 'var(--warning)' }}>{row.warnings.join('；')}</p> : null}</div>)}</div>}</section>}

        {section === 'versions' && <section className="card-cinematic p-5 space-y-3"><p className="label-cinematic">Versions / Export</p><div className="rounded p-4 text-xs" style={{ background: 'var(--bg-elevated)' }}><p>Schema V{selected.schemaVersion} · Pack V{selected.version}</p><p className="font-mono break-all mt-2" style={{ color: 'var(--text-muted)' }}>{selected.fingerprint}</p>{selected.migration?.warnings?.map((warning: string) => <p className="mt-2" style={{ color: 'var(--warning)' }} key={warning}>{warning}</p>)}</div><div className="flex flex-wrap gap-2"><button className="btn-cinematic" onClick={async () => downloadJson((selected.name || selected.packId) + '.videoforge-production-pack.json', await api.exportDirectorPack(selected.packId))}><DownloadSimple size={15}/> 导出 Manifest</button><button className="btn-cinematic" onClick={async () => { await api.uninstallDirectorPack(selected.packId); await onChanged() }}><Trash size={15}/> 卸载</button><button className="btn-gold" onClick={() => onUse(selected.packId)}><Package size={15}/> 在 Director 使用</button></div></section>}
      </> : <section className="card-cinematic empty-state min-h-[420px]"><Package size={32}/><span>选择一个 Pack，查看生产轨和 Eval。</span></section>}</main>

      <aside className="card-cinematic p-4 space-y-4 self-start xl:sticky xl:top-4"><div><p className="label-cinematic">Inspector</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>当前 Pack 的元数据、依赖状态和导入入口。</p></div>{selected && <><div className="border rounded p-3 text-xs" style={{ borderColor: 'var(--border)' }}><b>Pack Metadata</b><dl className="grid grid-cols-2 gap-y-2 mt-3"><dt style={{ color: 'var(--text-muted)' }}>Recipe</dt><dd>{selected.recipeId}</dd><dt style={{ color: 'var(--text-muted)' }}>Skills</dt><dd>{selected.skillPins?.length || 0}</dd><dt style={{ color: 'var(--text-muted)' }}>Bindings</dt><dd>{selected.rendererBindings?.length || 0}</dd><dt style={{ color: 'var(--text-muted)' }}>Eval Cases</dt><dd>{selected.evalCases?.length || 0}</dd></dl></div><div className="border rounded p-3 text-xs" style={{ borderColor: 'var(--border)' }}><b>Runtime Health</b><p className="mt-2" style={{ color: 'var(--text-muted)' }}>{health?.status === 'ready' ? '声明的 Renderer 依赖均可用。' : health?.status === 'warning' ? '存在可恢复依赖警告。' : '正在读取。'}</p>{health?.warnings?.map((warning: string) => <p className="mt-2" style={{ color: 'var(--warning)' }} key={warning}>{warning}</p>)}</div></>}<div className="border-t pt-4" style={{ borderColor: 'var(--border)' }}><p className="label-cinematic">导入 Production Pack</p><label className="btn-cinematic inline-flex text-xs mt-2 cursor-pointer"><UploadSimple size={14}/> 选择 JSON<input className="sr-only" type="file" accept="application/json,.json" onChange={importFile}/></label><textarea className="input-cinematic w-full min-h-[120px] text-xs font-mono mt-2" value={importText} onChange={event => setImportText(event.target.value)} placeholder="粘贴 Pack Manifest"/><button className="btn-gold w-full justify-center mt-2" disabled={!importText.trim() || !!busy} onClick={importPack}><UploadSimple size={15}/> 安全导入</button></div></aside>
    </div>

    <section className="card-cinematic p-5 space-y-3"><p className="label-cinematic">兼容创建器</p><p className="text-xs" style={{ color: 'var(--text-muted)' }}>旧版 Director Pack 可继续创建；只有点击保存后才迁移为 V2 Manifest，原始导入文件保持不变。</p><div className="grid md:grid-cols-2 gap-3"><label className="label-cinematic">包名称<input className="input-cinematic w-full mt-2" value={createName} onChange={event => setCreateName(event.target.value)} placeholder="例如：我的纪录片知识视频"/></label><label className="label-cinematic">描述<input className="input-cinematic w-full mt-2" value={createDescription} onChange={event => setCreateDescription(event.target.value)} placeholder="这个包适合什么内容"/></label></div><div className="grid sm:grid-cols-2 gap-2">{publishedSkills.map(skill => <label className="p-3 border rounded text-sm flex gap-2" style={{ borderColor: 'var(--border)' }} key={skill.skillId}><input type="checkbox" checked={createSkills.includes(skill.skillId)} onChange={event => setCreateSkills(current => event.target.checked ? [...current, skill.skillId] : current.filter(id => id !== skill.skillId))}/><span><b>{skill.name}</b><small className="block mt-1" style={{ color: 'var(--text-muted)' }}>固定 V{skill.version}</small></span></label>)}</div><button className="btn-gold" disabled={!createName.trim() || !createSkills.length || !!busy} onClick={createCompatible}><Plus size={15}/>{busy === 'create' ? '迁移中...' : '创建并迁移为 V2'}</button></section>
  </section>
}
