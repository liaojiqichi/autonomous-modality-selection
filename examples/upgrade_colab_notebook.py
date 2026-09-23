"""Create a clean five-condition notebook from the user's AP development notebook.

This transforms code only, strips all outputs/credentials metadata, and never
executes the input notebook. The original notebook and scientific data are untouched.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import textwrap
from pathlib import Path
from typing import Any


def replace_once(source: str, old: str, new: str) -> str:
    """Fail on an unexpected notebook version instead of partially migrating it."""
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one migration anchor: {old[:100]!r}")
    return source.replace(old, new, 1)


GIT_SETUP = """import subprocess
from pathlib import Path

PROJECT = Path("/content/autonomous-modality-selection")
if (PROJECT / ".git").is_dir():
    dirty = subprocess.check_output(
        ["git", "-C", str(PROJECT), "status", "--porcelain"], text=True
    ).strip()
    if dirty:
        raise RuntimeError("Colab 仓库有未提交改动，请先保存；本单元不会覆盖。")
    subprocess.run(["git", "-C", str(PROJECT), "fetch", "origin"], check=True)
    subprocess.run(
        ["git", "-C", str(PROJECT), "merge", "--ff-only", "origin/main"], check=True
    )
elif PROJECT.exists():
    raise RuntimeError(f"目录已存在且不是 Git 仓库，请先检查：{PROJECT}")
else:
    # 私有仓库：先完成 Git 认证。不要把访问令牌写进 URL 或 notebook。
    subprocess.run([
        "git", "clone", "https://github.com/liaojiqichi/autonomous-modality-selection.git",
        str(PROJECT),
    ], check=True)
