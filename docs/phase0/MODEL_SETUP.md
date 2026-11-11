# Model Setup (local)

Model files are not bundled. Create a folder, put files in it, and set `PRIVACYFIRST_MODEL_DIR`.

| Model | File name expected | Where to get it (verify URL and license yourself) |
|---|---|---|
| MediaPipe BlazeFace short range | `blaze_face_short_range.tflite` | MediaPipe Face Detector model card / Google AI Edge docs |
| YuNet 2023mar | `face_detection_yunet_2023mar.onnx` | OpenCV Zoo, `models/face_detection_yunet` (stored with Git LFS: clone with LFS, not a raw download) |

Smoke check:
```python
from privacyfirst.adapters.yunet import YuNetDetector
from privacyfirst.bench.runner import evaluate_detector
from privacyfirst.bench.synth import make_clip
print(evaluate_detector(YuNetDetector(), [make_clip("baseline", 0, 60)]))   # drawn faces: plumbing check only
```
Drawn faces are not a valid accuracy test. Use real, consented footage with ground truth for real numbers.

Why these are not fetched automatically: the build sandbox could not reach the hosts serving the weights
(the YuNet file on GitHub raw is a Git-LFS pointer; MediaPipe's current pip release bundles no model).
