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

## 与 vasp-sop 的接口边界

vasp-sop 通过以下接口消费 vasp-cache，不直接访问内部存储：

```
vasp-sop 需要                    vasp-cache 提供
─────────────────────────────────────────────────
cache_lookup(dir)                lookup(dir) → dict | None
vasp_results_put(dir)            put(dir) → None
vasp_results_get(f, key)         get(formula, key) → dict | None
query(...)                       query(...) → list[dict]
restore_from_cache(dir)          restore(dir) → bool
list_cache(n)                    list_entries(n) → list[dict]
cache_stats()                    stats() → dict
```

vasp-sop 保留的部分（不迁移）：
- submissions.db（`mark_submitted` / `is_submitted` / `clear_submission` / `_get_submitted_dirs`）
- 这是管线调度逻辑，不属于通用缓存

## 从 vasp-sop 迁移策略（待执行）

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


## 去重机制：content_hash

vasp-cache 靠 **content_hash** 判断两个计算是否"相同"。

### 什么是 content_hash

content_hash 是 VASP 输入的一个紧凑指纹，由四部分拼接而成：

```
content_hash = structure_tag + "_" + kpoints_tag + "_" + incar_fp + "_" + potcar_fp
```

| 部分 | 来源 | 作用 |
|------|------|------|
| `structure_tag` | POSCAR/CONTCAR → pymatgen Structure | 区分不同结构 |
| `kpoints_tag` | KPOINTS 文件 | 区分 k 点网格 |
| `incar_fp` | INCAR 的关键参数（ENCUT、PREC、ISMEAR、SIGMA、ISIF、LDAU、GGA、LASPH、METAGGA） | 区分计算参数 |
| `potcar_fp` | POTCAR 的元素符号列表 | 区分赝势 |

### 什么算"相同计算"

两个计算的 content_hash 完全一致 → 被视为相同 → 后者直接从缓存返回结果，不提交 VASP。

这包含：

- **相同结构 + 相同参数** → 指纹一致 → 去重 ✅
- **相同结构、不同 k 点** → 指纹不同 → 独立计算 ✅
- **相同结构、不同 INCAR 参数** → 指纹不同 → 独立计算 ✅

### 缓存命中条件

```
cache_lookup(dir) → 检测 dir 的 content_hash → 查 meta.json
                     ├── 命中 → 返回缓存结果
                     └── 未命中 → 需要提交 VASP 计算
```

### 去重的实际效果

```
项目 A 算过 GaN（ENCUT=520, 4×4×4 k-points）
                ↓ content_hash = "GaN..._444_ENCUT=520..."
                ↓ meta.json 存了这条
项目 B 提交同样的结构 + 参数
                ↓ content_hash 相同
                ↓ 直接返回缓存结果，不提交 VASP
```

如果 INCAR 或 k 点有任何不同 → content_hash 不同 → 独立计算。


## 存储与生命周期

### 存储位置

默认路径：`~/.vasp_cache/`（通过 `override_cache_root` 可切换）。

```
~/.vasp_cache/
├── meta.json      # 轻量元数据（235 KB / 478 条）
├── blobs.json     # 大文件解析数据（213 MB / 同条目数）
└── cache.db       # （可选）旧版 SQLite 迁移源
```

meta vs blob 的体积差异源于存储内容：

| 文件 | 每条大小 | 内容 |
|------|---------|------|
| meta.json | ~500 B | formula、energy、bandgap、tags、source_dir…… |
| blobs.json | ~500 KB | outcar_dict、vasprun_dict、structure_dict（序列化 JSON）|

### 生命周期

**当前行为**：永久保留，不主动清理。

元数据（meta.json）体积可控——478 条收敛记录仅 235 KB，即使扩展到 10 万条也只需 ~50 MB。

blobs.json 是主要存储消耗——一条记录 ~500 KB。当前 #91 正在讨论是否继续写入 blobs.json（因为数据写入但从不读取）。如果去掉 blob 存储，缓存的总磁盘占用仅取决于 meta.json，非常轻量。

### 清理

目前没有内置过期或清理策略。缓存目录可以安全删除——vasp-cache 只是存储，不是唯一来源。删除后下次 `put` 会重建。

如果需要手动清理：
- 删除整个 `~/.vasp_cache/` 目录（最干净）
- 或只删 `blobs.json`（保留元数据，但 restore 的 structure_dict 回退路径失效）

### 并发

两个层面：

1. **同一进程内**：`_get_stores()` 使用 `threading.Lock` + double-checked locking，首次初始化后无锁竞争
2. **跨进程 / NFS**：JSONStore 底层基于文件操作，多个进程同时写入可能冲突。实际使用中（vasp-soc 的 ProcessPoolExecutor 之前曾并行写入），将写入操作设计为批量 + 增量模式，避免大量并发写入同一文件。

### 多用户共享

缓存在 `~/.vasp_cache/`，默认只对当前用户可见。如果需要共享（如课题组公共缓存）：

- 将 `CACHE_ROOT` 指向 NFS 共享目录
- 文件权限设为 664，确保同组用户可读写
- 并发写入风险同上（JSONStore 没有服务端锁）
