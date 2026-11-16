# 设备量测资格（Gauge R&R）测试证据

批次 `grr-7702`，对应需求：设备量测资格试验、重复性/再现性/交互分解、缺测与负分量口径、隔离放行与并发取样。

## 运行方式

```bash
cd backend
python -m pytest tests/ -v        # 16 项，SQLite 临时库 + 假 Redis，无需 docker
```

测试通过注入 `redis` 假模块与临时 SQLite 库运行，不依赖 Postgres/Redis 服务；覆盖统计口径（`tests/test_grr_stats.py`）与完整业务事务（`tests/test_gauge_api.py`）。

## 覆盖矩阵

| 需求点 | 用例 |
|---|---|
| 平衡设计平方和守恒、负分量保留与零截断、零均方 F 记 null | `test_balanced_closed_form_and_negative_component` |
| 缺测 null 登记、Type III 偏平方和、调和均值除数、自由度修正 | `test_missing_readings_kept_as_null_and_type_iii` |
| 完整数据下闭式解与 effects 编码 OLS Type III 引擎逐项一致 | `test_balanced_and_type_iii_engines_agree_on_complete_design` |
| 空格拒绝（不插补） | `test_empty_cell_is_rejected_not_imputed` |
| 标准件×操作员交互变异独立分解 | `test_interaction_effect_isolated` |
| 可配阈值判定（%GRR / NDC / 缺测比例） | `test_threshold_qualification_and_missing_limit`、`test_threshold_validation` |
| 重复性零方差明确失败 | `test_repeatability_zero_variance_fails` |
| 建试验→重测暂停→录数→发布全生命周期与角色权限 | `test_device_permissions_and_study_lifecycle` |
| 隔离留存、达标放行、重试不重复放行（release_ledger 唯一约束） | `test_quarantine_release_and_no_duplicate_release` |
| 发布失败样本继续隔离、恢复后新建重测达标放行 | `test_publish_failure_keeps_hold_and_recovery_publishes` |
| 重测期间照常收样但暂缓入评议、快照按同一资格状态取样 | `test_requalifying_samples_held_from_assessment_snapshot` |
| 资格切换后已有评议快照依据保留 | `test_existing_assessments_keep_basis_after_qualification_change` |
| 读数矩阵坐标/重复/完整性校验 | `test_reading_matrix_validation` |
| 隔离期不进评议、放行后新评议才纳入的时间线 | `test_sample_enters_assessment_only_after_release` |
| worker 重启恢复 running 任务 | `test_worker_resume_interrupted_study` |

## 手工核对口径（2×2×2 玩具数据）

数据 P1/O1=[10,12]、P1/O2=[14,16]、P2/O1=[20,22]、P2/O2=[24,26]：

- SS：标准件 200、操作员 32、交互 0、重复 8、合计 240（守恒）。
- 方差分量：零件 50、操作员 8、交互 **−1（负值保留）**、重复 2；GR&R 截断后 10、总变异 60。
- 交互均方为 0 时标准件/操作员 F 记 `null`，不输出无穷值。

最近一次运行结果见 `pytest-result.txt`（16 passed）。
