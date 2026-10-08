# Third-party notices

Retron is built on open source software. This file lists the components that are
invoked at runtime or bundled in the distributed build, together with their
licenses. All copyrights belong to their respective authors.

## Runtime components

| Component | Role | License | Homepage |
|---|---|---|---|
| Ketcher | Chemical structure editor | Apache-2.0 | https://github.com/epam/ketcher |
| RDKit | Cheminformatics toolkit | BSD-3-Clause | https://www.rdkit.org/ |
| AiZynthFinder | Retrosynthesis search | MIT | https://github.com/MolecularAI/aizynthfinder |
| OPSIN | Systematic name parsing | MIT | https://github.com/dan2097/opsin |
| MolScribe | Structure recognition from images | MIT | https://github.com/thomas0809/MolScribe |
| DECIMER | Structure recognition from images (fallback) | MIT | https://github.com/Kohulan/DECIMER-Image_Transformer |
| ReactionT5v2 | Reaction product prediction | MIT | https://huggingface.co/sagawa/ReactionT5v2-forward-USPTO_MIT |
| Electron | Desktop application shell | MIT | https://www.electronjs.org/ |
| Chromium | Rendering engine (via Electron) | BSD-3-Clause | https://www.chromium.org/ |

## Bundled build artifacts

- `web/ketcher/` contains a build of **Ketcher** (Apache License 2.0). A Chinese
  interface string table has been applied on top of the upstream build. The
  patched build is reproducible with `tools/build_ketcher_zh.mjs`.
- The distributed build additionally bundles Python 3.11 and the third-party
  packages listed in `tools/requirements/requirements-*.txt`. Each package
  remains under its own license; the full text of those licenses is available in
  the corresponding package distributions.

## Data sources

| Data | Source | Notes |
|---|---|---|
| Purchasable compound stock (17.4M entries) | Zinc database, as distributed with AiZynthFinder | Used for retrosynthesis starting-material availability |
| USPTO_Condition precedents (680k) | USPTO patent reaction dataset | Used for reaction condition recommendation |
| Retrosynthesis models | AiZynthFinder release assets (USPTO-trained) | ONNX format |
| Recognition models | MolScribe / DECIMER official weights | See `data/vision/` |
| Prediction model | `sagawa/ReactionT5v2-forward-USPTO_MIT` | MIT |
| Compound dictionary | PubChem, Wikidata, public drug directories | Assembled locally; every entry records its source |

## Disclaimer

This software is provided for research assistance only. Retrosynthetic routes and
predicted products are **suggestions derived from literature data** and are not a
substitute for experimental judgement.
