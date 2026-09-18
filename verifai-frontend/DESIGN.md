# Verif.ai — reference-led Philippine redesign

## Approved direction

Match the supplied AI design.png hero composition: large left-aligned headline, short product description, three capability summaries, rounded primary action, and the large exploded paper stack on the right with four connected callouts. The second supplied image defines the identity and palette.

- Luzon Blue: #0B3D91
- Bayan Red: #D7263D
- Araw Gold: #F4B400
- Cloud White: #F8FAFC
- Manila Slate: #1F2937

Manrope carries headings and the wordmark; Source Sans 3 carries reading text and controls. The reference logo is recreated as vector artwork: blue and red corner brackets, a V, a gold sun, and three gold stars. The dark-surface lockup uses a light wordmark and a cloud-white backing for the symbol.

## Landing page and copy

Order: hero, Ang problema, Ang solusyon (three scroll-revealed verification modules), Paano gamitin, Browser extension, FAQ, Contact us, footer.

Hero: “’Wag basta maniwala. Siguraduhing tama.”
Everyday Filipino and familiar Taglish explain the problem and product. Avoid deep formal Tagalog. Modules are presented sequentially without tabs or click-to-read controls.

Contact uses verif.ai.dev2026@gmail.com. The form prepares a mailto draft and explicitly tells the visitor that their email app opens and they send it themselves. It never claims an email was sent.

The extension is labeled in development because no downloadable package is available. Examples are labeled illustrations, not actual analyses. Assessment uncertainty is explained without presenting fabricated scores or claims as verified results.

## Motion and surfaces

The user explicitly requested glass navigation and scroll reveals, overriding the earlier avoidance of those treatments. The header starts as a wide translucent bar and contracts into a frosted pill after 50px of scrolling. Framer Motion reveals each module as it enters the viewport. A scan line follows scroll position in the image example; the hero illustration moves subtly with scroll. The site respects reduced-motion preferences. The rest of the layout uses solid reading surfaces rather than glass cards.

## Generated project asset

- File: public/images/verification-stack-ph.png
- Generator: built-in image-generation tool
- Reference inputs: AI design.png (paper-stack composition) and the supplied Philippine identity board (palette).
- Final prompt: see artifacts/ui-review/hero-image-prompt.md.

## Scope

Frontend presentation, branding, page composition, interactions, and copy. Preserve real authentication, validation, API clients and payloads, result calculations, history, uploads, and routes. Do not modify the backend or unrelated user changes.
