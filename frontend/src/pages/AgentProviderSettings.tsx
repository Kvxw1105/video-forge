import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Check, Copy, FloppyDisk, Plug, Robot } from '@phosphor-icons/react'
import { api } from '../lib/api'

const blank = { enabled: false, providerId: 'custom', baseUrl: '', apiType: 'openai-completions', apiKey: '', model: '', timeoutSeconds: 30 }

export default function AgentProviderSettings() {
  const navigate = useNavigate()
  const [form, setForm] = useState<any>(blank); const [models, setModels] = useState<any[]>([]); const [manualModels, setManualModels] = useState(''); const [status, setStatus] = useState(''); const [busy, setBusy] = useState('')
  useEffect(() => { api.getAgentProviderSettings().then(setForm).catch(e => setStatus(e.message)) }, [])
  const change = (key: string, value: any) => setForm((old: any) => ({ ...old, [key]: value }))
  const probe = async (modelsOnly = false) => { setBusy(modelsOnly ? 'models' : 'test'); setStatus(''); try { const result = modelsOnly ? await api.fetchAgentProviderModels(form) : await api.testAgentProvider(form); setModels(result.models || []); setStatus(result.message || (result.ok ? '连接成功' : '连接失败')) } catch (e: any) { setStatus(e.message || '连接失败') } finally { setBusy('') } }
  const save = async () => { setBusy('save'); setStatus(''); try { const saved = await api.saveAgentProviderSettings(form); setForm((old: any) => ({ ...old, ...saved, apiKey: '' })); setStatus('已保存。新 Director Run 将使用此模型配置。') } catch (e: any) { setStatus(e.message || '保存失败') } finally { setBusy('') } }
  const allModels = [...models, ...manualModels.split(/[\n,]/).map(id => ({ id: id.trim(), name: id.trim() })).filter(item => item.id)].filter((item, index, list) => list.findIndex(other => other.id === item.id) === index)
  const selectModel = async (id: string) => { change('model', id); try { await navigator.clipboard.writeText(id); setStatus(`已选择并复制模型 ID：${id}`) } catch { setStatus(`已选择模型 ID：${id}`) } }
  return <main className="min-h-[100dvh] workbench-shell p-4 md:p-6"><div className="max-w-4xl mx-auto space-y-4">
    <header className="card-cinematic p-5 flex items-center gap-4"><button className="btn-cinematic" title="返回" onClick={() => window.history.length > 1 ? navigate(-1) : navigate('/director')}><ArrowLeft size={18} /></button><div className="home-brand-mark"><Robot size={20} weight="fill" /></div><div><p className="section-index">PI DIRECTOR / MODEL ROUTING</p><h1 className="text-2xl font-heading">Agent 模型服务</h1><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>兼容 OpenAI 协议的中转站、官方服务与本地模型均可接入。</p></div></header>
    <section className="card-cinematic p-5 grid md:grid-cols-2 gap-4">
      <label className="text-sm flex items-center gap-2 md:col-span-2"><input type="checkbox" checked={!!form.enabled} onChange={e => change('enabled', e.target.checked)} /> 启用此 Provider 供 Pi Director 使用</label>
      <label className="label-cinematic">Provider ID<input className="input-cinematic w-full mt-2" value={form.providerId} onChange={e => change('providerId', e.target.value)} placeholder="custom / openrouter / local" /></label>
      <label className="label-cinematic">协议<select className="input-cinematic w-full mt-2" value={form.apiType} onChange={e => change('apiType', e.target.value)}><option value="openai-completions">OpenAI Chat Completions</option><option value="openai-responses">OpenAI Responses</option></select></label>
      <label className="label-cinematic md:col-span-2">Base URL<input className="input-cinematic w-full mt-2" value={form.baseUrl} onChange={e => change('baseUrl', e.target.value)} placeholder="https://your-gateway.example/v1" /></label>
      <label className="label-cinematic">API Key<input className="input-cinematic w-full mt-2" type="password" value={form.apiKey} onChange={e => change('apiKey', e.target.value)} placeholder={form.apiKeyConfigured ? '已保存，留空则保持不变' : 'sk-...'} /></label>
      <label className="label-cinematic">默认模型<input className="input-cinematic w-full mt-2" list="agent-models" value={form.model} onChange={e => change('model', e.target.value)} placeholder="gpt-4o-mini" /><datalist id="agent-models">{models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</datalist></label>
      <div className="md:col-span-2 flex flex-wrap gap-2 pt-2"><button className="btn-gold" disabled={!form.baseUrl || !!busy} onClick={() => probe(false)}><Plug size={16}/>{busy === 'test' ? '测试中...' : '测试连接'}</button><button className="btn-cinematic" disabled={!form.baseUrl || !!busy} onClick={() => probe(true)}><Check size={16}/>{busy === 'models' ? '拉取中...' : '刷新上游模型'}</button><button className="btn-cinematic" disabled={!!busy} onClick={save}><FloppyDisk size={16}/>{busy === 'save' ? '保存中...' : '保存配置'}</button></div>
      {status && <div className="md:col-span-2 text-sm p-3 rounded" style={{ background: 'var(--bg-elevated)' }}>{status}{models.length ? ` · ${models.length} 个模型` : ''}</div>}
      <div className="md:col-span-2 border-t pt-4" style={{ borderColor: 'var(--border)' }}><p className="label-cinematic">可选模型</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>刷新成功后显示上游真实列表。也可把模型 ID 按行或逗号粘贴进下方，点击即可选中并复制。</p><textarea className="input-cinematic w-full min-h-[72px] mt-3 text-sm" value={manualModels} onChange={e => setManualModels(e.target.value)} placeholder="例如：gpt-4o-mini&#10;deepseek-chat&#10;qwen-plus" /><div className="mt-3 grid sm:grid-cols-2 lg:grid-cols-3 gap-2 max-h-[260px] overflow-auto">{allModels.map(item => <button key={item.id} className="btn-cinematic justify-between text-left" onClick={() => selectModel(item.id)}><span className="truncate">{item.name}</span><Copy size={14} /></button>)}{!allModels.length && <div className="text-xs p-3" style={{ color: 'var(--text-muted)', background: 'var(--bg-elevated)' }}>上游尚未返回模型。请先修复余额/配额后刷新，或直接粘贴模型 ID。</div>}</div></div>
    </section>
  </div></main>
}