print("当前提交:", subprocess.check_output(
    ["git", "-C", str(PROJECT), "rev-parse", "HEAD"], text=True
).strip())
"""


BRIDGE = '''from autonomous_modality.iterative import (
    ContentBlock, EvidenceObservation, IterativePolicy, IterativeSelection,
    run_iterative_selection,
)
from autonomous_modality.iterative_colab import notebook_generator
from autonomous_modality.models import (
    CraterQuestion, CraterReference, DataAssetProfile, InputDataModality,
    InputSelectionConstraints, InputSelectionRequest,
)

ITERATIVE_POLICY = IterativePolicy(
    cost_unit="legacy_ordinal_units",
    cost_definition="Development pilot: catalogue=1, optical=2, topography=2; complete packages.",
    selector_max_new_tokens=ITERATIVE_SELECTOR_TOKENS,
)
PINNED_RECEIPT_SHA256 = sha256(receipt_path)


def build_evidence_content(selected: list[str]) -> list[dict]:
    """Reuse the original routing, removing only the shared answer instruction prefix."""
    question = "Evidence routing placeholder"
    prefix = (
        ANSWER_POLICY + f"\\nTarget: {CASE_NAME}\\nQuestion:\\n{question}\\nRequirements:\\n"
        + "\\n\\n"
    )
    content = copy.deepcopy(build_answer_messages(question, [], selected)[0]["content"])
    if content[-1]["type"] != "text" or not content[-1]["text"].startswith(prefix):
        raise ValueError("Answer routing changed; verify evidence-only extraction.")
    content[-1]["text"] = content[-1]["text"][len(prefix):]
    return content


def load_notebook_evidence(modality: InputDataModality) -> EvidenceObservation:
    """Return actual receipt-verified input bytes through the original notebook routing."""
    if sha256(receipt_path) != PINNED_RECEIPT_SHA256:
        raise ValueError("Input receipt changed during acquisition.")
    for name, digest in receipt.output_sha256.items():
        if sha256(VIEW_DIR / name) != digest:
            raise ValueError(f"Input view changed: {name}")
    if sha256(SOURCES["catalogue.json"]) != SOURCE_HASHES["catalogue.json"]:
        raise ValueError("Catalogue changed during acquisition.")
    actual_catalogue = CatalogueRow.model_validate_json(
        SOURCES["catalogue.json"].read_text(encoding="utf-8")
    )
    if json.dumps(actual_catalogue.model_dump(), ensure_ascii=False) != CATALOGUE_TEXT:
        raise ValueError("In-memory catalogue differs from pinned input.")
    if (VIEW_DIR / "terrain.txt").read_text(encoding="utf-8") != TERRAIN_TEXT:
        raise ValueError("In-memory terrain differs from pinned input.")
    files_by_modality = {
        "CRATER_CATALOG": {"catalogue.json": SOURCE_HASHES["catalogue.json"]},
        "OPTICAL_IMAGE": {
            name: receipt.output_sha256[name]
            for name in ("optical_local.png", "optical_context.png")
        },
        "TOPOGRAPHY": {
            name: receipt.output_sha256[name]
            for name in ("elevation.png", "profile_east.png", "profile_north.png", "terrain.txt")
        },
    }
    return EvidenceObservation(
        modality=modality,
        blocks=[ContentBlock.model_validate(b) for b in build_evidence_content([modality.value])],
        evidence_sha256=files_by_modality[modality.value],
        package_sha256=PINNED_RECEIPT_SHA256,
    )


def select_inputs_iterative(question: str, question_id: str) -> IterativeSelection:
    """A separate entry point; the original select_inputs function remains unchanged."""
    spec = next(q for q in QUESTIONS if q["question_id"] == question_id)
    request = InputSelectionRequest(
        question=CraterQuestion(
            question_id=f"{CASE_ID}-{question_id}", text=question,
            question_type=spec["question_type"],
            crater=CraterReference(
                crater_id=CASE_ID, name=CASE_NAME,
                latitude=catalogue.lat_n, longitude=catalogue.lon_e_0,
            ),
        ),
        assets=[DataAssetProfile(
            asset_id=name, modality=name, title=name,
            estimated_cost=asset["cost"], limitations=[asset["description"]],
        ) for name, asset in sorted(ASSETS.items())],
        constraints=InputSelectionConstraints(
            maximum_modalities=MAX_MODALITIES, maximum_total_cost=BUDGET,
        ),
    )
    return run_iterative_selection(
        request, ITERATIVE_POLICY, notebook_generator(generate_reply, GENERATION_LOG),
        load_notebook_evidence, model_id=MODEL_NAME, execution_kind="model",
    )


# Routing checks only: no model call. The final answer still uses answer_question
# for ALL five conditions, preserving the exact input ordering and answer prompt.
for modality, images in [("CRATER_CATALOG", 0), ("OPTICAL_IMAGE", 2), ("TOPOGRAPHY", 3)]:
    observation = load_notebook_evidence(InputDataModality(modality))
    assert sum(b.type == "image" for b in observation.blocks) == images
    assert all(ANSWER_POLICY not in (b.text or "") for b in observation.blocks)
print("两步选择接口就绪；真实输入路由已校验，未调用模型。")
'''


def migrate_cells(original: dict[str, Any]) -> list[dict[str, Any]]:
    """Migrate the checked AP notebook while retaining its working generation interface."""
    sources = {
        index: "".join(cell["source"])
        for index, cell in enumerate(original["cells"])
        if cell["cell_type"] == "code"
    }
    required = {
        13: "ViewReceipt",
        14: "use_model_defaults=False",
        15: "class AgentChoice",
        16: "def build_answer_messages",
        17: '"colab-ap-development-2"',
    }
    for index, anchor in required.items():
        if anchor not in sources.get(index, ""):
            raise ValueError(f"Unsupported notebook: missing anchor in cell {index}")
    setup = replace_once(sources[13], 'RUN_LABEL = "emin-ap-002"', 'RUN_LABEL = "emin-agentic-001"')
    setup = replace_once(
        setup,
        'RECORD_VERSION = "colab-ap-development-2"',
        'RECORD_VERSION = "colab-ap-agentic-development-3"\nITERATIVE_SELECTOR_TOKENS = 512',
    )
    setup = replace_once(
        setup,
        '"thinking": "disabled",',
        '"thinking": "disabled", "cost_unit": "legacy_ordinal_units",\n'
        '    "iterative_selector_tokens": ITERATIVE_SELECTOR_TOKENS,',
    )
    setup = replace_once(
        setup,
        'print("每个模型：4 个问题 × (1 + 1 + 5 + 1) = 32 条记录；不是正式测试结果。")',
        'print("每个模型：4 个问题 × (1 + 1 + 5 + 1 + 1) = 36 条开发记录。")',
    )

    runner = sources[17].replace('"colab-ap-development-2"', '"colab-ap-agentic-development-3"')
    runner = runner.replace(
        '"NO_DATA", "ALL_AVAILABLE", "RANDOM", "AGENT"',
        '"NO_DATA", "ALL_AVAILABLE", "RANDOM", "AGENT", "AGENT_ITERATIVE"',
    )
    runner = replace_once(
        runner,
        "    selection_rationale: str\n",
        "    selection_rationale: str\n    iterative_selection: IterativeSelection | None = None\n",
    )
    runner = replace_once(
        runner,
        'self.condition in {"RANDOM", "AGENT"}',
        'self.condition in {"RANDOM", "AGENT", "AGENT_ITERATIVE"}',
    )
    runner = replace_once(
        runner,
        'self.condition != "NO_DATA" and not self.selected',
        'self.condition not in {"NO_DATA", "AGENT_ITERATIVE"} and not self.selected',
    )
    runner = replace_once(
        runner,
        "        return self\n",
        """        if self.condition == "AGENT_ITERATIVE":
            if self.status != "error" and self.iterative_selection is None:
                raise ValueError("Missing iterative acquisition trace.")
            if self.iterative_selection is not None:
                trace = self.iterative_selection
                if sorted(m.value for m in trace.accessed_modalities) != self.selected:
                    raise ValueError("Iterative access history differs from selected evidence.")
                if trace.cumulative_cost != self.input_cost:
                    raise ValueError("Iterative cumulative cost mismatch.")
                if self.status != "error" and trace.status != "ready":
                    raise ValueError("Cannot answer after failed acquisition.")
        elif self.iterative_selection is not None:
            raise ValueError("Iterative trace on another condition.")
        return self
