import { drawSelection, highlightActiveLine } from '@codemirror/view'
import { headingHang } from './headingHang'
import { frontmatterYamlStyle, highlightStyle } from './highlightStyle'
import { imeClass, theme } from './theme'
import { typewriter } from './typewriter'

export const cm6ThemeSilent = [
  drawSelection({ cursorBlinkRate: 1000 }),
  highlightActiveLine(),
  imeClass(),
  typewriter(),
  theme(),
  highlightStyle(),
  frontmatterYamlStyle(),
  ...headingHang(),
]
