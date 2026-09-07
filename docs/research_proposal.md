# An AI Agent for Autonomous Input Modality Selection in Scientific Problem Solving: A Case Study of Planetary Crater Questions

# 面向科学问题求解的自主输入模态选择 AI 智能体：以行星陨石坑问题为例

Proposal version: proposal-1.2, 2026-09-07. Supersedes proposal-1.1.

Student: Gefei Wang  
Responsible Person: Prof. Dr. Renato Pajarola (Visualization and Multimedia Lab, IfI)  
Co-Supervisors: Dr. Jason Armitage (Department of Computational Linguistics), Xiao Tan (Visualization and Multimedia Lab, IfI)

## 1. Project overview / 项目概述

This thesis designs and evaluates an AI agent that selects scientific input modalities according to a question, available assets and resource constraints. The primary outcome is solution richness: more analytical approaches, more explanatory perspectives and more cross-modal insights. Planetary crater questions, primarily concerning Mercury, provide the case study. Broader applicability remains a design aim, not a demonstrated result.

本论文设计并评估一个根据科学问题、可用数据资产和资源约束选择输入模态的 AI 智能体。主要结果是解决方案丰富度：更多分析方法、更多解释视角、更多跨模态洞见。以水星为主的行星陨石坑问题提供案例。研究主线是 AI 方法；跨领域适用性是设计目标，不预先声称得到验证。

## 2. Motivation and objectives / 动机与目标

Images, catalogs, topography, literature and simulations provide different information. Supplying all inputs may introduce redundancy and consume context. The agent will identify feasible inputs, select complementary modalities and explain its expected contributions. A separate generator will receive selected evidence to produce a solution. Output presentation is outside the selection task.

影像、目录、地形、文献和模拟提供不同信息，全部提供可能产生冗余并占用上下文。智能体识别可行输入、选择互补模态并解释预期贡献；独立生成器依据选中证据生成解答。选择对象为科学输入，而非答案展示形式。

## 3. Research questions and hypothesis / 研究问题与假设

Main question: How can an AI agent autonomously select scientific input data modalities that lead to richer solutions for scientific questions?

主要问题：AI 智能体如何自主选择科学输入模态，从而为科学问题产生更丰富的解决方案？

1. How do selections affect analytical approach diversity? / 选择如何影响分析方法多样性？
2. How do selections affect explanatory perspectives? / 选择如何影响解释视角？
3. Which combinations support cross-modal insights? / 哪些组合支持跨模态洞见？
4. How does agent selection compare with no data, all available and random selection? / 智能体与无数据、全部模态和随机选择相比表现如何？
5. How do question types and budgets affect these differences? / 问题类型和预算如何影响差异？

Hypothesis: task-relevant, complementary selection may improve one or more richness dimensions. This is to be tested, not guaranteed. No improvement, trade-offs or stronger simple baselines are valid results.

待检验假设：与任务相关且互补的选择可能提高一个或多个丰富度维度。没有提升、维度间存在取舍或简单基线更好，均可形成有效论文结果。

## 4. Scope and taxonomy / 范围与分类

The closed initial taxonomy comprises OPTICAL_IMAGE, CRATER_CATALOG, TOPOGRAPHY, SCIENTIFIC_LITERATURE and SIMULATION_OUTPUT. Experiments use the actually available subset and report missing modalities. Scientific modality, asset and model representation remain distinct: a DEM map and profile are two representations of one modality.

初始封闭分类为光学影像、陨石坑目录、地形、文献和模拟输出。实验使用实际可用子集并报告缺失。科学模态、资产和模型表示分别建模；同一 DEM 的地图和剖面不算两种模态。完整模拟档案不是毕业必要条件。

Questions address analysis methods, morphology, terrain relationships and alternative explanations. Caloris quantitative inversion, impact parameter estimation, gravity/crustal joint inversion and acceptable-model-set reduction are excluded from deliverables. Existing related materials remain historical archives only.

问题围绕分析方法、形态、地形关系和竞争解释。删除 Caloris 定量反演、撞击参数估计、重力／地壳联合反演和可接受模型集合缩减等交付要求。相关既有资料仅作历史归档。

## 5. Data and preparation / 数据与准备

Candidate sources are the Mercury crater catalog, MESSENGER MDIS imagery, available topography, relevant literature and accessible simulations. Adapters preserve provenance, units, coordinates, preprocessing and checksums. Local crops, catalog subsets and profiles bound input size. Integrity checks and preliminary visual screening do not replace expert review.

候选来源为水星目录、MDIS 影像、可用地形、相关文献和可获取的模拟。保留来源、单位、坐标、处理过程和校验值；以局部裁剪、目录子集与剖面限制输入规模。完整性检查及初步视觉筛查不替代专家审核。合成数据只用于离线软件测试。

## 6. Framework / 框架

Question modeling → asset registry → deterministic feasibility checks → agent selection → selected-evidence preparation → multimodal generation → evaluation. Hard constraints are enforced outside prompts. Selection rationales predict opportunities; they are not measured answer richness.

问题建模 → 资产登记 → 确定性检查 → 智能体选择 → 选中证据准备 → 多模态生成 → 评价。硬约束在提示之外执行。选择理由描述预期机会，不作为解答丰富度实测结果。

A replaceable model adapter, potentially Qwen3-VL or a comparable model, will follow agreement on the model phase and budget. Version prompts and models; record errors, retries and fallbacks. Offline preparation marks agent conditions pending. Rules cannot impersonate agent decisions.

