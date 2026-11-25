# React Design System & Vite UI Fix Reference

Lookup-only operational reference for React + Vite and paired Expo UI fixes during loop mode. Read by section with `python3 scripts/ref.py references/loop/react-design-system.md <1-6>`.

## 1. Surface and Token Discipline

- **Compiler-locked `@theme static`**: Reset Tailwind v4 defaults (`--color-*: initial; --radius-*: initial; --text-*: initial; --shadow-*: initial;`) in the design-system theme CSS so unapproved colors and Tailwind drop shadows fail to emit at compile time.
- **No-Card, No-Shadow surfaces**: Never wrap KPIs, feature grids, pricing columns, settings groups, or table rows in `<Card>` / `<CardHeader>` / `<CardContent>` or apply `shadow-sm/md/lg/xl/2xl` or ad-hoc `box-shadow`. Establish hierarchy with generous whitespace, 1px hairline dividers (`border-border-default`, `divide-x`, `divide-y`), subtle tonal ground shifts (`bg-bg-default` vs `bg-bg-subtle`), and `tabular-nums` alignment.
- **Glass & Veil overlays**: Floating chrome (top bars, sticky tab trays, dialogs, menus, command palettes) uses `LiquidGlass` (20px blur, 1.8x saturate, 1px masked vertical rim written with longhand `mask-image`, `mask-clip`, `mask-composite: exclude`, `-webkit-mask-composite: xor`) or `Veil` (8px blur, 1.6x saturate, 1px ring), falling back to `glass-fill-frost` under `prefers-reduced-transparency: reduce` or missing `backdrop-filter`.
- **Layout-only `className`**: Caller `className` props on primitives control margin, width, flex/grid placement, sticky positioning, and responsive visibility only — never inline color, padding, radius, or shadow overrides.

## 2. React-Only Base UI, Motion, and Expo Glass

- **React 19 + `@base-ui/react` only**: Build all interactive controls (`Button`, `Dialog`, `Drawer` BottomSheet, `Menu`, `Select`, `Combobox`, `Tabs`, `Popover`, `Tooltip`, `Switch`, `Checkbox`, `RadioGroup`, `Slider`, `Accordion`, `Collapsible`, `Toast`, `Meter`, `Field`) directly over `@base-ui/react/*`. Never use Vue, Svelte, Angular, `@radix-ui/*`, shadcn/ui, MUI, or AntD.
- **Polymorphic composition**: Use Base UI's `render` prop and `useRender` + `mergeProps` (`@base-ui/react/utils`) so refs, handlers, and `data-starting-style` / `data-ending-style` / `data-open` / `data-invalid` attributes never drop. Pair desktop `Dialog` with `@base-ui/react/drawer` `BottomSheet` (`env(safe-area-inset-bottom)` + `overscroll-contain`).
- **Dedicated Motion layer**: Isolate all animations inside `src/design-system/motion/` (`motion.css` + `motion/react` wrapped in `<MotionConfig reducedMotion="user">`). Use 3 canonical easings (`--ease-out-quint`, `--ease-emphasized`, `--ease-spring`), GPU-only properties (`transform`, `opacity`, `clip-path`), and collapse durations to `0.01ms` under `prefers-reduced-motion: reduce`. Delay `motion-indicator` transitions by 1 `requestAnimationFrame` so sliding indicators never fly from `(0, 0)`.
- **Expo Glass parity (`expo-glass-effect`)**: Gate native `GlassView` / `GlassContainer` behind `isLiquidGlassAvailable() && isGlassEffectAPIAvailable() && !reduceTransparency`. Never set `opacity: 0` on `GlassView` or any parent container (breaks native `UIVisualEffectView`); fade only a background wrapper or animate via `glassEffectStyle` `animate` / `transform`.

## 3. Safe Area, Mobile Viewport, and OpenGraph

