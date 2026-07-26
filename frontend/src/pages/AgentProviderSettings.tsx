import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, CheckCircle, Copy, FloppyDisk, House, Plug, Robot, WarningCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'

const blank = { enabled: false, providerId: 'custom', baseUrl: '', apiType: 'openai-completions', apiKey: '', model: '', timeoutSeconds: 30 }

export default function AgentProviderSettings() {
  const navigate = useNavigate()
  const [form, setForm] = useState<any>(blank); const [models, setModels] = useState<any[]>([]); const [manualModels, setManualModels] = useState(''); const [busy, setBusy] = useState('')
  const [feedback, setFeedback] = useState<{ tone: 'ok' | 'warn' | 'danger', title: string, detail: string, latencyMs?: number | null, modelCount?: number } | null>(null)
  useEffect(() => { api.getAgentProviderSettings().then(setForm).catch(e => setFeedback({ tone: 'danger', title: '读取配置失败', detail: e.message })) }, [])
  const change = (key: string, value: any) => setForm((old: any) => ({ ...old, [key]: value }))
  const probe = async (modelsOnly = false) => { setBusy(modelsOnly ? 'models' : 'test'); setFeedback(null); try { const result = modelsOnly ? await api.fetchAgentProviderModels(form) : await api.testAgentProvider(form); setModels(result.models || []); setFeedback(result.ok ? { tone: 'ok', title: modelsOnly ? '上游模型已读取' : '连接已验证', detail: result.message || '上游服务已响应当前凭据。', latencyMs: result.latencyMs, modelCount: (result.models || []).length } : { tone: 'danger', title: '上游服务未通过验证', detail: result.message || '请检查地址、密钥和账户状态。', latencyMs: result.latencyMs }) } catch (e: any) { setFeedback({ tone: 'danger', title: '连接失败', detail: e.message || '请求未能到达上游服务。' }) } finally { setBusy('') } }
  const save = async () => { setBusy('save'); setFeedback(null); try { const saved = await api.saveAgentProviderSettings(form); setForm((old: any) => ({ ...old, ...saved, apiKey: '' })); setFeedback({ tone: 'ok', title: '配置已保存', detail: '新的 Director Run 将使用此模型配置；仍建议先执行一次连接验证。' }) } catch (e: any) { setFeedback({ tone: 'danger', title: '保存失败', detail: e.message || '配置未保存。' }) } finally { setBusy('') } }
  const allModels = [...models, ...manualModels.split(/[\n,]/).map(id => ({ id: id.trim(), name: id.trim() })).filter(item => item.id)].filter((item, index, list) => list.findIndex(other => other.id === item.id) === index)
  const selectModel = async (id: string) => { change('model', id); try { await navigator.clipboard.writeText(id); setFeedback({ tone: 'warn', title: '模型已选中并复制', detail: id }) } catch { setFeedback({ tone: 'warn', title: '模型已选中', detail: id }) } }
  return <main className="min-h-[100dvh] workbench-shell p-4 md:p-6"><div className="max-w-4xl mx-auto space-y-4">
    <header className="card-cinematic p-5 flex items-center gap-4"><button className="icon-button" title="返回" onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/director')}><ArrowLeft size={18} /></button><div className="home-brand-mark"><Robot size={20} weight="fill" /></div><div className="flex-1"><p className="section-index">PI DIRECTOR / MODEL ROUTING</p><h1 className="text-2xl font-heading">Agent 模型服务</h1><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>兼容 OpenAI 协议的中转站、官方服务与本地模型均可接入。</p></div><button className="icon-button" title="打开智能助手" aria-label="打开智能助手" onClick={() => navigate('/director')}><Robot size={18}/></button><button className="icon-button" title="返回首页" aria-label="返回首页" onClick={() => navigate('/')}><House size={18}/></button></header>
    <section className="card-cinematic p-5 grid md:grid-cols-2 gap-4">
      <label className="text-sm flex items-center gap-2 md:col-span-2"><input type="checkbox" checked={!!form.enabled} onChange={e => change('enabled', e.target.checked)} /> 启用此 Provider 供 Pi Director 使用</label>
      <label className="label-cinematic">Provider ID<input className="input-cinematic w-full mt-2" value={form.providerId} onChange={e => change('providerId', e.target.value)} placeholder="custom / openrouter / local" /></label>
      <label className="label-cinematic">协议<select className="input-cinematic w-full mt-2" value={form.apiType} onChange={e => change('apiType', e.target.value)}><option value="openai-completions">OpenAI Chat Completions</option><option value="openai-responses">OpenAI Responses</option></select></label>
      <label className="label-cinematic md:col-span-2">Base URL<input className="input-cinematic w-full mt-2" value={form.baseUrl} onChange={e => change('baseUrl', e.target.value)} placeholder="https://your-gateway.example/v1" /></label>
      <label className="label-cinematic">API Key<input className="input-cinematic w-full mt-2" type="password" value={form.apiKey} onChange={e => change('apiKey', e.target.value)} placeholder={form.apiKeyConfigured ? '已保存，留空则保持不变' : 'sk-...'} /></label>
      <label className="label-cinematic">默认模型<input className="input-cinematic w-full mt-2" list="agent-models" value={form.model} onChange={e => change('model', e.target.value)} placeholder="gpt-4o-mini" /><datalist id="agent-models">{models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</datalist></label>
      <div className="md:col-span-2 flex flex-wrap gap-2 pt-2"><button className="btn-gold" disabled={!form.baseUrl || !!busy} onClick={() => probe(false)}><Plug size={16}/>{busy === 'test' ? '测试中...' : '测试连接'}</button><button className="btn-cinematic" disabled={!form.baseUrl || !!busy} onClick={() => probe(true)}><Check size={16}/>{busy === 'models' ? '拉取中...' : '刷新上游模型'}</button><button className="btn-cinematic" disabled={!!busy} onClick={save}><FloppyDisk size={16}/>{busy === 'save' ? '保存中...' : '保存配置'}</button></div>
      {feedback && (
        <div className="md:col-span-2 flex items-start gap-3 p-4 border rounded animate-surface-in" data-tone={feedback.tone} style={{ borderColor: feedback.tone === 'ok' ? 'var(--success)' : feedback.tone === 'danger' ? 'var(--danger)' : 'var(--warning)', background: feedback.tone === 'ok' ? 'var(--success-bg)' : 'var(--bg-elevated)' }}>
          {feedback.tone === 'ok' ? <span className="shrink-0 inline-flex p-1 rounded-full animate-pulse" style={{ color: 'var(--success)', background: 'var(--bg-surface)' }}><CheckCircle size={22} weight="fill" /></span> : <span className="shrink-0 inline-flex p-1" style={{ color: feedback.tone === 'danger' ? 'var(--danger)' : 'var(--warning)' }}><WarningCircle size={22} weight="fill" /></span>}
          <div className="min-w-0 flex-1">
            <div className="font-semibold">{feedback.title}</div>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{feedback.detail}</p>
            {feedback.tone === 'ok' && <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] mt-2" style={{ color: 'var(--success)' }}>
              <span>已验证 {new Date().toLocaleTimeString()}</span>
              {typeof feedback.latencyMs === 'number' && <span>{feedback.latencyMs} ms</span>}
              {typeof feedback.modelCount === 'number' && <span>{feedback.modelCount} 个可用模型</span>}
            </div>}
          </div>
        </div>
      )}
      <div className="md:col-span-2 border-t pt-4" style={{ borderColor: 'var(--border)' }}><p className="label-cinematic">可选模型</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>刷新成功后显示上游真实列表。也可把模型 ID 按行或逗号粘贴进下方，点击即可选中并复制。</p><textarea className="input-cinematic w-full min-h-[72px] mt-3 text-sm" value={manualModels} onChange={e => setManualModels(e.target.value)} placeholder="例如：gpt-4o-mini&#10;deepseek-chat&#10;qwen-plus" /><div className="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-[260px] overflow-auto">{allModels.map(item => <button key={item.id} className="btn-cinematic justify-between text-left" onClick={() => selectModel(item.id)}><span className="truncate">{item.name}</span><Copy size={14} /></button>)}{!allModels.length && <div className="text-xs p-3" style={{ color: 'var(--text-muted)', background: 'var(--bg-elevated)' }}>上游尚未返回模型。请先修复余额/配额后刷新，或直接粘贴模型 ID。</div>}</div></div>
    </section>
  </div></main>
}
