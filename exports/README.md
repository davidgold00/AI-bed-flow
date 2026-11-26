# Halvian slide assets

All nine PNGs are 1920×1080. Simulated results appear only as ranges across three synthetic years, introduced by the break-even point; every chart carries the model-estimate caveat. Use the speaker cues in the [presenter guide](../docs/PRESENTER_GUIDE.md) and check spoken values against the [numbers table](../docs/NUMBERS.md).

| Asset | Slide | Content |
| --- | --- | --- |
| [problem_to_feature.png](problem_to_feature.png) | AI Tool Architecture, focus area | Maps each case bottleneck to a distinct dashboard feature and staff action. |
| [architecture.png](architecture.png) | AI Tool Architecture, workflow | Follows the inputs through the models, forecast, staff review and oversight, with an accountable role at each step. |
| [ranges_vs_break_even.png](ranges_vs_break_even.png) | Budget and ROI, the result | The three scenarios (Cautious, Expected, Full rollout) and each part alone as ranges of minutes saved per admission, against the 6-minute break-even, with freed capacity a year. |
| [downstream_chain.png](downstream_chain.png) | Budget and ROI, downstream impact | Connects earlier bed work to boarding saved, waits, walkouts and payer gaps, as Expected-scenario ranges. |
| [payer_gaps.png](payer_gaps.png) | Risk Assessment and Mitigation, equity | The verdict (narrowed, flat or widened) for each payer group's wait and walkout gap against Commercial, Expected scenario. |
| [sensitivity.png](sensitivity.png) | Roadmap and Milestones, adoption, or Budget and ROI backup | Adoption and threshold sweeps as ranges of minutes saved, against the break-even line. |
| [roadmap.png](roadmap.png) | Roadmap and Milestones, pilot and scale | The 18-month milestones by phase, the Month 6 go or no-go and the Year 1 review, with how many gates the synthetic data already meets. |
| [budget_by_phase.png](budget_by_phase.png) | Budget and ROI, financial assumptions | Cost by phase in five groups, the hidden costs in each, and the 18-month and Year 1 totals against the brief's caps. |
| [value_vs_traditional.png](value_vs_traditional.png) | Budget and ROI, value against the traditional approach | The tool's yearly cost range against three traditional staffing options (cost only, brief rates), with the break-even and the freed-capacity ranges. |

Install the app dependencies, local Chrome or Chromium, and the pinned export dependency with `python -m pip install -r scripts/requirements-export.txt`. Then run this from the repository root to refresh the numbers table and all nine images from the saved artifacts.

```bash
python scripts/export_slide_assets.py
```
