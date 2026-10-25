---
name: Obsidian Factstream
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#c3c6d7'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#8d90a0'
  outline-variant: '#434655'
  surface-tint: '#b4c5ff'
  primary: '#b4c5ff'
  on-primary: '#002a78'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#0053db'
  secondary: '#4edea3'
  on-secondary: '#003824'
  secondary-container: '#00a572'
  on-secondary-container: '#00311f'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#996100'
  on-tertiary-container: '#ffeedd'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.025em
  headline-xl-mobile:
    fontFamily: Geist
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.015em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-lg:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.03em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-sm: 0.75rem
  gutter-lg: 1.75rem
  margin: 2rem
  margin-mobile: 1rem
  margin-desktop: 2.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.25rem
---

## Brand & Style

This design system drives a mission-critical, enterprise-grade institutional intelligence terminal. Designed for compliance officers, wealth managers, institutional analysts, and retail investors seeking unvarnished data, the interface projects absolute regulatory rigor, technical clarity, and precision.

The emotional resonance is anchored in institutional trust, intellectual calm, and zero ambiguity. The user experience rejects conversational fluff and speculative synthesis in favor of strictly sourced facts, immutable historical NAV data, SEBI/AMFI regulatory alignment, and explicit attribution.

The aesthetic blends **Dark-Mode Precision Minimalism** with **Technical Terminal Utility**:
- Ultra-deep obsidian canvases that eliminate eye strain during prolonged financial auditing sessions.
- Monolithic data architecture with structured tabular clarity and monospace metric tracking.
- Elevated slate containers bounded by hairline translucent boundaries, signaling high-value modular information architecture.
- High-contrast visual syntax reserving saturated accent colors strictly for functional feedback: verification (emerald), regulatory warning/disclaimer (amber), and active institutional focus (sapphire blue).

## Colors

The palette enforces a dark-first hierarchy engineered for prolonged density inspection and instant state differentiation:

- **Background Layers**: `#0B0F19` serves as the root application background, providing infinite depth. `#0F172A` defines structural sidebars, navigation docks, and recessed query panels.
- **Card and Surface Layers**: Elevated cards utilize `#1E293B`, reinforced by perimeter borders of `rgba(255, 255, 255, 0.08)`. Secondary surface tiers hover at `#334155`.
- **Primary (Electric Sapphire Blue)**: `#2563EB` (accentuating to `#3B82F6` for interactive states, hover triggers, active query highlights, and primary key indicators).
- **Secondary (Verified Emerald)**: `#10B981` is reserved strictly for verified metrics, statutory compliance seals, positive performance delta, and audited facts.
- **Tertiary (Regulatory Amber)**: `#F59E0B` designates risk disclosures, fund manager transitions, tracking error deviations, statutory warnings, and SEBI risk-o-meter notices.
- **Text & Foreground Spectrum**: Primary typography sits at `#F8FAFC` (98% contrast against obsidian). Secondary metadata sits at `#94A3B8`. Muted captions and citation markers use `#64748B`.

## Typography

The typographic hierarchy establishes clear boundaries between analytical inquiry, synthesized truth, and immutable statutory data:

- **Headlines (Geist)**: Delivers a clean, cold, technical geometry. Used for executive summaries, fund family titles, and major module headers.
- **Narrative & Synthesized Answers (Inter)**: High legibility at density with optimal aperture and x-height. Handles conversational query responses, SEBI clause narratives, and scheme investment objectives.
- **Tabular Data, Citations & Metadata (JetBrains Mono)**: Enforces tabular alignment across NAV figures, AUM amounts, expense ratios (TER), alpha/beta metrics, ISIN codes, and AMFI timestamps. Figures must always render with `font-variant-numeric: tabular-nums`.

## Layout & Spacing

The interface employs a responsive 12-column analytical fluid-grid system configured for high information density without visual crowding:

- **Canvas Architecture**:
  - **Desktop (>= 1280px)**: 12-column grid with a pinned query navigation rail (320px fixed) and a responsive two-pane analytical view (main factual response panel + collapsible statutory citation/NAV split-screen). Outer margins set at `margin-desktop` (2.5rem), gutters at `gutter-lg` (1.75rem).
  - **Tablet (768px - 1279px)**: 8-column layout. Navigation folds into an off-canvas drawer. Outer margin scales to `margin` (2rem), gutter to `gutter` (1.25rem). Citations and source prospectuses dock beneath the primary answer blocks.
  - **Mobile (< 768px)**: 4-column flow. Outer margins reduce to `margin-mobile` (1rem); gutters compress to `gutter-sm` (0.75rem). Cards drop horizontal padding to maximize data cell width.

- **Vertical Spacing Cadence**:
  - `space-xs` (4px) and `space-sm` (8px): Micro-gaps between related metrics, citation tags, and chip elements.
  - `space-md` (16px): Standard internal padding for cards, query inputs, and data tables.
  - `space-lg` (24px) to `space-xl` (36px): Delimits distinct factual modules, legal disclaimers, and interactive response stages.

## Elevation & Depth

Visual hierarchy is communicated through structural tonal layering and hair-thin optical borders rather than heavy diffuse drop-shadows, maintaining a crisp financial terminal environment:

