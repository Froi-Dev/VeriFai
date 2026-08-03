---
name: ui-design-standards
description: Mandatory design-system rules for building or reviewing any UI in this codebase — web apps, dashboards, landing pages, forms, modals, or individual components, in React/HTML/Tailwind or any other frontend stack. Always consult this skill before writing UI code and before presenting any UI output. It bans common "AI-generated" / vibe-coded patterns (gradient overload, glowing buttons, floating cards, huge border radii, decorative blobs, everything-centered layouts, sparkle/emoji icons, fake testimonials, generic hero copy) and replaces them with a strict spacing scale, typography ramp, disciplined color palette, consistent component tokens, and a pre-ship audit checklist. Use this any time the user asks to build, redesign, style, clean up, or review UI, a page, a component, or "make it look more professional/premium."
---

# UI Design Standards

## Why this exists

Most AI-generated UI is recognizable at a glance: purple gradients, glowing buttons, everything centered, floating cards, sparkle icons, fake testimonials from "Sarah Chen." It's not that any single choice is wrong — it's that the choices are made without a system, so nothing lines up and nothing tells the user what matters most.

The goal here is the opposite: UI that looks like it shipped from a mature product team. That means a strict spacing rhythm, one typography system, a small disciplined palette, components that share the same tokens everywhere, motion that's subtle and functional, and copy that's specific instead of inspirational. Every choice should be intentional and repeatable, not improvised per screen.

Treat this skill as the default for all product/system UI (dashboards, apps, internal tools, recurring components). It works alongside `frontend-design` — use that skill's process when a page genuinely needs a distinctive creative direction (e.g. a landing page hero), then lock that direction into this skill's tokens (spacing, type ramp, radius, color) so it stays consistent as more pages get built.

## Part 1 — The Banned List

Never do these, regardless of how the request is phrased ("make it pop," "more modern," "more premium"):

**Color & surface**
- Purple → blue → cyan gradients on buttons, cards, or backgrounds, used by default rather than for a specific brand reason
- Animated or moving gradient/mesh backgrounds that add no function
- Neon "glow" shadows on buttons or any element that looks like it's emitting light
- Abstract blurry gradient blobs placed behind content purely for visual noise
- Any color used for novelty rather than to reinforce hierarchy or meaning

**Shape & elevation**
- Border radius pushed to 20–32px+ on buttons/cards regardless of platform convention
- Every element "floating": rounded corners + shadow + excess whitespace applied uniformly, with no distinction between elevated and flat elements
- Cards that lift aggressively on hover (large translateY, oversized shadow jump)
- Mismatched radii or shadow styles between components on the same screen

**Layout & hierarchy**
- Hero sections, forms, and content blocks all centered by default, wasting screen width
- A UI that looks attractive at first glance but gives every element the same visual weight, so the user can't tell primary from secondary from decorative
- Icons huge relative to adjacent text, or text set far too large/small relative to its role
- Components placed slightly differently page to page instead of from one shared layout

