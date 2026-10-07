import { EditorView } from "@codemirror/view"

// const isTouch = matchMedia('(pointer: coarse)').matches
export const NARROW_QUERY = '(max-width: 750px)'

const cmVars = {
  '--cm-font': `system-ui, -apple-system, "Segoe UI", Roboto,
                "Helvetica Neue", Arial, "Noto Sans", "PingFang SC",
                "Hiragino Sans GB", "Microsoft YaHei", sans-serif`,
  '--cm-mono': `ui-monospace, SFMono-Regular, "SF Mono", Menlo,
                Consolas, "Cascadia Mono", "Roboto Mono", "DejaVu Sans Mono",
                "Liberation Mono", "Courier New", monospace`,
  '--cm-fg': '#222',
  '--cm-heading': '#141414',
  '--cm-muted': '#aaa',
  '--cm-selection': '#e9e9e9',
  '--cm-caret': '#222',
  '--cm-placeholder': '#444',
  '--cm-hash-gutter': '1em',
}

const cmVarsDark = {
  '--cm-fg': '#e8e8e8',
  '--cm-heading': '#f2f2f2',
  '--cm-muted': 'rgba(232, 232, 232, 0.52)',
  '--cm-selection': '#555',
  '--cm-caret': '#f2f2f2',
  '--cm-placeholder': 'rgba(232, 232, 232, 0.34)',
}

export const imeClass = () => EditorView.domEventHandlers({
  compositionstart(_event, view) {
    view.dom.classList.add('cm-ime')
  },
  compositionend(_event, view) {
    view.dom.classList.remove('cm-ime')
  },
})

export const theme = () => EditorView.theme({
  // Editor
  '&': {
    outline: 'none !important',
    flex: '1',
  },
  '.cm-scroller': {
    ...cmVars,
    fontSize: '1.2em',
    lineHeight: '1.6',
    color: 'var(--cm-fg)',
    fontFamily: 'var(--cm-font)',
    fontWeight: '400',
    justifyContent: 'center',
    overflow: 'visible',
  },
  '@media (prefers-color-scheme: dark)': {
    '.cm-scroller': cmVarsDark,
  },
  '.cm-content': {
    maxWidth: 'min(48em, 80vw)',
    flex: '1 1 auto',
    minHeight: '100%',
    padding: '0 var(--cm-hash-gutter) 50dvh',
  },
  [`@media ${NARROW_QUERY}`]: {
    '.cm-scroller': {
      '--cm-hash-gutter': '0',
    },
    '.cm-content': {
      'maxWidth': '95vw',
    },
    '.cm-heading-line': {
      textIndent: '0',
    },
  },

  // Line
  '.cm-line': {
    width: '100%',
    padding: '0',
    position: 'relative',
    opacity: '0.5',
    transition: 'opacity 0.1s ease-out',
  },
  '.cm-activeLine': {
    opacity: '1',
    backgroundColor: 'transparent',
  },

  // Cursor
  '.cm-cursor, .cm-dropCursor': {
    borderLeft: '0px solid transparent !important',
    width: '2px',
    backgroundColor: 'var(--cm-caret)',
    transform: 'translateX(0.5px)',
    borderRadius: '2px',
    transition: 'all 120ms ease',
  },
  '&.cm-focused > .cm-scroller > .cm-cursorLayer': {
    animation: 'cm-blink 1s ease-in-out infinite',
  },
  '@keyframes cm-blink': {
    '0%, 100%': { opacity: 1 },
    '50%': { opacity: 0 },
  },

  // Selection
  '.cm-selectionBackground': {
    backgroundColor: 'var(--cm-selection) !important',
    transition: `all 120ms ease`,
  },
  '.cm-selectionLayer .cm-selectionBackground:first-child': {
    boxSizing: 'content-box',
    paddingBottom: '1px',
  },

  // Heading hang: hashes stay in flow (selectable); text-indent hangs them.
  '.cm-heading-line': {
    textIndent: 'calc(-1 * var(--cm-hang, 0px))',
  },
  '.cm-heading-hash': {
    whiteSpace: 'pre',
    fontWeight: '400',
    color: 'var(--cm-heading)',
  },
  '.cm-heading-line-6 .cm-heading-hash': {
    color: 'var(--cm-muted)',
  },
})
