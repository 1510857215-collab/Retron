# Runtime patches

The recognition engine (`tools/venv-vision`) needs a few small adaptations that
cannot be expressed in a `requirements.txt`. They are collected here so that a
build can be reproduced end to end.

**Total: 5 files, about 30 KB.** All of them are drop-in replacements — copy them
over the corresponding files in the installed packages.

---

## 1. MolScribe (2 files)

MolScribe was written against albumentations 0.x. On albumentations 2.x its import
chain breaks (internal helpers were renamed or moved), and its vendored Swin module
fails to import against a modern `timm`. **Neither code path runs at inference
time** — they only need to import cleanly.

| File | What it changes |
|---|---|
| `molscribe/augment.py` | Tolerates the missing albumentations helpers (falls back to no-op stand-ins); pads with `cv2` instead of the removed `pad_with_params` |
| `molscribe/transformer/__init__.py` | Tolerates the failure of the dead `swin_transformer` import |

Apply:

```bash
cp -r tools/patches/molscribe/. tools/venv-vision/Lib/site-packages/molscribe/
```

---

## 2. torchtext stub (3 files)

MolScribe's Transformer decoder reuses modules from OpenNMT-py 2.2.0, and
`import onmt` transitively imports `torchtext` — which has been discontinued and
no longer works with PyTorch 2.x. Nothing in the inference path actually calls
torchtext, so a stub package lets the import chain pass without downgrading
PyTorch (and without touching the rest of the environment).

| File | What it provides |
|---|---|
| `torchtext/__init__.py` | `_Stub` / `_make` helpers; returns placeholder classes for any attribute |
| `torchtext/data/__init__.py` | The names OpenNMT-py imports (`Field`, `Dataset`, `Iterator`, …) |
| `torchtext/vocab/__init__.py` | `Vocab`, `Vectors`, `GloVe`, `FastText`, … |

These files create a package that **did not previously exist** in the environment.
If a real `torchtext` is present, remove it first, otherwise the stub will be
shadowed or conflict.

Apply:

```bash
cp -r tools/patches/torchtext/. tools/venv-vision/Lib/site-packages/torchtext/
```

---

## Verification

After applying both patches, the recognition engine should import cleanly:

```bash
tools/venv-vision/Scripts/python.exe -c "import molscribe; import torchtext; print('ok')"
```

And end to end (with the local service running):

```bash
tools/venv-vision/Scripts/python.exe engine/vision/ocr_cli.py web/_selftest/selftest_molecule.png
```

Expected output:

```json
{"ok": true, "smiles": "CC(=O)Oc1ccccc1C(=O)O", "engine": "molscribe"}
```

---

## Why drop-in files instead of a `.patch`?

These are small, self-contained modules, and the affected packages are installed
from source rather than from wheels. A drop-in copy is easier to apply and to
verify than a diff, which can fail against a slightly different upstream revision.
