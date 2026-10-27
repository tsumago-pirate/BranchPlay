import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { TaskList, TaskRow, clipTasks } from './elements.jsx'
import wordmark from './branchplay-wordmark.png'
import flagDe from 'flag-icons/flags/4x3/de.svg'
import flagEs from 'flag-icons/flags/4x3/es.svg'
import flagFr from 'flag-icons/flags/4x3/fr.svg'
import flagGb from 'flag-icons/flags/4x3/gb.svg'
import flagPt from 'flag-icons/flags/4x3/pt.svg'

const CARD = 'hud-card pointer-events-auto isolate overflow-hidden rounded-lg text-ink'

function titleCase(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/(^|\s)\S/g, (letter) => letter.toUpperCase())
}

const SCORE_NAMES = { FRQ: 'ARS', RBA: 'MNC' }

function scoreName(name, fallback) {
  if (name && SCORE_NAMES[name]) return SCORE_NAMES[name]
  return name || fallback
}

function possessionShare(status, side) {
  const share = status && status.possession
  const value = share && Number(share[side])
  if (!Number.isFinite(value)) return 50
  return Math.max(0, Math.min(100, Math.round(value)))
}

function Icon({ children }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      className="shrink-0"
    >
      {children}
    </svg>
  )
}

function ScreenIcon() {
  return (
    <Icon>
      <rect x="1.6" y="3.2" width="12.8" height="8.2" rx="1.4" stroke="currentColor" strokeWidth="1.4" />
      <path d="M6 13.2h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </Icon>
  )
}

function ActionIcon() {
  return (
    <Icon>
      <circle cx="8" cy="8" r="2.1" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 2.4v2.1M8 11.5v2.1M2.4 8h2.1M11.5 8h2.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </Icon>
  )
}

function MoveIcon() {
  return (
    <Icon>
      <path d="M8 2.2v11.6M2.2 8h11.6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <path d="M8 2.2 6.2 4M8 2.2 9.8 4M8 13.8 6.2 12M8 13.8 9.8 12M2.2 8 4 6.2M2.2 8 4 9.8M13.8 8 12 6.2M13.8 8 12 9.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </Icon>
  )
}

function Row({ selected, icon, label, onClick, disabled }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`mx-1.5 flex w-[calc(100%-12px)] items-center gap-3 rounded-lg px-2.5 py-[7px] text-left text-[14px] font-medium leading-5 transition-colors duration-150 ${
        selected ? 'bg-club text-pitch' : 'text-mute hover:bg-white/10 hover:text-ink'
      } ${disabled ? 'cursor-default opacity-40 hover:bg-transparent hover:text-mute' : ''}`}
    >
      {icon}
      <span className="min-w-0 flex-1 truncate">{label}</span>
    </button>
  )
}

function clockSeconds(clock) {
  const [minutes, seconds] = String(clock || '0:0').split(':')
  return (Number(minutes) || 0) * 60 + (Number(seconds) || 0)
}

function formatClock(seconds) {
  const whole = Math.max(0, Math.round(Number(seconds) || 0))
  const minutes = Math.floor(whole / 60)
  const remain = whole % 60
  return `${String(minutes).padStart(2, '0')}:${String(remain).padStart(2, '0')}`
}

const MOMENT_COPY = {
  en: {
    kicker: 'Key moment',
    close: 'Close',
    play: 'Play the key moment',
    writing: 'Writing the paragraph',
    read: 'Read the stretch',
    write: 'Write the paragraph',
    drawing: 'Drawing the moment',
    draw: 'Draw the pictures',
    finish: 'Finish the frame',
    filming: 'Filming the comparison',
    ask: 'Run a counterfactual?',
    yes: 'Yes',
    no: 'No',
    whatIf: 'What if',
    download: 'Download',
  },
  es: {
    kicker: 'Momento clave',
    close: 'Cerrar',
    play: 'Ver el momento clave',
    writing: 'Escribiendo el párrafo',
    read: 'Leer el tramo',
    write: 'Escribir el párrafo',
    drawing: 'Dibujando el momento',
    draw: 'Dibujar las imágenes',
    finish: 'Cerrar el plano',
    filming: 'Filmando la comparación',
    ask: '¿Un contrafactual?',
    yes: 'Sí',
    no: 'No',
    whatIf: 'Y si',
    download: 'Descargar',
  },
  fr: {
    kicker: 'Moment clé',
    close: 'Fermer',
    play: 'Lire le moment clé',
    writing: 'Rédaction du paragraphe',
    read: 'Lire le passage',
    write: 'Écrire le paragraphe',
    drawing: 'Dessin du moment',
    draw: 'Dessiner les images',
    finish: 'Finir le plan',
    filming: 'Tournage de la comparaison',
    ask: 'Lancer un contrefactuel ?',
    yes: 'Oui',
    no: 'Non',
    whatIf: 'Et si',
    download: 'Télécharger',
  },
  pt: {
    kicker: 'Momento-chave',
    close: 'Fechar',
    play: 'Ver o momento-chave',
    writing: 'A escrever o parágrafo',
    read: 'Ler o lance',
    write: 'Escrever o parágrafo',
    drawing: 'A desenhar o momento',
    draw: 'Desenhar as imagens',
    finish: 'Fechar o plano',
    filming: 'A filmar a comparação',
    ask: 'Correr um contrafactual?',
    yes: 'Sim',
    no: 'Não',
    whatIf: 'E se',
    download: 'Descarregar',
  },
  de: {
    kicker: 'Schlüsselszene',
    close: 'Schließen',
    play: 'Schlüsselszene abspielen',
    writing: 'Absatz wird geschrieben',
    read: 'Abschnitt lesen',
    write: 'Absatz schreiben',
    drawing: 'Moment wird gezeichnet',
    draw: 'Bilder zeichnen',
    finish: 'Einstellung schließen',
    filming: 'Vergleich wird gefilmt',
    ask: 'Ein Kontrafaktum rechnen?',
    yes: 'Ja',
    no: 'Nein',
    whatIf: 'Was wäre wenn',
    download: 'Herunterladen',
  },
}

function momentCopy(language) {
  return MOMENT_COPY[language] || MOMENT_COPY.en
}

const MOMENT_LANGUAGES = [
  ['en', 'English', flagGb],
  ['es', 'Spanish', flagEs],
  ['fr', 'French', flagFr],
  ['pt', 'Portuguese', flagPt],
  ['de', 'German', flagDe],
]

function LanguagePick({ onChoose, onClose }) {
  // Motion's height animation: the list opens from nothing and grows downward.
  // https://motion.dev/docs/react-animation
  return (
    <motion.div
      data-hud
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: 'auto', opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
      className="pointer-events-auto fixed left-1/2 top-[18%] z-50 w-[min(280px,86%)] -translate-x-1/2 overflow-hidden"
    >
      <div className="hud-card rounded-lg p-2 text-ink">
        <p className="px-3 pb-1 pt-2 text-[12px] text-mute">Language</p>
        {MOMENT_LANGUAGES.map(([id, label, flag]) => (
          <button key={id} type="button" onClick={() => onChoose(id)} className="btn mb-1 flex w-full items-center gap-2 text-left">
            <img src={flag} alt="" width="21" height="16" className="shrink-0" />
            {label}
          </button>
        ))}
        <button type="button" onClick={onClose} className="btn mt-1 w-full">Cancel</button>
      </div>
    </motion.div>
  )
}

