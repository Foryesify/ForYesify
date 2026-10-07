import { Decoration, EditorView, ViewPlugin } from '@codemirror/view'
import { EditorState, StateEffect, StateField, Transaction } from '@codemirror/state'
import { syntaxTree } from '@codemirror/language'
import { markdown } from '@codemirror/lang-markdown'
import { yamlFrontmatter } from '@codemirror/lang-yaml'
import { highlightStyle } from './highlightStyle'
import { NARROW_QUERY, theme } from './theme'

const ATX_HEADING_RE = /^ATXHeading([1-6])$/
const hashMark = Decoration.mark({
  class: 'cm-heading-hash',
  inclusiveStart: false,
  inclusiveEnd: false,
})
const lineDecoCache = new Map()

const SAMPLE_DOC = Array.from({ length: 6 }, (_, i) => {
  const hashes = '#'.repeat(i + 1)
  return `${hashes}\n${hashes} x`
}).join('\n')

const setHangsEffect = StateEffect.define()
const hangModeEffect = StateEffect.define()

const hangField = StateField.define({
  create() {
    return new Map()
  },
  update(value, tr) {
    for (const effect of tr.effects) {
      if (!effect.is(setHangsEffect)) continue
      if (effect.value === null) return new Map()
      const next = new Map(value)
      for (const [key, width] of effect.value) next.set(key, width)
      return next
    }
    return value
  },
})

function hangDisabled() {
  return matchMedia(NARROW_QUERY).matches
}

function findHeaderMark(node) {
  const cursor = node.cursor()
  if (!cursor.firstChild() || cursor.name !== 'HeaderMark') return null
  return { from: cursor.from, to: cursor.to }
}

function markKey(level) {
  return String(level)
}

function hangTo(view, mark) {
  const lineTo = view.state.doc.lineAt(mark.from).to
  let to = mark.to
  if (to < lineTo && view.state.doc.sliceString(to, to + 1) === ' ') to += 1
  return to
}

function imeBusy(view) {
  return view.composing || view.dom.classList.contains('cm-ime')
}

function lineDeco(level, hang) {
  const key = hang != null ? `${level}:${hang.toFixed(2)}` : `${level}`
  let deco = lineDecoCache.get(key)
  if (!deco) {
    const attributes = {
      class: `cm-heading-line cm-heading-line-${level}`,
    }
    if (hang != null) attributes.style = `--cm-hang:${hang.toFixed(2)}px`
    deco = Decoration.line({ attributes })
    lineDecoCache.set(key, deco)
  }
  return deco
}

function editorFontKey(view) {
  return getComputedStyle(view.scrollDOM).font
}

function collectHeadingMarks(view, range) {
  const marks = []
  syntaxTree(view.state).iterate({
    from: range?.from,
    to: range?.to,
    enter(node) {
      const match = ATX_HEADING_RE.exec(node.name)
      if (!match) return
      const mark = findHeaderMark(node.node)
      if (!mark) return false
      marks.push({
        level: Number(match[1]),
        from: mark.from,
        to: mark.to,
        lineFrom: view.state.doc.lineAt(node.from).from,
      })
      return false
    },
  })
  return marks
}

function hashSpanAt(view, from) {
  const found = view.domAtPos(from)
  if (!found?.node) return null
  const el =
    found.node.nodeType === Node.TEXT_NODE
      ? found.node.parentElement
      : found.node
  return el?.closest?.('.cm-heading-hash') ?? null
}

function measureHashWidth(view, from, to) {
  const start = view.domAtPos(from)
  const end = view.domAtPos(to)
  if (start?.node && end?.node) {
    try {
      const range = document.createRange()
      range.setStart(start.node, start.offset)
      range.setEnd(end.node, end.offset)
      const rects = range.getClientRects()
      if (rects.length) {
        let width = 0
        const top = rects[0].top
        for (const rect of rects) {
          if (Math.abs(rect.top - top) < 1) width += rect.width
        }
        if (width > 0) return width
      }
    } catch {
      /* fall through to span */
    }
  }
  const span = hashSpanAt(view, from)
  return span?.getBoundingClientRect().width || 0
}

function hashDecorations(view) {
  const ranges = []
  for (const mark of collectHeadingMarks(view)) {
    ranges.push(lineDeco(mark.level).range(mark.lineFrom))
    ranges.push(hashMark.range(mark.from, mark.to))
  }
  return Decoration.set(ranges, true)
}

