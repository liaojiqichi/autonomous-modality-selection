"""Direct execution cells for the formal revision notebook."""

CONTEXT = """import importlib.metadata
import importlib.util
import json
import re
from types import SimpleNamespace

from autonomous_modality.acquisition import sha256_file
from autonomous_modality.heldout_colab import load_context, preserve_json
from autonomous_modality.heldout_preparation import locate_dataset

OVERLAY = PROJECT / "configs/heldout_question_revision_20261016"
FORMAL_NOTEBOOK = REVISION_NOTEBOOK
PROMPT_PATH = PROJECT / "configs/heldout_runtime_revision_20261016/prompts.py"
AMENDMENT_PATH = PROMPT_PATH.with_name("revision.json")
amendment = json.loads(AMENDMENT_PATH.read_text())
if sha256_file(PROMPT_PATH) != amendment["prompt_sha256"]:
    raise ValueError("Runtime amendment prompt changed")
spec = importlib.util.spec_from_file_location("formal_prompts_v11", PROMPT_PATH)
FROZEN_PROMPTS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FROZEN_PROMPTS)
if BUDGET not in (3, 4):
    raise ValueError("Invalid budget")
if not all(re.fullmatch(r"[a-f0-9]{40}", r) for r in (MODEL_REVISION, PROCESSOR_REVISION)):
    raise ValueError("Set immutable model and processor revisions")
if MODEL_ID.startswith("Qwen/") and MODEL_REVISION == "ee0ef6023621cff504d758262d4e04895a5af4a2":
    raise ValueError("Supply the selected Qwen checkpoint revision")
DEPLOYMENT = SimpleNamespace(
    model_revision=MODEL_REVISION, processor_revision=PROCESSOR_REVISION,
    environment={
        "torch": "2.11.0+cu130",
        "transformers": "5.19.0" if MODEL_ID.startswith("google/") else "4.57.6",
        "bitsandbytes": "0.50.2", "accelerate": "1.15.0", "Pillow": "12.3.0",
        "numpy": "2.1.3", "pydantic": "2.13.5", "rasterio": "1.5.2",
        "matplotlib": "3.10.0",
    }, image_processor_size={}, image_processor_config={},
)
DATASET_ROOT = locate_dataset(DATASET_ROOT, DATASET_ZIP, DATASET_EXTRACT)
FORMAL = load_context(DATASET_ROOT, OVERLAY)
BATCH_TARGET_IDS = FORMAL.batch_ids(BATCH_NUMBER)
for filename in ("iterative.py", "iterative_colab.py"):
    frozen = DATASET_ROOT / "frozen/code/autonomous_modality" / filename
    current = PROJECT / "src/autonomous_modality" / filename
    if frozen.read_text(encoding="utf-8") != current.read_text(encoding="utf-8"):
        raise ValueError(f"Frozen iterative implementation differs: {filename}")
MAX_INPUT_TOKENS = 8192
OUTPUT: Path
CASE_ID: str
print("Targets:", BATCH_TARGET_IDS)
"""

INSTALL = """import subprocess
import sys
MODEL_CLASSES = {
    "Qwen/Qwen3-VL-8B-Instruct": "Qwen3VLForConditionalGeneration",
    "google/gemma-4-E4B-it": "Gemma4ForConditionalGeneration",
}
if MODEL_ID not in MODEL_CLASSES:
    raise ValueError(f"Unsupported model: {MODEL_ID}")
def installed_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""
changed = {n: v for n, v in DEPLOYMENT.environment.items() if installed_version(n) != v}
if changed and "model" in globals():
    raise RuntimeError("Start a fresh GPU runtime before changing installed libraries.")
loaded = {n for n in changed if n in sys.modules or (n == "Pillow" and "PIL" in sys.modules)}
if "torch" in changed:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "torch==" + changed["torch"], "torchvision==0.26.0+cu130",
                    "torchaudio==2.11.0+cu130", "--index-url",
                    "https://download.pytorch.org/whl/cu130"], check=True)
packages = [f"{n}=={v}" for n, v in changed.items() if n != "torch"]
if packages:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *packages], check=True)
if loaded:
    raise RuntimeError("Installed libraries changed. Restart the session once, then run in order.")
"""

DECLARATION = """import platform

from autonomous_modality.revision_colab import RuntimeDeclaration, RuntimeDeployment

DEPLOYMENT_PATH = RESULTS_ROOT / RUN_LABEL / MODEL_TAG / f"deployment-lock-b{BUDGET}.json"
RUNTIME_DECLARATION = RuntimeDeclaration(
    protocol_sha256=sha256_file(OVERLAY / "protocol.json"),
    notebook_sha256=sha256_file(REVISION_NOTEBOOK),
    models={MODEL_ID: RuntimeDeployment(
        model_revision=DEPLOYMENT.model_revision,
        processor_revision=DEPLOYMENT.processor_revision,
        environment=REVISION_RUNTIME["environment"],
        image_processor_config=REVISION_RUNTIME["image_processor"],
    )},
    python_version=platform.python_version(), gpu=torch.cuda.get_device_name(0),
    cuda=torch.version.cuda,
)
preserve_json(DEPLOYMENT_PATH, RUNTIME_DECLARATION.model_dump(mode="json"))
REVISION_PROTOCOL = REVISION_FINGERPRINT
"""
