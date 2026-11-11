---
name: wave-a11y-scan
description: Scan a project's source code for accessibility problems using the WAVE rule set plus the Mass.gov web testing checklist, and produce a client-ready report. Use when asked to run an accessibility or WAVE-style audit of a repo or folder of HTML, templates, JSX/TSX, Vue, Svelte or Astro files, or to check WCAG 2.x A/AA and Section 508 issues such as alt text, labels, headings, landmarks, ARIA, link and button names, tables and contrast. Reports Errors, Contrast Errors, Alerts, Features, Structural Elements and ARIA with file and line, each mapped to WCAG success criteria, and shows how the scan covers each item of the Mass.gov checklist and what is left for manual testing.
---

# WAVE-style accessibility scan of source code

Reads source files, applies the WAVE rule set (110 items, six categories) plus 21 extra source checks, and writes a Markdown, HTML and JSON report. Every finding has a file and line and carries its WCAG 2.x success criteria and a Section 508 note. No browser, network or install is needed: it needs only Python 3.

## Run a scan

**Invoking the skill by name is enough: run a full scan with no questions about options.** With no path given, scan the whole current repository (`.`), with every format and every finding listed. Only ask the user something if the repository path is genuinely unclear.

```bash
python3 <skill-dir>/scripts/scan.py                                   # full scan of the current directory
python3 <skill-dir>/scripts/scan.py PATH [PATH ...] --out ./a11y-report --title "Client name"
```

`PATH` is a file or a directory (scanned recursively); the default is the current directory. `<skill-dir>` is usually `~/.codex/skills/wave-a11y-scan`.

Options (all optional; the defaults give the full report): `--format md,html,json` (default all), `--max-instances N` and `--max-files N` (default `0` = list every instance and every file; set a number only to shorten a report on request), `--include-tests` (also scan test, spec and story files).

The Markdown and HTML reports contain every finding and every table row; nothing is cut off with "see JSON". `results.json` holds the same findings in machine-readable form.

Outputs in `--out`: `report.md`, `report.html` (hand to the client), and `results.json` with every finding (file, line, selector, snippet, contrast colors and ratios).

Scanned: `.html .htm .jsx .tsx .vue .svelte .astro` and common template types (`.php .erb .ejs .hbs .njk .liquid .twig .jinja .cshtml .razor`), plus `.js` files that import React. Skipped: `node_modules`, build output (`dist`, `build`, `.next`, `.nuxt`, `out`), `vendor`, tests and stories, minified files, files over 1 MB.

Exit codes: `0` ok (findings do not change it); `2` bad option; `3` a path does not exist or no markup files were found (no report is written).

## Extra checks beyond WAVE

Rules in the catalog with a `source` field are not WAVE rules:

- `mass-web-checklist` (6): zoom blocked by the viewport meta, media autoplay, multiple H1, iframe without title, focus outline removed in CSS, dialog without a name.
- `axe-core` (15, a static subset of the rules behind axe DevTools and Accessibility Insights): video without a captions track, duplicate id, invalid ARIA role or attribute, missing required ARIA attribute, ARIA control without a name, focusable content inside `aria-hidden`, nested interactive controls, `input type=button` without a name, `role=img` without a name, visible text missing from the accessible name (2.5.3), invalid `scope`, missing or duplicate `main`, text spacing locked with `!important`.

axe rules that need a rendered page (for example `target-size`, `link-in-text-block`, `scrollable-region-focusable`, `autocomplete-valid`) are not implemented; axe DevTools covers them in the browser.

The report also contains:

- **Contrast checks left for a person:** the text elements whose colors could not be worked out, per file and line, to check with the WebAIM Contrast Checker, the Vispero Colour Contrast Analyser or ANDI's cANDI module. Each contrast error has a `verify` link that opens the WebAIM checker with its colors. Ratios are truncated to two decimals, like WebAIM, and were cross-checked against WebAIM's API (pass/fail agreed on every pair tried).
- **Tools to use with this report:** axe DevTools, WAVE, Accessibility Insights, ANDI, the WebAIM checker and the Vispero CCA, each with what it adds and whether it is open source. Open source: axe-core (engine of axe DevTools), Accessibility Insights (MIT), ANDI (Apache-2.0, self-hostable), CCA (GPL-3.0). Closed: WAVE and the WebAIM checker (which has a free JSON API and a bookmarklet).

