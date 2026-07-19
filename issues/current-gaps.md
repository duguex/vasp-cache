# vasp-cache 当前欠缺 (2026-07-19)

v3 核心架构健全。以下为仍存在的三类问题。

## 一、Identity 正确性：坐标噪声无容差

v3 对 `structure.as_dict()` 做全精度 SHA-256。同一计算 restart 后 POSCAR
坐标末位微扰 (0.25000000 → 0.25000001) 产生不同 identity key，导致缓存
miss。晶格层有容差 (0.01 A / 0.1 deg)，分数坐标没有。

设计意图：末位噪声视作同一计算 (exact reuse)。当前代码视作不同计算。

影响：缓存命中率。唯一影响正确性的 identity 缺口。

## 二、运维与工程化

### Schema 无版本管理

旧版 index.sqlite 遇 v0.3.0 代码抛 `no such column`。无检测、无迁移、
无清晰报错。workaround 只有删库重建。共享 NFS 缓存场景为部署阻塞。

### 大树 rebuild 无增量模式

全量扫描 O(n)，每目录 pymatgen 解析 4 文件。万级目录耗时显著。
ROADMAP 列为 "Later"，未实现。

### 批量 put 无快速路径

batch 循环中 identity 计算 (解析 POSCAR/INCAR/KPOINTS/POTCAR) 无法跳过，
即使目录已缓存。has() 短路 BLOB 压缩但不短路 identity 计算。

### 并发写入无调优

BEGIN IMMEDIATE 保证正确性，但未配置 busy_timeout / WAL。
多进程 batch 下写者串行，可能触发 SQLITE_BUSY。

## 三、质量保障

### POTCAR 解析无回归测试

TITEL 正则 (XC + element + date) 是 identity 六层之一，无边界测试
(缺失 date、非标准格式、多 TITEL 行)。

### vasp-sop 集成未做 full regression

INTEGRATION.md 为 v3 开发期间点验证，非完整套件回归。adapter 语义已变，
下游隐性破坏未知。

### 无 CI

27 个测试只能本地跑，无自动化门禁。
