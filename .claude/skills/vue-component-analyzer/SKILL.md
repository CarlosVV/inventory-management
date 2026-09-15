---
name: vue-component-analyzer
description: Analyzes the structure of Vue 3 components in client/src and suggests concrete optimizations for rendering performance and code reuse (duplicated helpers to extract into composables, methods that should be computed, index keys, oversized components, watchers that refetch too often, scoped CSS that belongs in App.vue). Use this skill whenever the user asks to review, audit, refactor, clean up, optimize, or "improve" any .vue file or the frontend in general, asks why a page feels slow or re-renders too much, asks what is duplicated across views, or asks where a helper should live, even if they never say the word "performance" or "reuse".
---

# Vue Component Analyzer

You are looking for two things: work the browser does more often than it needs to, and code that exists in more places than it needs to. Everything below is in service of a report the user can act on in an afternoon, not a rewrite of the app.

This is a workshop demo with eight views and nine components. Prioritize clarity over cleverness: a finding is worth reporting when fixing it removes real duplication or real re-renders, not when it merely makes the code more idiomatic.

## Workflow

1. **Run the scanner first.** It gives you numbers for the whole tree in one call so you don't have to open every file to know where to look.

   ```bash
   python3 .claude/skills/vue-component-analyzer/scripts/scan_components.py client/src
   ```

   It reports per component: line count, Options API vs `<script setup>`, style block size, `:key` bound to an index, function calls inside `{{ }}` and bound attributes, `v-for` and `watch` counts, direct axios imports. It also lists helper names defined in two or more components. Treat every number as a lead, never as a finding.

2. **Confirm each lead by reading the file.** The scanner cannot tell whether a template call is a cheap formatter or an aggregation over 250 orders, whether two helpers with the same name do the same thing, or whether a large component is large because of markup or because of logic. Read the relevant section before you write anything down. If the user named specific components, read those in full.

3. **Rank by payoff.** Put first what removes the most work or the most duplicated lines with the smallest diff. A helper copied into six files beats a `v-if` that could be `v-show`.

4. **Write the report** using the structure below. Do not edit `.vue` files from this skill. If the user wants a fix applied, the project requires the `vue-expert` subagent for `.vue` changes; hand it the specific finding and the target file.

## What to look for: performance

**Functions called from templates inside `v-for`.** A method call in the template re-runs on every render of that component. For a formatter like `formatDate` that is fine. For anything that filters or reduces `orders` or `inventory` it is not: the same aggregation runs once per row per render. Move it to a `computed`, or precompute a lookup map once and index into it. `Dashboard.vue` is the file to check first; it holds most of the app's aggregation logic.

**Index as `v-for` key.** With `:key="index"`, Vue patches rows in place when the list reorders or shrinks, which corrupts row-local state such as an open `<details>` and forces child re-renders. Use `sku`, `month`, `id`, or `order_number`. The project's CLAUDE.md already forbids index keys, so any occurrence is a straightforward finding.

**Watchers that refetch on filters the view ignores.** Each view watches a subset of the shared filter refs from `useFilters.js` and refetches. Check that the subset matches what the endpoint accepts: a view that watches `selectedPeriod` but calls an endpoint with no time dimension refetches for nothing. Conversely, a view that filters client-side in a `computed` doesn't need to refetch at all.

**Oversized single-file components.** Over roughly 400 lines a component is usually two or three components sharing one `setup()`. The cost is not runtime, it is that every reactive change re-evaluates every computed in that scope and every reader has to hold the whole file in their head. Suggest the seam (a chart, a modal, a table) rather than "split this up".

**Large scoped style blocks.** Styles for cards, tables, badges and stat tiles already exist globally in `App.vue`. A view carrying 300+ lines of scoped CSS is usually redefining them. Point at the specific duplicated rules; suggest removing the local copy, not adding more globals.

**Custom SVG charts.** They are drawn from computed arrays; that is the right pattern. Flag them only when the chart data is built by a method in the template or when a `v-for` over bars has an index key.

## What to look for: code reuse

The scanner's `duplicated_helpers` list is the starting point. As of September 2026 these are the known repeats, so a fresh scan that still shows them is your first findings:

| Helper | Defined in | Where it should live |
|---|---|---|
| `formatDate` | Dashboard, Orders, Spending, three modals | `useI18n.js` (it already owns the locale) |
| `currencySymbol` computed | Inventory, Orders, Spending, three modals | `utils/currency.js` or `useI18n.js` |
| `translateCategory` | Inventory, Dashboard, Restocking, Spending | `useI18n.js` next to `translateWarehouse` |
| status-to-class maps | Orders, TasksModal | one `utils/status.js` |

Other reuse patterns to check:

- **Load-state boilerplate.** Every view declares `loading`, `error`, `data`, a `loadX()` with try/catch/finally and a `watch` on filters. That is a `useApiResource(fetcher, watchedRefs)` composable. Suggest it once, with one view as the worked example, and note that it is optional for a demo.
- **Modal shells.** The six `*Modal.vue` components repeat the overlay, close button and header markup. A `BaseModal.vue` with a default slot removes the repetition; the modals keep their content.
- **`Reports.vue` bypasses `api.js`** and calls axios with the hard-coded base URL. Every other view goes through `api.js`; move the two report calls there.
- **Mixed component styles.** Views use Options API with `setup()`; the newer modals use `<script setup>`. Both work. Do not recommend a wholesale migration; recommend that new components use `<script setup>` and that a file is migrated only when it is being substantially rewritten anyway.

## Report structure

Use this shape so findings are comparable across runs:

```markdown
# Vue component analysis: <scope>

Scanned N components (M views, K shared). Top three actions: <one line each>.

## Performance
1. **<Finding>** — `path/File.vue:line`
   What happens today, why it costs, the specific change. Estimated diff size.

## Code reuse
1. **<Finding>** — files affected
   What is duplicated, where the single copy should live, which call sites change.

## Fine as is
Things the scanner flagged that you checked and are not worth changing, with the reason. This section keeps the next run from re-investigating them.
```

Reference lines as `client/src/views/File.vue:123` so they are clickable. Keep each finding to a short paragraph; the user will read the file, not your prose. Skip categories that have nothing to report rather than padding them.

## What not to recommend

- Rewriting Options API components to `<script setup>` for its own sake.
- Adding a state library, a UI kit, or a CSS framework. The design system is hand-rolled on purpose.
- Virtualized lists or pagination. The largest list is 250 orders; it renders in milliseconds.
- Changes to `server/` or the JSON fixtures. If a frontend problem is really a missing filter on the API, say so as a note, don't propose the backend change here.
