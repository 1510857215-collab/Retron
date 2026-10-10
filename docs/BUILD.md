# Building a complete offline build

This document describes how to assemble a ready-to-run Retron build from this source tree.

The repository contains **code only**. A working installation also needs:

- a base Python 3.11 interpreter
- five isolated Python environments
- model weights and data files (about 4.8 GB)

Everything below is obtained from public sources and stored locally. After the build is complete, the application never accesses the network again.

---

## 1. Directory layout of a complete build

```
Retron/
├── Retron/                  desktop shell (Retron.exe + Electron runtime)
├── app/                     local service
├── web/                     interface + drawing canvas
├── engine/                  the five engines
├── data/                    models and data (about 4.8 GB)
├── tools/
│   ├── python311/           base Python 3.11 interpreter
│   ├── venv/                environment: conversion
│   ├── venv-retro/          environment: retrosynthesis
│   ├── venv-vision/         environment: image recognition
│   ├── venv-forward/        environment: product prediction
│   ├── venv-conditions/     environment: condition recommendation
│   ├── repair_env.py
│   ├── check_runtime_deps.py
│   ├── make_dist.py
│   └── requirements/        dependency snapshots
├── 使用说明.md
└── 首次使用必读.txt
```

The shell locates the project root by searching upward from `Retron.exe` for a directory containing both `app/server.py` and `tools/python311/python.exe`. Keep this layout when assembling your own build.

---

## 2. Base interpreter

Place a **Windows x64 Python 3.11** installation (embeddable or full) in `tools/python311/`.

Make sure `vcruntime140.dll` and `vcruntime140_1.dll` are present next to `python311.dll`. Also copy the following from `C:\Windows\System32` into `tools/python311/` so the build does not depend on the target machine having the Visual C++ redistributable installed:

```
msvcp140.dll
msvcp140_1.dll
msvcp140_2.dll
msvcp140_atomic_wait.dll
msvcp140_codecvt_ids.dll
concrt140.dll
```

`tools/check_runtime_deps.py` audits this automatically:

```
tools\python311\python.exe tools\check_runtime_deps.py
```

It walks every `.pyd` and `.dll` under `tools/`, parses PE import tables, and reports any Visual C++ runtime libraries that are required but not bundled.

---

## 3. The five environments

Create each environment with the base interpreter, then install its snapshot:

```
tools\python311\python.exe -m venv tools\venv
tools\venv\Scripts\pip.exe install -r tools\requirements\requirements-base.txt
```

| Environment | Snapshot | Engine | Notes |
|---|---|---|---|
| `tools/venv` | `requirements-base.txt` | conversion | RDKit, OPSIN |
| `tools/venv-retro` | `requirements-retro.txt` | retrosynthesis | AiZynthFinder |
| `tools/venv-vision` | `requirements-vision.txt` | recognition | PyTorch CPU |
| `tools/venv-forward` | `requirements-forward.txt` | prediction | PyTorch **CPU build** is sufficient |
| `tools/venv-conditions` | `requirements-conditions.txt` | conditions | Pure RDKit / numpy |

Notes:

- **Install PyTorch separately, from its own index.** PyPI only carries the CUDA build (roughly 2.4 GB larger, and it expects an NVIDIA software stack). This project uses the CPU build:

  ```bash
  # for venv-forward
  tools\python311\python.exe -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu

  # for venv-vision (needs torchvision as well)
  tools\python311\python.exe -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
  ```

  PyTorch is therefore **deliberately absent from the `requirements-*.txt` snapshots** — installing those files alone is not sufficient, and a plain `pip install torch` would silently pull the CUDA build instead.

  Inference here is dominated by model loading rather than computation, so the CPU build is not a compromise — it also removes any dependency on an NVIDIA GPU on the target machine.
- `venv-vision` pins `timm==0.4.12`: MolScribe's vendored Swin code registers `swin_base` at import time. This is an older release paired with a recent PyTorch, but **this is the exact combination the project was built and tested against**. If you widen it, re-run the recognition check described in [`tools/patches/README.md`](../tools/patches/README.md).
- **Two packages need small runtime patches** before the recognition engine will import at all:

  | Target | Why |
  |---|---|
  | MolScribe (2 files) | Written against albumentations 0.x; on 2.x its import chain breaks. Its vendored Swin module also fails to import under a modern `timm`. Neither path is used at inference time — they only have to import cleanly. |
  | `torchtext` (3 files) | MolScribe's decoder reuses OpenNMT-py 2.2.0 modules, and `import onmt` transitively imports `torchtext`, which is discontinued and does not work with PyTorch 2.x. A stub package lets the import chain pass. |

  Both are provided as drop-in files in [`tools/patches/`](../tools/patches/) — **without them the vision engine will not start**. The folder's README has the two copy commands and a verification step.

---

## 4. Models and data

Place these under `data/`. Sources:

| Data | Source | Location |
|---|---|---|
| Purchasable compound stock (17.4M entries) | Zinc stock shipped with AiZynthFinder | `data/retro/zinc_stock.hdf5` |
| Retrosynthesis models (USPTO-trained) | AiZynthFinder release assets | `data/retro/*.onnx`, `*.csv.gz`, `config.yml` |
| Product prediction model | [`sagawa/ReactionT5v2-forward-USPTO_MIT`](https://huggingface.co/sagawa/ReactionT5v2-forward-USPTO_MIT) | `data/forward/模型/` |
| Structure recognition | MolScribe and DECIMER weights | `data/vision/models/`, `data/vision/pystow/` |
| Condition precedents (680k) | USPTO_Condition dataset | `data/conditions/` |
| Compound dictionary | PubChem / Wikidata / drug directories | `data/中文名字典.sqlite` |

The dictionary is built with `engine/chemistry/dict_build.py` from the seed list in `engine/chemistry/seed_list.txt`.

> **Large downloads:** the Zinc stock file is about 660 MB. If a download is interrupted you may end up with a truncated file that still looks plausible — verify the header and the line count before trusting it.

---

## 5. Desktop shell

```
cd shell
npm install
npm run pack          # produces ../Retron-dist/win-unpacked/
```

Then place the output at `<build root>/Retron/` so that the layout matches section 1.

---

## 6. Producing a distributable build

`tools/make_dist.py` copies everything needed for running (and nothing that is not) into a clean folder:

```
tools\python311\python.exe tools\make_dist.py "D:\Retron"
```

It excludes development scripts, caches, temporary files and runtime artifacts, then verifies that all critical files are present.

---

## 7. Moving the build to another computer

Copy the **entire folder**, then run `Retron\Retron.exe`.

Virtual environment configuration files (`pyvenv.cfg`) contain absolute paths and will point at the build machine. This is repaired automatically:

```
Retron\tools\python311\python.exe Retron\tools\repair_env.py
```

The shell runs an equivalent check on every startup, so normally you do not need to do anything. The script is idempotent: it rewrites only path references and reports "skipped" for engines that are not installed.

No Python, Java, or runtime packages are required on the target machine, and no administrator rights are needed.
