# Context-identifier scan benchmark (run 006)

SYNTHETIC. Part 1 uses clean rendered fonts (Liberation/DejaVu) on invented plates, numbers and addresses with controlled degradation; real plates, signs, cameras, perspective, motion blur and non-English text are NOT represented, so treat every number as an optimistic upper bound. Part 2 uses a simulated scanner and measures tracking logic only.

## Part 1: scan quality (real Tesseract, 4 scenes per variant, 5 items per scene)

'covered' = at least 80% of the item's text area lies inside a redaction region the pipeline would apply.

| config | sec/frame (1 core) | identifiers covered | plates covered |
|---|---|---|---|
| psm6 | 0.15 | 71% | 33% |
| default | 0.30 | 80% | 48% |
| default+shape | 0.54 | 94% | 85% |
| thorough+shape | 0.95 | 93% | 85% |

### psm6

| variant | plate | phone | e-mail | address | sign flagged/covered | false ident. findings/frame | unread-shape flags off-item/frame | blank area redacted | signs wrongly redacted |
|---|---|---|---|---|---|---|---|---|---|
| clear | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| clutter | 50% | 100% | 100% | 100% | 75% | 0.00 | 0.00 | 5.42% | 0% |
| small | 0% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 1.51% | 0% |
| tiny | 0% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 0.54% | 0% |
| blur_light | 50% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.04% | 0% |
| blur_heavy | 0% | 100% | 50% | 75% | 100% | 0.00 | 0.00 | 2.71% | 0% |
| rot_10 | 0% | 75% | 50% | 75% | 75% | 0.00 | 0.00 | 7.78% | 0% |
| rot_25 | 25% | 25% | 0% | 75% | 33% | 0.00 | 0.00 | 4.18% | 0% |
| noisy | 75% | 100% | 75% | 100% | 75% | 0.00 | 0.00 | 5.60% | 0% |
| low_contrast | 50% | 100% | 75% | 100% | 100% | 0.00 | 0.00 | 3.62% | 0% |
| dark | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| hard_mix | 0% | 50% | 50% | 50% | 50% | 0.00 | 0.00 | 1.58% | 0% |

### default

| variant | plate | phone | e-mail | address | sign flagged/covered | false ident. findings/frame | unread-shape flags off-item/frame | blank area redacted | signs wrongly redacted |
|---|---|---|---|---|---|---|---|---|---|
| clear | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| clutter | 50% | 100% | 100% | 100% | 75% | 0.00 | 0.00 | 5.42% | 0% |
| small | 25% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 1.55% | 0% |
| tiny | 0% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 0.54% | 0% |
| blur_light | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 5.76% | 0% |
| blur_heavy | 75% | 100% | 50% | 100% | 100% | 0.00 | 0.00 | 6.51% | 0% |
| rot_10 | 0% | 100% | 75% | 100% | 75% | 0.00 | 0.00 | 9.03% | 0% |
| rot_25 | 50% | 25% | 25% | 100% | 33% | 0.00 | 0.00 | 7.47% | 0% |
| noisy | 75% | 100% | 75% | 100% | 100% | 0.00 | 0.00 | 6.52% | 0% |
| low_contrast | 50% | 100% | 75% | 100% | 100% | 0.00 | 0.00 | 3.62% | 0% |
| dark | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| hard_mix | 25% | 75% | 50% | 100% | 75% | 0.00 | 0.00 | 6.06% | 0% |

### default+shape

| variant | plate | phone | e-mail | address | sign flagged/covered | false ident. findings/frame | unread-shape flags off-item/frame | blank area redacted | signs wrongly redacted |
|---|---|---|---|---|---|---|---|---|---|
| clear | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| clutter | 100% | 100% | 100% | 100% | 75% | 0.00 | 0.25 | 6.87% | 0% |
| small | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 2.05% | 0% |
| tiny | 100% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 0.82% | 0% |
| blur_light | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 5.76% | 0% |
| blur_heavy | 100% | 100% | 50% | 100% | 100% | 0.00 | 0.00 | 7.02% | 0% |
| rot_10 | 100% | 100% | 75% | 100% | 75% | 0.00 | 0.00 | 13.83% | 0% |
| rot_25 | 100% | 100% | 50% | 100% | 33% | 0.00 | 0.00 | 24.07% | 0% |
| noisy | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.25 | 7.91% | 0% |
| low_contrast | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 5.57% | 0% |
| dark | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| hard_mix | 75% | 100% | 100% | 100% | 75% | 0.00 | 0.50 | 9.87% | 0% |

### thorough+shape

| variant | plate | phone | e-mail | address | sign flagged/covered | false ident. findings/frame | unread-shape flags off-item/frame | blank area redacted | signs wrongly redacted |
|---|---|---|---|---|---|---|---|---|---|
| clear | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| clutter | 100% | 100% | 100% | 100% | 75% | 0.00 | 0.25 | 6.87% | 0% |
| small | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 1.83% | 0% |
| tiny | 100% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 0.82% | 0% |
| blur_light | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 5.90% | 0% |
| blur_heavy | 100% | 100% | 50% | 100% | 100% | 0.00 | 0.00 | 7.06% | 0% |
| rot_10 | 100% | 100% | 75% | 100% | 100% | 0.00 | 0.00 | 14.93% | 0% |
| rot_25 | 100% | 100% | 50% | 100% | 67% | 0.00 | 0.00 | 25.68% | 0% |
| noisy | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.25 | 8.09% | 0% |
| low_contrast | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| dark | 75% | 100% | 100% | 100% | 100% | 0.00 | 0.00 | 4.07% | 0% |
| hard_mix | 75% | 100% | 75% | 100% | 100% | 0.00 | 0.50 | 7.13% | 0% |

