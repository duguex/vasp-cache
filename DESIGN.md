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

## 功能清单

### 对外 API

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `put(dir)` | 计算目录路径 | `None` | 解析 OUTCAR/CONTCAR/INCAR/KPOINTS，写入 meta.json + blobs.json |
| `get(formula, key)` | formula 字符串 + content_hash 或 task_name | `dict \| None` | 返回合并了 meta + blob 的完整记录，或 None |
| `lookup(dir)` | 计算目录路径 | `dict \| None` | 自动检测 formula + content_hash，调用 `get` |
| `query(formula, functional, calc_type, tags_contains, bandgap_min, lattice_max, converged_only, limit)` | 过滤条件 | `list[dict]` | 语义搜索，支持 MongoDB 风格过滤 |
| `restore(dir)` | 计算目录路径 | `bool` | 从缓存恢复 OUTCAR/CONTCAR/vasprun.xml 到磁盘 |
| `list_entries(limit)` | 最大条数 | `list[dict]` | 按缓存时间倒序返回最近条目 |
| `stats()` | 无 | `dict` | 总条目数、收敛条目数、唯一 formula 数、formula 列表 |

### 内部函数

| 函数 | 用途 |
|------|------|
| `_parse_vasp_dir(dir)` | 解析 VASP 目录（TaskDoc 优先，regex 回退） |
| `_build_blob(dir)` | 构造 big blob 数据（outcar_dict, vasprun_dict, structure_dict） |
| `_detect_calc_info(dir)` | 检测 formula / content_hash / task_name |
| `_content_hash(dir)` | 计算输入指纹（结构 + KPOINTS + INCAR + POTCAR） |
| `_incar_fingerprint(dir)` | INCAR 指纹（ENCUT, PREC, ISMEAR, ...） |
| `_potcar_fingerprint(dir)` | POTCAR 指纹 |
| `_extract_tags(incar, kpoints, structure, sga)` | 从输入文件提取标签 |
| `_tags_from_doc(doc)` | 从 TaskDoc 提取标签 |
| `_sanitize_value(v)` | 递归转换非 JSON 类型为可序列化类型 |
| `_sanitize_dict(d)` | 应用 `_sanitize_value` 到整个字典 |
| `_get_stores()` | 返回 (meta_store, blob_store) 单例，double-checked locking |
| `override_cache_root(path)` | 测试用——切换缓存根目录 |
| `migrate_from_sqlite()` | 从旧版 SQLite cache.db 迁移到 JSONStore |

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