function ClipWindow({ src, progress, compare, heading, copy, onClose, onYes, onNo }) {
  const [showing, setShowing] = useState(false)
  const [asking, setAsking] = useState(false)
  const videoRef = useRef(null)
  const skipEnd = useRef(false)
  useEffect(() => {
    setShowing(false)
    setAsking(false)
    skipEnd.current = false
  }, [src])
  useEffect(() => {
    const node = videoRef.current
    if (!node || !src) return undefined
    const pending = node.play()
    if (pending && typeof pending.catch === 'function') pending.catch(() => {})
    return undefined
  }, [src])
  useLayoutEffect(() => {
    reportCards()
  }, [asking, src])
  const ready = Boolean(showing && src)
  const words = copy || momentCopy('en')
  const states = clipTasks(progress, ready)
  const done = states.filter((state) => state === 'done').length
  return (
    <section data-hud className={`${CARD} moment-window pointer-events-auto fixed left-1/2 top-1/2 z-40 w-[min(960px,78vw)]`}>
      <div className="relative px-4 py-2.5">
        <p className="text-[13px] font-medium">{heading}</p>
      </div>
      <div className={`relative aspect-video w-full ${ready ? 'bg-black' : 'bg-black/[0.62]'}`}>
        <video
          ref={videoRef}
          key={src || 'empty'}
          src={src || undefined}
          autoPlay
          muted
          playsInline
          className={`moment-video absolute inset-0 h-full w-full object-contain transition-opacity duration-500 ${ready ? 'bg-black opacity-100' : 'opacity-0'}`}
          onCanPlay={() => setShowing(true)}
          onEnded={() => {
            if (skipEnd.current) return
            setAsking(true)
          }}
        />
        {ready ? null : (
          <div className="absolute inset-0 flex items-center justify-center p-8">
            <TaskList title={compare ? words.filming : words.drawing} count={`${done} / 3`}>
              <TaskRow state={states[0]} title={words.read} file="touches.json" />
              <TaskRow state={states[1]} title={words.draw} file="clip.mp4" />
              <TaskRow state={states[2]} title={words.finish} />
            </TaskList>
          </div>
        )}
        {asking && src ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/55">
            <div className="hud-card w-[min(340px,86%)] rounded-lg p-4 text-ink">
              {compare ? null : <p className="text-[15px] font-medium">{words.ask}</p>}
              <div className={`flex items-center justify-between gap-2 ${compare ? '' : 'mt-4'}`}>
                <a
                  className="btn no-underline"
                  href={src}
                  download={compare ? 'branchplay-comparison.mp4' : 'branchplay-key-moment.mp4'}
                >
                  {words.download}
                </a>
                <div className="flex gap-2">
                  {compare ? (
                    <button type="button" onClick={onClose} className="btn">{words.close}</button>
                  ) : (
                    <>
                      <button type="button" onClick={onNo} className="btn">{words.no}</button>
                      <button
                        type="button"
                        onClick={() => {
                          skipEnd.current = true
                          onYes()
                        }}
                        className="btn btn-solid"
                      >
                        {words.yes}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

function MomentArticle({ title, span, lead, preview, phase, progress, language, onClose, onPlay }) {
  const [showing, setShowing] = useState(false)
  useEffect(() => {
    setShowing(false)
  }, [preview])
  const pictureReady = Boolean(preview && showing)
  const states = pictureReady ? ['done', 'done'] : preview ? ['done', 'now'] : ['now', 'wait']
  const copy = momentCopy(language)
  return (
    <section data-hud className={`${CARD} wiki-card moment-window pointer-events-auto fixed left-1/2 top-1/2 z-40 w-[min(640px,92vw)] p-4`}>
      <p className="text-[12px] text-mute">{copy.kicker}</p>
      <div className="mt-1 flex items-start justify-between gap-3">
        <h1 className="text-[22px] font-medium leading-tight tracking-tight">{title || copy.kicker}</h1>
        <button type="button" onClick={onClose} className="btn">{copy.close}</button>
      </div>
      {span ? <p className="mt-1 text-[12px] text-mute">{span}</p> : null}
      {!lead ? (
        <div className="mt-3">
          <TaskList title={copy.writing} count={`${states.filter((state) => state === 'done').length} / 2`}>
            <TaskRow state={states[0]} title={copy.read} file="touches.json" />
            <TaskRow state={states[1]} title={copy.write} />
          </TaskList>
        </div>
      ) : (
        <div className="mt-3 grid grid-cols-[1fr_200px] items-start gap-4">
          <div>
            <p className="text-[14px] leading-relaxed">{lead}</p>
            <p className="mt-2 text-[12px] text-mute">Phi-4</p>
          </div>
          <div className="relative aspect-video overflow-hidden rounded-md bg-black/50">
            {preview ? (
              <img
                key={preview}
                src={preview}
                alt={title || 'Key moment'}
                className={`h-full w-full object-contain transition-opacity duration-500 ${pictureReady ? 'opacity-100' : 'opacity-0'}`}
                onLoad={() => setShowing(true)}
              />
            ) : null}
          </div>
        </div>
      )}
      <div className="mt-4 flex justify-end">
        <button type="button" onClick={onPlay} className="btn btn-solid">{copy.play}</button>
      </div>
    </section>
  )
}

function clipRail(pts, start, end) {
  if (!pts || pts.length < 2) return []
  const from = Math.min(start, end)
  const to = Math.max(start, end)
  const out = []
  function at(a, b, t) {
    const span = (b.t - a.t) || 1
    const u = Math.max(0, Math.min(1, (t - a.t) / span))
    return { x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u }
  }
  for (let index = 1; index < pts.length; index += 1) {
    const a = pts[index - 1]
    const b = pts[index]
    const lo = Math.min(a.t, b.t)
    const hi = Math.max(a.t, b.t)
    if (hi < from || lo > to) continue
    if (!out.length) out.push(at(a, b, Math.max(from, lo)))
    out.push(at(a, b, Math.min(to, hi)))
  }
  return out
}

function momentPoints(pts, start, end) {
  const from = Math.min(Number(start) || 0, Number(end) || 0)
  const to = Math.max(Number(start) || 0, Number(end) || 0)
  return clipRail(pts, from, to)
}

function railPath(points) {
  return points.map((point, index) => (
    `${index ? 'L' : 'M'} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`
  )).join(' ')
}

function MomentPaint({ moments, rail, onMoment, lineId }) {
  const rows = moments || []
  if (!rail || rail.length < 2) return null
  const safe = String(lineId == null ? 'match' : lineId || 'match').replace(/[^A-Za-z0-9_-]/g, '') || 'match'
  return (
    <AnimatePresence>
      {rows.map((segment, index) => {
        const points = momentPoints(rail, segment.start, segment.end)
        const d = railPath(points)
        if (!d) return null
        const id = `moment-${safe}-${segment.start}-${segment.end}`
        const head = points[0]
        const tail = points[points.length - 1]
        return (
          <motion.g
            key={`${safe}-${segment.start}-${segment.end}`}
            initial={{ scaleY: 0.04, opacity: 0 }}
            animate={{
              scaleY: 1,
              opacity: 1,
              transition: {
                scaleY: { type: 'spring', stiffness: 280, damping: 9, mass: 0.85, delay: index * 0.16 },
                opacity: { duration: 0.18, delay: index * 0.16 },
              },
            }}
            exit={{
              scaleY: 0.08,
              opacity: 0,
              transition: { duration: 0.18, ease: [0.4, 0, 0.2, 1] },
            }}
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          >
            <linearGradient id={id} gradientUnits="userSpaceOnUse" x1={head.x} y1={head.y} x2={tail.x} y2={tail.y}>
              <stop offset="0" stopColor="#00FF85" />
              <stop offset="1" stopColor="#E90052" />
            </linearGradient>
            <path d={d} fill="none" stroke={`url(#${id})`} strokeWidth="16" strokeLinecap="butt" strokeLinejoin="miter" />
            <path
              d={d}
              fill="none"
              stroke="transparent"
              strokeWidth="22"
              className="cursor-pointer"
              onPointerDown={(event) => onMomentPointerDown(event, segment, onMoment, lineId)}
            />
          </motion.g>
        )
      })}
    </AnimatePresence>
  )
}

const momentTap = { time: 0, x: 0, y: 0 }

function onMomentPointerDown(event, segment, onMoment, lineId) {
  const now = performance.now()
  const again = now - momentTap.time < 500
    && Math.abs(event.clientX - momentTap.x) < 14
    && Math.abs(event.clientY - momentTap.y) < 14
  momentTap.time = now
  momentTap.x = event.clientX
  momentTap.y = event.clientY
  if (!again) return
  event.stopPropagation()
  event.preventDefault()
  momentTap.time = 0
  if (onMoment) onMoment(segment, lineId)
}

const LANE_GAP = 26
const LANE_PAD_X = 18
const LANE_PAD_Y = 16
const FORK_R = 4
const FORK_GAP = 11
const MIN_BRANCH_PX = 48

// A one-minute branch is shorter than the fork ring, so the ring erases it
// and a longer branch from the same area is all that remains. The clock
// stays on the points. Only the drawn run grows.
function widenTail(pts, forkT) {
  if (!pts || pts.length < 2) return pts
  const head = pts.find((pt) => pt.t >= forkT - 0.05)
  const tail = pts[pts.length - 1]
  if (!head || tail.t <= forkT + 0.05) return pts
  if (tail.x - head.x >= MIN_BRANCH_PX) return pts
  const spanT = Math.max(0.001, tail.t - forkT)
  return pts.map((pt) => {
    if (pt.t <= forkT + 0.001) return pt
    const u = Math.max(0, Math.min(1, (pt.t - forkT) / spanT))
    return { t: pt.t, x: head.x + MIN_BRANCH_PX * u, y: pt.y }
  })
}

function laneOf(branches) {
  // A child sits on the free side of its parent. If that side is taken, the
  // older lines shift outward. The curve then only crosses empty space.
  const lane = new Map([['', 0]])
  const rows = [...(branches || [])].sort((a, b) => (
    a.clock - b.clock || String(a.id).localeCompare(String(b.id))
  ))
  const kids = new Map()
  function free(slot, from, to) {
    if (slot === lane.get('')) return false
    for (const row of rows) {
      const id = String(row.id)
      if (lane.get(id) !== slot) continue
      const start = Number(row.clock) || 0
      const end = Number(row.end_clock) || start
      if (start < to && end > from) return false
    }
    return true
  }
  rows.forEach((row) => {
    const id = String(row.id)
    const parent = lane.has(String(row.parent || '')) ? String(row.parent || '') : ''
    const parentLane = lane.get(parent) || 0
    const born = kids.get(parent) || 0
    kids.set(parent, born + 1)
    const dir = parentLane === 0 ? (born % 2 === 0 ? 1 : -1) : Math.sign(parentLane)
    const slot = parentLane + dir
    const from = Number(row.clock) || 0
    const to = Number(row.end_clock) || from
    if (!free(slot, from, to)) {
      for (const [key, value] of lane) {
        if (dir > 0 && value >= slot) lane.set(key, value + 1)
        if (dir < 0 && value <= slot) lane.set(key, value - 1)
      }
    }
    lane.set(id, slot)
  })
  return lane
}

function TimelineLanes({ span, length, clock, branches, activeId, moments, lineMoments, onPick, onMoment }) {
  const frame = useRef(null)
  const drag = useRef(null)
  const [pinned, setPinned] = useState(null)
  const [width, setWidth] = useState(640)
  const rows = branches || []
  const lanes = laneOf(rows)
  const indexes = [...lanes.values()]
  const minLane = Math.min(...indexes)
  const maxLane = Math.max(...indexes)
  const height = (maxLane - minLane) * LANE_GAP + LANE_PAD_Y * 2
  const extent = Math.max(1, length || span, ...rows.map((row) => Number(row.end_clock) || 0))
  const baseEnd = length || span
  const riding = pinned != null ? pinned : (activeId || '')

  useEffect(() => {
    if (pinned != null && pinned === (activeId || '')) setPinned(null)
  }, [activeId, pinned])

  useLayoutEffect(() => {
    const node = frame.current
    if (!node) return undefined
    const measure = () => setWidth(Math.max(240, node.clientWidth))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  function xAt(seconds) {
    const ratio = Math.max(0, Math.min(extent, seconds)) / extent
    return LANE_PAD_X + ratio * Math.max(1, width - LANE_PAD_X * 2)
  }

  function yAt(id) {
    return LANE_PAD_Y + (maxLane - (lanes.get(id || '') ?? 0)) * LANE_GAP
  }

  function rowOf(id) {
    return rows.find((item) => String(item.id) === String(id)) || null
  }

  function chainOf(id) {
    const chain = []
    let cursor = id ? rowOf(id) : null
    const seen = new Set()
    while (cursor && !seen.has(String(cursor.id))) {
      seen.add(String(cursor.id))
      chain.push(cursor)
      cursor = cursor.parent ? rowOf(cursor.parent) : null
    }
    chain.reverse()
    return chain
  }

  function finishOf(id) {
    if (!id) return baseEnd
    const row = rowOf(id)
    return row ? Math.max(Number(row.clock) || 0, Number(row.end_clock) || 0) : baseEnd
  }

  // One point list per line, from kickoff through every fork it rides.
  function pointsOf(id) {
    const chain = chainOf(id)
    const end = finishOf(id)
    const pts = []
    let walked = 0
    let lane = ''
    function add(t, x, y) {
      const last = pts[pts.length - 1]
      if (last && Math.abs(last.x - x) < 0.2 && Math.abs(last.y - y) < 0.2) return
      pts.push({ t, x, y })
    }
    chain.forEach((row) => {
      const fork = Math.max(walked, Number(row.clock) || 0)
      add(walked, xAt(walked), yAt(lane))
      add(fork, xAt(fork), yAt(lane))
      const y0 = yAt(lane)
      const y1 = yAt(String(row.id))
      const x0 = xAt(fork)
      const parentId = lanes.has(String(row.parent || '')) ? String(row.parent || '') : ''
      const parentLane = lanes.get(parentId) || 0
      let hops = 1
      let room = Math.max(12, xAt(end) - x0)
      for (const other of rows) {
        const otherParent = lanes.has(String(other.parent || '')) ? String(other.parent || '') : ''
        if (otherParent !== parentId || Math.abs((Number(other.clock) || 0) - fork) > 0.5) continue
        hops = Math.max(hops, Math.abs((lanes.get(String(other.id)) || 0) - parentLane) || 1)
        room = Math.min(room, Math.max(12, xAt(finishOf(String(other.id))) - x0))
      }
      const bend = Math.min(room, 18 + hops * 14)
      const x1 = x0 + bend
      const spanT = Math.max(0.001, ((x1 - LANE_PAD_X) / Math.max(1, width - LANE_PAD_X * 2)) * extent - fork)
      for (let step = 1; step <= 12; step += 1) {
        const u = step / 12
        const v = 1 - u
        const pull = bend * 0.55
        const x = v * v * v * x0 + 3 * v * v * u * (x0 + pull) + 3 * v * u * u * (x0 + pull) + u * u * u * x1
        const y = v * v * v * y0 + 3 * v * v * u * y0 + 3 * v * u * u * y1 + u * u * u * y1
        add(fork + spanT * u, x, y)
      }
      walked = fork + spanT
      lane = String(row.id)
    })
    add(walked, xAt(walked), yAt(lane))
    add(end, xAt(end), yAt(lane))
    const own = chain.length ? chain[chain.length - 1] : null
    return own ? widenTail(pts, Number(own.clock) || 0) : pts
  }

  function along(pts, seconds) {
    if (pts.length === 0) return { t: 0, x: xAt(0), y: yAt('') }
    if (seconds <= pts[0].t) return pts[0]
    for (let index = 1; index < pts.length; index += 1) {
      const a = pts[index - 1]
      const b = pts[index]
      if (seconds > b.t) continue
      const spanT = b.t - a.t || 1
      const u = Math.max(0, Math.min(1, (seconds - a.t) / spanT))
      return { t: seconds, x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u }
    }
    return pts[pts.length - 1]
  }

  function gapRails(pts, circles, radius) {
  if (!pts || pts.length < 2) return []
  const pieces = []
  let current = []
  function flush() {
    if (current.length >= 2) pieces.push(current)
    current = []
  }
  function push(pt) {
    const last = current[current.length - 1]
    if (last && Math.hypot(last.x - pt.x, last.y - pt.y) < 0.15) return
    current.push(pt)
  }
  function inside(x, y) {
    return circles.some((circle) => Math.hypot(x - circle.x, y - circle.y) < radius - 0.01)
  }
  for (let index = 1; index < pts.length; index += 1) {
    const a = pts[index - 1]
    const b = pts[index]
    const dx = b.x - a.x
    const dy = b.y - a.y
    const cuts = [0, 1]
    for (const circle of circles) {
      const fx = a.x - circle.x
      const fy = a.y - circle.y
      const quad = dx * dx + dy * dy
      if (quad < 1e-6) continue
      const linear = 2 * (fx * dx + fy * dy)
      const constant = fx * fx + fy * fy - radius * radius
      const disc = linear * linear - 4 * quad * constant
      if (disc < 0) continue
      const root = Math.sqrt(disc)
      for (const u of [(-linear - root) / (2 * quad), (-linear + root) / (2 * quad)]) {
        if (u > 0 && u < 1) cuts.push(u)
      }
    }
    cuts.sort((left, right) => left - right)
    for (let cut = 1; cut < cuts.length; cut += 1) {
      const u0 = cuts[cut - 1]
      const u1 = cuts[cut]
      if (u1 - u0 < 1e-4) continue
      const mid = (u0 + u1) / 2
      if (inside(a.x + dx * mid, a.y + dy * mid)) {
        flush()
        continue
      }
      push({ t: a.t + (b.t - a.t) * u0, x: a.x + dx * u0, y: a.y + dy * u0 })
      push({ t: a.t + (b.t - a.t) * u1, x: a.x + dx * u1, y: a.y + dy * u1 })
    }
  }
  flush()
  return pieces
}

function nearest(pts, px, py) {
    let best = { dist: Infinity, t: 0, x: pts[0]?.x || 0, y: pts[0]?.y || 0 }
    for (let index = 1; index < pts.length; index += 1) {
      const a = pts[index - 1]
      const b = pts[index]
      const dx = b.x - a.x
      const dy = b.y - a.y
      const len = dx * dx + dy * dy || 1
      const u = Math.max(0, Math.min(1, ((px - a.x) * dx + (py - a.y) * dy) / len))
      const x = a.x + dx * u
      const y = a.y + dy * u
      const dist = Math.hypot(px - x, py - y)
      if (dist < best.dist) best = { dist, t: a.t + (b.t - a.t) * u, x, y }
    }
    return best
  }

  function pointer(clientX, clientY) {
    const rect = frame.current.getBoundingClientRect()
    const scaleX = width / Math.max(1, rect.width)
    const scaleY = height / Math.max(1, rect.height)
    return { x: (clientX - rect.left) * scaleX, y: (clientY - rect.top) * scaleY }
  }

  const paths = new Map([['', pointsOf('')]])
  rows.forEach((row) => paths.set(String(row.id), pointsOf(String(row.id))))

  function grab(clientX, clientY) {
    const pt = pointer(clientX, clientY)
    let best = { id: '', dist: Infinity, t: 0 }
    for (const [id, pts] of paths) {
      const hit = nearest(pts, pt.x, pt.y)
      const own = !id || hit.t + 0.5 >= (Number(rowOf(id)?.clock) || 0)
      const dist = hit.dist + (own ? 0 : 10)
      if (dist < best.dist) best = { id, dist, t: hit.t }
    }
    return best
  }

  function parentOf(row) {
    const key = String(row.parent || '')
    return lanes.has(key) ? key : ''
  }

  function forksOn(id) {
    const seen = new Set()
    const list = []
    function add(parentId, clock) {
      const key = `${parentId}:${clock}`
      if (seen.has(key)) return
      seen.add(key)
      const time = Number(clock) || 0
      list.push({ parentId, clock: time, x: xAt(time), y: yAt(parentId) })
    }
    for (const row of rows) {
      const parent = parentOf(row)
      if (parent === (id || '')) add(parent, row.clock)
      if (String(row.id) === (id || '')) add(parent, row.clock)
    }
    return list
  }

  function chooseExit(fork, pt) {
    const parentY = yAt(fork.parentId)
    const side = pt.y - parentY
    if (Math.abs(side) < 10) return fork.parentId
    let best = null
    let bestDist = Infinity
    for (const row of rows) {
      if (parentOf(row) !== fork.parentId) continue
      if (Math.abs((Number(row.clock) || 0) - fork.clock) > 0.5) continue
      const y = yAt(String(row.id))
      if ((y - parentY) * side <= 0) continue
      const dist = Math.abs(pt.y - y)
      if (dist < bestDist) {
        best = String(row.id)
        bestDist = dist
      }
    }
    return best || fork.parentId
  }

  function reached(id, hit, prev, pt) {
    let best = null
    let bestDist = 28
    for (const fork of forksOn(id)) {
      const dist = Math.hypot(hit.x - fork.x, hit.y - fork.y)
      if (dist < bestDist) {
        best = fork
        bestDist = dist
      }
      if (!prev) continue
      const minX = Math.min(prev.x, pt.x) - 8
      const maxX = Math.max(prev.x, pt.x) + 8
      if (fork.x < minX || fork.x > maxX) continue
      const span = pt.x - prev.x
      const u = Math.max(0, Math.min(1, span === 0 ? 0 : (fork.x - prev.x) / span))
      const y = prev.y + (pt.y - prev.y) * u
      if (Math.abs(y - fork.y) > 36) continue
      if (!best || Math.abs(pt.x - fork.x) < Math.abs(pt.x - best.x)) best = fork
    }
    return best
  }

  function ride(id, clientX, clientY) {
    const pt = pointer(clientX, clientY)
    const prev = drag.current
    const hit = nearest(paths.get(id) || pointsOf(id), pt.x, pt.y)
    const fork = reached(id, hit, prev, pt)
    let next = id
    if (fork) {
      const choice = chooseExit(fork, pt)
      if (choice !== id) next = choice
    }
    const switched = next !== id
    if (switched) setPinned(next)
    const aimed = nearest(paths.get(next) || pointsOf(next), pt.x, pt.y)
    let time = aimed.t
    if (fork && switched && next !== fork.parentId) time = Math.max(fork.clock, time)
    onPick(next, Math.round(Math.max(0, Math.min(finishOf(next), time))))
    drag.current = { id: next, x: pt.x, y: pt.y }
  }

  function dOf(pts, circles) {
    const pieces = gapRails(pts, circles, FORK_GAP)
    return pieces.map((piece) => piece.map((pt, index) => (
      `${index === 0 ? 'M' : 'L'} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`
    )).join(' ')).join(' ')
  }

  const play = along(paths.get(riding) || pointsOf(''), clock)
  const ink = '#FCFCFC'
  const dim = '#6A6C6B'

  function marksOf(id) {
    if (lineMoments && typeof lineMoments === 'object') return lineMoments[id] || []
    return (id || '') === (activeId || '') ? (moments || []) : []
  }
  const rideChain = chainOf(riding)
  const forks = []
  const forkSeen = new Set()
  rows.forEach((row) => {
    const parent = lanes.has(String(row.parent || '')) ? String(row.parent || '') : ''
    const key = `${parent}:${row.clock}`
    if (forkSeen.has(key)) return
    forkSeen.add(key)
    const live = rideChain.some((item) => `${lanes.has(String(item.parent || '')) ? String(item.parent || '') : ''}:${item.clock}` === key)
    forks.push({ key, x: xAt(Number(row.clock) || 0), y: yAt(parent), live })
  })
  function uniqueOf(id) {
    const row = rowOf(id)
    const fork = Number(row?.clock) || 0
    const pts = paths.get(id) || []
    const cut = pts.findIndex((pt) => pt.t >= fork - 0.001)
    return cut <= 0 ? pts : pts.slice(cut - 1)
  }

  return (
    <svg
      ref={frame}
      role="slider"
      tabIndex={0}
      aria-label="Match time"
      aria-valuemin={0}
      aria-valuemax={Math.round(finishOf(riding))}
      aria-valuenow={Math.round(clock)}
      aria-valuetext={formatClock(clock)}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="block w-full touch-none cursor-pointer outline-none"
      onPointerDown={(event) => {
        try {
          event.currentTarget.setPointerCapture(event.pointerId)
        } catch (error) {
          // A pointer that cannot be captured still scrubs from the events that arrive.
        }
        const pt = pointer(event.clientX, event.clientY)
        const hit = grab(event.clientX, event.clientY)
        drag.current = { id: hit.id, x: pt.x, y: pt.y }
        setPinned(hit.id)
        ride(hit.id, event.clientX, event.clientY)
      }}
      onPointerMove={(event) => {
        if (drag.current == null) return
        ride(drag.current.id, event.clientX, event.clientY)
      }}
      onPointerUp={() => {
        drag.current = null
      }}
      onKeyDown={(event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
        event.preventDefault()
        const end = finishOf(riding)
        const next = Math.max(0, Math.min(end, clock + (event.key === 'ArrowRight' ? 1 : -1)))
        onPick(riding, Math.round(next))
      }}
    >
      <path d={dOf(paths.get(''), forks)} fill="none" stroke={dim} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {rows.map((row) => (
        <path key={row.id} d={dOf(uniqueOf(String(row.id)), forks)} fill="none" stroke={dim} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      ))}
      <path d={dOf(paths.get(riding), forks)} fill="none" stroke={ink} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d={`M ${xAt(baseEnd).toFixed(1)} ${(yAt('') - 8).toFixed(1)} L ${xAt(baseEnd).toFixed(1)} ${(yAt('') + 8).toFixed(1)}`} fill="none" stroke={riding ? dim : ink} strokeWidth="2" strokeLinecap="round" />
      {rows.map((row) => {
        const tail = (paths.get(String(row.id)) || []).at(-1)
        if (!tail) return null
        return (
          <path
            key={`end-${row.id}`}
            d={`M ${tail.x.toFixed(1)} ${(tail.y - 8).toFixed(1)} L ${tail.x.toFixed(1)} ${(tail.y + 8).toFixed(1)}`}
            fill="none"
            stroke={String(row.id) === riding ? ink : dim}
            strokeWidth="2"
            strokeLinecap="round"
          />
        )
      })}
      {forks.map((fork) => (
        <circle key={`fork-${fork.key}`} cx={fork.x} cy={fork.y} r={FORK_R} fill="none" stroke={fork.live ? ink : dim} strokeWidth="2" />
      ))}
      <MomentPaint moments={marksOf('')} rail={paths.get('') || pointsOf('')} onMoment={onMoment} lineId="" />
      {rows.map((row) => (
        <MomentPaint
          key={`marks-${row.id}`}
          moments={marksOf(String(row.id))}
          rail={paths.get(String(row.id))}
          onMoment={onMoment}
          lineId={String(row.id)}
        />
      ))}
      <circle cx={play.x} cy={play.y} r="3.5" fill="#F4F4F2" pointerEvents="none" />
    </svg>
  )
}

function TimelineFlat({ length, clock, moments, onPick, onMoment }) {
  const frame = useRef(null)
  const drag = useRef(false)
  const [width, setWidth] = useState(640)
  const extent = Math.max(1, length)
  const height = 36

  useLayoutEffect(() => {
    const node = frame.current
    if (!node) return undefined
    const measure = () => setWidth(Math.max(240, node.clientWidth))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  function xAt(seconds) {
    const ratio = Math.max(0, Math.min(extent, seconds)) / extent
    return LANE_PAD_X + ratio * Math.max(1, width - LANE_PAD_X * 2)
  }

  function secondsAt(clientX) {
    const rect = frame.current.getBoundingClientRect()
    const x = (clientX - rect.left) * (width / Math.max(1, rect.width))
    const ratio = (x - LANE_PAD_X) / Math.max(1, width - LANE_PAD_X * 2)
    return Math.max(0, Math.min(extent, ratio * extent))
  }

  function pick(clientX) {
    onPick(Math.round(secondsAt(clientX)))
  }

  const y = height / 2
  const endX = xAt(extent)
  const playX = xAt(clock)

  return (
    <svg
      ref={frame}
      role="slider"
      tabIndex={0}
      aria-label="Match time"
      aria-valuemin={0}
      aria-valuemax={Math.round(extent)}
      aria-valuenow={Math.round(clock)}
      aria-valuetext={formatClock(clock)}
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="block w-full touch-none cursor-pointer outline-none"
      onPointerDown={(event) => {
        try {
          event.currentTarget.setPointerCapture(event.pointerId)
        } catch (error) {
          // A pointer that cannot be captured still scrubs from the events that arrive.
        }
        drag.current = true
        pick(event.clientX)
      }}
      onPointerMove={(event) => {
        if (!drag.current) return
        pick(event.clientX)
      }}
      onPointerUp={() => {
        drag.current = false
      }}
      onKeyDown={(event) => {
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
        event.preventDefault()
        const next = Math.max(0, Math.min(extent, clock + (event.key === 'ArrowRight' ? 1 : -1)))
        onPick(Math.round(next))
      }}
    >
      <path d={`M ${LANE_PAD_X} ${y} L ${endX.toFixed(1)} ${y}`} fill="none" stroke="#FCFCFC" strokeWidth="2" strokeLinecap="round" />
      <path d={`M ${endX.toFixed(1)} ${(y - 8).toFixed(1)} L ${endX.toFixed(1)} ${(y + 8).toFixed(1)}`} fill="none" stroke="#FCFCFC" strokeWidth="2" strokeLinecap="round" />
      <MomentPaint
        moments={moments}
        rail={[{ t: 0, x: xAt(0), y }, { t: extent, x: endX, y }]}
        onMoment={onMoment}
      />
      <circle cx={playX} cy={y} r="3.5" fill="#F4F4F2" pointerEvents="none" />
    </svg>
  )
}

function oneFeed(left, right) {
  return [...(left || []), ...(right || [])]
    .sort((a, b) => (b.id || 0) - (a.id || 0) || clockSeconds(b.clock) - clockSeconds(a.clock))
    .slice(0, 4)
}

const rowInitial = { opacity: 0, y: -18 }
const rowAnimate = { opacity: 1, y: 0 }
const rowTransition = {
  layout: { type: 'spring', stiffness: 240, damping: 32, mass: 1 },
  opacity: { duration: 0.5, ease: [0.16, 1, 0.3, 1] },
  y: { type: 'spring', stiffness: 240, damping: 32, mass: 1 },
}
const rowExit = { opacity: 0, y: 10, transition: { duration: 0.28, ease: [0.4, 0, 0.2, 1] } }

function TouchFeed({ lines, place = 'absolute bottom-4 left-4' }) {
  // Changes only when the four rows change. A status tick must not restart
  // the slide, or the row leaving never finishes and the list grows.
  const listKey = lines.map((line) => line.id).join(',')
  return (
    <section data-hud data-slide="sw" className={`${CARD} ${place} w-[272px] overflow-hidden`}>
      <div className="relative flex items-baseline justify-between gap-3 px-4 pb-1 pt-3.5">
        <h2 className="min-w-0 truncate text-[15px] font-semibold tracking-[-0.011em]">Touches</h2>
      </div>
      <ul className="relative h-[138px] overflow-hidden px-2 pb-2.5">
        {lines.length === 0 ? (
          <li className="px-2 py-1.5 text-[13px] text-mute">Waiting for a touch</li>
        ) : (
          <AnimatePresence initial={false} mode="popLayout">
            {lines.map((line, index) => (
              <motion.li
                key={line.id}
                layout="position"
                layoutDependency={listKey}
                initial={rowInitial}
                animate={rowAnimate}
                exit={rowExit}
                transition={rowTransition}
                className="flex h-8 items-center gap-2.5 px-2"
              >
                <span
                  className={`grid h-[22px] min-w-[22px] place-items-center rounded-full px-1 text-[11px] font-semibold leading-none ${
                    index === 0
                      ? 'bg-ink text-card'
                      : 'text-mute ring-1 ring-inset ring-white/20'
                  }`}
                >
                  {line.shirt}
                </span>
                <span className={`min-w-0 flex-1 truncate text-[13.5px] leading-5 ${index === 0 ? 'text-ink' : 'text-mute'}`}>
                  {titleCase(line.action)}
                </span>
                <span className="shrink-0 text-[12px] tabular-nums leading-none text-[#8E8E93]">
                  {line.clock}
                </span>
              </motion.li>
            ))}
          </AnimatePresence>
        )}
      </ul>
    </section>
  )
}

function dotColor(dot) {
  if (dot.team === 1) return 'rgb(137, 207, 240)'
  const max = Math.max(dot.r, dot.g, dot.b)
  if (max < 80) return 'rgb(236, 236, 236)'
  return `rgb(${dot.r}, ${dot.g}, ${dot.b})`
}

function Pitch({ dots, ball }) {
  const players = dots || []
  return (
    <section data-hud data-slide="ne" className={`${CARD} absolute right-4 top-3 w-[232px] p-3`}>
      <div className="relative aspect-[110/72] w-full">
        <svg className="absolute inset-0 h-full w-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <rect x="2" y="2" width="96" height="96" rx="1.2" fill="rgba(255,255,255,0.025)" stroke="rgba(255,255,255,0.28)" strokeWidth="0.7" />
          <line x1="50" y1="2" x2="50" y2="98" stroke="rgba(255,255,255,0.2)" strokeWidth="0.45" />
          <ellipse cx="50" cy="50" rx="8" ry="12.2" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="0.45" />
          <circle cx="50" cy="50" r="0.7" fill="rgba(255,255,255,0.45)" />
          <rect x="2" y="23.1" width="14.4" height="53.8" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="0.45" />
          <rect x="83.6" y="23.1" width="14.4" height="53.8" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="0.45" />
          <rect x="2" y="37.8" width="4.8" height="24.4" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="0.45" />
          <rect x="93.2" y="37.8" width="4.8" height="24.4" fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth="0.45" />
        </svg>
        {players.map((dot, index) => (
          <span
            key={`${dot.team}-${index}`}
            className="absolute h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full ring-1 ring-black/50"
            style={{ left: `${dot.x * 100}%`, top: `${dot.y * 100}%`, background: dotColor(dot) }}
          />
        ))}
        {ball ? (
          <span
            className="absolute h-[6px] w-[6px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-white ring-1 ring-black/70"
            style={{ left: `${ball.x * 100}%`, top: `${ball.y * 100}%` }}
          />
        ) : null}
      </div>
    </section>
  )
}

function reportCards() {
  const bridge = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.hud
  if (!bridge) return
  const rects = [...document.querySelectorAll('[data-hud]')].map((node) => {
    const rect = node.getBoundingClientRect()
    const width = window.innerWidth || 1
    const height = window.innerHeight || 1
    return {
      x: rect.left / width,
      y: rect.top / height,
      w: rect.width / width,
      h: rect.height / height,
    }
  })
  bridge.postMessage(rects)
}

const ACTION_CAMERA = { team: -1, player: 0, lens: 2 }

function setTyping(on) {
  const bridge = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.type
  if (bridge) bridge.postMessage(on)
}

function MicrosoftMark() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" className="shrink-0">
      <rect width="6" height="6" fill="#F25022" />
      <rect x="8" width="6" height="6" fill="#7FBA00" />
      <rect y="8" width="6" height="6" fill="#00A4EF" />
      <rect x="8" y="8" width="6" height="6" fill="#FFB900" />
    </svg>
  )
}

function Chevron({ up }) {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true" className="shrink-0">
      <path d={up ? 'M2.5 7.5 6 4l3.5 3.5' : 'M2.5 4.5 6 8l3.5-3.5'} stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

const SUGGESTIONS = [
  'Highlight all Schmarsenal players',
  'Box all Schman City players',
  'Highlight the player with the most dribbles',
  'Highlight players who have long passed',
  'Highlight odd number shirts',
  "Show me Schmarsenal 7's perspective",
  'Follow Schman City 7',
]

function useTypedPrompt(active) {
  const [shown, setShown] = useState('')
  useEffect(() => {
    if (!active) return undefined
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setShown(SUGGESTIONS[0])
      return undefined
    }
    let prompt = 0
    let count = 0
    let deleting = false
    let timer
    const tick = () => {
      const full = SUGGESTIONS[prompt]
      if (!deleting) {
        count += 1
        setShown(full.slice(0, count))
        if (count >= full.length) {
          deleting = true
          timer = setTimeout(tick, 1100)
          return
        }
        timer = setTimeout(tick, 42)
        return
      }
      count -= 1
      setShown(full.slice(0, Math.max(count, 0)))
      if (count <= 0) {
        deleting = false
        prompt = (prompt + 1) % SUGGESTIONS.length
        timer = setTimeout(tick, 280)
        return
      }
      timer = setTimeout(tick, 22)
    }
    timer = setTimeout(tick, 280)
    return () => clearTimeout(timer)
  }, [active])
  return shown
}

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 13.2V3.2M8 3.2 4.2 7M8 3.2 11.8 7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function MatchChat({ messages, pending, onAsk, place = 'absolute bottom-4 left-1/2 -translate-x-1/2' }) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const listRef = useRef(null)
  const fieldRef = useRef(null)
  const shellRef = useRef(null)
  const collapsedWidthRef = useRef(0)
  const widthFromRef = useRef(null)
  const growGenRef = useRef(0)
  const [shaped, setShaped] = useState(false)
  const [grown, setGrown] = useState(false)
  const suggestion = useTypedPrompt(open && text === '')
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const rise = reduceMotion ? { duration: 0 } : { duration: 0.2 }

  useEffect(() => {
    const node = listRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [messages, pending, open])

  useEffect(() => {
    if (open && fieldRef.current) fieldRef.current.focus()
  }, [open])

  useEffect(() => () => setTyping(false), [])

  function expandedWidth() {
    return Math.min(440, Math.max(160, window.innerWidth - 640))
  }

  function changeOpen(next) {
    const node = shellRef.current
    if (node) widthFromRef.current = node.getBoundingClientRect().width
    if (!next) {
      setTyping(false)
      setGrown(false)
    }
    if (next) setShaped(true)
    setOpen(next)
  }

  useEffect(() => {
    if (!open) return undefined
    const frame = requestAnimationFrame(() => setGrown(true))
    return () => cancelAnimationFrame(frame)
  }, [open])

  useLayoutEffect(() => {
    const node = shellRef.current
    if (!node) return undefined
    if (!collapsedWidthRef.current) {
      collapsedWidthRef.current = node.offsetWidth
      node.style.width = `${collapsedWidthRef.current}px`
    }
    const from = widthFromRef.current
    widthFromRef.current = null
    if (from == null) return undefined
    const to = open ? expandedWidth() : collapsedWidthRef.current
    if (reduceMotion || Math.abs(from - to) < 1) {
      node.style.width = `${to}px`
      reportCards()
      return undefined
    }
    node.style.width = `${from}px`
    const generation = growGenRef.current + 1
    growGenRef.current = generation
    const animation = node.animate(
      [{ width: `${from}px` }, { width: `${to}px` }],
      { duration: 360, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', fill: 'forwards' },
    )
    const started = performance.now()
    let frame = 0
    const track = (now) => {
      reportCards()
      if (now - started < 400) frame = requestAnimationFrame(track)
    }
    frame = requestAnimationFrame(track)
    animation.onfinish = () => {
      if (generation !== growGenRef.current) return
      node.style.width = `${to}px`
      animation.cancel()
      reportCards()
    }
    return () => {
      animation.cancel()
      cancelAnimationFrame(frame)
    }
  }, [open, reduceMotion])

  useEffect(() => {
    if (!open) return undefined
    const onResize = () => {
      const node = shellRef.current
      if (!node) return
      node.style.width = `${expandedWidth()}px`
      reportCards()
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [open])

  function submit(event) {
    event.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || pending) return
    setText('')
    onAsk(trimmed)
  }

  const ease = 'duration-[360ms] ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none'

  return (
    <section
      ref={shellRef}
      data-hud
      data-slide="s"
      data-chat=""
      onClick={() => {
        if (!open) changeOpen(true)
      }}
      className={`${CARD} ${place} flex flex-col ${open ? 'max-h-[176px]' : ''}`}
    >
      {shaped ? (
        <div className={`grid min-h-0 transition-[grid-template-rows] ${ease} ${grown ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
          <div className="min-h-0 overflow-hidden">
            <div className="relative flex shrink-0 items-center justify-between px-3.5 pb-0.5 pt-2.5">
              <h2 className="text-[15px] font-semibold tracking-[-0.011em]">Match</h2>
              <button
                type="button"
                aria-label="Collapse match chat"
                aria-hidden={open ? undefined : true}
                tabIndex={open ? 0 : -1}
                onClick={(event) => {
                  event.stopPropagation()
                  event.currentTarget.blur()
                  changeOpen(false)
                }}
                className="grid h-5 w-5 place-items-center text-mute"
              >
                <Chevron />
              </button>
            </div>
            {messages.length > 0 || pending ? (
              <ul ref={listRef} className="hud-scroll relative min-h-0 max-h-[44px] overflow-y-auto px-3.5">
                {messages.map((message) => (
                  <motion.li
                    key={message.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={rise}
                    className={`py-0.5 text-[13px] leading-[18px] ${message.role === 'you' ? 'text-ink' : 'text-mute'}`}
                  >
                    {message.text}
                  </motion.li>
                ))}
                {pending ? <li className="py-0.5 text-[13px] leading-[18px] text-mute">Looking at the log</li> : null}
              </ul>
            ) : null}
          </div>
        </div>
      ) : null}
      <form
        className={`relative min-w-0 transition-[padding] ${ease} ${open ? 'px-2.5 pb-2.5 pt-1' : ''}`}
        onSubmit={submit}
      >
        <div className={`min-w-0 transition-colors ${ease} ${open ? 'rounded-md bg-black/35' : ''}`}>
          {shaped ? (
            <div className={`grid transition-[grid-template-rows] ${ease} ${grown ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
              <div className="min-h-0 overflow-hidden">
                <div className="relative">
                  <textarea
                    ref={fieldRef}
                    value={text}
                    disabled={pending}
                    maxLength={400}
                    rows={1}
                    spellCheck={false}
                    autoCorrect="off"
                    autoCapitalize="off"
                    autoComplete="off"
                    writingsuggestions="false"
                    placeholder=""
                    aria-label="Ask about this match"
                    onChange={(event) => setText(event.target.value)}
                    onFocus={() => setTyping(true)}
                    onBlur={() => setTyping(false)}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') {
                        fieldRef.current && fieldRef.current.blur()
                        return
                      }
                      if (event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault()
                        submit(event)
                      }
                    }}
                    className="block h-9 w-full resize-none overflow-hidden bg-transparent px-3 py-2 text-[13.5px] font-medium leading-5 text-ink outline-none placeholder:text-mute disabled:opacity-100"
                  />
                  {text === '' ? (
                    <div aria-hidden="true" className="pointer-events-none absolute inset-x-3 top-2 flex h-5 items-center overflow-hidden text-[13.5px] font-medium leading-5 text-mute">
                      <span className="truncate">{suggestion}</span>
                      <span className="chat-caret ml-px inline-block h-3.5 w-px shrink-0 bg-mute" />
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}
          <div className={`flex items-center transition-[padding] ${ease} ${open ? 'justify-between px-2.5 pb-2 pt-1.5' : 'px-3 py-2'}`}>
            <button
              type="button"
              aria-expanded={open}
              aria-label={open ? 'Collapse match chat' : 'Open match chat'}
              onClick={(event) => {
                event.stopPropagation()
                changeOpen(!open)
              }}
              className="flex min-w-0 items-center gap-1.5 text-[12px] font-medium leading-none text-mute"
            >
              <MicrosoftMark />
              <span className="truncate">Phi-4 Mini Instruct</span>
              <span className={`inline-flex transition-transform ${ease} ${open ? '' : 'rotate-180'}`}>
                <Chevron />
              </span>
            </button>
            <div className={`grid min-w-0 transition-[grid-template-columns] ${ease} ${open ? 'grid-cols-[1fr]' : 'grid-cols-[0fr]'}`}>
              <div className={`min-w-0 overflow-hidden transition-[max-height] ${ease} ${open ? 'max-h-7' : 'max-h-0'}`}>
                <div className="pl-2">
                  <button
                    type="submit"
                    aria-label="Send"
                    tabIndex={open ? 0 : -1}
                    disabled={!text.trim() || pending}
                    className={`grid h-7 w-7 place-items-center rounded-full transition-transform duration-150 ${
                      text.trim() && !pending ? 'bg-epl text-white hover:scale-105' : 'bg-white/10 text-mute'
                    }`}
                  >
                    <SendIcon />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </form>
    </section>
  )
}

function MarkIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0">
      <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="m3.3 7 8.7 5 8.7-5" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M12 22V12" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  )
}

function simulationLabel(sim) {
  const left = scoreName(sim.left, 'Left')
  const right = scoreName(sim.right, 'Right')
  const score = sim.score || [0, 0]
  const stamp = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(sim.id || '')
  let when = ''
  if (stamp) {
    const date = new Date(
      Number(stamp[1]),
      Number(stamp[2]) - 1,
      Number(stamp[3]),
      Number(stamp[4]),
      Number(stamp[5]),
    )
    when = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  }
  return `${left} ${score[0]} – ${score[1]} ${right}${when ? ` · ${when}` : ''}`
}

function Menu({ screen, onScreen, onRun, onOpen, onRemove, onQuit, fullscreen, onFullscreen, simulations }) {
  const [picked, setPicked] = useState(0)
  const [over, setOver] = useState(null)
  const saved = simulations || []
  const items = screen === 'home'
    ? [
        { label: 'Run a simulation', onClick: () => onScreen('run') },
        { label: 'Previous simulations', onClick: () => onScreen('previous') },
        { label: 'Settings', onClick: () => onScreen('settings') },
        { label: 'Quit', onClick: onQuit },
      ]
    : screen === 'settings'
      ? [
          { label: fullscreen ? 'Window' : 'Full screen', onClick: onFullscreen },
          { label: 'Back', onClick: () => onScreen('home') },
        ]
      : screen === 'run'
        ? [
            { label: 'Deterministic', onClick: () => onRun(true) },
            { label: 'Stochastic', onClick: () => onRun(false) },
            { label: 'Back', onClick: () => onScreen('home') },
          ]
        : screen === 'previous'
        ? [{ label: 'Back', onClick: () => onScreen('home') }]
        : [{ label: 'Back', onClick: () => onScreen('home') }]

  useEffect(() => {
    setPicked(0)
    setOver(null)
  }, [screen])

  return (
    <>
      <div data-hud className="absolute inset-0" aria-hidden="true" />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,rgba(9,10,9,0.7)_0%,rgba(9,10,9,0.46)_16%,rgba(9,10,9,0.24)_34%,rgba(9,10,9,0.1)_56%,rgba(9,10,9,0.03)_78%,transparent_100%)]"
      />
      <img
        src={wordmark}
        alt="BranchPlay"
        className="pointer-events-none absolute left-14 top-11 h-[56px] w-auto"
      />
      <div data-hud className={`pointer-events-auto absolute left-14 top-[46%] w-[280px] ${screen === 'home' ? '' : 'rounded-lg bg-black/60 p-2'}`}>
        {screen === 'previous' && saved.length === 0 ? (
          <p className="px-[13px] pb-1 text-[15.4px] font-medium leading-[22px] text-mute">No saved simulations.</p>
        ) : null}
        {screen === 'about' ? (
          <p className="max-w-[360px] px-[13px] pb-3 text-[15.4px] font-medium leading-[22px] text-mute">
            BranchPlay is a counterfactuals engine for football. It runs a simulated match so a moment can be revisited and played another way.
          </p>
        ) : null}
        <div className="flex flex-col gap-0.5">
          {screen === 'previous' ? saved.map((sim, index) => (
            <div
              key={sim.id}
              className={`flex items-center rounded-md ${over === index ? 'bg-white/10' : ''}`}
              onMouseEnter={() => {
                setPicked(index)
                setOver(index)
              }}
              onMouseLeave={() => setOver((current) => (current === index ? null : current))}
            >
              <button
                type="button"
                onClick={() => onOpen(sim.id)}
                className="min-w-0 flex-1 truncate px-3 py-2 text-left text-[14px] font-medium leading-5 text-ink"
              >
                {simulationLabel(sim)}
              </button>
              <button
                type="button"
                aria-label={`Remove ${simulationLabel(sim)}`}
                onClick={() => onRemove && onRemove(sim.id)}
                className="shrink-0 px-2.5 py-2 text-[12px] font-medium text-ink"
              >
                Remove
              </button>
            </div>
          )) : null}
          {items.map((item, index) => {
            const place = screen === 'previous' ? saved.length + index : index
            const featured = screen === 'home' && item.label === 'Run a simulation'
            const button = (
              <button
                key={featured ? undefined : (item.id || item.label)}
                type="button"
                onMouseEnter={() => {
                  setPicked(place)
                  setOver(place)
                }}
                onMouseLeave={() => setOver((current) => (current === place ? null : current))}
                onClick={item.onClick}
                className={`rounded-md py-2 text-left text-[14px] font-medium leading-5 text-ink transition-colors duration-200 ${
                  featured ? 'w-full px-3' : 'px-4'
                } ${over === place ? 'bg-white/10' : ''}`}
              >
                {item.label}
              </button>
            )
            if (!featured) return button
            return (
              <div key={item.label} className="mb-1 rounded-lg bg-black/60 p-1">
                {button}
              </div>
            )
          })}
        </div>
      </div>
      <div className="absolute bottom-8 left-14 flex items-center gap-2 text-[16.5px] font-medium text-ink">
        <MarkIcon />
        <span>Jesse Zheng</span>
      </div>
      <button
        type="button"
        data-hud
        onClick={() => onScreen('about')}
        onMouseEnter={() => setOver('about')}
        onMouseLeave={() => setOver((current) => (current === 'about' ? null : current))}
        className={`pointer-events-auto absolute bottom-8 right-14 rounded-md px-2 py-1 text-[16.5px] font-medium text-ink ${
          over === 'about' ? 'bg-black/70' : ''
        }`}
      >
        About
      </button>
    </>
  )
}

export default function App() {
  const [status, setStatus] = useState(null)
  const [mode, setMode] = useState('menu')
  const [screen, setScreen] = useState('home')
  const [messages, setMessages] = useState([])
  const [pending, setPending] = useState(false)
  const [scrub, setScrub] = useState(null)
  const [branchCount, setBranchCount] = useState(2)
  const [branchMinutes, setBranchMinutes] = useState('')
  const [showBranches, setShowBranches] = useState(false)
  const [reel, setReel] = useState(null)
  const [article, setArticle] = useState(null)
  const [languageAsk, setLanguageAsk] = useState(null)
  const [articleOpen, setArticleOpen] = useState(false)
  const [panelsAway, setPanelsAway] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editReady, setEditReady] = useState(false)
  const [addHide, setAddHide] = useState(false)
  const [momentOpen, setMomentOpen] = useState(false)
  const reelRef = useRef(null)
  const articleRef = useRef(null)
  const slideGen = useRef(0)
  reelRef.current = reel
  articleRef.current = article
  const barRef = useRef(null)
  const stripSent = useRef(-1)
  const socketRef = useRef(null)
  const chatId = useRef(0)
  const viewRef = useRef({ team: -1, player: 0, lens: 0 })
  const modeRef = useRef('menu')
  const statusTick = useRef(0)
  const loadingTick = useRef(0)
  const sawWork = useRef(false)
  const keepChat = useRef(false)
  const editWant = useRef(null)
  const editHold = useRef(0)
  modeRef.current = mode

  useEffect(() => {
    let socket = null
    let stopped = false
    let timer = 0
    const connect = () => {
      socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/session`)
      socketRef.current = socket
      socket.onopen = () => {
        socket.send(JSON.stringify({ callouts: true, menu: modeRef.current === 'menu' }))
        const node = barRef.current
        const height = node && node.isConnected ? Math.round(node.getBoundingClientRect().height) : 0
        stripSent.current = height
        socket.send(JSON.stringify({ strip: height }))
      }
      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') return
        try {
          const next = JSON.parse(event.data)
          if (next.kind === 'chat') {
            if (next.reset) {
              setMessages([])
              setPending(false)
              return
            }
            setPending(false)
            if (next.text) {
              setMessages((current) => [
                ...current,
                { id: `a-${next.id || current.length}`, role: 'match', text: next.text },
              ])
            }
            return
          }
          if (next.moment === 'done') {
            const current = reelRef.current
            if (current && next.clip_id != null && current.id !== next.clip_id) {
              // A newer clip is already open.
            } else {
              momentSent.current = false
              slideGen.current += 1
              setMomentOpen(false)
              setReel(null)
              if (!articleRef.current) setPanelsAway(false)
            }
          } else if (next.clip) {
            setReel((current) => {
              if (!current || current.id !== next.clip_id) return current
              return {
                ...current,
                src: next.clip,
                compare: next.clip_kind === 'compare',
                asking: false,
              }
            })
          } else if (next.moment === 'loading') {
            setReel((current) => {
              if (!current || (next.clip_id != null && current.id !== next.clip_id)) return current
              const progress = Number(next.progress)
              if (!Number.isFinite(progress)) return current
              return { ...current, progress }
            })
          }
          if (next.brief && next.brief.id != null) {
            setArticle((current) => {
              if (!current || current.id !== next.brief.id) return current
              const progress = Number(next.brief.progress)
              return {
                ...current,
                title: next.brief.title || current.title,
                span: next.brief.span || current.span,
                lead: next.brief.lead || current.lead,
                preview: next.brief.preview || current.preview,
                phase: next.brief.phase || current.phase,
                progress: Number.isFinite(progress) ? progress : current.progress,
              }
            })
          }
          if (next.view) viewRef.current = next.view
          statusTick.current += 1
          // A formation branch publishes this while the match is on screen.
          // The running screen is the same one the branch button uses.
          if (next.phase === 'saving' && modeRef.current === 'match') {
            keepChat.current = true
            loadingTick.current = statusTick.current
            setMode('loading')
          }
          setStatus(next)
        } catch (error) {
          // A broken status line is skipped. The next one replaces it.
        }
      }
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        if (!stopped) timer = window.setTimeout(connect, 400)
      }
    }
    connect()
    return () => {
      stopped = true
      window.clearTimeout(timer)
      if (socket) socket.close()
    }
  }, [])

  useLayoutEffect(() => {
    reportCards()
  })

  useEffect(() => {
    const onResize = () => reportCards()
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    const onKey = (event) => {
      if (event.key !== 'Escape' || modeRef.current === 'menu') return
      event.preventDefault()
      const socket = socketRef.current
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ home: true }))
      }
      slideGen.current += 1
      setMomentOpen(false)
      setArticleOpen(false)
      setPanelsAway(false)
      setReel(null)
      setArticle(null)
      setPending(false)
      setScreen('home')
      setMode('menu')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (!(status && status.add_prompt)) setAddHide(false)
  }, [status])

  useEffect(() => {
    const onKey = (event) => {
      if (!editing) return
      if (event.key !== 'Delete' && event.key !== 'Backspace') return
      const tag = event.target && event.target.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      event.preventDefault()
      const socket = socketRef.current
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ edit: 'remove' }))
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [editing])

  useEffect(() => {
    if (!status || !Object.prototype.hasOwnProperty.call(status, 'edit')) return
    const phase = status.edit || ''
    if (editWant.current != null && phase !== editWant.current && performance.now() < editHold.current) {
      return
    }
    editWant.current = null
    setEditing(phase === 'on')
    setEditReady(phase === 'ready')
  }, [status])

  useEffect(() => {
    if (mode === 'match') return
    editWant.current = null
    setEditing(false)
    setEditReady(false)
  }, [mode])

  function send(message) {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message))
    }
  }

  useEffect(() => {
    if (mode !== 'menu') return undefined
    let stopped = false
    let timer = 0
    const hold = () => {
      if (stopped) return
      const socket = socketRef.current
      const open = socket && socket.readyState === WebSocket.OPEN
      const view = viewRef.current
      const onAction = view.team < 0 && view.lens === 2
      if (open && !onAction) {
        socket.send(JSON.stringify({ camera: ACTION_CAMERA }))
      }
      timer = window.setTimeout(hold, open ? 1000 : 400)
    }
    hold()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [mode])

  function ask(text) {
    if (pending) return
    chatId.current += 1
    const id = chatId.current
    setMessages((current) => [...current, { id: `q-${id}`, role: 'you', text }])
    setPending(true)
    send({ ask: text, id })
  }

  function armLoading(keep) {
    keepChat.current = Boolean(keep)
    loadingTick.current = statusTick.current
    sawWork.current = false
    setMode('loading')
  }

  function runSimulation(deterministic) {
    armLoading(false)
    send({ simulate: true, deterministic: Boolean(deterministic) })
  }

  function openSimulation(id) {
    armLoading(false)
    send({ open: id })
  }

  const momentSent = useRef(false)
  const clipSerial = useRef(0)

  function openBrief(segment, lineId) {
    setLanguageAsk({ segment, lineId })
  }

  function chooseLanguage(code) {
    const ask = languageAsk
    setLanguageAsk(null)
    if (!ask) return
    startBrief(ask.segment, ask.lineId, code)
  }

  function startBrief(segment, lineId, language) {
    if (editing || editReady) {
      editWant.current = ''
      editHold.current = performance.now() + 800
      setEditing(false)
      setEditReady(false)
      send({ edit: 'off' })
    }
    if (momentSent.current) {
      send({ moment_stop: true, clip_done: true })
      momentSent.current = false
    }
    const start = Number(segment.start) || 0
    const end = Number(segment.end) || start
    clipSerial.current += 1
    const id = clipSerial.current
    const next = {
      id,
      start,
      end,
      title: momentCopy(language).kicker,
      language: language || 'en',
      span: `${formatClock(start)}–${formatClock(end)}`,
      lead: '',
      preview: '',
      phase: 'writing',
      progress: 0,
    }
    setReel(null)
    setMomentOpen(false)
    setArticle(next)
    slideGen.current += 1
    const generation = slideGen.current
    setPanelsAway(true)
    setArticleOpen(false)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.setTimeout(() => {
      if (slideGen.current !== generation) return
      setArticleOpen(true)
    }, reduce ? 0 : 420)
    const payload = { brief: { start, end, id, language: language || 'en' } }
    if (lineId != null && String(lineId) !== String(line || '')) payload.line = lineId
    send(payload)
  }

  function closeArticle() {
    send({ brief_stop: true })
    slideGen.current += 1
    setArticleOpen(false)
    setPanelsAway(false)
    setArticle(null)
  }

  function playArticle() {
    const current = articleRef.current
    if (!current) return
    setArticle(null)
    setArticleOpen(false)
    send({ brief_stop: true })
    playMoment(current)
  }

  function playMoment(segment) {
    if (editing || editReady) {
      editWant.current = ''
      editHold.current = performance.now() + 800
      setEditing(false)
      setEditReady(false)
      send({ edit: 'off' })
    }
    const start = Number(segment.start) || 0
    const end = Number(segment.end) || start
    clipSerial.current += 1
    const id = clipSerial.current
    momentSent.current = true
    slideGen.current += 1
    const generation = slideGen.current
    setPanelsAway(true)
    setMomentOpen(false)
    setReel({ id, start, end, src: '', progress: 0, language: segment.language || 'en' })
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    window.setTimeout(() => {
      if (slideGen.current !== generation) return
      setMomentOpen(true)
    }, reduce ? 0 : 420)
    send({ moment: { start, end, id, language: segment.language || 'en' } })
  }

  function acceptCompare() {
    setReel((current) => (
      current ? { ...current, src: '', progress: 0, piece: 'compare', compare: false } : current
    ))
    send({ compare: true })
  }

  function closeMoment() {
    const socket = socketRef.current
    const open = socket && socket.readyState === WebSocket.OPEN
    if (momentSent.current && open) {
      send({ moment_stop: true, clip_done: true })
      return
    }
    momentSent.current = false
    slideGen.current += 1
    setMomentOpen(false)
    setPanelsAway(false)
    setReel(null)
  }

  function startBranch() {
    const count = Math.min(4, Math.max(1, Math.round(Number(branchCount) || 2)))
    const typed = String(branchMinutes).trim()
    const minutes = typed === '' ? null : Math.min(90, Math.max(1, Number(typed) || 0))
    armLoading(true)
    send({ branch: { count, minutes: typed === '' || minutes === 0 ? null : minutes } })
  }

  function changeMinutes(step) {
    setBranchMinutes((current) => {
      const typed = String(current || '').trim()
      const value = typed === '' ? 0 : Number(typed)
      if (!Number.isFinite(value)) return ''
      const next = value + step
      if (next < 1) return ''
      return String(Math.min(90, next))
    })
  }

  function removeSimulation(id) {
    send({ remove_simulation: id })
  }

  function quitApp() {
    send({ quit: true })
  }

  function armEdit(phase) {
    editWant.current = phase
    editHold.current = performance.now() + 800
    setEditing(phase === 'on')
    setEditReady(phase === 'ready')
  }

  function beginEdit() {
    if (reelRef.current) return
    armEdit('on')
    send({ edit: 'on' })
  }

  function cancelEdit() {
    armEdit('')
    send({ edit: 'off' })
  }

  function commitEdit() {
    armEdit('ready')
    send({ edit: 'commit' })
  }

  function toggleFreeze() {
    if (editReady) {
      armEdit('')
      send({ edit: 'play' })
      return
    }
    send({ frozen: !frozen })
  }

  const view = status && status.view ? status.view : { team: -1, player: 0, lens: 0 }
  const frozen = Boolean(status && status.frozen)
  const fullscreen = Boolean(status && status.fullscreen)
  const span = Math.max(0, Number(status && status.span) || 0)
  const length = Math.max(span, Number(status && status.length) || 0)
  const liveClock = clockSeconds(status && status.clock)
  const branches = (status && status.branches) || []
  const line = String((status && status.branch) || '')
  const shownClock = scrub == null ? liveClock : scrub
  const moments = (status && status.moments) || []
  const lineMoments = status && status.line_moments
  const timelineOptions = [...branches].sort((a, b) => (
    (Number(a.clock) || 0) - (Number(b.clock) || 0) || String(a.id).localeCompare(String(b.id))
  ))

  function showLine(id) {
    const row = timelineOptions.find((item) => String(item.id) === id)
    const end = row ? Number(row.end_clock) || span : length
    const seconds = Math.max(0, Math.min(end, shownClock))
    setScrub(seconds)
    if ((id || '') !== line) send({ line: id || '', scrub: seconds })
    else send({ scrub: seconds })
  }

  useEffect(() => {
    setScrub(null)
  }, [span])

  useEffect(() => {
    if (scrub == null) return
    if (Math.abs(liveClock - scrub) <= 1) setScrub(null)
  }, [liveClock, scrub])

  function chooseCamera(lens) {
    send({ camera: { team: -1, player: 0, lens } })
  }

  function cameraSelected(lens) {
    if (lens === 3) return view.lens === 3
    if (lens === 2) return view.team < 0 && view.lens === 2
    return view.team < 0 && view.lens !== 2 && view.lens !== 3
  }

  useLayoutEffect(() => {
    const node = barRef.current
    const publish = () => {
      const height = node && node.isConnected ? Math.round(node.getBoundingClientRect().height) : 0
      // Loading unmounts the bar. A height of 0 resizes the match window and
      // the overlay drops off it. Keep the band until the bar is back.
      if (height === 0 && mode === 'loading') return
      if (stripSent.current === height) return
      const socket = socketRef.current
      if (!socket || socket.readyState !== WebSocket.OPEN) return
      stripSent.current = height
      socket.send(JSON.stringify({ strip: height }))
    }
    publish()
    if (!node) return undefined
    const observer = new ResizeObserver(publish)
    observer.observe(node)
    return () => observer.disconnect()
  }, [mode, span, showBranches])

  useEffect(() => {
    if (!status) return
    if (status.phase === 'menu' && mode === 'match') {
      slideGen.current += 1
      setMomentOpen(false)
      setArticleOpen(false)
      setPanelsAway(false)
      setReel(null)
      setArticle(null)
      setPending(false)
      setScreen('home')
      setMode('menu')
      return
    }
    if (mode !== 'loading') return
    if (statusTick.current === loadingTick.current) return
    if (status.phase === 'view') {
      sawWork.current = false
      setMode('match')
      setScreen('home')
      if (!keepChat.current) setMessages([])
      keepChat.current = false
      setPending(false)
    } else if (status.phase === 'saving') {
      sawWork.current = true
    } else if (status.phase === 'menu' && (status.open_failed || sawWork.current)) {
      // A menu frame from before the click is applied is not a failed open.
      // That frame was sending the page back to the menu while the match started.
      sawWork.current = false
      setMode('menu')
    }
  }, [mode, status])

  if (mode === 'loading') {
    const saving = status && status.phase === 'saving'
    const fraction = saving ? Number(status.progress) || 0 : 0
    const percent = Math.round(Math.max(0, Math.min(1, fraction)) * 100)
    return (
      <div className="pointer-events-none fixed inset-0 font-sans">
        <div data-hud className="absolute inset-0 bg-black/45" />
        <div data-hud className="absolute left-1/2 top-1/2 w-[340px] -translate-x-1/2 -translate-y-1/2">
          <TaskList title={saving ? 'Running the match' : 'Opening the simulation'} count={saving ? `${percent}%` : '1 / 1'}>
            <TaskRow state={saving && percent < 100 ? 'now' : 'done'} title={saving ? 'Play the match' : 'Find the save'} file={saving ? 'match' : ''} />
          </TaskList>
        </div>
      </div>
    )
  }

  if (mode === 'menu') {
    return (
      <div className="pointer-events-none fixed inset-0 font-sans">
        <Menu
          screen={screen}
          onScreen={setScreen}
          onRun={runSimulation}
          onOpen={openSimulation}
          onRemove={removeSimulation}
          onQuit={quitApp}
          fullscreen={fullscreen}
          onFullscreen={() => send({ fullscreen: !fullscreen })}
          simulations={status && status.simulations}
        />
      </div>
    )
  }

  return (
    <div className="pointer-events-none fixed inset-0 font-sans">
      <div className={`flex h-full min-h-0 flex-col ${panelsAway || editing ? 'hud-leave' : ''} ${editing ? 'edit-open' : ''}`}>
      <div className="relative min-h-0 flex-1">
      <div className="absolute left-4 top-3 flex min-w-[220px] flex-col gap-2">
        <section data-hud data-slide="nw" className={`${CARD} relative w-full px-4 py-2`}>
          <div className="relative flex items-center gap-3">
            <span className="text-[13px] font-medium text-mute">{scoreName(status && status.left_name, 'Left')}</span>
            <span className="text-[18px] font-semibold tabular-nums leading-none">
              {status && status.score ? status.score[0] : 0}
            </span>
            <span className="text-[14px] text-[#6E706F]">–</span>
            <span className="text-[18px] font-semibold tabular-nums leading-none">
              {status && status.score ? status.score[1] : 0}
            </span>
            <span className="text-[13px] font-medium text-mute">{scoreName(status && status.right_name, 'Right')}</span>
            <span className="pl-1 text-[13px] tabular-nums text-[#C8C8C8]">
              {scrub == null ? ((status && status.clock) || '00:00') : formatClock(scrub)}
            </span>
          </div>
        </section>
        <section data-hud data-slide="nw" className={`${CARD} relative w-full px-4 py-2`}>
          <p className="relative text-[13px] font-medium text-mute">Possession</p>
          <div className="relative mt-1.5 flex items-center gap-2">
            <span className="w-10 text-[13px] font-medium tabular-nums text-ink">{possessionShare(status, 0)}%</span>
            <div
              className="flex h-0.5 min-w-[92px] flex-1 overflow-hidden rounded-sm bg-white/15"
              aria-hidden="true"
            >
              <div className="h-full bg-ink" style={{ width: `${possessionShare(status, 0)}%` }} />
            </div>
            <span className="w-10 text-right text-[13px] font-medium tabular-nums text-ink">{possessionShare(status, 1)}%</span>
          </div>
        </section>
      </div>

      <Pitch dots={status && status.dots} ball={status && status.ball} />

        <TouchFeed
          lines={oneFeed(status && status.left, status && status.right)}
          place="absolute bottom-4 left-4"
        />
        <MatchChat
          messages={messages}
          pending={pending}
          onAsk={ask}
          place="absolute bottom-4 left-1/2 -translate-x-1/2"
        />
        <section data-hud data-slide="se" className={`${CARD} absolute bottom-4 right-4 flex w-[191px] flex-col`}>
        <div className="relative flex items-center px-4 pb-1 pt-3.5">
          <h2 className="text-[15px] font-semibold tracking-[-0.011em]">Camera</h2>
        </div>
        <div className="pb-1">
          <Row selected={cameraSelected(0)} icon={<ScreenIcon />} label="Broadcast" onClick={() => chooseCamera(0)} />
          <Row selected={cameraSelected(2)} icon={<ActionIcon />} label="Action" onClick={() => chooseCamera(2)} />
          <Row selected={cameraSelected(3)} icon={<MoveIcon />} label="Free" onClick={() => chooseCamera(3)} />
        </div>

        <div className="flex items-center gap-1.5 px-2.5 py-2.5">
          <button
            type="button"
            onClick={toggleFreeze}
            className={`btn ${frozen ? 'btn-solid' : ''}`}
          >
            {frozen ? 'Resume' : 'Freeze'}
          </button>
          <button
            type="button"
            onClick={() => send({ fullscreen: !fullscreen })}
            className="btn"
          >
            {fullscreen ? 'Window' : 'Full screen'}
          </button>
        </div>
      </section>
      </div>
        {span > 0 ? (
          <section
            ref={barRef}
            data-hud
            data-slide="s"
            className="hud-card pointer-events-auto isolate relative flex w-full shrink-0 flex-col gap-2 overflow-hidden px-4 py-3 text-ink"
          >
            <div className="relative flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1.5 text-[12px] text-mute">
                Line
                <select
                  aria-label="Timeline"
                  value={line}
                  onChange={(event) => showLine(event.target.value)}
                  className="h-7 max-w-[190px] rounded-md bg-white/10 px-3 text-[13px] text-ink outline-none"
                  style={{ colorScheme: 'dark' }}
                >
                  <option value="">Match</option>
                  {timelineOptions.map((row, index) => (
                    <option key={row.id} value={String(row.id)}>
                      {`Branch ${index + 1} · ${formatClock(row.clock)}–${formatClock(row.end_clock)}`}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" onClick={() => setShowBranches((open) => !open)} className="btn">
                {showBranches ? 'One line' : 'All lines'}
              </button>
              <span className="ml-auto flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1.5 text-[12px] text-mute">
                  Branches
                  <input
                    type="number"
                    min={1}
                    max={4}
                    value={branchCount}
                    spellCheck={false}
                    autoCorrect="off"
                    autoCapitalize="off"
                    autoComplete="off"
                    writingsuggestions="false"
                    aria-label="Branches"
                    onFocus={() => setTyping(true)}
                    onBlur={() => setTyping(false)}
                    onChange={(event) => {
                      const next = Math.round(Number(event.target.value))
                      if (!Number.isFinite(next)) return
                      setBranchCount(Math.min(4, Math.max(1, next)))
                    }}
                    className="h-7 w-12 rounded-md bg-white/10 text-center text-[13px] text-ink outline-none"
                  />
                </label>
                <label className="flex items-center gap-1.5 text-[12px] text-mute">
                  Minutes
                  <button type="button" aria-label="Shorter branch" onClick={() => changeMinutes(-1)} className="btn !h-7 !w-7 !px-0">−</button>
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder="Full"
                    value={branchMinutes}
                    spellCheck={false}
                    autoCorrect="off"
                    autoCapitalize="off"
                    autoComplete="off"
                    writingsuggestions="false"
                    aria-label="Branch length in match minutes"
                    onFocus={() => setTyping(true)}
                    onBlur={() => setTyping(false)}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') {
                        event.stopPropagation()
                        event.currentTarget.blur()
                      }
                      if (event.key === 'Enter') {
                        event.preventDefault()
                        startBranch()
                      }
                    }}
                    onChange={(event) => setBranchMinutes(event.target.value.replace(/[^\d]/g, '').slice(0, 2))}
                    className="h-7 w-14 rounded-md bg-white/10 text-center text-[13px] text-ink outline-none placeholder:text-mute"
                  />
                  <button type="button" aria-label="Longer branch" onClick={() => changeMinutes(1)} className="btn !h-7 !w-7 !px-0">+</button>
                </label>
                <button type="button" onClick={startBranch} className="btn btn-solid">Branch</button>
                {branches.length ? (
                  <button type="button" onClick={() => send({ clear_branches: true })} className="btn">Clear</button>
                ) : null}
              </span>
            </div>
            <div className="relative">
              {showBranches ? (
                <TimelineLanes
                  span={span}
                  length={length}
                  clock={Math.min(length, shownClock)}
                  branches={branches}
                  activeId={line}
                  moments={moments}
                  lineMoments={lineMoments}
                  onPick={(id, seconds) => {
                    setScrub(seconds)
                    if ((id || '') !== line) send({ line: id || '', scrub: seconds })
                    else send({ scrub: seconds })
                  }}
                  onMoment={openBrief}
                />
              ) : (
                <TimelineFlat
                  length={span}
                  clock={Math.min(span, shownClock)}
                  moments={moments}
                  onPick={(seconds) => {
                    setScrub(seconds)
                    send({ scrub: seconds })
                  }}
                  onMoment={openBrief}
                />
              )}
            </div>
            <div className="relative flex justify-end gap-2">
              <button type="button" onClick={editing ? cancelEdit : beginEdit} className="btn">
                {editing ? 'Cancel' : 'Edit'}
              </button>
              {editing ? (
                <button type="button" onClick={commitEdit} className="btn btn-solid">Commit</button>
              ) : null}
            </div>
          </section>
        ) : null}
      </div>
      <AnimatePresence>
        {languageAsk ? (
          <LanguagePick key="language" onChoose={chooseLanguage} onClose={() => setLanguageAsk(null)} />
        ) : null}
      </AnimatePresence>
      {article && articleOpen ? (
        <MomentArticle
          title={article.title}
          span={article.span}
          lead={article.lead}
          preview={article.preview}
          phase={article.phase}
          progress={article.progress}
          language={article.language}
          onClose={closeArticle}
          onPlay={playArticle}
        />
      ) : null}
      {reel && momentOpen ? (
        <ClipWindow
          src={reel.src}
          progress={reel.progress}
          compare={Boolean(reel.compare)}
          heading={reel.piece === 'compare' ? momentCopy(reel.language).whatIf : momentCopy(reel.language).kicker}
          copy={momentCopy(reel.language)}
          onClose={closeMoment}
          onYes={acceptCompare}
          onNo={closeMoment}
        />
      ) : null}
      {editing && status && status.add_prompt && !addHide ? (
        <div data-hud className="pointer-events-auto fixed left-1/2 top-1/2 z-50 w-[min(380px,86%)] -translate-x-1/2 -translate-y-1/2">
          <div className="hud-card rounded-lg p-4 text-ink">
            <div className="relative px-5 py-4">
              <p className="text-[15px] font-medium">Add a Schmarsenal or Schman City player?</p>
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setAddHide(true)
                    send({ edit: 'dismiss' })
                  }}
                  className="btn"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAddHide(true)
                    send({ edit: 'add', team: 0 })
                  }}
                  className="btn btn-solid"
                >
                  Schmarsenal
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAddHide(true)
                    send({ edit: 'add', team: 1 })
                  }}
                  className="btn btn-solid"
                >
                  Schman City
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