确认模型阶段与预算后接入可替换模型接口，候选可为 Qwen3-VL 或相近模型。版本化提示与模型，记录错误、重试和回退。离线阶段 agent 组标记待接入，不用规则结果冒充 agent。

## 7. Primary comparisons / 四组主对照

| Condition / 条件 | Definition / 定义 |
| --- | --- |
| No data / 无额外数据 | Question and common target context only / 仅问题与共同目标上下文 |
| All available / 全部可用模态 | All permitted, verified available modalities / 全部允许且确认可用的模态 |
| Random / 随机选择 | Seeded uniform sampling over nonempty feasible subsets / 按种子均匀抽取非空可行子集 |
| Agent / 智能体选择 | Question-driven selection under the same constraints as random / 与随机组相同约束下的问题驱动选择 |

Random and agent share budgets, cost definitions and modality limits. All-available is a non-budget-matched reference with separate costs; no-data intentionally contains no selectable evidence. Required-input constraints apply to data conditions, not the no-data control. Question intent does not force specific modality pairs in the primary comparisons; missing evidence may be acknowledged.

随机与 agent 共享预算、成本定义和数量上限。全部模态为非等预算参照，单列成本；无数据组有意不提供可选证据。必需输入约束用于数据组，不用于无数据对照。主对照不因问题类型强制指定某一模态对，允许说明缺失证据。规则与固定影像＋地形只作辅助分析。

All groups share questions, generator version, answer prompt, decoding and output-length policy. Freeze representation and compression policies; do not silently truncate. Selector scores, full inventory and rationales are withheld from the generator. Diameter and classification remain selectable evidence.

各组统一问题、解答模型、提示、生成参数与长度政策。固定表示与压缩政策，不静默截断。解答模型不接收选择器分数、完整目录或理由。直径与分类保留在可选证据中。

## 8. Richness and quality / 丰富度与质量

Report analytical approaches, explanatory perspectives and cross-modal insights separately. Executable proposed analyses may contribute without completed numerical results. Preserve proposals, hypotheses and observed results as distinct statuses. Annotation handles synonymous duplicates.

分别报告分析方法、解释视角、跨模态洞见。可执行分析建议无需已完成数值计算即可贡献丰富度，须区分建议、假说和观测结果。标注处理同义重复。

Cross-modal levels are juxtaposition, correspondence and synthesis, provisionally weighted 0, 1, 2. CMI = correspondence count + 2 × synthesis count. Validate this project convention in a rubric pilot. Distinguish proposed cross-modal investigations from relationships derived from supplied evidence.

跨模态分并置、对应和综合，初步权重 0、1、2；CMI = 对应数 + 2 × 综合数。该约定须经试标审核。另行标记建议的跨模态研究与依据实际输入建立的关系。

Scientific validity and evidence fidelity are independent checks. They must not silently replace primary richness with the number of correct, supported answers. Report contradictions, unsupported assertions and evidence misuse alongside richness.

科学有效性与证据忠实度独立报告，不作为隐含权重或过滤条件把主要终点改成正确且有证据的答案数。单列矛盾、无依据断言和证据误用，并与丰富度共同解释。

## 9. Annotation and statistics / 标注与统计

Pilot with relevant experts, blind annotators to selection methods and rationales, retain separate annotations and report agreement. Repeat generations, split development/test by target, and analyze paired differences with target grouping. Report effects and uncertainty. Small samples support exploratory conclusions; repeated questions are not independent crater samples. Automated annotation requires validation against human judgments.

邀请专家试标，对条件和选择理由盲评，分别保存标注并报告一致性。重复生成、按目标划分开发／测试，以目标分组分析配对差异。报告效应与不确定性；小样本作探索性结论，同一坑的多问题不当作独立样本。自动标注需与人工判断验证。

## 10. Risks and reproducibility / 风险与可复现性

Risks include limited modalities, metadata bias, shared sources, representation effects, verbosity, superficial multimodality and model dependence. Standardize preprocessing and prompts, review annotations and limit claims to tested cases. Use Python 3.12+, src layout, Pydantic, offline tests and versioned artifacts. Keep credentials outside the repository and raw sources read-only.

风险包括模态有限、元数据偏差、同源相关性、表示差异、冗长、表面多模态和模型依赖。固定处理与提示、审核标注并限定结论范围。采用 Python 3.12+、src、Pydantic、离线测试和版本化档案。不保存凭据，不改写原始来源，无需开发大型物理求解器。

## 11. Timeline / 时间计划

| Deadline / 截止日期 | Deliverable / 交付 |
| --- | --- |
| Sep 20, 2026 | Scope, data and rubric preparation / 范围、数据与量表准备 |
| Oct 20, 2026 | Agent framework and four-condition pilot / 智能体框架与四组试验 |
| Nov 20, 2026 | Main evaluation and annotations / 主实验与标注 |
| Dec 15, 2026 | First thesis draft / 初稿 |
| Jan 10, 2027 | Revisions / 修改 |
| Jan 20, 2027 | Final submission / 最终提交 |

## 12. Deliverables / 交付成果

Versioned taxonomy and schemas; AI selector; four primary comparisons; reproducible evidence preparation and generation; reviewed richness rubric; annotated results; thesis. Auxiliary rules and historical packages may remain. Completion requires actual generated answers and evaluation, not preparation records alone. Negative results are valid; no Caloris inversion or new physical mechanism is required.

交付分类与 Schema、AI 选择器、四组主对照、可复现证据准备与生成、审核后的丰富度规范、标注结果和论文。保留辅助规则与历史输入包。完成标准包括实际解答和评价，不以准备记录代替结果。负结果有效，不要求 Caloris 反演或新的物理机制。
