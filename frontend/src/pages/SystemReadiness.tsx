import { ArrowLeft, ArrowClockwise, Check, CheckCircle, CaretDown, Circle, CloudWarning, Gear, Info, Warning, XCircle } from '@phosphor-icons/react'
import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useSystemReadiness } from '../contexts/SystemReadinessContext'
import type { ReadinessCheck, ReadinessCheckStatus, ReadinessStatus } from '../types/systemReadiness'

const statusCopy: Record<ReadinessStatus, { title: string; description: string; tone: string }> = {
  ready: { title: '运行环境正常', description: '所有必要检查均已通过，可以正常使用 VideoForge。', tone: 'ok' },
  degraded: { title: '部分功能受限', description: 'VideoForge 可以继续使用，但部分能力可能暂不可用。', tone: 'warn' },
  blocked: { title: '存在需要处理的问题', description: '至少一个必要检查未通过，请先处理下方标记的问题。', tone: 'danger' },
}

const checkStatus: Record<ReadinessCheckStatus, { label: string; tone: string }> = {
  pass: { label: '正常', tone: 'ok' },
  warn: { label: '注意', tone: 'warn' },
  fail: { label: '未通过', tone: 'danger' },
}

const capabilityLabels: Record<string, string> = {
  projectEditing: '项目编辑',
  voiceover: '配音生成',
  previewRendering: '预览渲染',
  jianyingZipExport: '剪映 ZIP 导出',
  jianyingDirectExport: '剪映直接导出',
}

const detailLabels: Record<string, string> = {
  path: '路径', freeGb: '可用空间', totalBytes: '总空间', version: '版本',
  selectedEngine: '当前引擎', missingFields: '缺少配置', draftCount: '草稿数量',
  productionMode: '生产模式', python: 'Python', os: '操作系统', mode: '工作模式',
  authConfigured: '已配置鉴权', error: '错误', errorType: '异常类型',
  detected: '已检测', directoryExists: '目录存在', writable: '可写入',
}