""",
    )
    runner = replace_once(
        runner,
        "    build_answer_messages, answer_question, Attempt.check_record,",
        "    build_answer_messages, answer_question, Attempt.check_record,\n"
        "    build_evidence_content, load_notebook_evidence, select_inputs_iterative,",
    )
    runner = replace_once(
        runner,
        '"schemas": {cls.__name__:',
        '"iterative_policy": ITERATIVE_POLICY.model_dump(mode="json"),\n'
        '    "condition_roles": {"AGENT": "one_shot_ablation", "AGENT_ITERATIVE": "primary_agent"},\n'
        '    "schemas": {cls.__name__:',
    )
    runner = replace_once(
        runner,
        "(GenerationTrace, AgentChoice, Attempt, ViewReceipt)",
        "(GenerationTrace, AgentChoice, Attempt, ViewReceipt, IterativeSelection)",
    )
    runner = replace_once(
        runner,
        '    "options": OPTIONS,\n    "random_choices":',
        '    "options": OPTIONS,\n    "iterative_policy": ITERATIVE_POLICY.model_dump(mode="json"),\n'
        '    "conditions": CONDITIONS,\n    "random_choices":',
    )
    runner = replace_once(
        runner,
        '    "selector_tokens": SELECTOR_TOKENS, "max_input_tokens": MAX_INPUT_TOKENS,',
        '    "selector_tokens": SELECTOR_TOKENS, "max_input_tokens": MAX_INPUT_TOKENS,\n'
        '    "iterative_selector_tokens": ITERATIVE_SELECTOR_TOKENS,',
    )
    runner = replace_once(
        runner,
        '            selected, rationale = [], ""\n',
        '            selected, rationale = [], ""\n            iterative_selection = None\n',
    )
    runner = replace_once(
        runner,
        """                selected, rationale = select_inputs(
                    condition, question, question_id, draw_index=draw_index
                )""",
        """                if condition == "AGENT_ITERATIVE":
                    iterative_selection = select_inputs_iterative(question, question_id)
                    selected = sorted(m.value for m in iterative_selection.accessed_modalities)
                    rationale = " | ".join(
                        t.action.reason for t in iterative_selection.turns if t.action is not None
                    )
                    if iterative_selection.status != "ready":
                        raise ValueError(
                            f"{iterative_selection.stop_reason}: {iterative_selection.error}"
                        )
                else:
                    selected, rationale = select_inputs(
                        condition, question, question_id, draw_index=draw_index
                    )""",
    )
    runner = replace_once(
        runner,
        "                selected=selected, selection_rationale=rationale,",
        "                selected=selected, selection_rationale=rationale,\n"
        "                iterative_selection=iterative_selection,",
    )
    # Recheck observation hashes and in-memory representations immediately before
    # the shared answer function re-reads the acquired files.
    runner = replace_once(
        runner,
        '                answer = answer_question(question, spec["answer_requirements"], selected)',
        """                if iterative_selection is not None:
                    for turn in iterative_selection.turns:
                        if turn.observation is not None:
                            current = load_notebook_evidence(turn.observation.modality)
                            if current != turn.observation:
                                raise ValueError("Acquired evidence changed before answering.")
                answer = answer_question(question, spec["answer_requirements"], selected)""",
    )

    model_cell = (
        'if "model" in globals():\n'
        '    if str(globals()["model"].config._name_or_path) != "Qwen/Qwen3-VL-8B-Instruct" or "processor" not in globals():\n'
        '        raise RuntimeError("已有模型与 Qwen3-VL-8B 不一致，请使用新的运行时。")\n'
        '    print("复用已加载的 Qwen3-VL-8B；不重复分配显存。")\n'
        "else:\n" + textwrap.indent(sources[8], "    ")
    )
    cells: list[dict[str, Any]] = []

    def add(kind: str, source: str) -> None:
        cell: dict[str, Any] = {
            "cell_type": kind,
            "metadata": {},
            "source": source.splitlines(True),
        }
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
            if not source.lstrip().startswith(("%", "!")):
                ast.parse(source)
        cells.append(cell)

    add(
        "markdown",
        """# Bounded agent experiment — existing Colab data

