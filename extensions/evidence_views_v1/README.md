# 独立输入表示试验 evidence-views-1.0

本目录是可删除、显式启用的扩展。**不修改原始数据、现有证据包、旧 notebook、旧 API、根目录配置或实验选择规则。** 不下载数据，不调用 LLM，不安装或升级依赖。

## 生成什么

从已有 `input-package-1.0` 证据包读取 catalogue.json、image_local.tif、image_context.tif、dem_local.tif，核对原包全部文件的校验值后输出：

- 原目录记录的逐字节副本（不修改字段、不重新解释未知代码）。
- 两张光学图：局部和区域背景，统一画布、坐标标注和 0–255 显示范围。
- 数值 DEM 的逐字节副本（不是重新下载或重新提取）。
- 一张数值高程图，注明剖面位置。
- 固定东西／南北剖面，各有全量 CSV 和 PNG；由已有 DEM 计算，不改旧东西向 CSV。
- 全量 terrain_summary.json：整个裁剪区域的统计量、坐标、单位、缩放信息、全量剖面。
- terrain.txt：模型可见的统计量和每方向默认 17 个等索引抽样数值；不保证保留局部极值。缺失值为 null，不跨缺口插值。
- manifest.json：来源／产物 SHA-256、设置、扩展代码哈希及依赖版本；最后写入，代表生成完成。

偶数行／列采用中心两条线的均值，要求两个样本均有效；奇数尺寸采用中心线。南北剖面按由南至北排序。剖面是栅格中心横截面，不是经专家描绘的坑缘／坑底测量；统计范围不是坑深。横轴相对于源投影的目录中心。显示不消除源配准误差。仍只有三个科学模态，图表数量不增加模态数量。

## 在项目根目录运行

沿用现有 Python 3.12+ 环境，需要 pydantic、numpy、rasterio、matplotlib。启动器仅修改当前进程的导入路径，不修改安装环境。

```powershell
.venv/Scripts/python.exe extensions/evidence_views_v1/run.py build `
  --source experiments/benchmarks/mercury-screened-v2-20260907/crater-16604 `
  --output experiments/benchmarks/mercury-screened-v2-20260907/representation_trials/evidence-views-v1/crater-16604
```

输出目录必须不存在。没有 `--overwrite`。失败可能留下没有 manifest.json 的不完整新目录；它不会被适配器接受。重试请用一个新输出目录，旧目录可手动检查后删除。

```powershell
.venv/Scripts/python.exe extensions/evidence_views_v1/run.py preview `
  --package experiments/benchmarks/mercury-screened-v2-20260907/representation_trials/evidence-views-v1/crater-16604 `
  --question "How could we investigate terrain asymmetry?" `
  --selected TOPOGRAPHY
```

`preview` 仅打印模型输入，不生成答案。NO_DATA 用空选择；目录输出文本，光学输出两张图，地形输出数值摘要和三张图。全部模态共五张图，**不能承诺原 15 GB GPU 设置仍可运行**。试验时先单独测试资源，并使用新 RUN_ID；不要与旧预览实验混合比较。

## Colab：只在新的试验单元中接入

上传整个新输出目录和这个扩展目录，保留已有仓库。下列路径按实际上传位置调整：

```python
import sys
from pathlib import Path

REPO = Path("/content/autonomous-modality-selection")
sys.path.insert(0, str(REPO / "extensions/evidence_views_v1/src"))
sys.path.insert(0, str(REPO / "src"))
from ams_evidence_views.adapter import build_content

TRIAL_PACKAGE = Path("/content/evidence-views-v1/crater-16604")
trial_content = build_content(TRIAL_PACKAGE, question, selected)
trial_messages = [{"role": "user", "content": trial_content}]
# 显式交给自己的图文推理函数；保留所有 image 块。
# 不覆盖 generate_reply、select_inputs、answer_question 等原函数。
```

不要让旧的 PREVIEWS 字典把五张图重新压成一张或丢弃背景／剖面。目录和 TIFF/CSV 仍是不同表示：适配器向模型提供数值文本和图像，**不会赋予模型直接操作 GeoTIFF/CSV 的能力**。原有选模预算、成本、四组条件均不在这里更改。全文／数值内容按 selected 白名单输出，不把原包的人工审核或 selector rationale 注入模型。

## 测试与回退

```powershell
.venv/Scripts/python.exe -m pytest extensions/evidence_views_v1/tests
.venv/Scripts/python.exe -m ruff check extensions/evidence_views_v1
.venv/Scripts/python.exe -m ruff format --check extensions/evidence_views_v1
```

默认旧 `pytest` 的 testpaths 仍只运行旧 tests；扩展测试需显式指定。临时目录无权限时可将 pytest 的 `--basetemp` 指向本扩展 `_checks` 下一个新子目录，并用 `-o cache_dir=extensions/evidence_views_v1/_checks/cache`；先创建 `_checks` 父目录。

回退只需停止新的试验进程／Colab 单元，删除 `extensions/evidence_views_v1/` 和本次新增 `representation_trials/evidence-views-v1/`。原代码没有反向依赖这些目录，旧证据和旧运行入口保持原样。无需 Git reset、重下数据或覆盖旧文件。历史依赖环境的既有问题不属于本扩展的兼容性保证。