function formatBytes(value: number) {
  if (!Number.isFinite(value)) return ''
  if (value > 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GB`
  if (value > 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${Math.round(value / 1024)} KB`
}

function formatDetail(key: string, value: unknown) {
  if (value === null || value === undefined || value === '') return null
  if (key === 'path') return <span className="readiness-detail-path">{String(value)}</span>
  if (key === 'freeGb') return `${Number(value).toFixed(2)} GB`
  if (key === 'totalBytes') return formatBytes(Number(value))
  if (key === 'missingFields' && Array.isArray(value)) return value.map(String).join('、')
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function DetailGrid({ details, failed }: { details: Record<string, unknown>; failed: boolean }) {
  const entries = Object.entries(details).filter(([key, value]) => detailLabels[key] && value !== null && value !== undefined && value !== '')
  if (!entries.length) return null
  return (
    <div className={`readiness-detail-grid ${failed ? 'is-failed' : ''}`}>
      {entries.map(([key, value]) => {
        const formatted = formatDetail(key, value)
        if (formatted === null) return null
        return <div className="readiness-detail" key={key}><dt>{detailLabels[key]}</dt><dd>{formatted}</dd></div>
      })}
    </div>
  )
}

function StatusIcon({ status }: { status: ReadinessCheckStatus | ReadinessStatus }) {
  if (status === 'pass' || status === 'ready') return <CheckCircle weight="fill" />
  if (status === 'warn' || status === 'degraded') return <Warning weight="fill" />
  return <XCircle weight="fill" />
}

function ReadinessSkeleton() {
  return <div className="readiness-skeleton" aria-label="正在加载系统检查"><span /><span /><span /><span /></div>
}

export default function SystemReadiness() {
  const { data, loading, refreshing, error, refresh } = useSystemReadiness()
  const overall = data ? statusCopy[data.status] : null

  return (
    <div className="readiness-page">
      <header className="readiness-header">
        <div className="readiness-header-left">
          <Link to="/" className="readiness-back" aria-label="返回首页"><ArrowLeft size={17} weight="bold" /></Link>
          <div><p className="readiness-eyebrow"><Gear size={13} /> 系统 / 诊断</p><h1>运行环境检查</h1><p className="readiness-subtitle">检查 VideoForge 的运行目录、磁盘空间、渲染组件、配音配置和剪映连接状态。</p></div>
        </div>
        <div className="readiness-header-actions">
          {data && <div className="readiness-meta"><span>版本 {data.app.version}</span><span>最近检查 {new Date(data.checkedAt).toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span></div>}
          <button className="btn-gold readiness-refresh" onClick={() => void refresh()} disabled={refreshing} aria-busy={refreshing}>
            <ArrowClockwise size={15} className={refreshing ? 'readiness-spin' : ''} />{refreshing ? '检查中…' : '重新检查'}
          </button>
        </div>
      </header>

      <main className="readiness-content">
        {loading && !data ? <ReadinessSkeleton /> : error && !data ? <ErrorPanel onRetry={() => void refresh()} /> : data ? <>
          <section className={`readiness-overview readiness-tone-${overall?.tone}`} aria-live="polite">
            <div className="readiness-overview-main"><div className="readiness-overview-icon"><StatusIcon status={data.status} /></div><div><p className="readiness-overline">SYSTEM READINESS</p><h2>{overall?.title}</h2><p>{overall?.description}</p></div></div>
            <div className="readiness-overview-stamp">{data.app.productionMode ? '生产模式' : '开发模式'}<span>{data.app.name}</span></div>
          </section>

          {error && <div className="readiness-inline-error" role="status"><Info size={16} />重新检查失败，当前显示上一次结果。</div>}

          <section className="readiness-summary-grid" aria-label="检查摘要">
            <SummaryCard icon={<Check size={16} />} label="已通过" value={data.summary.passed} tone="ok" />
            <SummaryCard icon={<Warning size={16} />} label="需注意" value={data.summary.warnings} tone="warn" />
            <SummaryCard icon={<XCircle size={16} />} label="未通过" value={data.summary.failed} tone="danger" />
          </section>

          <section className="readiness-section"><div className="readiness-section-heading"><div><p className="readiness-overline">CAPABILITIES</p><h2>可用能力</h2></div><span>{Object.values(data.capabilities).filter(Boolean).length}/{Object.keys(data.capabilities).length} 项可用</span></div><div className="readiness-capability-grid">{Object.entries(data.capabilities).map(([key, available]) => <div className={`readiness-capability ${available ? 'is-available' : ''}`} key={key}><span className="readiness-capability-mark">{available ? <Check size={13} weight="bold" /> : <Circle size={10} weight="bold" />}</span><span>{capabilityLabels[key] ?? key}</span><small>{available ? '可用' : '暂不可用'}</small></div>)}</div></section>

          <section className="readiness-section"><div className="readiness-section-heading"><div><p className="readiness-overline">CHECKS</p><h2>检查项目</h2></div><span>按服务端返回顺序</span></div><div className="readiness-check-list">{data.checks.length ? data.checks.map(check => <CheckCard key={check.id} check={check} />) : <div className="readiness-empty"><CloudWarning size={23} />暂时没有可显示的检查项目。</div>}</div></section>
        </> : null}
      </main>
    </div>
  )
}

function SummaryCard({ icon, label, value, tone }: { icon: ReactNode; label: string; value: number; tone: string }) {
  return <div className={`readiness-summary-card readiness-tone-${tone}`}><span className="readiness-summary-icon">{icon}</span><div><strong>{value}</strong><span>{label}</span></div></div>
}

function CheckCard({ check }: { check: ReadinessCheck }) {
  const state = checkStatus[check.status]
  return <article className={`readiness-check-card readiness-check-${state.tone} ${check.required ? 'is-required' : ''}`}><div className="readiness-check-top"><div className="readiness-check-icon"><StatusIcon status={check.status} /></div><div className="readiness-check-title"><h3>{check.label}</h3><p>{check.message}</p></div><span className="readiness-check-status">{state.label}</span></div><div className="readiness-check-footer"><span className="readiness-check-id">{check.id}</span><span className="readiness-required">{check.required ? '必要检查' : '可选检查'}</span></div>{Object.keys(check.details).length > 0 && <details className="readiness-details"><summary><CaretDown size={13} />查看详情</summary><DetailGrid details={check.details} failed={check.status === 'fail'} /></details>}</article>
}

function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  return <section className="readiness-error-panel" role="alert"><XCircle size={24} /><div><h2>无法获取系统检查结果</h2><p>请确认 VideoForge 后端正在运行，然后重新检查。</p></div><button className="btn-cinematic" onClick={onRetry}>重新检查</button></section>
}
