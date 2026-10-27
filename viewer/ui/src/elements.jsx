function Status({ state }) {
  if (state === 'done') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="mt-0.5 shrink-0">
        <circle cx="8" cy="8" r="6" fill="#00FF85" />
        <path d="M5 8.2 7 10.2 11 6" fill="none" stroke="#142018" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    )
  }
  if (state === 'now') {
    return (
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="mt-0.5 shrink-0">
        <circle cx="8" cy="8" r="5.2" fill="none" stroke="#E90052" strokeWidth="1.4" />
        <circle cx="8" cy="8" r="2" fill="#E90052" />
      </svg>
    )
  }
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true" className="mt-0.5 shrink-0">
      <circle cx="8" cy="8" r="5.2" fill="none" stroke="#9A9A9A" strokeDasharray="1.4 2.2" />
    </svg>
  )
}

export function TaskList({ title, count, children }) {
  return (
    <div className="w-full rounded-md bg-black/40 px-2.5 py-2 text-left">
      <div className="flex items-center px-1 pb-1">
        <p className="text-[13px] font-medium text-ink">{title}</p>
        {count ? <span className="ml-auto text-[12px] text-mute">{count}</span> : null}
      </div>
      <div>{children}</div>
    </div>
  )
}

export function TaskRow({ state, title, file }) {
  const verb = state === 'done' ? 'Done' : state === 'now' ? 'Working..' : 'Waiting'
  const tone = state === 'done' ? 'text-[#00FF85]' : state === 'now' ? 'text-[#E90052]' : 'text-mute'
  return (
    <div className={`flex items-start gap-2 border-t border-white/10 py-2 transition-opacity duration-300 ${state === 'wait' ? 'opacity-40' : 'opacity-100'}`}>
      <Status state={state} />
      <div className="min-w-0">
        <p className="text-[13px] font-medium leading-4 text-ink">{title}</p>
        <p className="mt-0.5 text-[12px] leading-4">
          <span className={tone}>{verb}</span>
          {file ? <span className="ml-1.5 font-mono text-[11px] text-mute">{file}</span> : null}
        </p>
      </div>
    </div>
  )
}

export function clipTasks(progress, ready) {
  const value = Math.max(0, Math.min(1, Number(progress) || 0))
  if (ready) return ['done', 'done', 'done']
  if (value >= 0.82) return ['done', 'done', 'now']
  if (value >= 0.2) return ['done', 'now', 'wait']
  return ['now', 'wait', 'wait']
}
