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
- **不存 POTCAR**；身份默认也不依赖 POTCAR 文件（mapping gen 4）。
- 同一 `content_hash` 再 `put` 会按 provenance 权限合并：自动/`unknown` 不会降级显式角色；同级的不同非 `unknown` 显式角色会拒绝并保持原条目不变。

## 日常命令

```bash
export VASP_CACHE_ROOT=/mnt/shared/vasp_cache   # 若环境未指默认根
# 单目录入库；显式声明角色可覆盖自动分类
vasp-cache put /path/to/complete_calc --provenance canonical

# 批量扫树（所有 OUTCAR 父目录）
vasp-cache put -r /path/to/project_tree --provenance sampled

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
