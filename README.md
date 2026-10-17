# REFINERY

![REFINERY — explainable process decisions](assets/contest/cover.svg)

REFINERY is an engineering prototype for diagnosing disturbances and comparing actions in a **synthetic refinery unit**. It connects a physical process model, observation-based hypotheses, conditional forecasts, and an operator workspace.

Run a scenario, follow the observed evidence, and compare the simulated consequences before reviewing a possible response.

## Run the CPU demo

Use Python 3.13 and install the dependencies in a virtual environment:

```sh
python -m venv .venv
```

Activate the environment with `.venv\Scripts\Activate.ps1` on Windows PowerShell or `source .venv/bin/activate` on macOS/Linux. Then run:

```sh
python -m pip install -r requirements.txt
python -m amd.server
```

Open **http://127.0.0.1:8765/industry**. No API key is needed for this CPU demo. A fresh checkout starts without calculation history: choose **New calculation** to create a result. The package name `amd` is retained for command compatibility.

## Explore the workspace

- **Six logical loops:** feed and heating, distillation, condensation, reflux return, cooling, and independent protection.
- **Diagnosis:** ranked hypotheses with observed evidence; similarity scores are not calibrated probabilities.
- **What-if actions:** compare hold, restore cooling, reduce heating, and reduce feed under the model's stated assumptions.
- **Review tools:** time-aligned charts, expand all equipment signals, alarms, calculation history, engineering notes, CSV/JSON exports, and printable reports.
- **Video wall:** loop summaries, observed channels, histograms, events, and shared-time trends.
- **Configuration:** English/Russian, light/dark themes, labels, units, and display alarm thresholds.

## Demonstration limits

This prototype models a unit using a synthetic three-component mixture. It is not connected to operating equipment and issues no equipment commands. Imported readings have unverified provenance. Industrial calibration, authenticated plant integration, redundancy, and real-plant validation remain future work. Configurable display thresholds do not change the model's physical protection limits.

The included model bundle supports a limited synthetic A/B/C configuration experiment. Its integrity checks do not establish industrial accuracy or acceptance on other process datasets.

**AMD Token Factory integration is pending.** Account registration and an official endpoint/model are still required. This submission does not claim AMD inference or GPU execution.

## Contest materials

- [Submission text and status](docs/submission.md)
- Presentation: [PDF](docs/presentation.pdf) · [PowerPoint](docs/presentation.pptx) · [interactive HTML](docs/presentation.html).
- [16:9 cover PNG](assets/contest/cover.png)
- [Cover artwork](assets/contest/cover.svg)

The contest entry is proposed for the **Intelligent Industry** track of the [AMD Developer Hackathon — ACT III](https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii).

## License

[MIT](LICENSE).
