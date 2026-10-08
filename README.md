# Retron

**A fully offline organic synthesis workbench for Windows.**

Draw chemical structures, convert between names and structures, plan retrosynthetic routes, recommend reaction conditions, and predict reaction products — all running locally on your own machine.

**No internet connection. No subscription. Your structures never leave your computer.**

[English](README.md) | [简体中文](README.zh-CN.md)

![Retron overview](docs/screenshots/01-overview.png)

---

## Why this exists

Planning a synthesis usually means juggling several online tools: one to draw a structure, another to look up a name, another to plan a route — and most of them either charge a subscription or want your structures uploaded to their servers.

Retron puts all of it into one self-contained desktop application. Install it, unplug the network cable, and everything still works. The compounds you draw, look up, and plan stay on your disk.

> The application interface is in **Simplified Chinese**. Runs on Windows 10/11 (64-bit).

---

## Features

### Structure drawing

A full chemical editor (Ketcher, Chinese interface) for drawing molecules and reactions. Paste a screenshot of a structure straight onto the canvas and it gets recognized and drawn for you.

### Name ⇄ structure conversion

Type any of `布洛芬` / `ibuprofen` / `CC(C)Cc1ccc(C(C)C(=O)O)cc1` and get the others back — including molecular formula and InChI.

The bundled dictionary covers **~200,000 compounds** and **over 3.2 million aliases** (trade names, abbreviations such as THF / DMSO, CAS numbers), so everyday names work, not just IUPAC.

![Conversion](docs/screenshots/02-convert.png)

### Retrosynthesis planning

Give a target molecule and get multiple retrosynthetic routes, ordered in forward-synthesis direction (step 1 = the first reaction you would actually run). Each step is annotated with whether its starting materials are commercially available.

You can also pin a starting material you already have — *"plan a route from A to B."*

![Retrosynthesis](docs/screenshots/03-retrosynthesis.png)

### Reaction condition recommendation

Every step can be completed with suggested **reagents, solvents, catalysts and temperature**, derived from 680,000 literature precedents plus named-reaction rules.

Routes can be sent to the drawing canvas step by step or all at once; existing content on the canvas is never cleared.

### Product prediction

Given reactants (optionally with reagents), predict the most likely products ranked by probability. Any candidate can go straight to the canvas or be set as a retrosynthesis target.

![Prediction](docs/screenshots/04-prediction.png)

### Structure recognition from images

Paste a screenshot from a paper or another chemistry application and it is recognized into an editable structure (MolScribe, with DECIMER as fallback). Copy-paste of MOL blocks from other software is supported too.

---

## Architecture

```
Electron desktop shell
   └─ silently starts a local service on 127.0.0.1:8765 (no console window)
         ├─ Conversion      RDKit + bundled dictionary + OPSIN
         ├─ Retrosynthesis  AiZynthFinder (MCTS)
         ├─ Recognition     MolScribe / DECIMER
         ├─ Prediction      ReactionT5v2
         └─ Conditions      DRFP fingerprints + precedent retrieval
```

The five engines live in **five isolated Python environments**. Their dependencies conflict (different PyTorch, TensorFlow and OpenNMT versions) and cannot share one environment — keeping them apart also means a broken engine never takes down the others.

The interface and the engines talk over a loopback HTTP socket that never leaves the machine. Closing the window shuts the engines down cleanly, leaving no background processes.

---

## Getting the full application

The complete offline build (about 11 GB: compound database, dictionary, four AI models, five Python environments) is **not** stored in this repository — those are large binaries from upstream sources.

See [`docs/BUILD.md`](docs/BUILD.md) for how to assemble a ready-to-run build from this source.

**Requirements:** Windows 10/11 (64-bit). No Python, Java or runtime packages need to be installed beforehand, and no administrator rights are required.

> Moving it to another computer? Copy the **whole folder** and run `Retron\Retron.exe`. On first start it repairs its own environment paths, creates a desktop shortcut, and runs offline from then on.

---

## Repository layout

```
app/                 Local service: routing + engine process management
engine/              The five engines
  chemistry/         structure / name / formula conversion
  retro/             retrosynthetic route search
  vision/            structure recognition from images
  forward/           reaction product prediction
  conditions/        reaction condition recommendation
web/                 Interface (three tabs) and the drawing canvas
shell/               Electron desktop shell
tools/               Maintenance scripts + per-environment dependency snapshots
  repair_env.py            rewrites environment paths after moving the folder
  check_runtime_deps.py    audits runtime library dependencies
  make_dist.py             produces a distributable build
  requirements/            dependency snapshots for the five environments
docs/                Screenshots and build notes
```

---

## Open source components

Retron would not exist without these projects:

| Component | Role | License |
|---|---|---|
| [Ketcher](https://github.com/epam/ketcher) | Chemical structure editor | Apache-2.0 |
| [RDKit](https://www.rdkit.org/) | Cheminformatics toolkit | BSD-3-Clause |
| [AiZynthFinder](https://github.com/MolecularAI/aizynthfinder) | Retrosynthesis search | MIT |
| [OPSIN](https://github.com/dan2097/opsin) | Systematic name parsing | MIT |
| [MolScribe](https://github.com/thomas0809/MolScribe) | Structure recognition | MIT |
| [DECIMER](https://github.com/Kohulan/DECIMER-Image_Transformer) | Structure recognition | MIT |
| [ReactionT5v2](https://huggingface.co/sagawa/ReactionT5v2-forward-USPTO_MIT) | Reaction prediction | MIT |
| [Electron](https://www.electronjs.org/) | Desktop shell | MIT |

Data: AiZynthFinder's Zinc stock (17.4M purchasable compounds), USPTO_Condition (680k precedents), PubChem / Wikidata / drug directories (dictionary).

---

## Limitations

- **Windows only.** The engines are cross-platform Python, but the desktop shell and the path-repair logic target Windows.
- **First retrosynthesis run is slow** — about a minute to load the compound database and models; later runs take roughly 20 seconds.
- **Image recognition** is accurate on printed structures; hand-drawn sketches and complex stereochemistry may need manual correction.
- Routes and predicted products are **suggestions derived from literature data** — experimental feasibility is up to you.

---

## License

[MIT](LICENSE) — see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) for the bundled components, build artifacts and data sources.
