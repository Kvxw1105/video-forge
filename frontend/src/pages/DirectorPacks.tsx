import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft, CheckCircle, CircleNotch, DownloadSimple, Package, Plus,
  Power, Trash, UploadSimple, WarningCircle,
} from '@phosphor-icons/react'
import { api } from '../lib/api'
import type { DirectorPackDetail, DirectorPackSummary, ResolvedDirectorPolicy } from '../types/directorPack'

const tone = (status: string) => status === 'enabled' ? 'ok' : status === 'blocked' ? 'danger' : 'warn'
const trustName = (trust: string) => trust === 'TRUSTED_BUILTIN' ? '内置可信' : trust === 'LOCAL' ? '本地' : '未经验证'

export default function DirectorPacks() {
  const navigate = useNavigate()
  const fileInput = useRef<HTMLInputElement>(null)
  const [packs, setPacks] = useState<DirectorPackSummary[]>([])
  const [selectedKey, setSelectedKey] = useState('')
  const [detail, setDetail] = useState<DirectorPackDetail | null>(null)
  const [policy, setPolicy] = useState<ResolvedDirectorPolicy | null>(null)
  const [presetText, setPresetText] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [deriveOpen, setDeriveOpen] = useState(false)
  const [derivedId, setDerivedId] = useState('')
  const [derivedVersion, setDerivedVersion] = useState('0.1.0')
  const [derivedStyle, setDerivedStyle] = useState('')

  const selected = useMemo(() => packs.find(pack => `${pack.id}@${pack.version}` === selectedKey) || null, [packs, selectedKey])

  const refresh = async (preferKey = selectedKey) => {
    const values = await api.listDirectorPacks()
    setPacks(values)
    const key = values.some(pack => `${pack.id}@${pack.version}` === preferKey)
      ? preferKey
      : values[0] ? `${values[0].id}@${values[0].version}` : ''
    setSelectedKey(key)
  }

  useEffect(() => { refresh().catch(reason => setError(reason.message || '无法读取导演包')) }, [])

  useEffect(() => {
    if (!selected) { setDetail(null); setPolicy(null); setPresetText(''); return }
    let closed = false
    setError('')
    Promise.all([
      api.getDirectorPack(selected.id, selected.version),
      api.resolveDirectorPack(selected.id, selected.version, 'auto').catch(() => null),
    ]).then(async ([nextDetail, nextPolicy]) => {
      if (closed) return
      setDetail(nextDetail); setPolicy(nextPolicy)
      const preset = nextDetail.manifest.presets?.[0]
      setPresetText(preset ? await api.getDirectorPackAssetText(selected.id, selected.version, preset.path).catch(() => '') : '')
    }).catch(reason => !closed && setError(reason.message || '无法读取导演包详情'))
    return () => { closed = true }
  }, [selectedKey])

  const importPack = async (file?: File) => {
    if (!file || busy) return
    setBusy('import'); setError('')
    try {
      const record = await api.importDirectorPack(file)
      await refresh(`${record.id}@${record.version}`)
    } catch (reason: any) { setError(reason.message || '导演包导入失败') }
    finally { setBusy(''); if (fileInput.current) fileInput.current.value = '' }
  }

  const toggleEnabled = async () => {
    if (!selected || busy) return
    setBusy('toggle'); setError('')
    try { await api.setDirectorPackEnabled(selected.id, selected.version, selected.status === 'disabled'); await refresh(selectedKey) }
    catch (reason: any) { setError(reason.message || '无法更新导演包状态') }
    finally { setBusy('') }
  }

  const uninstall = async () => {
    if (!selected || busy) return
    const confirmed = window.confirm('卸载不会删除已有项目、素材、Scene 绑定或输出，但旧 Run 将不能重新导演。确定卸载吗？')
    if (!confirmed) return
    setBusy('delete'); setError('')
    try { await api.uninstallDirectorPack(selected.id, selected.version); await refresh('') }
    catch (reason: any) { setError(reason.message || '导演包卸载失败') }
    finally { setBusy('') }
  }

  const openDerive = () => {
    if (!detail) return
    const [publisher, slug] = detail.id.split('/', 2)
    setDerivedId(`${publisher}/${slug}-custom`)
    setDerivedVersion('0.1.0')
    setDerivedStyle(detail.manifest.style.anchor)
    setDeriveOpen(true)
  }

  const derive = async () => {
    if (!selected || busy || !derivedId.trim() || !derivedVersion.trim()) return
    setBusy('derive'); setError('')
    try {
      const result = await api.deriveDirectorPack(selected.id, selected.version, {
        id: derivedId.trim(), version: derivedVersion.trim(), style: { anchor: derivedStyle.trim() },
      })
      setDeriveOpen(false)
      await refresh(`${result.id}@${result.version}`)
    } catch (reason: any) { setError(reason.message || '派生导演包失败') }
    finally { setBusy('') }
  }

  return <main className="min-h-[100dvh] workbench-shell p-6">
    <div className="max-w-6xl mx-auto space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <button className="icon-button" onClick={() => navigate('/')} aria-label="返回首页"><ArrowLeft size={18} /></button>
          <div><p className="section-index">DIRECTOR PACKS / PROTOCOL V1</p><h1 className="text-2xl font-heading">导演包</h1></div>
        </div>
        <div className="flex gap-2">
          <input ref={fileInput} type="file" className="hidden" accept=".vfdirector,.zip" onChange={event => importPack(event.target.files?.[0])} />
          <button className="btn-cinematic" onClick={() => fileInput.current?.click()} disabled={Boolean(busy)}>
            {busy === 'import' ? <CircleNotch className="animate-spin" size={15} /> : <UploadSimple size={15} />} 导入 .vfdirector
          </button>
          <button className="btn-gold" onClick={() => navigate('/factory/new')}><Plus size={15} /> 用导演包生产</button>
        </div>
      </header>

      <section className="card-cinematic p-4">
        <p className="text-sm">导演包决定怎么拍；Provider 负责生产素材；VideoForge 负责审批、绑定和时间轴。</p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>导演包只包含声明式策略、参考模板和结构化参数，不执行 Python、JavaScript 或安装脚本。</p>
      </section>

      {error && <div className="operation-error">{error}</div>}

      <div className="grid lg:grid-cols-[320px_minmax(0,1fr)] gap-4 items-start">
        <aside className="card-cinematic p-3 space-y-2">
          <div className="flex items-center justify-between px-1"><p className="label-cinematic">INSTALLED</p><span className="text-xs" style={{ color: 'var(--text-muted)' }}>{packs.length} 个版本</span></div>
          {packs.length === 0 && <div className="p-6 text-center text-sm" style={{ color: 'var(--text-muted)' }}><Package size={28} className="mx-auto mb-2" />尚未安装导演包</div>}
          {packs.map(pack => {
            const active = selectedKey === `${pack.id}@${pack.version}`
            return <button key={`${pack.id}@${pack.version}`} onClick={() => setSelectedKey(`${pack.id}@${pack.version}`)} className={`w-full text-left rounded-md border p-3 ${active ? 'selected-surface' : ''}`} style={!active ? { background: 'var(--bg-surface)', borderColor: 'var(--border)', color: 'var(--text-primary)' } : undefined}>
              <div className="flex items-start gap-2"><Package size={16} className="mt-0.5" /><div className="min-w-0"><strong className="block truncate">{pack.name || pack.id}</strong><span className="text-xs opacity-80">{pack.id} · v{pack.version}</span></div></div>
              <div className="flex items-center gap-2 mt-2 text-xs"><span>{trustName(pack.sourceTrust)}</span><span>·</span><span>{pack.referenceCount} 个参考</span></div>
            </button>
          })}
        </aside>

        <section className="card-cinematic p-5 min-h-[520px]">
          {!selected || !detail ? <div className="h-[440px] grid place-items-center"><CircleNotch className="animate-spin" size={24} /></div> : <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><p className="section-index">{detail.id} / {detail.version}</p><h2 className="text-2xl font-heading">{detail.manifest.name}</h2><p className="text-sm mt-1 max-w-2xl" style={{ color: 'var(--text-muted)' }}>{detail.manifest.description}</p></div>
              <span className="status-pill px-3 py-1 text-xs" data-tone={tone(policy?.status || detail.status)}>{policy?.status || detail.status}</span>
            </div>

            <div className="grid sm:grid-cols-3 gap-2 text-xs">
              <div className="panel-section"><span style={{ color: 'var(--text-muted)' }}>来源信任</span><strong className="block mt-1">{trustName(detail.sourceTrust)}</strong></div>
              <div className="panel-section"><span style={{ color: 'var(--text-muted)' }}>候选数量</span><strong className="block mt-1">每 Scene {detail.manifest.candidates.count} 个</strong></div>
              <div className="panel-section"><span style={{ color: 'var(--text-muted)' }}>默认审批</span><strong className="block mt-1">{detail.manifest.approval.defaultMode.toUpperCase()}</strong></div>
            </div>

            {policy?.degradations?.length ? <div className="status-pill px-3 py-2 text-xs" data-tone="warn"><WarningCircle size={15} />{policy.degradations.join('；')}</div> : <div className="status-pill px-3 py-2 text-xs" data-tone="ok"><CheckCircle size={15} />依赖满足，可使用已解析策略</div>}

            <div>
              <p className="label-cinematic mb-2">REFERENCE TEMPLATES</p>
              <div className="grid md:grid-cols-3 gap-3">
                {(detail.manifest.references || []).map(reference => <figure key={reference.path} className="rounded-md overflow-hidden border" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
                  <img className="w-full aspect-video object-contain p-2" src={api.directorPackAssetUrl(detail.id, detail.version, reference.path)} alt={`${reference.role} 参考模板`} />
                  <figcaption className="px-3 py-2 text-xs border-t" style={{ borderColor: 'var(--border)' }}>{reference.role}<span className="block truncate" style={{ color: 'var(--text-muted)' }}>{reference.path}</span></figcaption>
                </figure>)}
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <div className="panel-section"><p className="label-cinematic mb-2">STYLE POLICY</p><p className="text-sm">{detail.manifest.style.anchor}</p><div className="flex flex-wrap gap-1 mt-3">{detail.manifest.style.avoid.map(item => <span key={item} className="status-pill px-2 py-1 text-xs">避免：{item}</span>)}</div></div>
              <div className="panel-section"><p className="label-cinematic mb-2">PALETTE PRESET</p>{presetText ? <pre className="text-xs whitespace-pre-wrap overflow-auto">{presetText}</pre> : <p className="text-xs" style={{ color: 'var(--text-muted)' }}>此包没有结构化 preset。</p>}</div>
            </div>

            <div className="panel-section"><p className="label-cinematic mb-2">RESOLVED PROVIDERS</p><div className="space-y-2">{policy?.providers.map(provider => <div key={provider.id} className="flex items-center justify-between text-sm"><span>{provider.id} <small style={{ color: 'var(--text-muted)' }}>v{provider.version}</small></span><span className="status-pill px-2 py-1 text-xs" data-tone={provider.ready ? 'ok' : 'danger'}>{provider.ready ? 'ready' : 'missing'}</span></div>)}</div></div>

            <details className="panel-section"><summary className="cursor-pointer text-sm">查看本次 Resolved Director Policy</summary><pre className="text-xs mt-3 overflow-auto max-h-80 whitespace-pre-wrap">{JSON.stringify(policy, null, 2)}</pre></details>

            {deriveOpen && <div className="panel-section space-y-3">
              <div><p className="label-cinematic">DERIVE LOCAL COPY</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>只允许修改原包声明为 editable 的字段；原版本保持不变。</p></div>
              <div className="grid sm:grid-cols-2 gap-2"><label className="text-xs">新 ID<input className="input-cinematic mt-1" value={derivedId} onChange={event => setDerivedId(event.target.value)} /></label><label className="text-xs">版本<input className="input-cinematic mt-1" value={derivedVersion} onChange={event => setDerivedVersion(event.target.value)} /></label></div>
              <label className="text-xs">风格锚点<textarea className="input-cinematic mt-1 min-h-24" value={derivedStyle} onChange={event => setDerivedStyle(event.target.value)} /></label>
              <div className="flex justify-end gap-2"><button className="btn-cinematic text-xs" onClick={() => setDeriveOpen(false)}>取消</button><button className="btn-gold text-xs" onClick={derive} disabled={busy === 'derive'}>{busy === 'derive' && <CircleNotch className="animate-spin" size={14} />}保存派生包</button></div>
            </div>}

            <div className="flex flex-wrap gap-2 pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
              <button className="btn-cinematic text-xs" onClick={() => api.exportDirectorPack(detail.id, detail.version).catch(reason => setError(reason.message))}><DownloadSimple size={14} />导出</button>
              <button className="btn-cinematic text-xs" onClick={openDerive}><Plus size={14} />复制并派生</button>
              <button className="btn-cinematic text-xs" onClick={toggleEnabled} disabled={Boolean(busy)}><Power size={14} />{selected.status === 'disabled' ? '启用' : '禁用'}</button>
              <button className="btn-cinematic text-xs ml-auto" onClick={uninstall} disabled={Boolean(busy)}><Trash size={14} />卸载</button>
            </div>
          </div>}
        </section>
      </div>
    </div>
  </main>
}
