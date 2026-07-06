# vasp-cache 设计文档

## 背景

vasp-cache 从 vasp-sop 项目中拆分而来。vasp-sop 是一个 VASP 点缺陷计算自动化管线，其 `vasp_sop/core/cache.py` 模块负责：

- 存储 VASP 计算结果的元数据和解析数据
- 提供语义查询
- 跟踪作业提交状态

经过多轮重构后，提交跟踪部分（submissions.db）仍与管线强耦合，但元数据存储和查询部分是**完全通用**的——任何做 VASP 计算的工具都可以使用。

## 数据模型

### meta.json（maggma JSONStore）

每条记录是一个 VASP 计算目录：

```
{
  "formula": "GaN",            // 化学式
  "content_hash": "...",       // 输入指纹（结构 + KPOINTS + INCAR + POTCAR）
  "task_name": "GaN_mp-804",  // 任务标识
  "cached_at": 1234567890,    // 缓存时间戳
  "total_energy": -12.345,    // 总能（eV）
  "bandgap": 3.4,             // 带隙（eV）
  "converged": 1,             // 是否收敛
  "calc_type": "Static",      // 计算类型
  "nsites": 128,              // 原子数
  "formula_pretty": "GaN",    // 友好化学式
  "space_group": "P6_3mc",    // 空间群
  "a": 3.19, "b": 3.19, "c": 5.19,  // 晶格常数
  "max_abc": 5.19,            // 最大晶格矢量
  "tags": "PBE,DFT+U,HSE",   // 标签
  "source_dir": "/path/to/calc",  // 原始目录
  "parsed_by": "TaskDoc",     // 解析器
}
```

key = (formula, content_hash) — 输入指纹保证了相同计算不会重复缓存。

### blobs.json（备选，见 #91 问题）

存储完整的 OUTCAR 字典、vasprun 字典、Structure 对象，用于文件恢复。

## 接口

### CLI

```
vasp-cache put <dir>             缓存一个计算目录
vasp-cache put -r <root>         递归缓存所有收敛目录
vasp-cache query --formula GaN   按条件查询
vasp-cache status                聚合统计
vasp-cache restore <dir>         从缓存恢复 OUTCAR
```

### Python API

```python
from vasp_cache import (
    put,              # 写入缓存
    get,              # 按 formula + key 查
    lookup,           # 按路径查
    query,            # 语义查询
    restore,          # 恢复文件
    stats,            # 统计
    list_entries,     # 列举
)
```

## 从 vasp-sop 迁移策略

1. 将 `vasp_sop/core/cache.py` 中通用函数复制到 vasp-cache：
   - `vasp_results_put` → `put`
   - `vasp_results_get` → `get`
   - `cache_lookup` → `lookup`
   - `query` → `query`
   - `restore_from_cache` → `restore`
   - `list_cache` → `list_entries`
   - `cache_stats` → `stats`
   - 内部函数：`_parse_vasp_dir`, `_build_blob`, `_detect_calc_info`, `_content_hash` 等
   - 常量：`MAX_LATTICE`, `lattice_too_large`

2. vasp-sop 改为依赖 vasp-cache：
   - 删除 `vasp_sop/core/cache.py` 中移动的函数
   - 保留 `submissions.db` 相关函数（`mark_submitted`, `is_submitted`, `clear_submission`, `_get_submitted_dirs`）
   - 导入 `from vasp_cache import lookup as cache_lookup` 等

3. 修 #91（停止写无用 blob）在步骤 1 中做

### 数据流

```
                    put(dir)
                        │
                        ▼
              ┌─────────────────┐
              │  _detect_calc_info │── formula, content_hash, task_name
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  _parse_vasp_dir  │── dict{converged, total_energy, ...}
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐    converged?    ┌──────────────┐
              │  _build_blob      │──────────────▶  │ blobs.json   │
              └────────┬────────┘                   └──────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │ meta.json        │
              │ (JSONStore)       │
              └─────────────────┘

                    query(...)
                        │
                        ▼
              ┌─────────────────┐
              │ meta_store.query  │── list[dict]
              │ (MongoDB syntax) │
              └─────────────────┘
```

## 两个操作

vasp-cache 提供两个核心操作：

### 1. 入库（ingest）

把 VASP 计算结果存入缓存。

```
输入:  VASP 计算目录
      /path/to/calc/
      ├── OUTCAR     计算结果
      ├── CONTCAR    最终结构
      ├── vasprun.xml (可选) 详细输出
      ├── INCAR      输入参数
      ├── KPOINTS    k 点设置
      └── POTCAR     赝势

处理:  解析 OUTCAR → 提取总能/带隙/力/结构
      计算输入指纹（content_hash）
      写入 meta.json + blobs.json

输出:  无（数据已存入缓存）
```

### 2. 查询（query）

从缓存中检索已有的计算结果。

```
输入:  搜索条件
      - formula（必需或可选，视查询类型而定）
      - content_hash 或 task_name（精确匹配）
      - functional、calc_type、tags（语义过滤）
      - bandgap_min、lattice_max（范围过滤）

处理:  meta_store.query() → MongoDB 风格过滤

输出:  结构化计算结果
      - 总能、带隙、原子数、空间群
      - 晶格常数、计算类型、标签
      - 原始目录路径（source_dir）
      - 可选的完整 OUTCAR/CONTCAR 文件恢复
```

### 数据流

```
    入库                         查询
                                
  VASP 计算目录 ──→ vasp-cache ──→ 结构化数据
  (OUTCAR+输入)      │             (总能、带隙、tags...)
                     │ 恢复
                     ▼
                OUTCAR/CONTCAR
                （写回磁盘）
```


## 与下游工具的关系

vasp-cache 不直接调用下游工具，但它的设计受下游工具的需求驱动。

### pydefect（缺陷分析）

pydefect 的 CLI（`pydefect_vasp cr`、`pydefect_vasp pbes` 等）从磁盘读取 OUTCAR 文件。这意味着：

- vasp-cache 的 `restore` 功能存在的直接原因：把缓存的 OUTCAR 写回磁盘，让 pydefect CLI 能读到
- 如果 pydefect 提供 Python API 可以直接接收 `outcar_dict`，则 vasp-cache 可以直接提供解析后的数据，跳过磁盘读写

### vasp-sop（管线）

vasp-sop 是 vasp-cache 的第一个也是当前最主要的消费者。它使用缓存做两件事：

- **提交去重**：查缓存 → 算过就不提交 VASP
- **文件恢复**：缓存有但磁盘无 → restore → 继续后处理

### 其他潜在消费者

任何需要 VASP 计算结果的工具都可以成为消费者：

- 机器学习力场训练脚本（批量查询总能和结构）
- 热力学数据库构建工具（按 formula 聚合总能）
- 高-throughput 筛选工具（按 bandgap 范围过滤候选材料）

### 设计原则

vasp-cache 对下游做**零假设**——不要求下游用特定版本、特定框架、甚至不要求下游用 Python。只要下游能读 JSON 或读文件，就能消费 vasp-cache 的数据。
