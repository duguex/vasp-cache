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

- **OUTCAR 正常结束且可入库**的计算会 `put` 成功（不等同于电子或离子收敛）。
- 缺少 OUTCAR 正常结束标记 → 跳过；读取或解析异常会报错，由调用方处理。
- 超大晶胞（`max_abc > 25` Å，可配）→ 跳过。
- **不存 POTCAR**；默认身份使用 POSCAR，不依赖 POTCAR 文件（mapping gen 5）。
- 主身份是 **POSCAR + KPOINTS + 归一化输入 protocol + hard INCAR**；CONTCAR 是输出，可附带 `result_geom_hash`，不是主身份。
- 同一 `content_hash` 默认 `strict`：OUTCAR 字节不一致会在 CAS 写入前抛出 `CacheConflictError`；相同字节幂等。

## 日常命令

```bash
export VASP_CACHE_ROOT=/mnt/shared/vasp_cache   # 若环境未指默认根
# 单目录入库；strict 是默认冲突策略
vasp-cache put /path/to/complete_calc --provenance canonical --on-conflict strict
vasp-cache put /path/to/complete_calc --on-conflict skip
vasp-cache put /path/to/complete_calc --on-conflict overwrite

# 批量扫树（所有 OUTCAR 父目录）
vasp-cache put -r /path/to/project_tree --provenance sampled --on-conflict strict
# 是否命中 / 恢复标准输出（仅 exact identity 命中）
vasp-cache has   /path/to/inputs
vasp-cache fetch /path/to/inputs

 # 按化学式检索；默认只返回 canonical
vasp-cache query --formula SiC
vasp-cache query -f ZnO -n 10
vasp-cache query --functional PBE --limit 20
vasp-cache query -f GaN --provenance sampled --json
vasp-cache query -f GaN --provenance all --json

vasp-cache content-hash /path/to/inputs
vasp-cache mapping show
```

## 只读检查（inspect）

`inspect` 是只读的可观测性界面：从 SQLite 读取元数据、从 CAS 读取存储
信息，但不会创建、改写或删除缓存状态。可用以下命令同时查看逻辑条目和
物理对象：

```bash
vasp-cache inspect overview --top-formulas 20
vasp-cache inspect health [--scan-cas] [--max-objects N] [--json]
vasp-cache inspect summary
vasp-cache inspect entries --formula GaN --provenance all --limit 50
vasp-cache inspect entries --jsonl --limit 1000
vasp-cache inspect entry 5:...
vasp-cache inspect objects --orphans-only
```

这里的命令边界很重要：`overview` = 快速的 SQLite 聚合视图；它展示条目数、
化学式数、能量和收敛覆盖率、provenance、identity generation、最常见化学式
以及时间/能量范围，明确不扫描 CAS，并返回 `storage_scan: false`。`health` =
只读的元数据质量报告；默认只读 SQLite，只有明确传入 `--scan-cas` 才扫描物理
CAS。`summary` = 较慢的完整存储汇总，会扫描 metadata 引用和物理 CAS 对象并
计算存储量。GC/repair（清理、修复）尚未实现。
为了避免把不同层次的结果混为一谈：

```text
overview = fast SQLite aggregates
health = read-only metadata quality report; CAS scan only with --scan-cas
summary = slower full storage summary
GC/repair = not implemented
```

`health` 的能量上下界选项只产生供人工复核的 flags，**不是**对科学有效性、
收敛性或结果正确性的判断，也不会重标记、删除或改写条目。CAS 扫描会逐个在
stderr 报告进度；对大型共享缓存可用 `--max-objects N` 做有界扫描。达到上限
时，物理对象/字节仍是已扫描部分，但需要完整物理扫描才能和 metadata 引用
核对的字段（例如 `referenced_*`、missing/orphan totals）会报告为 `null`，
不可当作全库精确总数。`report_timestamp` 是本次运行的 UTC 报告版本时间，
用于比较报告运行，不表示缓存内容的修改时间或内容差异。