**Icons, badges & decoration**
- An icon or emoji on every heading "just because"
- Status badges added purely for decoration (e.g. a permanent "System Online" pill that isn't wired to anything real)
- Social icons or links that don't go anywhere

**Typography**
- Oversized heading weights paired with thin, hard-to-read body weights
- Inconsistent spacing between paragraphs or random line-height jumps
- More than one heading font or one body font in the same product
- Generic system fonts used with no defined type scale — sizes and weights picked ad hoc per screen

**Motion**
- Animations that pop in at odd times, without an easing curve, or that stutter
- Movement added purely for decoration rather than to communicate state
- Interactions that behave unpredictably (hover states that jump, layouts that shift)

**Copy**
- Hero lines like "Launch faster," "Build your dreams," "Create without limits" — inspirational but content-free
- Heavy em-dash-driven marketing voice that reads as filler
- Fake testimonials, especially with a stock name pattern (e.g. "Sarah Chen"), a reused AI-generated face, or a quote so generic it could apply to any product

If you catch yourself about to produce any of the above, stop and rewrite it using Part 2 before presenting it.

## Part 2 — The System

### 1. Spacing rhythm
Pick a single scale for the whole project — either **4pt** or **8pt** — and derive every margin, padding, and gap from it. Never hand-write an arbitrary pixel value.

Example 8pt scale: `4, 8, 12, 16, 24, 32, 48, 64, 96, 128`

Encode it as design tokens (Tailwind theme, CSS variables, or a spacing constants file) rather than relying on memory to stay consistent.

### 2. Typography
One heading (display) font, one body font. System font stack is a legitimate choice if it's applied consistently — the point is discipline, not decoration.

Define a type ramp once and reuse it everywhere:

| Role | Size | Line height | Weight |
|---|---|---|---|
| Display / H1 | 36–48px | 1.1–1.2 | 600–700 |
| H2 | 28–32px | 1.2–1.3 | 600 |
| H3 | 20–24px | 1.3 | 600 |
| Body | 15–16px | 1.5–1.6 | 400 |
| Small / caption | 13px | 1.4 | 400–500 |

Body text is never set fully bold or ultra-thin. Paragraph spacing is a single fixed value from the spacing scale, applied everywhere — not adjusted per section.

### 3. Color discipline
Keep the palette small and purposeful:
- One neutral scale for background/surface/border/text (e.g. 6–8 steps from white to near-black)
- One accent color, used only for primary actions, links, and focus states — not sprinkled decoratively
- Semantic colors (success/warning/error/info) only where they carry meaning
- Gradients only if the brand identity specifically calls for one — never as a default

Contrast must meet WCAG AA at minimum for text and interactive elements. Every accent should point the user toward what's actionable, not just add color.

### 4. Component consistency
Buttons, cards, inputs, modals, and nav must share:
- One border-radius value per component tier (e.g. 6–8px for controls, up to ~12px for cards — never 20px+ unless the brand explicitly calls for a rounded identity)
- One shadow style, used sparingly, for genuinely elevated surfaces (modals, dropdowns) — not applied to everything
- Consistent internal padding logic (derived from the spacing scale) and consistent alignment
- A clear visual distinction between primary, secondary, and tertiary actions — via weight and fill, not just hue

If a component looks different on two screens, that's a bug, not a style choice.

### 5. Motion & interaction
- Duration: ~150–250ms for most UI transitions
- Easing: standard ease-out/ease-in-out; avoid springy/bouncy curves unless there's a specific reason
- Hover states shift opacity, background, or a small (1–2px) elevation — never distort layout or jump
- Every interactive element must actually work: tabs switch, accordions open and close, carousels slide, buttons respond. Non-functional placeholders are not acceptable in a final output.

### 6. Layout & grid
- Use a real grid (12-column, or a defined max-width container, e.g. 1200–1280px) with gutters tied to the spacing scale
- Nothing should drift between breakpoints; alignment should be exact, not approximate
- Give sections real breathing room via the spacing scale, not by centering everything into a narrow column
- Favor deliberate, asymmetric layouts where they serve the content, over defaulting to centered stacks

### 7. Loading & async states
Every action that can take time needs visible feedback:
- Buttons shift into a loading/disabled state during a request
- Data-heavy areas use skeleton placeholders, not a blank space that pops content in suddenly
- Content transitions in, it doesn't just appear

### 8. Copywriting
- Hero and section copy should say specifically what the product does and why it matters — no generic inspirational filler
- Testimonials must be real, or clearly marked as placeholder content — never fabricated with an invented name/photo presented as real
- Footer content must be accurate and complete, not template text left in place
- Voice: confident, plain, active. A button says "Save changes," not "Submit." The label an action uses in the UI matches the label used in the resulting confirmation/toast.

### 9. Technical fundamentals
Every shipped page needs:
- A real page title and meta description
- OG image / social meta where relevant
- A favicon
- Functional links (or clearly disabled ones — never a dead `href="#"` presented as real)
- A layout that works fully on mobile, not just scaled-down desktop
- Accessible markup: semantic HTML, visible keyboard focus states, alt text on images, proper labels on form fields

No test/lorem-ipsum text, no half-wired links, in the final output.

## Part 3 — Recommended tooling

Reach for these when they reduce inconsistency risk — not to pad the stack:

- **shadcn/ui** (Radix primitives + Tailwind) as the default component base for React projects. It gives accessible, unstyled-enough primitives that are easy to theme consistently rather than fight.
- **Tailwind CSS**, configured with a theme (`tailwind.config`) that encodes the spacing scale, type ramp, color tokens, and radius values from Part 2 — so "arbitrary value" usage in class names becomes the exception, not the rule.
- **lucide-react** for icons, used only where an icon adds function (e.g. inside a button, marking a state) — not decoratively on every heading.
- **Inter**, **Geist**, or the system font stack as safe, consistent defaults when the brief doesn't call for a specific display face.

Install shadcn into an existing project:
```bash
npx shadcn@latest init
npx shadcn@latest add button card input dialog
```

Only add a new dependency when it replaces several inconsistent one-off implementations with one consistent one.

## Part 4 — Pre-ship audit

Run this against any UI before presenting it. Fix failures before showing the result — don't present something you know violates the list.

- [ ] Every spacing value traces back to the 4pt/8pt scale — no odd pixel values
- [ ] Exactly one heading font and one body font are in use
- [ ] Type sizes/line-heights/weights match a single defined ramp, not ad hoc choices
- [ ] One border-radius value per component tier, applied consistently; nothing at 20px+ without a brand reason
- [ ] No unjustified purple/blue/cyan gradient anywhere
- [ ] No glowing/neon button shadows
- [ ] No decorative blurry blobs
- [ ] Layout is not "everything centered" — there's real, deliberate structure
- [ ] Icons appear only where they add function, not on every heading
- [ ] Primary action is visually distinct from secondary/tertiary by weight, not color alone
- [ ] No decorative status badges (e.g. an unwired "System Online" pill)
- [ ] Hero/section copy is specific to this product, not generic inspirational filler
- [ ] No fabricated testimonials
- [ ] Every interactive element actually functions (tabs, accordions, carousels, buttons)
- [ ] Loading/skeleton states exist for anything async
- [ ] Page title, meta description, favicon, and OG tags are present; all links go somewhere real
- [ ] Verified at a mobile viewport width, not just desktop
- [ ] Text contrast meets WCAG AA

If anything fails, revise before presenting — don't ship the first pass.