- **Ground Level (Canvas)**: `#0B0F19` sits flat.
- **Level 1 (Sub-Panels & Structural Sidebar)**: `#0F172A` with no shadow, demarcated via `1px solid rgba(255, 255, 255, 0.05)` borders on adjacent edges.
- **Level 2 (Fact Cards & Metric Modules)**: `#1E293B` elevated with a continuous border stroke of `1px solid rgba(255, 255, 255, 0.08)` and an ultra-subtle ambient drop shadow: `0 4px 20px -2px rgba(0, 0, 0, 0.5)`.
- **Level 3 (Interactive Overlays & Source Footnotes)**: `#1E293B` elevated over a `backdrop-filter: blur(12px)` scrim (`rgba(11, 15, 25, 0.7)`). Border stroke tightens to `1px solid rgba(59, 130, 246, 0.25)` to signify active focus, with an ambient shadow of `0 12px 32px -4px rgba(0, 0, 0, 0.7)`.
- **States of Warning & Verification**: When highlighting active compliance reviews or verification data, containers receive a 1px border shift to `rgba(16, 185, 129, 0.3)` for verified items or `rgba(245, 158, 11, 0.3)` for regulatory disclaimers, accompanied by an ultra-subtle 4% tint wash over the card background.

## Shapes

The design system implements a disciplined **Soft (Scale 1)** geometry:
- Standard component containers, text inputs, buttons, and data cards adhere to a base radius of `0.25rem` (4px).
- Structural metric tiles and secondary fact cards use `rounded-lg` (`0.5rem` / 8px).
- Modals, complex comparative tables, and floating query panels cap at `rounded-xl` (`0.75rem` / 12px).
- Inline badges, citation tags, and tabular status dots use a micro-radius (`2px`) or are fully circular (`50%`) to communicate strict technical precision, avoiding informal pill shapes across analytical zones.

## Components

### Buttons & Interactive Controls
- **Primary Command Button**: Background `#2563EB`, text `#FFFFFF`, font `JetBrains Mono` 12px bold. Hover: `#3B82F6` with subtle box-shadow `0 0 12px rgba(37, 99, 235, 0.35)`. Active: `#1D4ED8`. Radius: 4px.
- **Secondary / Action Button**: Background `rgba(255, 255, 255, 0.04)`, border `1px solid rgba(255, 255, 255, 0.08)`, text `#94A3B8`. Hover: Background `rgba(255, 255, 255, 0.08)`, text `#F8FAFC`.
- **Destructive / Reset Button**: Ghost background, text `#EF4444`, hover background `rgba(239, 68, 68, 0.1)`.

### Input & Query Fields
- **Terminal Input Box**: Dark `#0B0F19` inset with `1px solid rgba(255, 255, 255, 0.12)`. Padding `0.875rem 1rem`. Typography `Inter` 14px regular. Placeholder `#64748B`.
- **Focused State**: Border shifts to `#3B82F6` with a precision glow: `box-shadow: 0 0 0 1px #3B82F6, 0 0 16px rgba(59, 130, 246, 0.15)`.

### Verified Data Badges & Status Chips
- **Verified Fact Tag**: Monospace `JetBrains Mono` 10px uppercase, padding `2px 6px`, background `rgba(16, 185, 129, 0.1)`, text `#10B981`, border `1px solid rgba(16, 185, 129, 0.25)`. Prepended with an emerald verified shield icon.
- **Regulatory Warning Badge**: Background `rgba(245, 158, 11, 0.1)`, text `#F59E0B`, border `1px solid rgba(245, 158, 11, 0.25)`. Used alongside mandatory statutory disclaimers and mutual fund risk-o-meter ratings.
- **Scheme Category Filter Chips**: Inactive `#1E293B` background, text `#94A3B8`, border `rgba(255, 255, 255, 0.08)`. Selected state fills with `#2563EB` at 20% opacity, border `#2563EB`, text `#60A5FA`.

### Cards & Analytical Panels
- **Fact Card**: Surface `#1E293B`, border `1px solid rgba(255, 255, 255, 0.08)`. Header contains the precise fund scheme title, category badge, and instant timestamp. Body displays factual answers followed by monospace data pills.
- **Regulatory Warning Card**: Inset with a continuous `2px` left accent border in `#F59E0B`. Surface tinted with `rgba(245, 158, 11, 0.03)` over `#1E293B`. Font size `12px` for statutory disclaimers (e.g., "Mutual Fund investments are subject to market risks...").

### Tabular Metric Grids & Citation Links
- **Financial Metric Matrix**: Alternating rows using `#1E293B` and `#182234`. Borders between cells: `1px solid rgba(255, 255, 255, 0.04)`. All numbers displayed in `JetBrains Mono` right-aligned.
- **Inline Citation Nodes**: Discrete interactive index tags (e.g., `[SID p.42]`, `[AMFI Dec-24]`). Styling: `JetBrains Mono` 10px, color `#60A5FA`, background `rgba(37, 99, 235, 0.12)`, border `1px solid rgba(59, 130, 246, 0.2)`. Clicking opens a slide-over panel displaying the raw verified source excerpt.