When presenting results, tell the user to run axe DevTools or Accessibility Insights (Assessment for the manual items) on the rendered pages and to use ANDI to settle name and label findings.

## Mass.gov web testing checklist

The report has a section for the [Mass.gov Web Testing Checklist](https://accessibility.mass.gov/testing-checklists/web-testing-checklist/) (50 items in 11 groups). `references/mass-web-checklist.json` maps every item to the scanner rules that check it, its WCAG criteria and a manual test. Each item is marked **Scan** (checked in source), **Partly** or **Manual** (needs a person with a browser, keyboard and screen reader), with the scan result beside it.

- A clean result on a Scan or Partly item is not a pass; the manual test is still required. Say so when you present the report.
- Lead with the Manual items as a to-do list: keyboard traps, focus order and return, error messages, captions, zoom and reflow, screen reader announcements.
- Mass.gov's own guidance, repeated in the report: automated tools catch roughly 25-30% of errors; screen reader testing is always needed and should be done by a specialist, a tester with a year of experience or a daily user (NVDA+Chrome, JAWS+Chrome or VoiceOver+Safari).
- To refresh the checklist, the page loads its items from `https://accessibility.mass.gov/testing-checklists/web-testing-checklist.csv`; update the JSON from it and re-map new items.

## Reading the results

- **Errors** and **Contrast Errors** are failures. Lead with these.
- **Alerts** need human review; never present them as confirmed defects.
- **Features**, **Structural Elements** and **ARIA** are informational. ARIA means "present", not "correct".
- Some items map to no WCAG criterion (for example PDF links, small text). The report says "none listed in the catalog"; do not invent a criterion.
- Never state that code is accessible or conformant. Automated checks cover part of WCAG. Say what was checked and what still needs manual testing (keyboard, screen reader, captions, focus order).

## How source scanning behaves

- A value that is only known at runtime (`alt={desc}`, `:alt="x"`, `<?= $x ?>`, `{{ x }}`, spread props) is treated as present and is never reported. Elements rendered by components defined elsewhere are treated as unknown content, except icon components imported from icon libraries (lucide-react, react-icons, heroicons, MUI icons, Font Awesome and similar), which count as a glyph with no text. An icon-only button or link with no `aria-label`, `title` or text is reported as empty.
- References by id (`for`, `aria-labelledby`, `#anchor`) are resolved across all scanned files. They are not reported when any element in the file has a dynamic id.
- Document-level rules (`lang`, `<title>`, missing headings or landmarks) apply to files with a full `<html>` page. Single-page-app shells with an empty mount element are not reported for missing headings.
- Event-handler, `tabindex` and `accesskey` checks apply to native elements only, not custom components.
- Contrast is computed from CSS in `<style>` blocks, linked and imported `.css` files, inline styles and CSS-in-JS object literals, with `var(--x)` resolved. Elements whose colors come from dynamic classes or utility classes such as `bg-primary` or `text-gray-500` (Tailwind palette and theme values are not resolved), gradients, images or other files are counted as skipped in the report, not guessed.

## Files

- `scripts/scan.py` finds files, runs the checks and builds the reports.
- `scripts/source_parser.py` parses HTML, JSX, Vue, Svelte and template syntax into an element tree with line numbers.
- `scripts/source_checks.py` holds the rule checks. `scripts/source_css.py` resolves CSS for contrast and text-size checks.
- `references/wave-rule-catalog.json` is the rule catalog (IDs, titles, categories, WCAG mapping). Rules with `"source": "mass-web-checklist"` are not WAVE rules.
- `references/mass-web-checklist.json` is the Mass.gov checklist with its mapping to rules, WCAG and manual tests, plus the recommended tools.

## Known limits

- Rules that need a rendered page are not implemented: `heading_possible`, `list_possible`, `table_caption_possible`, `longdesc_invalid`. The report lists them.
- Only what appears in source is checked; menus, dialogs and tabs built at runtime are not seen.
- WAVE's "AIM score" is not reproduced.