- **Viewport & Safe Area (`index.html` + CSS)**: Require `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />` and forbid `user-scalable=no` or `maximum-scale=1`. Apply `env(safe-area-inset-top/right/bottom/left)` utilities on fixed/sticky top bars, bottom bars, sheets, and toasts, and use `min-h-dvh` / `100dvh` instead of raw `100vh`.
- **iOS coarse touch ergonomics**: Add unlayered `@media (pointer: coarse) { input, textarea, select { font-size: max(16px, 1em); } }` to stop Safari auto-zoom on focus. Enforce `44x44px` hit targets on coarse pointers (`pointer-coarse:h-11` or `.touch-slop` `::after`); never attach `.touch-slop` to elements that already own `::after` or `position: fixed/absolute`.
- **Static & dynamic OpenGraph**: Include light/dark `theme-color`, canonical `<link rel="canonical">`, `apple-touch-icon`, `og:type`/`og:url`/`og:title`/`og:description`/`og:image` (1200x630)/`og:site_name`/`og:locale`, and `twitter:card="summary_large_image"` in `index.html`, plus per-route `@tanstack/react-router` `head()` + `<HeadContent />`.

## 4. Reference Mining and 21st.dev Landing Adaptation

- **4-Stage Reference Deconstruction**: Harvest 2 UX/IA refs (Mobbin, UIBowl) + 1 token/system ref (Figma, `horon-ai/design`) + 1–2 visual craft refs (Dribbble, Behance, Pinterest) + `21st.dev` (landing/intro pages). Extract quantitative metrics (type scale ratio, `55-70ch` measure, `4px` spacing base, hairline contrast, motion timing, touch height) before authoring JSX.
- **21st.dev adaptation**: Replace `"use client"`, `next/image`, `next/link`, `@radix-ui/*`, and boxed `shadow-lg` cards with flat hairline grids, tonal featured pricing columns, `@base-ui/react` Tabs/Accordion/Switch, and `@tanstack/react-router` `<Link>`.
- **Shader guardrails**: Cap WebGL/Canvas `dpr <= 1.5`, pause offscreen loops via `IntersectionObserver`, render a static high-contrast frame under `prefers-reduced-motion`, and maintain `>= 4.5:1` text contrast.

## 5. React + Vite Optimization and Skeleton UI

- **Canonical folder structure**: `src/app/`, `src/design-system/{tokens,motion,primitives,patterns,stories}/`, `src/routes/`, `src/features/<domain>/{api,queries,stores,components,types.ts}`, `src/shared/{lib/http.ts,lib/cn.ts,hooks}`.
- **Zero-waterfall data loading**: Configure `createRouter({ defaultPreload: "intent", defaultPreloadStaleTime: 0, context: { queryClient } })` so TanStack Query owns cache freshness. Prefetch above-the-fold data in parallel with `Promise.all([context.queryClient.ensureQueryData(...), ...])` inside route `loader`, and forward `signal` to `ky`. Eliminate N+1 fetches and serial `useEffect` waterfalls.
- **Table, Store & Skeletons**: Sync `@tanstack/react-table` (`manualSorting`/`manualFiltering`/`manualPagination` + `keepPreviousData`) with `validateSearch`, keep `zustand` strictly for client-only UI state, implement optimistic mutations (`onMutate` -> `onError` rollback -> `onSettled` invalidation), and render exact-geometry Zero-CLS `Skeleton` placeholders (`aria-busy="true"`, `max-sm:max-w-full`).

## 6. Storybook and Responsive Visual QA Verification

- **Storybook (`@storybook/react-vite`)**: Ship `*.stories.tsx` for every primitive/pattern with `@storybook/addon-a11y` (`test: "error"`), Light/Dark and `data-platform` toolbars, Mobile/Tablet/Desktop viewports, stress states, and `play` interaction checks (`storybook/test`).
- **Multi-viewport Visual QA**: Verify across Mobile (`320x568`, `375x812`), Tablet (`768x1024`, `1024x768`), and Desktop (`1280x800`, `1440x900`) in Light/Dark modes and Loaded/Skeleton/Empty/Error/Focus/Overlay states using the companion skill's `scripts/audit-react-ds.sh --strict --json` and `assets/templates/visual-qa-probe.js`.
- **Honest reporting**: Report browser/probe checks as `not_verified` when no live browser capability is available in the session.