const probeHashMarks = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.decorations = hashDecorations(view)
    }

    update(update) {
      if (update.docChanged || update.viewportChanged) {
        this.decorations = hashDecorations(update.view)
      }
    }
  },
  { decorations: (v) => v.decorations },
)

function measureProbeCache(probe) {
  const updates = []
  for (const mark of collectHeadingMarks(probe)) {
    const width = measureHashWidth(probe, mark.from, hangTo(probe, mark))
    if (width > 0) updates.push([markKey(mark.level), width])
  }
  return updates
}

function warmHangCache(hostView, isCancelled) {
  return new Promise((resolve) => {
    const host = document.createElement('div')
    host.setAttribute('aria-hidden', 'true')
    host.style.cssText =
      'position:absolute;left:0;top:0;width:40em;visibility:hidden;pointer-events:none'
    const parent = hostView.dom.parentNode || document.body
    parent.appendChild(host)

    const probe = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: SAMPLE_DOC,
        extensions: [
          EditorView.lineWrapping,
          yamlFrontmatter({ content: markdown() }),
          theme(),
          highlightStyle(),
          probeHashMarks,
        ],
      }),
    })

    const finish = (updates) => {
      probe.destroy()
      host.remove()
      resolve(updates)
    }

    let tries = 0
    const job = {
      read: () => (isCancelled() ? [] : measureProbeCache(probe)),
      write: (updates) => {
        if (isCancelled()) {
          finish([])
          return
        }
        if (updates.length < 12 && tries < 4) {
          tries += 1
          requestAnimationFrame(() => probe.requestMeasure(job))
          return
        }
        finish(updates)
      },
    }
    probe.contentDOM.getBoundingClientRect()
    const immediate = isCancelled() ? [] : measureProbeCache(probe)
    if (immediate.length >= 12) {
      finish(immediate)
      return
    }
    probe.requestMeasure(job)
  })
}

function buildDecorations(view) {
  if (hangDisabled()) {
    return { decorations: Decoration.none, marks: [] }
  }

  const ranges = []
  const marks = []
  const measured = view.state.field(hangField)

  for (const visible of view.visibleRanges) {
    for (const mark of collectHeadingMarks(view, visible)) {
      const hang = measured.get(markKey(mark.level))
      ranges.push(lineDeco(mark.level, hang).range(mark.lineFrom))
      ranges.push(hashMark.range(mark.from, mark.to))
      marks.push(mark)
    }
  }

  return {
    decorations: Decoration.set(ranges, true),
    marks,
  }
}

function paintHang(view, mark, width) {
  const span = hashSpanAt(view, mark.from)
  const line = span?.closest('.cm-line')
  if (line) line.style.setProperty('--cm-hang', `${width.toFixed(2)}px`)
}

function later(fn) {
  setTimeout(fn, 0)
}

function commitHangs(view, updates) {
  if (!updates.length || !view.dom.isConnected) return
  view.dispatch({
    effects: setHangsEffect.of(updates),
    annotations: Transaction.addToHistory.of(false),
  })
}

