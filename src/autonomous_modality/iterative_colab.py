"""Compatibility bridge for generate_reply plus the existing GENERATION_LOG list."""

from collections.abc import Callable
from typing import Any

from autonomous_modality.iterative import Generate, GenerationReply


def notebook_generator(
    generate_reply: Callable[..., str], generation_log: list[dict[str, Any]]
) -> Generate:
    """Wrap the original notebook function without replacing it or its globals.

    The function must append exactly one record per call, including the actual
    finish_reason. Recreate this adapter if the notebook replaces GENERATION_LOG.
    """

    def generate(messages: list[dict[str, object]], max_new_tokens: int) -> GenerationReply:
        before = len(generation_log)
        text = generate_reply(messages, max_new_tokens=max_new_tokens)
        if len(generation_log) != before + 1:
            raise ValueError("generate_reply must append one fresh GENERATION_LOG record")
        record = generation_log[-1]
        if "text" in record and record["text"] != text:
            raise ValueError("generation log text differs from returned answer")
        return GenerationReply(
            text=text,
            finish_reason=record.get("finish_reason", "unknown"),
            input_tokens=record.get("input_tokens"),
            output_tokens=record.get("output_tokens"),
            peak_gpu_gib=record.get("peak_gpu_gib"),
        )

    return generate
