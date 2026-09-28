# tech-skills

给 AI 编程助手用的技能（Skill）仓库，聚焦**技术调研**：拿到一个需求，去市面上找已有实现、读清它的实现逻辑、判断能不能复现与可行，最后产出两份 Markdown 文档。

## 包含的技能

| 技能 | 说明 |
| --- | --- |
| [`tech-research`](skills/tech-research/SKILL.md) | 前期技术实现调研：对着需求找开源方案，产出内部详细报告与对外汇报稿 |

## tech-research

一个甲方需求，常常只是三五句话。这个技能把它变成能落地的技术方案判断。

**输出两份文档**，是详略之分而非内容隔离：

- `report.md` —— 内部详细报告，带 `文件:行` 级证据，给自己和写代码的人看。
- `调研汇报.md` —— 可交付的调研汇报文档，给项目组内与领导看：项目间横向对比、各候选的优秀之处与缺点、值得借鉴的地方、整体设计、怎么实现。

**三个落点，顺序固定**：实现逻辑 → 可复现 → 可行。成本与工作量是判「可行」的要素之一，不单列成章。

**候选以开源项目为主**（GitHub 为主，Gitee 兜底）；商业 SDK 与官方产品只出现在兜底方案里。

### 工作流程

1. **需求解读** —— 把需求翻译成能回答「是/否」的能力清单，原文与解读分开写，歧义单独列出并标注是否影响选型。
2. **宽搜候选** —— 按能力搜 5–8 个候选，只收原始仓库，转存镜像仓排除在外。
3. **硬筛除 + 打分** —— 六维度打分排序，取 Top 2–3 进深挖。
4. **确认门** —— 停下，把能力清单、候选表、筛除记录、打分表落进报告，等用户点头再往下走。
5. **并行深挖** —— 每个候选派一个 subagent，按 `读 / 挖 / 跑` 三档取证，并发上限 4。
6. **写详细报告** —— 按模板逐节填 `report.md`，结论词与置信度从固定表里选。
7. **写汇报稿** —— 从 `report.md` 取事实，删到实现级为止，机制、数值、结论、风险、许可证义务全部保留。
8. **落盘** —— 两份文档 + 证据目录一并交付。

### 取证档位与置信度

| 档位 | 做什么 | 置信度 |
| --- | --- | --- |
| `读` | 仓库元数据、README、官方文档、依赖清单、许可证、活跃度 | 低 |
| `挖` | 浅克隆后读关键源码：入口、核心模块、配置与扩展点 | 中 |
| `跑` | 按官方路径本地实跑最小验证，或对核心链路做最小 PoC | 高 |

`挖` 是默认下限；`跑` 只在核心链路存在真实不确定性时开，且须经确认门批准。档位是上限，subagent 不得自行升级。

### 结论词

`可直接复现` / `需改造可复现` / `仅供参考不可直接复现` / `不建议`

## 安装

用 [skills CLI](https://github.com/vercel-labs/skills)：

```bash
npx skills add CoteNite/tech-skills
```

或手动复制到助手的技能目录：

```bash
git clone https://github.com/CoteNite/tech-skills.git
cp -r tech-skills/skills/tech-research ~/.claude/skills/     # Claude Code 全局
# 或复制到项目的 .claude/skills/ 下按项目生效
```

`tech-research` 是**手动调用**的技能（`disable-model-invocation: true`）：它流程长、要跑确认门、会派 subagent、要实跑构建，不适合被助手自动触发。直接点名调用即可——「用 tech-research 调研一下……」

## 依赖

- **Python 3.8+**，只用标准库。`scripts/repo_probe.py` 采集候选仓库的元数据、目录树、许可证、依赖清单与活跃度。
- **可选 `gh` CLI** —— 已鉴权时 GitHub 侧走 `gh`，API 额度更高、搜索更稳。没有也能跑，只是会更快触发限流。

```bash
python skills/tech-research/scripts/repo_probe.py search 'mqtt broker'
python skills/tech-research/scripts/repo_probe.py ./evidence github:owner/name --clone
```

脚本只做取证，不做判断；证据落盘后由技能里的分析步骤下结论。

## 目录结构

```
skills/
└── tech-research/
    ├── SKILL.md                # 技能主体：步骤、判定标准、纪律
    ├── DIG-BRIEF.md            # 深挖 subagent 的 brief 模板、候选卡契约、三档命令清单
    ├── REPORT-TEMPLATE.md      # 内部详细报告骨架
    ├── BRIEFING-TEMPLATE.md    # 可交付汇报文档骨架（含删减边界）
    ├── agents/openai.yaml      # 界面元数据
    └── scripts/repo_probe.py   # 候选仓库元数据采集
```

## 设计取舍

- **报告是唯一事实来源。** 确认门的成果、深挖的结论都落盘，不在对话里口头交代；中断时 `report.md` 的状态栏就是交接点。
- **不升格置信度。** 只读文档得出的判断就是低置信度，读了两篇博客也不例外；实跑过才算高。
- **镜像仓不进矩阵。** `gitee.com/mirrors/*` 这类转存快照元数据大面积失真，只用于确认国内可达性。
- **两份文档详略不同、事实同源。** 汇报稿可以且应该与报告重复，但不新增报告里没有依据的判断。
