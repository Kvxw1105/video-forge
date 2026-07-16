import { motion } from 'framer-motion'
interface Props { checked: boolean; onChange: (v: boolean) => void }
export function Toggle({ checked, onChange }: Props) {
  return (
    <button onClick={() => onChange(!checked)}
      className="w-8 h-[18px] rounded-full p-0.5 transition-colors"
      style={{ background: checked ? 'var(--accent)' : 'var(--bg-elevated)' }}>
      <motion.div animate={{ x: checked ? 14 : 0 }} transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        className="w-3.5 h-3.5 rounded-full shadow-sm"
        style={{ background: 'var(--text-inverse)' }} />
    </button>
  )
}
