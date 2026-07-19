# vasp-cache 设计 v3

**Date:** 2026-07-19
**Status:** ✅ 全部完成 (9/9). 25 tests + 3 CLI 消费者 + extraction 对照 pymatgen.
---

## 1. Identity

### 1.1 构成

identity_key = SHA256(canonical_json({formula, incar, kpoints, potcar, lattice}))

| Layer | 来源 | 内容 | 状态 |
|-------|------|------|------|
| formula | POSCAR | `Structure.from_file().composition.reduced_formula` | ✅ |
| incar | INCAR | `Incar.from_file()` → dict → JSON | ✅ |
| kpoints | KPOINTS | `Kpoints.from_file()` → as_dict → JSON | ✅ |
| potcar | POTCAR | species tokens + XC + versions → JSON | ✅ |
| lattice | POSCAR | {a, b, c, alpha, beta, gamma}, tolerance: a/b/c 0.01 Å, α/β/γ 0.1° | ✅ |

基矢置换: 枚举 6 种 (a,b,c) 排列, 从 lattice matrix 重新计算对应的 (α,β,γ), 选 lexicographically 最小的六元组.

### 1.2 碰撞处理

同 key 再次 put:
- |energy_diff| < 1e-4 eV + n_sites 相同 → skip
- 任一不同 → 按代表选择规则判定:

**D: 收敛优先 + 确定性 tie-break**

```
1. 收敛的 > 不收敛的
2. 都收敛（或不收敛）→ 按 rebuild root 的相对路径排序, 选第一个
3. 已有代表不被覆盖
```

被跳过的候选不写入 entry, 记录到独立审计表 `discarded_candidates`.

---

## 2. Admission gate

POSCAR, INCAR, KPOINTS, POTCAR, OUTCAR, CONTCAR, vasprun.xml 全部存在 → 入库。缺任一 → 跳过。

---

## 3. 文件处理：混合策略

**约束：验收针对未修改的 pydefect/vasp-sop/crisp CLI。**
下游通过文件路径消费 (`Outcar(path)`, `Vasprun(path)`, `Structure.from_file(path)`,
`check_converged(dir)`, 内联 regex) — 不可注入 facade 或 DTO。

**决策：可结构化输入用 JSON，POTCAR 和输出文件存压缩 BLOB。**

| 文件 | 存储方式 | 备注 |
|------|---------|------|
| POSCAR | `structure_json` TEXT | identity 层，语义重建 |
| INCAR | `incar_json` TEXT | identity 层，语义重建 |
| KPOINTS | `kpoints_json` TEXT | identity 层，语义重建 |
| POTCAR | `potcar_json` TEXT | identity 用 `species + XC + version`. fetch 写 TITEL stub（非实际 POTCAR） |
| OUTCAR | `outcar_blob` BLOB (zlib) | vasp-sop/crisp regex + pydefect `Outcar()` |
| vasprun.xml | `vasprun_blob` BLOB (zlib) | pydefect `Vasprun(parse_potcar_file=False)` |
| CONTCAR | `contcar_blob` BLOB (zlib) | pydefect `Structure.from_file("CONTCAR")` |

**BLOB 文件（OUTCAR, vasprun, CONTCAR）为原始字节恢复；**
**JSON 文件（POSCAR, INCAR, KPOINTS）为语义恢复，不保留注释/空白。POTCAR 写 TITEL stub。**
**结构化提取**（独立列，只用于查询，不用于重建文件）：

| 列 | 来源 | pydefect 消费者 |
|----|------|----------------|
| `final_energy` REAL | OUTCAR/vasprun | `make_composition_energies`, `make_calc_results_from_vasp` |
| `total_mag` REAL | OUTCAR | `make_calc_results_from_vasp` |
| `electrostatic_potentials` TEXT (JSON array) | OUTCAR | `make_calc_results_from_vasp` |
| `final_structure_json` TEXT | vasprun.final_structure | `make_calc_results_from_vasp` |
| `converged_ionic` INTEGER | vasprun | `make_calc_results_from_vasp` |
| `converged_electronic` INTEGER | vasprun | `make_calc_results_from_vasp` |
| `n_ionic_steps` INTEGER | vasprun | 查询辅助 |

提取失败不会拒绝 admission — extraction 是 best-effort；BLOB 始终是权威来源。

### 3.1 为什么不是结构化 + facade

pymatgen `Outcar("rebuilt_OUTCAR")` 构造需要 NBANDS/NPLWV/… 等内部字段，
重建兼容文件需要仿造 VASP 输出格式的全部细节，成本高且 pymatgen 版本变化随时打破。

pydefect CLI 的 `argparse type=Outcar` 直接构造 `Outcar(path)`，
无法注入 facade 对象。vasp-sop `check_converged(dir)` 内联 regex
扫描 OUTCAR 文件，必须写出物理文件。

