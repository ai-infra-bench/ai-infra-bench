# Selected website

The accepted edition is the white-paper site with lightly tinted section
headings and the **contour / 等高回声** masthead print. The chosen artwork is
fixed, including on initial server render; URL parameters do not select art.
Historical candidate artwork and galleries remain outside this checkout.

Preserved presentation:

- Homepage: complete chart cover, Results table, then 6 tasks per page.
- Standalone Tasks: 8 per page, search, Work type and Domain filters.
- Static Pass Average label, no set or Pass@4 selector.
- Resource axes run from larger values on the left to smaller on the right.
- Model identities and colours remain independent of decorative UI colours.
- Up to 3 model/harness series: point labels show effort and score.
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
