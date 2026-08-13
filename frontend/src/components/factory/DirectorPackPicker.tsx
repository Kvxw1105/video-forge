import { Check, FilmSlate, Package, WarningCircle } from '@phosphor-icons/react'
import type { DirectorPackSummary, DirectorSource, ProductionProfileSummary } from '../../types/directorPack'

type Props = {
  profiles: ProductionProfileSummary[]
  packs: DirectorPackSummary[]
  value: DirectorSource
  onChange: (value: DirectorSource) => void
  onManagePacks: () => void
}

const trustLabel = (value: DirectorPackSummary['sourceTrust']) => {
  if (value === 'TRUSTED_BUILTIN') return '内置可信'
  if (value === 'LOCAL') return '本地派生'
  return '未经验证'
}

export default function DirectorPackPicker({ profiles, packs, value, onChange, onManagePacks }: Props) {
  return <section className="space-y-3" aria-labelledby="director-source-title">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p className="label-cinematic">DIRECTOR METHOD</p>
        <h3 id="director-source-title" className="text-lg font-heading">选择导演方式</h3>
        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
          快捷预设和导演包只能选择一种，避免规则相互覆盖。
        </p>
      </div>
      <button type="button" className="btn-cinematic text-xs" onClick={onManagePacks}>
        <Package size={14} /> 管理导演包
      </button>
    </div>

    <div className="grid md:grid-cols-2 gap-2">
      {profiles.map(profile => {
        const selected = value.kind === 'profile' && value.id === profile.id
        return <button
          type="button"
          key={`profile:${profile.id}`}
          aria-pressed={selected}
          onClick={() => onChange({ kind: 'profile', id: profile.id })}
          className={`text-left rounded-md border p-3 transition-transform active:scale-[0.98] ${selected ? 'selected-surface selected-text' : ''}`}
          style={!selected ? { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border)' } : undefined}
        >
          <div className="flex items-center gap-2"><FilmSlate size={16} /><strong>{profile.name}</strong>{selected && <Check className="ml-auto" size={15} />}</div>
          <p className="text-xs mt-1 opacity-80">快捷预设 · {profile.description || '使用内置语义路由'}</p>
        </button>
      })}
      {packs.filter(pack => pack.status !== 'disabled').map(pack => {
        const selected = value.kind === 'director_pack' && value.id === pack.id && value.version === pack.version
        const degraded = pack.status === 'enabled_with_degradation' || pack.degradations.length > 0
        return <button
          type="button"
          key={`pack:${pack.id}@${pack.version}`}
          aria-pressed={selected}
          disabled={pack.status === 'blocked'}
          onClick={() => onChange({ kind: 'director_pack', id: pack.id, version: pack.version })}
          className={`text-left rounded-md border p-3 transition-transform active:scale-[0.98] disabled:opacity-45 ${selected ? 'selected-surface selected-text' : ''}`}
          style={!selected ? { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: degraded ? 'var(--warning)' : 'var(--border)' } : undefined}
        >
          <div className="flex items-center gap-2"><Package size={16} /><strong>{pack.name || pack.id}</strong>{selected && <Check className="ml-auto" size={15} />}</div>
          <p className="text-xs mt-1 opacity-80">v{pack.version} · {trustLabel(pack.sourceTrust)} · {pack.referenceCount} 个参考模板</p>
          {degraded && <span className="inline-flex items-center gap-1 text-xs mt-2"><WarningCircle size={13} />降级可用，运行时将进入审核</span>}
        </button>
      })}
    </div>
  </section>
}
