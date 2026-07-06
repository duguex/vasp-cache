# vasp-cache

VASP 计算结果缓存——持久化存储、语义查询、跨项目复用。

## 目的

每个 VASP 计算产生大量数据：总能、能带隙、力、结构、DOS。传统做法是让这些数据散落在各个项目的 OUTCAR 文件里——按需重算、按需解析、用完即弃。

vasp-cache 把这些数据集中存储，让后续查询和复用成为可能。

## 意图

1. **写一次，查多次**——一个 VASP 计算完成后自动缓存，之后任意项目、任意工具可以直接按条件查询
2. **跨项目知识库**——不同项目（SiC 缺陷、GaN 掺杂...）的 VASP 结果存在同一个缓存里，避免重复计算
3. **语义查询**——不依赖文件路径，按 formula / functional / bandgap / tags 等条件搜索
4. **工具无关**——不绑定任何特定管线框架（vasp-sop、custodian、pydefect），任何 Python 脚本或 CLI 都可以消费

## 核心能力

| 能力 | 说明 |
|------|------|
| 写入 | 解析 VASP 输出目录，提取元数据和大 blob |
| 按路径查 | 给定计算目录，返回缓存条目 |
| 按条件查 | formula、functional、tags、bandgap 范围等 |
| 列举 | 最近条目、聚合统计 |
| 文件恢复 | 从缓存重建 OUTCAR/CONTCAR |

## 非目标

- 不做作业调度（那是 vasp-sop / crisp 的事）
- 不做形成能分析（那是 pydefect / vasp-sop analysis 的事）
- 不做 VASP 输入生成



## 参考

### 相关项目

| 项目 | 关系 |
|------|------|
| **[vasp-sop](https://github.com/duguex/pydefect-workflow-sop)** | vasp-cache 从中拆分而来。vasp-sop 是 VASP 点缺陷计算管线，vasp-cache 是其缓存层的独立版本 |
| **[pymatgen](https://github.com/materialsproject/pymatgen)** | 结构解析、OUTCAR/Vasprun 解析、Spacegroup 分析。vasp-cache 的核心下游依赖 |
| **[maggma](https://github.com/materialsproject/maggma)** | JSONStore 后端——提供 MongoDB 风格的本地文件数据库 |
| **[emmet](https://github.com/materialsproject/emmet)** | TaskDoc —— VASP 计算的结构化解析结果 |
| **[Materials Project](https://next-gen.materialsproject.org/)** | 材料数据库，提供参考能量和晶体结构 |

### 相关文档

- **maggma JSONStore 文档**：了解底层存储机制（https://maggma.readthedocs.io/）
- **pymatgen Outcar / Vasprun 解析**：了解写入缓存的数据格式
- **vasp-sop AGENTS.md**：了解 cache 模块的原始设计背景和集成方式

## 许可

MIT