五组开发实验：NO_DATA / ALL_AVAILABLE / RANDOM（5 次）/ AGENT（一次性消融）/
AGENT_ITERATIVE（两步获取）。每模型、每陨石坑四问题共 **36** 条记录。
原 notebook 保留；这个副本没有历史输出或密钥。开发成本仍为 1/2/2 抽象单位，
不是 token 成本。大栅格只读；本 notebook 不下载科学数据，不重新运行 pilot。

1. 先完成私有仓库 Git 授权，再更新代码。若此运行时已导入旧项目模块，重启后运行。
2. 已有正确模型时跳过依赖安装与模型加载；全新运行时按顺序执行。
3. 在「实验配置」修改 CASE_DIR、RESULTS_ROOT、RUN_LABEL；默认 Eminescu 路径沿用旧本。
4. 新 RUN_LABEL 只生成小型视图；旧 TIFF 与实验结果不改动。
5. 两步选择第二次请求后由系统停止；显式 FINISH 与系统停止分别保存。
6. 只比较本轮匹配运行的结果。失败和截断均保留；这不是正式 held-out 实验。
""",
    )
    add("markdown", "## 1. 更新项目与检查（无需重下载数据）")
    for source in [sources[0], GIT_SETUP, sources[2], sources[3], sources[6]]:
        add("code", source)
    add("markdown", "## 2. 模型环境\n已加载并可运行时跳过安装；安装后如有提示请重启运行时。")
    add("code", sources[7])
    add("code", model_cell)
    add("markdown", "## 3. 实验配置与小型输入视图\n先修改路径和新 RUN_LABEL；旧源数据只读。")
    add("code", setup)
    add("markdown", "## 4. 推理统计、旧选择接口与统一回答接口")
    for index in (14, 15, 16):
        add("code", sources[index])
    add("markdown", "## 5. 两步 agent 与 receipt 输入包兼容层\n此单元仅定义接口和校验输入。")
    add("code", BRIDGE)
    add("markdown", "## 6. 执行五组实验\n此单元开始 GPU 推理；原 AGENT 保留为消融。")
    add("code", runner)
    add("markdown", "## 7. 汇总与导出\n没有 A/P 标注前，生成成功不代表丰富度提升。")
    add("code", replace_once(sources[18], '"/ 32"', '"/ 36"'))
    add("code", sources[21])
    return cells


def main() -> None:
    """Export a sanitized new notebook; never overwrite either input or prior output."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = json.loads(args.source.read_text(encoding="utf-8"))
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
            "language_info": {"name": "python"},
            "colab": {"provenance": [], "gpuType": "T4"},
            "accelerator": "GPU",
            "source_notebook_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        },
        "cells": migrate_cells(original),
    }
    for index, cell in enumerate(notebook["cells"]):
        cell["id"] = f"agentic-{index:02d}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(notebook, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    print(f"Created {args.output}; source unchanged; outputs removed.")


if __name__ == "__main__":
    main()
