# 16. Context-identifier scan v0 (run 006)

Faces are not the only thing that identifies a person. A plate, a phone number on a poster, an e-mail on a screen or a
street address on a letter can do it just as well, and for a child it can point to home or school. v0 looks for these with
ordinary OCR plus rules and destroys the identifier-like ones exactly as a face is destroyed. It is **off by default**
(`--context-scan`) and **heuristic**: read "what it cannot do" before trusting it.

## What it does
| Kind | Examples (all invented) | Default |
|---|---|---|
| `plate_like` | ABC1D23, ABC-1234, 7ABC123, "ABC 1234" | **BLOCK** |
| `contact_like` | e-mail, phone (8-15 digits), URL, @handle | **BLOCK** |
| `address_like` | "Rua das Flores 123", "742 Evergreen Terrace", "Main Road 133", postal codes, block/apartment numbers | **BLOCK** |
| `text` | any other readable text (a shop sign) | flag only, pixels untouched |
| `plate_shape_unread` | plate-shaped object whose text OCR could not read | flag only |

Flagged regions appear as review markers that **require a decision** (accept as is, or escalate to a redaction); see doc 17.
Whether ordinary text should be redacted outright is decision D11 (ADR 0009).

## How it works (`context.py`)
1. **OCR** (`TesseractOcr`): the system `tesseract` binary, frames passed as PNG over **stdin** (no temp files; a test enforces it).
   Two whole-frame passes (`--psm 6` and `--psm 3`) are merged.
2. **Classification** (`classify_line`, a pure function): regexes on OCR lines, mapped back to word boxes so only the matching words
   are blocked ("Call 61 99876-5432 tomorrow" blocks the number, flags the rest). A lone plate-like token counts in any line.
3. **Plate-shape finder** (`find_plate_shapes`): rectangles with aspect 1.8-7 holding 4-10 similar character-sized blobs, deskewed to an
   upright 44 px crop and read as a single line (`--psm 7`), at most 4 crops per frame. A plate-shaped object that reads cleanly as a
   word is a sign, not an "unread plate".
4. **Tracks** (`_Linker`): findings are linked across scans by overlap, falling back to centre distance for fast movers. A track's
   treatment is the strongest of any kind ever seen on it, so it never weakens.
5. **Two sources** feed the pipeline. `LiveContext`: scan every N frames, hold the region between scans (constant-velocity guess,
   box grows 3%/frame), backfill the lookahead. `PlannedContext`: whole-file planning in `TwoPassRunner` (pass keeps geometry and
   fingerprints only): interpolation between sightings, extension of `2*scan_every-1` frames before the first and after the last
   sighting, same-video fingerprint check.
6. **Render**: context regions are applied **after** faces/swaps, so nothing can paste pixels back over them. A scan failure on a
   frame **blocks the whole frame**. A missing engine or language exits 2 before any output exists.

## Recognised text never leaves the module
`ContextFinding` holds kind, box and confidence only: not the string, not a hash (a plate or phone number has too little entropy: a
hash is a lookup table). Reports and review JSON therefore cannot leak it; tests check that planted strings never appear.

## Measured (`runs/run-006/context_benchmark.md`)
**Synthetic and optimistic.** Invented text in clean Liberation/DejaVu fonts, 12 degradation variants, 4 scenes each (so every cell is a
multiple of 25%), 5 items per scene, one CPU core. Real plates (fonts, embossing, glare, perspective, motion blur, dirt), other
languages and real cameras are not represented.

| engine config | s/frame | identifiers covered* | plates covered* |
|---|---|---|---|
| psm 6 only | 0.15 | 71% | 33% |
| psm 6 + 3 | 0.30 | 80% | 48% |
| **psm 6 + 3 + plate-shape crops (default)** | **0.54** | **94%** | **85%** |
| psm 6 + 3 at 1x and 2x + crops | 0.95 | 93% | 85% |

*at least 80% of the item's text area inside a redaction region. The 4-pass "thorough" config costs 1.8x for no measurable gain, so it
is not the default. Weak spots in the default: clean-font plates 75% (3 of 4 scenes), rotated 25 degrees e-mail 50%, rotated sign
flagged 33%. Rotated text inflates redacted area: 14% (10 degrees) and 24% (25 degrees) of the frame is redacted away from any text.
No ordinary sign was redacted in any variant; unread-shape flags off any item: 0 to 0.5 per frame.

Exploration that shaped the design (read rate on single passes): sparse-text mode (`--psm 11`) reads big signs but almost nothing
else (about 3% of phones/e-mails/addresses), so it is not used. A stacked "montage" of crops read in one call fails because
Tesseract's layout analysis skips large bright bordered rectangles; crops are read one by one.

**Temporal coverage** (simulated scanner, 90 frames; not OCR accuracy). With a perfect scanner, scan-every-3 leaks nothing on static, moving,
late-appearing or briefly occluded items, but a 6-frame pass leaks at cadence 8 (25%). With 30% of scans missing the item, the two-pass
extension cuts leak on a static item at cadence 3 from 13.9% to 0.8%. An item visible for fewer frames than the cadence can be missed
entirely: that is the price of the speed dial (D12).

## What it cannot do (also in `KNOWN_LIMITATIONS` and every report)
Text that is small, blurred, rotated, stylised, upside down, reflective or in a language whose OCR data is not installed (this build's
sandbox had English only); name tags, uniforms, logos, tattoos, QR codes and signage as a location cue (only readable text is flagged);
items visible for fewer frames than the scan cadence. **Re-OCRing the output cannot verify the result**: in run 006 Tesseract also
returned nothing for a visible sign in a mostly black frame, so "OCR found nothing" is weak evidence. There is no independent verifier.

## Use
```
privacyfirst video in.mp4 out.mp4 --context-scan [--context-every 3] [--ocr-lang eng+por] --review-json review.json
python -m privacyfirst.bench.contextbench --out runs/bench          # needs tesseract + Liberation fonts
python scripts/demo_context.py runs/demo-context
```
Install: `apt install tesseract-ocr` (or `brew install tesseract`) plus the language packs you need.
