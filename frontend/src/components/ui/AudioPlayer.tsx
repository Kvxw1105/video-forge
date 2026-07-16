import { Play, Pause, SpeakerHigh } from '@phosphor-icons/react'
import { useState, useRef, useEffect } from 'react'

export default function AudioPlayer({ src }: { src: string }) {
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    setPlaying(false)
    setCurrentTime(0)
    setDuration(0)
    el.pause()
    el.load()
    const onTime = () => setCurrentTime(el.currentTime)
    const onMeta = () => setDuration(Number.isFinite(el.duration) ? el.duration : 0)
    const onEnd = () => setPlaying(false)
    el.addEventListener('timeupdate', onTime)
    el.addEventListener('loadedmetadata', onMeta)
    el.addEventListener('durationchange', onMeta)
    el.addEventListener('ended', onEnd)
    return () => {
      el.removeEventListener('timeupdate', onTime)
      el.removeEventListener('loadedmetadata', onMeta)
      el.removeEventListener('durationchange', onMeta)
      el.removeEventListener('ended', onEnd)
    }
  }, [src])

  const toggle = () => {
    const el = audioRef.current
    if (!el) return
    if (playing) {
      el.pause()
      setPlaying(false)
    } else {
      el.play().catch(() => {})
      setPlaying(true)
    }
  }

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = audioRef.current
    if (!el || !duration) return
    const rect = e.currentTarget.getBoundingClientRect()
    const pct = (e.clientX - rect.left) / rect.width
    el.currentTime = pct * duration
  }

  const fmt = (s: number) => {
    const m = Math.floor(s / 60)
    const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  if (!src) return null

  return (
    <div className="flex items-center gap-3 rounded-xl px-3 py-2"
      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
      <audio key={src} ref={audioRef} src={src} preload="metadata" />
      <button onClick={toggle}
        className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-all active:scale-90"
        style={{ background: 'var(--accent)', color: 'var(--text-inverse)' }}>
        {playing ? <Pause size={14} weight="fill" /> : <Play size={14} weight="fill" />}
      </button>
      <div className="flex-1 h-1.5 rounded-full cursor-pointer relative"
        style={{ background: 'var(--border-subtle)' }} onClick={seek}>
        <div
          className="h-full rounded-full"
          style={{
            width: duration ? `${(currentTime / duration) * 100}%` : '0%',
            background: 'var(--accent)',
          }}
        />
      </div>
      <span className="text-[11px] font-mono w-16 text-right tabular-nums shrink-0"
        style={{ color: 'var(--text-muted)' }}>
        {duration ? `${fmt(currentTime)} / ${fmt(duration)}` : '--:--'}
      </span>
      <SpeakerHigh size={14} className="shrink-0" style={{ color: 'var(--text-muted)' }} />
    </div>
  )
}