const hangPlugin = ViewPlugin.fromClass(
  class {
    constructor(view) {
      this.marks = []
      this.retries = 0
      this.cancelled = false
      this.disabled = hangDisabled()
      this.warmGen = 0
      this.fontKey = editorFontKey(view)
      this.contentDOM = view.contentDOM
      this.mq = matchMedia(NARROW_QUERY)
      this.onImeEnd = () => {
        later(() => {
          if (this.cancelled || !view.dom.isConnected || hangDisabled() || imeBusy(view)) {
            return
          }
          this.apply(view)
          if (this.needsMeasure(view)) view.requestMeasure(this.measure)
        })
      }
      this.contentDOM.addEventListener('compositionend', this.onImeEnd)
      this.onMq = () => {
        if (!view.dom.isConnected || this.cancelled) return
        later(() => {
          if (!view.dom.isConnected || this.cancelled) return
          if (hangDisabled() === this.disabled) return
          view.dispatch({
            effects: hangModeEffect.of(null),
            annotations: Transaction.addToHistory.of(false),
          })
        })
      }
      this.mq.addEventListener('change', this.onMq)
      this.measure = {
        read: (v) => this.readHangs(v),
        write: (measured, v) => this.writeHangs(measured, v),
      }
      this.apply(view)
      if (!this.disabled) {
        this.warm(view)
        later(() => {
          if (!this.cancelled && view.dom.isConnected && this.needsMeasure(view)) {
            view.requestMeasure(this.measure)
          }
        })
      }
    }

    warm(view) {
      if (this.cancelled || hangDisabled()) return
      this.warmGen += 1
      const gen = this.warmGen
      warmHangCache(view, () => this.cancelled || gen !== this.warmGen).then(
        (updates) => {
          if (gen !== this.warmGen || this.cancelled || !view.dom.isConnected) {
            return
          }
          if (!updates.length || hangDisabled()) return
          later(() => {
            if (gen !== this.warmGen || this.cancelled || !view.dom.isConnected) {
              return
            }
            if (hangDisabled()) return
            const current = view.state.field(hangField)
            const next = updates.filter(([key, width]) => {
              const prev = current.get(key)
              return prev == null || Math.abs(prev - width) > 0.5
            })
            commitHangs(view, next)
          })
        },
      )
    }

    apply(view) {
      const built = buildDecorations(view)
      this.decorations = built.decorations
      this.marks = built.marks
    }

    needsMeasure(view) {
      if (hangDisabled()) return false
      const measured = view.state.field(hangField)
      return this.marks.some(
        (mark) => !measured.has(markKey(mark.level)),
      )
    }

    readHangs(view) {
      if (hangDisabled()) return []
      return this.marks.map((mark) => {
        const to = hangTo(view, mark)
        return {
          key: markKey(mark.level),
          mark,
          complete: to > mark.to,
          width: measureHashWidth(view, mark.from, to),
        }
      })
    }

    writeHangs(measured, view) {
      if (!view.dom.isConnected || this.cancelled || hangDisabled() || imeBusy(view)) return
      const current = view.state.field(hangField)
      const updates = []
      for (const { key, mark, width, complete } of measured) {
        if (width <= 0) continue
        const prev = current.get(key)
        // A lone `#` is shorter than `# `; don't let it overwrite a real heading hang.
        if (!complete && prev != null) continue
        if (prev == null) paintHang(view, mark, width)
        if (prev == null || Math.abs(prev - width) > 0.5) {
          updates.push([key, width])
        }
      }
      if (updates.length) {
        this.retries = 0
        later(() => {
          if (!this.cancelled && view.dom.isConnected && !hangDisabled()) {
            commitHangs(view, updates)
          }
        })
        return
      }
      if (this.needsMeasure(view) && this.retries < 4) {
        this.retries += 1
        later(() => {
          if (!this.cancelled && view.dom.isConnected && !hangDisabled() && !imeBusy(view)) {
            view.requestMeasure(this.measure)
          }
        })
      }
    }

    update(update) {
      const disabled = hangDisabled()
      if (disabled !== this.disabled) {
        this.disabled = disabled
        this.apply(update.view)
        if (!disabled) {
          this.warm(update.view)
          later(() => {
            if (this.cancelled || !update.view.dom.isConnected || hangDisabled()) {
              return
            }
            if (this.needsMeasure(update.view)) {
              update.view.requestMeasure(this.measure)
            }
          })
        }
        return
      }
      if (disabled) return

      // IME inserts into the hash text node if the mark covers `# `.
      // Rebuilding/remeasuring then grows --cm-hang every compose tick.
      if (imeBusy(update.view)) {
        if (update.docChanged) this.decorations = this.decorations.map(update.changes)
        return
      }

      const hangsChanged = update.transactions.some((tr) =>
        tr.effects.some((e) => e.is(setHangsEffect)),
      )
      const fontKey = editorFontKey(update.view)
      const fontChanged = fontKey !== this.fontKey
      if (fontChanged) {
        this.fontKey = fontKey
        later(() => {
          if (this.cancelled || !update.view.dom.isConnected || hangDisabled()) {
            return
          }
          update.view.dispatch({
            effects: setHangsEffect.of(null),
            annotations: Transaction.addToHistory.of(false),
          })
          this.warm(update.view)
        })
      }
      if (
        update.docChanged ||
        update.viewportChanged ||
        hangsChanged ||
        fontChanged
      ) {
        this.apply(update.view)
      }
      if (
        !hangsChanged &&
        (update.viewportChanged ||
          fontChanged ||
          this.needsMeasure(update.view))
      ) {
        const view = update.view
        later(() => {
          if (!this.cancelled && view.dom.isConnected && !hangDisabled() && !imeBusy(view)) {
            view.requestMeasure(this.measure)
          }
        })
      }
    }

    destroy() {
      this.cancelled = true
      this.warmGen += 1
      this.mq.removeEventListener('change', this.onMq)
      this.contentDOM.removeEventListener('compositionend', this.onImeEnd)
    }
  },
  { decorations: (v) => v.decorations },
)

export const headingHang = () => [hangField, hangPlugin]
