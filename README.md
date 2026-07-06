# vasp-cache

VASP 计算结果缓存——持久化存储、语义查询、跨项目复用。

## 目标

**让每一个 VASP 计算结果只解析一次，之后任意查询、任意恢复。**

具体来说：

1. **消除重复解析**——同一计算被不同项目或工具重复解析 OUTCAR 是常态（不同课题组各自解析同一批数据、同一管线多次重入重新解析）。vasp-cache 存解析结果，从此只需一次。

2. **跨项目复用**——一个项目的 VASP 计算结果对另一个项目有参考价值（GaN 的能带隙、SiC 的晶格常数……）。传统做法是每个项目各自维护 OUTCAR 目录，无法搜索。vasp-cache 提供统一的查询入口。

3. **工具链解耦**——vasp-sop 管线需要缓存来做提交去重和文件恢复，但缓存本身不依赖管线逻辑。任何 Python 工具或 CLI 都可以独立使用 vasp-cache 来存取 VASP 数据。

## 非目标

- 不做作业调度
- 不做形成能分析
- 不做 VASP 输入生成
- 不做计算队列管理## 核心能力

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
| **[vasp-wiki](https://github.com/duguex/vasp_incar)** | VASP 知识库——INCAR 参数、输入文件模板、常见问题排错、DFT 工具集 |。vasp-sop 是 VASP 点缺陷计算管线，vasp-cache 是其缓存层的独立版本 |
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
