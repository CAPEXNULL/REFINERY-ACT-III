# Contest submission

## Title

REFINERY: Explainable Process Decisions

## Short description

REFINERY turns a synthetic refinery process into an operator workspace: inspect six loops, rank diagnostic hypotheses, and compare what-if actions with visible observations and forecasts. The CPU demo runs locally without an API key.

## Long description

REFINERY is an engineering prototype for understanding disturbances in a synthetic refinery unit. It brings a physical process model, observation-based diagnosis, conditional action forecasts, and an operator workspace into one reproducible CPU demonstration.

An engineer can run a scenario, inspect temperatures and pressures across six logical loops, review ranked diagnostic hypotheses and their observed evidence, and compare the predicted consequences of holding, restoring cooling, reducing heating, or reducing feed. Charts, an expandable signal table, alarms, calculation history, engineering notes, report exports, and a dedicated video wall connect the analysis to a practical review workflow. English and Russian interfaces, configurable labels, units, themes, and alarm thresholds support different presentation needs.

The prototype keeps important boundaries visible. Diagnostic similarity scores are not calibrated probabilities. Forecasts depend on stated assumptions. Imported data is marked as unverified, missing observations remain missing, and the interface issues no commands to operating equipment. This is a synthetic unit model, not an industrially qualified refinery control system.

The current demonstration uses Python, NumPy, SciPy, CoolProp, and a browser interface built with JavaScript, HTML, and CSS. AMD Token Factory integration is pending: participant access and an official endpoint/model are still required. No AMD inference or GPU execution is claimed. The proposed Intelligent Industry entry demonstrates an inspectable decision-support workflow and a clear path toward future validated integrations.

## Proposed track

Intelligent Industry

## Technology tags

Python · NumPy · SciPy · CoolProp · JavaScript · HTML · CSS · Process Simulation · Explainable AI · Decision Support

## Assets and publication status

| Material | Location / status |
| --- | --- |
| Cover | [16:9 PNG](../assets/contest/cover.png) · [SVG source](../assets/contest/cover.svg) |
| Slides | [PDF](presentation.pdf) · [PowerPoint](presentation.pptx) · [HTML](presentation.html) |
| Public repository | [CAPEXNULL/REFINERY-ACT-III](https://github.com/CAPEXNULL/REFINERY-ACT-III) - public and verified |
| Permanent project page | [https://capexnull.github.io/REFINERY-ACT-III/](https://capexnull.github.io/REFINERY-ACT-III/) |
| Recorded interactive demo | [Read-only synthetic replay](https://capexnull.github.io/REFINERY-ACT-III/demo/) |
| Live CPU workspace | [https://cold-brave-mpegs-nights.trycloudflare.com/industry](https://cold-brave-mpegs-nights.trycloudflare.com/industry) - temporary, while its host runs |
| Hosting | GitHub Pages (permanent recorded replay); Cloudflare quick tunnel (temporary live CPU application) |
| Demo video | [MP4](https://capexnull.github.io/REFINERY-ACT-III/demo.mp4) - 2:28, 4.63 MB, English narration; [captions](demo.vtt) and [transcript](demo-transcript.txt) |
| AMD Token Factory | Pending participant access and an official endpoint/model; no AMD execution claimed |

The local CPU demonstration is available by running `python -m amd.server` and opening `http://127.0.0.1:8765/industry`. No API key is required.

## Suggested demonstration sequence

1. Open the workspace and switch to English if needed.
2. Start a synthetic disturbance scenario with action comparison enabled.
3. Trace the six loops, expand equipment signals, and inspect a trend.
4. Show ranked diagnostic hypotheses and their observed evidence.
5. Compare conditional action forecasts, then open the video wall.
6. Close with the synthetic-data limits and AMD integration status.

Requirements source: [official ACT III event page](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii). The repository, permanent page and interactive replay have been verified publicly. The entry remains a draft package: meaningful AMD integration is not yet demonstrated, and the final contest form has not been submitted.
