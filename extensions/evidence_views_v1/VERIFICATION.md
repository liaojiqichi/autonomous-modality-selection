# 隔离扩展验证记录

本轮只新增扩展和试验输出，不修改根项目配置、原模块、旧 notebook 或已提取证据。

## 已生成

推荐使用完整批次：

`experiments/benchmarks/mercury-screened-v2-20260907/representation_trials/evidence-views-v1/batch-01/`

| 目录 | 目标 |
| --- | --- |
| crater-16604 | Eminescu |
| crater-1851 | Giotto |
| crater-19610 | Scarlatti |
| crater-2179 | Thoreau |
| crater-4870 | Mofolo |
| crater-5031 | Nampeyo |
| crater-858 | Soseki |

每例 11 个输出文件加 manifest.json。`evidence-views-v1/crater-16604/` 为较早的单例冒烟检查，保留但建议后续使用 batch-01。所有源数据均来自既有证据包，没有重新下载。

## 检查结果

- 七例的 210 个原文件：批量生成前后 SHA-256 完全一致。
- 全部七个新包的模型验证、输出大小、SHA-256 和 PNG 解码通过。
- 七例的新旧东西向 CSV：尺寸一致，距离与高程逐元素比较通过（rtol=0，绝对容差 0.001；两列单位分别 km、m）。
- 全部模态内容路由均为五张图；单模态不会带入其他模态的图像或数值内容。
- Eminescu 五张图完成目视检查；这不是行星科学专家认证。
- 旧测试单独运行：139 passed。
- 扩展测试单独运行：17 passed。
- 联合运行：156 passed，150 条 Rasterio/Affine 弃用提示，无测试失败。
- `ruff check extensions/evidence_views_v1 src tests` 通过；同范围 `ruff format --check` 通过。
- 已运行要求的全库 `ruff check .` 和 `ruff format --check .`：唯一剩余问题是之前已存在的 `tmp/pdfs/proposal-20260914/check_proposal.py` 导入排序／格式。按不修改旧文件的要求未更改该文件，也未改根配置隐藏它。
- `git diff --stat` 为空：所有原有跟踪文件保持不变。原有 output/ 和 tmp/ 为本轮前已存在的未跟踪目录。

## 未执行与限制

没有调用 LLM、没有进行新答案实验或科学标注、没有验证 Colab 显存、没有提交或推送 GitHub。五图输入可能比旧双预览输入更耗显存；在新 notebook 单元和新 RUN_ID 中先测试。不会自动改变原有函数、预算或模态成本。

## 回退边界

停止试验进程后，可只删除 `extensions/evidence_views_v1/` 和 `representation_trials/evidence-views-v1/`。所有新增代码、测试、文档、检查临时文件及试验数据都位于这两处；不需要删除原始数据或重置 Git。根项目并不导入扩展。
