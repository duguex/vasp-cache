# vasp-cache 使用说明（一页）

目标：**同一套 VASP 输入只算一次**；之后 `has` / `fetch` 复用，或按化学式等查元数据。

## 安装与默认路径

```bash
pip install -e ~/vasp_cache
# 可选：pip install -e ~/vasp_sop   # 管线通过 adapter 调本库
```

| 项 | 值 |
|----|-----|
| 默认缓存根 | **`/mnt/shared/vasp_cache`** |
| 覆盖 | `export VASP_CACHE_ROOT=/path` 或 `override_cache_root(path)` |
| 后端 | CAS（`cas/`）+ SQLite（`meta.sqlite`） |

```bash
vasp-cache status
```

## 入库规则（重要）

- **仅收敛**计算会 `put` 成功（OUTCAR 需完整结束标记）。
- 未收敛 → 跳过（不入库）。
- 超大晶胞（`max_abc > 25` Å，可配）→ 跳过。
- **不存 POTCAR**；身份默认也不依赖 POTCAR 文件（mapping gen 4）。
- 同一 `content_hash` 再 `put` → **覆盖元数据**，CAS 按内容去重（不会变成两条逻辑结果）。

## 日常命令

```bash
export VASP_CACHE_ROOT=/mnt/shared/vasp_cache   # 若环境未指默认根

# 单目录入库
vasp-cache put /path/to/complete_calc

# 批量扫树（所有 OUTCAR 父目录）
vasp-cache put -r /path/to/project_tree

# 是否命中 / 恢复 OUTCAR·CONTCAR
vasp-cache has   /path/to/inputs
vasp-cache fetch /path/to/inputs

# 按化学式检索（exact match，默认只要收敛）
vasp-cache query --formula SiC
vasp-cache query -f ZnO -n 10
vasp-cache query --functional PBE --limit 20
vasp-cache query -f GaN --json          # 全字段 JSON

vasp-cache content-hash /path/to/inputs
vasp-cache mapping show
```

Python：

```python
from vasp_cache import put, has, fetch, query, stats

put("/path/to/calc")
has("/path/to/inputs")
fetch("/path/to/inputs")
query(formula="SiC", limit=20)
stats()
```

## 增量添加

直接再 `put` / `put -r` 即可，**不必**整库重迁。

大批量树（日志 + 统计）可用：

```bash
python scripts/reingest_tree.py /path/to/tree \
  --cache-root /mnt/shared/vasp_cache \
  --log /tmp/vasp_cache_reingest.log
```

（同输入重复 `put` 不会多出第二条结果；只会重做入库计算。续跑若要省时间可用脚本的 `--skip-existing`，非必须。）

## 从旧 signac 迁到 CAS（一次性）

```bash
python scripts/migrate_signac_to_cas.py \
  --src ~/.vasp_cache \
  --dest /mnt/shared/vasp_cache
```

改 mapping 身份后重算主键：

```bash
python scripts/rehash_meta_cas.py --root /mnt/shared/vasp_cache
```

备份整库：`vasp-cache export-archive backup.tgz`

## vasp-sop

`vasp_sop.core.cache` 薄封装本库的 `put` / `has` / `fetch`。  
结果缓存请指向同一 `VASP_CACHE_ROOT`（共享 CAS）。  
MP 下载缓存、jobs.db 仍在 `~/.vasp_sop/`，与结果库分离。

## 身份（摘要）

详见 [IDENTITY.md](./IDENTITY.md)。硬键含结构 geom_hash、KPOINTS、选定 INCAR；**不含** POTCAR；generation 前缀 `4:`。

## 非目标

作业调度、形成能分析、自动造 VASP 输入、结构相似度搜索（未产品化）。

## 日志（诊断 + 审计）

两路：

| 通道 | 作用 | 如何开 |
|------|------|--------|
| stderr logging | 诊断（skip 原因等） | `vasp-cache -v`（INFO）/ `-vv`（DEBUG）；或 `VASP_CACHE_LOG_LEVEL=DEBUG` |
| JSONL audit | 可审计操作轨迹 | 默认 `$VASP_CACHE_ROOT/logs/audit.jsonl`；`--audit-log PATH`；`VASP_CACHE_AUDIT_LOG=`；`VASP_CACHE_AUDIT=0` 关闭 |

事件示例：`put_ok` / `put_skip` / `has_hit` / `has_miss` / `fetch_ok` / `fetch_miss`。

每行字段含：`ts`, `ts_iso`, `event`, `host`, `pid`, `user`, `dir`, `content_hash`, `reason`, …

```bash
vasp-cache -v put /path/to/calc
vasp-cache --audit-log /tmp/vc-audit.jsonl put -r /tree
tail -f /mnt/shared/vasp_cache/logs/audit.jsonl
```
