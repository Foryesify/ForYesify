import { ViewPlugin } from '@codemirror/view'

const ANCHOR = 0.45
const EPSILON = 4
const DURATION = 220

function desktopOk() {
  return !matchMedia('(pointer: coarse)').matches
}

function imeBusy(view) {
  return view.composing || view.dom.classList.contains('cm-ime')
}

function easeOutCubic(t) {
  return 1 - (1 - t) ** 3
}

function scrollParent(el) {
  let node = el.parentElement
  while (node && node !== document.documentElement) {
    const { overflowY } = getComputedStyle(node)
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) {
      return node
    }
    node = node.parentElement
  }
  return window
}

function scrollTopOf(scroller) {
  if (scroller === window) return document.scrollingElement?.scrollTop ?? scrollY
  return scroller.scrollTop
}

function setScrollTop(scroller, top) {
  if (scroller === window) (document.scrollingElement ?? document.documentElement).scrollTop = top
  else scroller.scrollTop = top
}

function anchorY(scroller) {
  if (scroller === window) {
    const vv = window.visualViewport
    if (vv) return vv.offsetTop + vv.height * ANCHOR
    return innerHeight * ANCHOR
  }
  const rect = scroller.getBoundingClientRect()
  return rect.top + rect.height * ANCHOR
}

class Typewriter {
  constructor(view) {
    this.view = view
    this.manual = false
    this.ignoreScroll = 0
    this.raf = 0
    this.anim = null
    this.onUserScroll = () => {
      if (this.ignoreScroll) return
      this.manual = true
      this.stopAnim()
    }
    window.addEventListener('wheel', this.onUserScroll, { passive: true, capture: true })
    window.addEventListener('scroll', this.onUserScroll, { passive: true })
    view.scrollDOM.addEventListener('scroll', this.onUserScroll, { passive: true })
  }

  update(update) {
    if (!desktopOk() || imeBusy(update.view)) return
    if (!update.docChanged) return
    this.manual = false
    this.schedule()
  }

  schedule() {
    if (this.raf) cancelAnimationFrame(this.raf)
    this.raf = requestAnimationFrame(() => {
      this.raf = 0
      this.snap()
    })
  }

  snap() {
    if (!desktopOk() || imeBusy(this.view) || this.manual) return
    const coords = this.view.coordsAtPos(this.view.state.selection.main.head)
    if (!coords) return
    const mid = (coords.top + coords.bottom) / 2
    const scroller = scrollParent(this.view.scrollDOM)
    const from = scrollTopOf(scroller)
    const to = from + (mid - anchorY(scroller))
    if (Math.abs(to - from) < EPSILON) return
    this.play(scroller, from, to)
  }

  play(scroller, from, to) {
    this.stopAnim()
    this.ignoreScroll += 1
    const started = performance.now()
    const step = (now) => {
      const t = Math.min(1, (now - started) / DURATION)
      setScrollTop(scroller, from + (to - from) * easeOutCubic(t))
      if (t < 1 && !this.manual) {
        this.anim.raf = requestAnimationFrame(step)
        return
      }
      this.anim = null
      this.ignoreScroll = Math.max(0, this.ignoreScroll - 1)
    }
    this.anim = { raf: requestAnimationFrame(step) }
  }

  stopAnim() {
    if (!this.anim) return
    cancelAnimationFrame(this.anim.raf)
    this.anim = null
    this.ignoreScroll = Math.max(0, this.ignoreScroll - 1)
  }

  destroy() {
    if (this.raf) cancelAnimationFrame(this.raf)
    this.stopAnim()
    window.removeEventListener('wheel', this.onUserScroll, { capture: true })
    window.removeEventListener('scroll', this.onUserScroll)
    this.view.scrollDOM.removeEventListener('scroll', this.onUserScroll)
  }
}

export const typewriter = () => ViewPlugin.fromClass(Typewriter)
