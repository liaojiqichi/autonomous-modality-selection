# Four-modality notebook compatibility adapter

The maintained four-modality notebook incorporates the loader and generation cell
from the user's working notebook supplied on 16 October 2026. The original uploaded
notebook and historical runs are unchanged. The older three-modality iterative
notebook is not migrated by this change.

Select MODEL_ID in the model-environment cell before installing dependencies.
Qwen uses Transformers 4.57.6 and its explicit-KV memory-efficient SDPA workaround;
Gemma uses its native SDPA path and a compatible Transformers 5 installation.
Pillow 12.3.0 follows the supplied working setup. Dependencies are installed before
importing their processor modules, and changing an already imported version requires
a runtime restart. Actual installed versions remain recorded in run metadata.

Generation uses a single GenerationConfig. Gemma receives no use_model_defaults
argument. Qwen retains it only in the pinned 4.57.6 branch. Sampling settings are reset
to library defaults before greedy decoding; image routing, input limits, raw output,
EOS/truncation/error and memory logging remain intact. Input length is checked before
moving processed tensors to the GPU. The Qwen attention patch is scoped to each call.

The one-shot selector continues to accept bare JSON or one complete JSON fence and
reject malformed output; it imports Field itself. The shared revised four questions,
budget, answer limit, repetition penalty and input package construction are preserved.
The redundant IMAGE_EDGE=320 assignment was removed; the effective value remains 448.
A new default run label prevents accidental reuse of previous configuration records.

Temporary troubleshooting cells, duplicate configurations and the upload-based batch
runner in the supplied copy were not imported. The maintained notebook remains a
single-target development runner. No formal frozen protocol snapshot was overwritten.

Offline tests use explicitly fake models to check both generation branches, input
limit failures, source syntax and selector parsing. These tests do not demonstrate
GPU compatibility or available VRAM. Run the all-input Colab preflight before inference,
and use a fresh runtime when switching models. Do not reuse previous run labels.