## Part 2: temporal coverage with a simulated scanner (90 frames, 800x560)

leak% = share of frames where the item is visible but less than 80% covered; area = redacted area / item area while visible; extra = share of frames redacting while the item is NOT visible (tails). `extend=none` turns off the two-pass extension.

| mode | every | p_miss | extend | static leak% / area | crossing_8px leak% / area | brief_pass_6f leak% / area | late_appear leak% / area | occluded_4f leak% / area | extra% (mean) |
|---|---|---|---|---|---|---|---|---|---|
| live | 1 | 0.0 | default | 0.0 / 2.3 | 0.0 / 2.1 | 0.0 / 2.2 | 0.0 / 2.3 | 0.0 / 2.3 | 3.3 |
| live | 1 | 0.3 | default | 0.3 / 2.5 | 0.3 / 2.3 | 0.0 / 2.2 | 0.0 / 2.4 | 0.0 / 2.5 | 2.8 |
| live | 3 | 0.0 | default | 0.0 / 2.5 | 0.0 / 2.3 | 0.0 / 2.4 | 0.0 / 2.4 | 0.0 / 2.5 | 3.7 |
| live | 3 | 0.3 | default | 1.1 / 2.6 | 1.1 / 2.5 | 50.0 / 1.2 | 2.7 / 2.5 | 1.2 / 2.6 | 2.3 |
| live | 5 | 0.0 | default | 0.0 / 2.6 | 0.0 / 2.5 | 0.0 / 2.5 | 0.0 / 2.6 | 0.0 / 2.7 | 4.4 |
| live | 5 | 0.3 | default | 3.3 / 2.8 | 3.3 / 2.6 | 50.0 / 1.2 | 6.6 / 2.7 | 3.5 / 2.9 | 2.7 |
| live | 8 | 0.0 | default | 0.0 / 2.9 | 0.0 / 2.7 | 25.0 / 1.8 | 2.2 / 2.8 | 0.0 / 3.0 | 4.9 |
| live | 8 | 0.3 | default | 6.7 / 3.2 | 6.7 / 2.9 | 75.0 / 0.6 | 16.4 / 2.8 | 7.0 / 3.3 | 2.5 |
| plan | 1 | 0.0 | default | 0.0 / 2.3 | 0.0 / 2.1 | 0.0 / 2.2 | 0.0 / 2.3 | 0.0 / 2.3 | 1.1 |
| plan | 1 | 0.0 | none | 0.0 / 2.3 | 0.0 / 2.1 | 0.0 / 2.2 | 0.0 / 2.3 | 0.0 / 2.3 | 0.0 |
| plan | 1 | 0.3 | default | 2.8 / 2.2 | 2.8 / 2.1 | 8.3 / 2.0 | 2.2 / 2.2 | 2.0 / 2.2 | 0.8 |
| plan | 1 | 0.3 | none | 6.9 / 2.1 | 6.9 / 2.0 | 20.8 / 1.7 | 5.2 / 2.1 | 6.1 / 2.1 | 0.0 |
| plan | 3 | 0.0 | default | 0.0 / 2.3 | 0.0 / 2.2 | 0.0 / 2.4 | 0.0 / 2.3 | 0.0 / 2.3 | 3.5 |
| plan | 3 | 0.0 | none | 2.2 / 2.2 | 2.2 / 2.1 | 33.3 / 1.5 | 5.7 / 2.1 | 3.5 / 2.2 | 0.7 |
| plan | 3 | 0.3 | default | 0.8 / 2.4 | 0.8 / 2.2 | 50.0 / 1.1 | 1.8 / 2.3 | 0.9 / 2.4 | 2.2 |
| plan | 3 | 0.3 | none | 13.9 / 1.9 | 13.9 / 1.9 | 66.7 / 0.7 | 15.8 / 1.9 | 16.9 / 1.9 | 0.4 |
| plan | 5 | 0.0 | default | 0.0 / 2.3 | 0.0 / 2.2 | 0.0 / 2.6 | 0.0 / 2.3 | 0.0 / 2.3 | 5.5 |
| plan | 5 | 0.0 | none | 4.4 / 2.2 | 4.4 / 2.1 | 62.5 / 0.8 | 11.3 / 2.0 | 4.7 / 2.1 | 0.9 |
| plan | 5 | 0.3 | default | 0.6 / 2.5 | 0.6 / 2.3 | 50.0 / 1.2 | 2.2 / 2.6 | 0.6 / 2.5 | 3.2 |
| plan | 5 | 0.3 | none | 15.3 / 1.9 | 15.3 / 1.9 | 70.8 / 0.6 | 28.5 / 1.6 | 20.3 / 1.8 | 0.4 |
| plan | 8 | 0.0 | default | 0.0 / 2.3 | 0.0 / 2.1 | 25.0 / 2.1 | 0.0 / 2.3 | 0.0 / 2.3 | 7.6 |
| plan | 8 | 0.0 | none | 1.1 / 2.2 | 1.1 / 2.1 | 87.5 / 0.3 | 7.9 / 2.1 | 1.2 / 2.2 | 0.9 |
| plan | 8 | 0.3 | default | 0.6 / 2.7 | 0.6 / 2.6 | 75.0 / 0.6 | 6.6 / 2.8 | 0.6 / 2.9 | 3.9 |
| plan | 8 | 0.3 | none | 18.6 / 1.8 | 18.6 / 1.7 | 95.8 / 0.1 | 32.2 / 1.5 | 25.0 / 1.7 | 0.7 |