BLOB 是唯一满足"不改下游 CLI 代码"的技术路径。

### 3.2 为什么不是 pickle

`pickle.dumps(Outcar(...))` ~15 MB，`pickle.dumps(Vasprun(...))` ~40 MB。
1000 个计算 = 55 GB。SQLite 单行 BLOB 可支持但体积大。
且下游 CLI 不懂 pickle — 需额外 loader 层，收益低于 BLOB。

---

## 4. Schema

```sql
CREATE TABLE entries (
    identity_key TEXT PRIMARY KEY,
    formula TEXT NOT NULL,
    incar_json TEXT NOT NULL,
    structure_json TEXT NOT NULL,
    kpoints_json TEXT NOT NULL,
    potcar_json TEXT NOT NULL,
    lattice_json TEXT NOT NULL,
    -- output extracts (queryable, NOT authoritative)
    final_energy REAL,
    total_mag REAL,
    electrostatic_potentials TEXT,
    final_structure_json TEXT,
    n_ionic_steps INTEGER,
    converged_ionic INTEGER,
    converged_electronic INTEGER,
    -- BLOBs (authoritative for file reconstruction)
    outcar_blob   BLOB NOT NULL,
    vasprun_blob  BLOB,
    contcar_blob  BLOB,
    -- metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_path TEXT
);

CREATE INDEX entries_formula ON entries(formula);
CREATE INDEX entries_energy ON entries(final_energy);
```

---

## 5. fetch 契约

`fetch(identity_key, dir)`:
1. 从 BLOB 解压写出 `dir/OUTCAR`, `dir/vasprun.xml`, `dir/CONTCAR`（字节等价）
2. 从结构化 JSON 语义重建 `dir/POSCAR`, `dir/INCAR`, `dir/KPOINTS`；`dir/POTCAR` 写 TITEL stub

验收标准: fetch 生成的目录 → `pydefect_vasp mce` 成功, `check_converged(dir)` True,
`crisp check_task_complete` True。

---

## 6. pydefect 属性审计（确定 extraction 字段）

来源: 离线审计 `/home/duguex/vasp_sop/libs/pydefect/pydefect/cli/vasp/`.

| 文件 | 函数 | 对象 | 属性 |
|------|------|------|------|
| make_calc_results.py | make_calc_results_from_vasp | outcar | .final_energy, .total_mag, .electrostatic_potential |
| make_calc_results.py | make_calc_results_from_vasp | vasprun | .final_structure, .converged_electronic, .converged_ionic |
| main_vasp_functions.py | make_composition_energies._inner | outcar | .final_energy |
| main_vasp_functions.py | make_unitcell | outcar | passed into VaspBandEdgeProperties (需要完整 Outcar) |
| main_vasp_util_functions.py | make_total_dos | vasprun | .complete_dos (densities, energies), .structures[0].volume |
| make_band_edge_orbital_infos.py | make_band_edge_orbital_infos | vasprun | .actual_kpoints, .eigenvalues, .final_structure, .efermi |

mce/cr 路径只需前 6 个字段。band/DOS (Phase 2) 需要完整 Vasprun BLOB。

---

## 7. vasp-sop 接口审计

vasp-sop `check_converged(dir)` 通过内联 regex 解析 `dir/OUTCAR`:
- 扫描 timing section (`"General timing and accounting"`) → true
- 扫描 TOTAL-FORCE 行确认迭代完成
- 不构造 pymatgen 对象
- => 只需要 OUTCAR BLOB write 到磁盘

---

## 8. C4/C5 状态更新

| ID | 阻塞项 | 旧设计 | 新决策 | 状态 |
|----|--------|-------|--------|------|
| C4 | OUTCAR schema | 结构化重建 | **BLOB + 提取列** | ✅ 决策完成 |
| C5 | vasprun AST | XML AST → JSON | **BLOB + 提取列** | ✅ 决策完成 |

---

## 9. 实施路线

| # | 任务 | 状态 |
|---|------|------|
| 1 | schema: identity 6 层 + extraction 列 + BLOB + audit 表 | ✅ |
| 2 | `put()`: identity → BLOBs + pymatgen extraction | ✅ |
| 3 | `fetch()`: BLOBs → files + JSON → POSCAR/INCAR/KPOINTS + POTCAR stub | ✅ |
| 4 | 压缩: zlib (level=6), ~92% 缩减 | ✅ |
| 5 | `rebuild()`: 批量导入 + 相对路径排序 + 原子替换 | ✅ |
| 6 | OUTCAR extraction: total_mag, electrostatic_potentials | ✅ |
| 7 | 碰撞处理: 收敛优先, 已有代表不被覆盖 | ✅ |
| 8 | `discarded_candidates` 审计表 | ✅ |
| 9 | CLI 消费者验收 (pydefect mce/cr, vasp-sop check, crisp) | ✅ |
