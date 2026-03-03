# LaTeX Rendering in Textual TUI Apps

## The short answer
Textual has no built-in LaTeX/math support, and no third-party plugin exists for it. However, the architecture is extensible enough to make it work with some custom code. The key constraint is that terminals are text-based, so you're limited to Unicode approximations of math — not pixel-perfect rendered equations.

## Parsing (the easy part)
markdown-it-py (which Textual already uses for its Markdown widget) has a companion package mdit-py-plugins that provides math parsing out of the box:
- dollarmath_plugin — recognizes $inline$ and $$block$$ syntax
- texmath_plugin — configurable delimiters (\(...\), \[...\], etc.)
These produce math_inline / math_block tokens, ready for a renderer.

## Rendering (the hard part)
Since terminals can't do graphical rendering, you have three practical options:
| Library | What it does | Quality |
|---|---|---|
| unicodeit | Direct LaTeX symbol → Unicode mapping (\alpha → α, \int → ∫, e^+ → e⁺) | Good for simple expressions |
| pylatexenc | Full LaTeX parser with latex2text module | More robust for complex markup |
| SymPy pprint | Renders 2D ASCII/Unicode math with box-drawing characters | Best visual fidelity, but requires parsing LaTeX into SymPy expression objects first (fragile) |

## Integration approach
Textual's Markdown widget exposes two clean extension points:
1. parser_factory — you can inject a custom MarkdownIt instance with math plugins enabled
2. BLOCKS class variable — you subclass Markdown and register custom widget classes for math_inline / math_block token types
So the implementation would be: subclass Markdown, wire up mdit-py-plugins for parsing, and write small widget classes that convert LaTeX content to Unicode using one of the libraries above.

## Honest limitations
- Simple expressions (\alpha, x^2, \sum, \int) render well in Unicode
- Complex expressions (matrices, multi-line equations, large fractions with proper bars, limits positioned above/below operators) will look mediocre at best
- There's no way around this — it's a fundamental constraint of terminal rendering
- The SymPy approach gives the best 2D layout but can't parse arbitrary LaTeX reliably

## Is it "efficient"?
Yes, performance-wise this is lightweight. Unicode conversion is essentially a dictionary lookup, and the parsing overhead from mdit-py-plugins is negligible. The bottleneck would only matter if you're rendering thousands of math blocks simultaneously, which is unlikely in a TUI.

## Bottom line
If your math content is mostly inline formulas, Greek letters, common operators, and simple superscripts/subscripts, this approach works well. If you need publication-quality rendering of complex equations, a TUI is fundamentally the wrong medium — you'd want to render to an image and display it in a terminal that supports image protocols (Kitty, iTerm2), but that's a much heavier approach.