`entries` 列出筛选后的元数据；`entry` 展示完整条目，并为每个逻辑输出列出
CAS digest、大小、是否存在及 CAS 相对路径，从而透明显示元数据到 CAS 对象的
对应关系。`objects` 展示物理 CAS 对象及其元数据引用。`--orphans-only` 只报告
未被引用的对象，不会删除任何对象。

所有 `inspect` 命令只负责观测：不会修复缺失对象、执行自动 GC 或修改缓存。
现有 `status` 仍是快速统计/预览；需要全库上下文时优先使用 `inspect overview`，
需要完整存储汇总时使用 `inspect summary`，需要元数据质量或显式 CAS 扫描时使用
`inspect health`。


## Read-only Materials Atlas dashboard

启动只读 dashboard：

```bash
vasp-cache web [--root DIR] [--host HOST] [--port PORT]
```

默认使用 `VASP_CACHE_ROOT`（或现有默认缓存根），监听 `localhost:8765`，只
提供固定静态资源和只读元数据 API，且不提供身份认证。若明确使用
`--host 0.0.0.0` 等 localhost 之外的地址，CLI 会打印警告；只有在确实需要
局域网访问时才应这样配置，因为只读 dashboard 将可被局域网客户端访问。

`fetch` 只恢复 `OUTCAR`、`CONTCAR`、`vasprun.xml` 等标准输出，不会自动
生成新的 `INCAR`、`KPOINTS` 或 `POTCAR`。相关计算需要工作流自行定位或
重建起始结构和输入。

Python：

```python
from vasp_cache import put, has, fetch, query, stats

put("/path/to/calc", provenance="canonical")
has("/path/to/inputs")
fetch("/path/to/inputs")
query(formula="SiC", limit=20)
stats()
```

## 应用场景与边界

- **已支持：**相同输入 identity 的计算只运行一次，后续通过 `has/fetch`
  复用标准输出。
- **规划/部分支持：**相关计算可参考已有条目的结构和元数据，但当前没有
  公开的按 `content_hash` 导出启动结构/目录的接口；改变 INCAR 或 KPOINTS
  后不会自动命中原 cache。
- 随机、无 provenance 的扰动单点不作为 canonical 材料结果。

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

改 mapping 身份后先盘点，再显式应用无冲突迁移：

```bash
python scripts/rehash_meta_cas.py --root /mnt/shared/vasp_cache
python scripts/rehash_meta_cas.py --root /mnt/shared/vasp_cache --apply
```

备份整库：`vasp-cache export-archive backup.tgz`

## vasp-sop

`vasp_sop.core.cache` 薄封装本库的 `put` / `has` / `fetch`。  
结果缓存请指向同一 `VASP_CACHE_ROOT`（共享 CAS）。  
MP 下载缓存、jobs.db 仍在 `~/.vasp_sop/`，与结果库分离。

详见 [IDENTITY.md](./IDENTITY.md)。gen 5 硬键含 **POSCAR geometry、KPOINTS、归一化输入 protocol、选定 INCAR**；CONTCAR 不是主身份。

## 非目标

作业调度、形成能分析、自动造 VASP 输入、结构相似度搜索（未产品化）。



## 日志（诊断，被动写文件）

**不用你手动开。** 一用库/CLI 就会写到：

```text
$VASP_CACHE_ROOT/logs/vasp_cache.log
```

默认生产路径：`/mnt/shared/vasp_cache/logs/vasp_cache.log`  
覆盖：`export VASP_CACHE_LOG_FILE=/path/to.log`

- 文件：INFO 及以上（put skip/ok、has/fetch、异常）
- 终端：默认几乎安静；`-v` / `-vv` 只影响终端详细程度
- 轮转：约 20MB × 5

```bash
tail -f /mnt/shared/vasp_cache/logs/vasp_cache.log
vasp-cache -v put /path    # 同时在终端看 INFO
```
