# Selected website

The accepted edition is the white-paper site with lightly tinted section
headings and the **contour / 等高回声** masthead print. The chosen artwork is
fixed, including on initial server render; URL parameters do not select art.
Historical candidate artwork and galleries remain outside this checkout.

The accepted refinement uses **Index** typography, inline sans-serif chart
annotations, aligned numeric columns and the Index sidebar. Home and Tasks
keep **Folio Clear's two-column task composition** (single-column on phones).
Expanded task results use three columns when their table container is at least
1100px wide, otherwise one column. The selected rules live in
`app/editorial-index.css` and load unconditionally: development and CI exports
render the same edition without design-selection environment variables.

Shared interaction fixes include measured font bounds and actual-curve sampling
for annotations, explicit leaders for displaced labels, nearest-point mouse and
touch selection, contained mobile expanded Results, accessible result counts,
and sticky model/effort context while reading an expanded configuration.

The selected browser icon is the **single-colour simplified contour**: three
retro-blue outlines on the existing light-paper ground. `public/favicon.svg`
is the scalable source, with a matching 32px PNG fallback. Its versioned SVG
URL avoids retaining the previous red-letter icon in browser caches. The
masthead print itself is unchanged.

Preserved presentation:

- Homepage: complete chart cover, Results table, then 6 tasks per page.
- Standalone Tasks: 8 per page, search, Work type and Domain filters.
- Main content shares the 1240px measure across the homepage, Results and
  Tasks. Navigation and footer remain full-width.
- Task cards share a 32/20/14px title/description/metadata hierarchy on desktop,
  and 28/19/14px on mobile, using the existing fonts.
- Results, Tasks and standalone Leaderboard headings share lighter background
  panels (134px desktop, 146px mobile with current copy). Longer copy can grow
  naturally; the homepage masthead's vertical spacing, artwork, title sizes and
  colours are unchanged.
- Instruction keeps its centred 850px reading column and left-aligned prose.
  Metadata aligns to the title/tab bar's left edge within its existing 980px measure.
- Navigation, resource/content tabs and pagination share underline and focus
  styling. These UI rules do not affect the chart's model colours or geometry.
- Static Pass Average label, no set or Pass@4 selector.
- Resource axes run from larger values on the left to smaller on the right.
- Model identities and colours remain independent of decorative UI colours.
- Up to 3 model/harness series: point labels show effort and score.
- Label positions account for loaded fonts and all three resource axes. Curve
  geometry and recorded values are unchanged by annotation placement.
- Above 3 series: only model names remain until a point is hovered, focused or
  pinned. That point alone then shows its effort and pass rate on the plot.
- Hovering a curve greys out the other series; hovering a point preserves
  that focus and adds projection guides to both axes.
- Model colours use a restrained retro blue / brick-red palette, independent
  of the decorative UI palette.
- Results scroll within a viewport capped at the header plus 9 configuration
  rows, with a sticky table header. Short tables keep their natural height.
- On narrow screens, plots with more than 3 series scroll horizontally inside
  their own frame instead of compressing all labels into the page width.

The real snapshot contains 8 configurations / 543 valid trials. Source mapping
and missing-repetition methodology are documented in README.md and
leaderboard-source.json. No mock model measurements belong in that snapshot.

The chart and Results table read only this committed snapshot. There are no
simulation controls, alternative theme switches or selectable artwork in the
production site. Point-label density remains automatic as real models are added.

The right-hand Results scrollbar is transparent at the top and appears after
scrolling down, without changing the table width or disabling scrolling.
Vertical scrolling passes through to the page at the table's top/bottom edges.
When the table does not overflow, both wheel directions scroll the page; while
inside an overflowing table, scrolling stays within it. Horizontal containment
is preserved.
