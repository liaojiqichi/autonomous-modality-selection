"""Exercise the supplied notebook adapter with fake tensors and no GPU or models."""

import ast
import copy
import json
import sys
import time
from contextlib import ExitStack, nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Literal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ConfigDict

NOTEBOOK = Path("notebooks/autonomous_modality_selection_four_modality.ipynb")


def sources() -> list[str]:
    return [
        "".join(c["source"])
        for c in json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
        if c["cell_type"] == "code"
    ]


@pytest.mark.parametrize("qwen", [False, True])
@pytest.mark.parametrize("limit", [2, 8])
def test_model_adapter_arguments_and_limit(
    monkeypatch: pytest.MonkeyPatch, qwen: bool, limit: int
) -> None:
    transformers = ModuleType("transformers")
    transformers.__version__ = "4.57.6" if qwen else "5.fixture"
    transformers.GenerationConfig = lambda: SimpleNamespace(temperature=1.0, top_p=1.0, top_k=50)
    integrations = ModuleType("transformers.integrations")
    sdpa = ModuleType("transformers.integrations.sdpa_attention")

    def original_helper(attention_mask: object, key: object) -> bool:
        return True

    sdpa.use_gqa_in_sdpa = original_helper
    transformers.integrations = integrations
    integrations.sdpa_attention = sdpa
    for name, module in (
        ("transformers", transformers),
        ("transformers.integrations", integrations),
        ("transformers.integrations.sdpa_attention", sdpa),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    model_id = "Qwen/Qwen3-VL-8B-Instruct" if qwen else "google/gemma-4-E4B-it"
    torch = MagicMock()
    torch.cuda.is_available.return_value = True
    torch.cuda.max_memory_allocated.return_value = 1024**3
    torch.inference_mode.side_effect = nullcontext
    inputs = MagicMock()
    inputs.__getitem__.return_value.shape = (1, 4)
    inputs.to.return_value = {"input_ids": "fixture"}
    processor = MagicMock()
    processor.apply_chat_template.return_value = inputs
    processor.batch_decode.return_value = ["Fixture response"]
    processor.tokenizer.eos_token_id = 2
    output = MagicMock()
    output.__getitem__.return_value.__getitem__.return_value.tolist.return_value = [7, 2]
    model = MagicMock()
    model.config._name_or_path = model_id
    model.generation_config = SimpleNamespace(temperature=0.8, top_p=0.9, top_k=20, eos_token_id=2)
    model.generate.return_value = output
    ns = dict(
        copy=copy,
        time=time,
        Any=Any,
        Literal=Literal,
        BaseModel=BaseModel,
        ConfigDict=ConfigDict,
        ExitStack=ExitStack,
        patch=patch,
        torch=torch,
        transformers=transformers,
        model=model,
        processor=processor,
        MODEL_NAME=model_id,
        MODEL_ID=model_id,
        MODEL_CLASSES={model_id: "Fixture"},
        MAX_INPUT_TOKENS=limit,
        sdpa_kernel=lambda **kwargs: nullcontext(),
        SDPBackend=SimpleNamespace(EFFICIENT_ATTENTION="fixture"),
    )
    source = next(s for s in sources() if "class GenerationTrace" in s)
    tree = ast.parse(source)
    tree.body = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
    exec(compile(tree, "<fake-model-adapter>", "exec"), ns)
    if limit < 4:
        with pytest.raises(ValueError, match="INPUT_TOKEN_LIMIT"):
            ns["generate_reply"]([], max_new_tokens=8)
        model.generate.assert_not_called()
        inputs.to.assert_not_called()
        assert ns["GENERATION_LOG"][-1]["finish_reason"] == "error"
        return
    assert ns["generate_reply"]([], max_new_tokens=8) == "Fixture response"
    kwargs = model.generate.call_args.kwargs
    assert set(kwargs) == {"input_ids", "generation_config"} | (
        {"use_model_defaults"} if qwen else set()
    )
    config = kwargs["generation_config"]
    assert config.do_sample is False and config.max_new_tokens == 8
    assert config.top_p == 1.0 and config.top_k == 50
    assert config.return_dict_in_generate is False
    assert ("enable_thinking" in processor.apply_chat_template.call_args.kwargs) is not qwen
    assert ns["GENERATION_LOG"][-1]["finish_reason"] == "eos"
    assert sdpa.use_gqa_in_sdpa is original_helper


def test_install_order_and_shared_questions() -> None:
    cells = sources()
    install = next(s for s in cells if "packages =" in s and "MODEL_CLASSES" in s)
    assert "import transformers" not in install and "from PIL" not in install
    assert "Pillow==12.3.0" in install and "transformers==4.57.6" in install
    config = next(s for s in cells if "TARGET_ID =" in s)
    assert "configs/mercury_selection_questions_v2.json" in config
    assert config.count("IMAGE_EDGE =") == 1
    selector = next(s for s in cells if "class AgentChoice" in s)
    assert "from pydantic import BaseModel, ConfigDict, Field" in selector
    assert "parsed = parse_agent_choice(raw)" in selector
