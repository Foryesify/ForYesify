import { EditorView, placeholder, keymap } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { markdown } from '@codemirror/lang-markdown'
import { yamlFrontmatter } from '@codemirror/lang-yaml'
import { cm6ThemeSilent } from './cm6ThemeSilent'
import { EditorState } from '@codemirror/state'

/**
 * 创建SilentWrite编辑器对象
 * @param {string} parentSelector CSS选择器，指向挂载的DOM节点元素
 * @param {Function<ViewUpdate>} onUpdate 当编辑器更新的时候执行的动作
 * @returns {EditorView} 编辑器对象
 */
export function editor(parentSelector, onUpdate) {
  return new EditorView({
    parent: document.querySelector(parentSelector),
    state: EditorState.create({
      extensions: [
        ...cm6ThemeSilent,
        yamlFrontmatter({ content: markdown() }),
        history(),
        placeholder('Type here...'),
        EditorView.lineWrapping,
        keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
        EditorView.updateListener.of(onUpdate),
      ]
    }),
  })
}

