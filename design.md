---
name: Humanoid
colors:
  surface: '#f9f9f9'
  surface-dim: '#dadada'
  surface-bright: '#f9f9f9'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f3f3'
  surface-container: '#eeeeee'
  surface-container-high: '#e8e8e8'
  surface-container-highest: '#e2e2e2'
  on-surface: '#1a1c1c'
  on-surface-variant: '#4c4546'
  inverse-surface: '#2f3131'
  inverse-on-surface: '#f1f1f1'
  outline: '#7e7576'
  outline-variant: '#cfc4c5'
  surface-tint: '#5e5e5e'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#1b1b1b'
  on-primary-container: '#848484'
  inverse-primary: '#c6c6c6'
  secondary: '#5e5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e1dfdf'
  on-secondary-container: '#626262'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#1a1c1c'
  on-tertiary-container: '#838484'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e2e2e2'
  primary-fixed-dim: '#c6c6c6'
  on-primary-fixed: '#1b1b1b'
  on-primary-fixed-variant: '#474747'
  secondary-fixed: '#e4e2e2'
  secondary-fixed-dim: '#c7c6c6'
  on-secondary-fixed: '#1b1c1c'
  on-secondary-fixed-variant: '#464747'
  tertiary-fixed: '#e2e2e2'
  tertiary-fixed-dim: '#c6c6c6'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#454747'
  background: '#f9f9f9'
  on-background: '#1a1c1c'
  surface-variant: '#e2e2e2'
typography:
  display:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '600'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '500'
    lineHeight: '1.4'
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  mono-code:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.6'
  mono-label:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: '1.2'
  label-caps:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  xs: 8px
  sm: 16px
  md: 24px
  lg: 40px
  xl: 64px
  gutter: 24px
  margin: 32px
---

## Brand & Style

The design system is rooted in **Reductionist Minimalism**. It aims to eliminate visual noise to facilitate deep focus for high-level AI research. The aesthetic is inspired by mid-century Swiss design and modern technical documentation—precise, editorial, and quiet.

The target audience consists of researchers, engineers, and analysts who require a high-density, low-distraction interface. The UI should evoke a sense of absolute clarity and objective truth. There are no gradients, shadows, or decorative flourishes; the "style" is derived entirely from typographic hierarchy, structural grid alignment, and the rhythmic use of whitespace.

## Colors

This is a strict achromatic palette. Color is never used as a functional signifier (e.g., no red for errors or green for success). Instead, state changes and feedback are communicated through weight, inversion, or iconography.

- **Primary (#000000):** Used for primary text, headlines, and filled button states.
- **Secondary (#666666):** Used for meta-data, secondary labels, and de-emphasized UI chrome.
- **Border/Divider (#E5E5E5):** The standard stroke for containers, input fields, and separators.
- **Surface (#F5F5F5):** Used for subtle background shifts in sidebars or code blocks.
- **Base (#FFFFFF):** The default canvas color for maximum contrast.

## Typography

The system utilizes a dual-font approach. **Inter** handles the primary interface and prose, providing a neutral, highly legible foundation. **JetBrains Mono** is reserved for technical data, status logs, citations, and system-level labels, reinforcing the research-oriented nature of the product.

All headings use tight tracking and heavy weights to create a strong visual anchor. Body text is optimized for long-form reading with generous line heights. Monospace elements should always be rendered with subpixel antialiasing turned on to maintain sharpness.

## Layout & Spacing

The layout follows a **Fixed-Column Grid** for desktop (12 columns) and a fluid single-column layout for mobile. A 4px baseline grid governs all vertical rhythm.

- **Margins:** 32px on desktop, scaling down to 16px on mobile.
- **Gutters:** Consistent 24px width to provide clear separation without the need for heavy lines.
- **Section Spacing:** Use `lg` (40px) or `xl` (64px) between major content blocks to emphasize the "Editorial" feel.
- **Density:** High density is acceptable in sidebars and logs (using `xs` and `sm` spacing), but the main research canvas must remain airy.

## Elevation & Depth

This design system is strictly flat. It eschews all shadows and blurs. Depth is communicated through:

1.  **Strict Layering:** Elements appear "above" others via 1px solid black borders and high-contrast background shifts (e.g., a white modal on a #F5F5F5 background).
2.  **Inversion:** The highest level of focus or an active state is often indicated by inverting the color scheme (Black background with White text).
3.  **Outlines:** Low-contrast outlines (#E5E5E5) define container boundaries, while high-contrast outlines (#000000) indicate focus or selection.

## Shapes

The shape language is architectural and precise. The default corner radius is 4px (Soft), providing just enough visual comfort to prevent the UI from feeling aggressive while maintaining a professional, technical edge. Small components like tags or checkboxes use 2px, while large cards use 4px. No pill-shaped or fully rounded elements are permitted.

## Components

### Buttons
- **Primary:** Solid #000000 background, #FFFFFF text. No border.
- **Secondary:** #FFFFFF background, 1px #000000 border, #000000 text.
- **Ghost:** No background or border. Text-only with an underline on hover.
- **Shape:** Rectangular with 4px corners.

### Chat Interface
- **Bubbles:** Avoid traditional speech bubbles. Use a vertical 2px border on the left to denote the AI response and a simple indentation for the user.
- **Status:** "Thinking" or "Researching" states are displayed in JetBrains Mono with a simple text-based loader (e.g., `[PROCESSING...]`).

### Input Fields
- **Default:** 1px #E5E5E5 border. 
- **Focus:** 1px #000000 border. 
- **Label:** Monospace, 11px, uppercase, placed above the field.

### Lists & Citations
- Citations appear at the end of responses in a dedicated block with a #F5F5F5 background. Use JetBrains Mono for the citation index (e.g., `[1]`, `[2]`).

### Navigation
- Sidebar navigation uses 14px Inter. The active state is indicated by a bold weight and a 2px black vertical line on the leading edge.
