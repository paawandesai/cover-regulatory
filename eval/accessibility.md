# Accessibility check

Run 2026-10-16 on the `wave6` branch with axe-core 4.10 (WCAG 2.0 A/AA, 2.1 AA and best-practice rules) in
headless Chromium, in light and dark mode. Pages: home, an assessment (with the source panel open), a stop state,
rule review sign-in and every review tab, and a client report link.

| Found | Fix |
|---|---|
| The lot diagram was `role="img"` but holds focusable yard labels (nested-interactive) | It is now a labelled group; each label is a button that also answers Space |
| The top disclaimer sat outside any landmark | It is an `aside` labelled "Disclaimer" |
| Stop states, the review tabs and an unavailable report had no level-one heading | Stop states use `h1`; Rule review has a screen-reader heading; the report error has a heading |
| Scrolling source-text blocks could not be reached by keyboard | They take focus and are labelled "Source text" |
| Elements focusable through `tabindex` or `role="button"` had no focus ring | They get the same ring as buttons and links |

After the fixes axe reports no violations on any of those pages, in either mode; colour contrast passed throughout.

Keyboard walk (Tab through an assessment): every control is reachable in reading order, each shows a focus
ring, and opening a value with Enter now moves focus to the source panel's heading (announced through its live
region); Escape returns focus to the value. The map view (MapLibre) is mouse-first; the diagram view and the value
list give the same information by keyboard.

Not done: a pass with a real screen reader (VoiceOver or NVDA) and a check at 200% zoom by a person.
