# Halvian Bed Flow design system

## Palette and type

| Token | Value | Use |
| --- | --- | --- |
| `--hv-primary` | `#1F4FD8` | Links, actions, chart ranges and eyebrows |
| `--hv-primary-hover` | `#173FB0` | Hover and blue-tint labels |
| `--hv-ink`, `--hv-muted` | `#0E1B2E`, `#5A6B80` | Headings, body and supporting copy |
| `--hv-white`, `--hv-bg`, `--hv-line` | `#FFFFFF`, `#F4F7FB`, `#DCE3EC` | Canvas, quiet bands and borders |
| `--hv-blue-tint` | `#E7EEFF` | In-treatment tiles |
| `--hv-on-track`, `--hv-on-track-bg` | `#006B55`, `#E7F5EF` | On-track text and surface |
| `--hv-watch`, `--hv-watch-bg` | `#795100`, `#FFF3DA` | Watch text and surface |
| `--hv-act`, `--hv-act-bg` | `#972D32`, `#FBEAED` | Act text and surface |

Inter ships locally. Use bold headlines with tight tracking, readable body copy, and short uppercase eyebrows. Use square corners on every surface. Keep text and a visible focus indicator on all controls. Chart ranges use royal blue and a neutral dashed break-even marker with direct labels.

## Page components

Import helpers from `halvian.ui.components`. Keep page-specific numbers in the supplied case data, replay, models or published impact contract.

| Helper or class | Usage |
| --- | --- |
| `section_eyebrow(text)` / `.hv-eyebrow` | `section_eyebrow("Beds and capacity")` above a short heading. |
| `section_heading(text, sub=None)` / `.hv-section-heading`, `.hv-section-subtitle` | `section_heading("Check available beds", sub="Review each unit at the selected time.")`. |
| `card(key=None)` / `.hv-card` | `with card(key="review"): ...` for native widgets. For HTML, use `<div class="hv-card">...</div>`. |
| `kpi(label, value, note)` / `.hv-kpi`, `.hv-kpi-value`, `.hv-kpi-note` | `kpi("Clean beds", clean_beds, "Ready for assignment")`. Format the supplied value in the caller. |
| `status_tag(level, text)` / `.hv-status-tag` | `status_tag("watch", "Waiting for transport")`. Levels are `on-track`, `watch`, and `act`. |
| `callout(text)` / `.hv-callout` | `callout("Review open tasks before assigning a bed.")`. |
| `.hv-tile.hv-tile--empty` | `<div class="hv-tile hv-tile--empty">Empty</div>`. |
| `.hv-tile.hv-tile--treatment` | `<div class="hv-tile hv-tile--treatment">In treatment</div>`. |
| `.hv-tile.hv-tile--boarding` | `<div class="hv-tile hv-tile--boarding">Boarding</div>`. |
| `.hv-tile.hv-tile--cleaning` | `<div class="hv-tile hv-tile--cleaning">Being cleaned</div>`. |
| `.hv-tile.hv-tile--opening` | `<div class="hv-tile hv-tile--opening">About to open</div>`. |
| `.hv-swatch` | `<span class="hv-swatch hv-tile--boarding" aria-hidden="true"></span>Boarding`. |

## Page layout

- Lead with the staff question and place the evidence near its action. Keep Approve and Override together.
- Use short headers, units and case-sourced figures. Keep the same published impact ranges on Overview and Results.
- Keep the native navigation, offline assets and synthetic-data footer. Check pages at 1440×900 and 1920×1080.

## Native controls and navigation

- Streamlit sets both `baseRadius` and `buttonRadius` to `none`. The shared CSS also squares controls mounted outside the page, including menus, calendar panels, popovers, tooltips, and the replay slider. The Plotly template uses square bar corners, square range markers, thin grid lines, and transparent backgrounds.
- The Halvian mark and name sit at the left of the masthead. Streamlit renders the native navigation in its own layer over the center of the desktop row. The primary guided demo button is a native Streamlit action at the right. On narrower screens, the navigation moves to a second row. The smallest screens use Streamlit’s native navigation drawer.
- Use labeled text for every status and preserve keyboard focus. The palette tests cover body text, muted text, action labels, and status text on their intended surfaces. The synthetic-data notice stays in the footer.
