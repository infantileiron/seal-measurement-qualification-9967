ROLES=('admin','analyst','viewer')
TASK_STATUS=('queued','running','completed','failed')
# 设备量测资格状态：未获资格 / 已发布合格 / 重测暂停中
DEVICE_STATUS=('unqualified','qualified','requalifying')
DEVICE_STATUS_LABELS={'unqualified':'未获资格','qualified':'资格有效','requalifying':'重测暂停'}
# 生产样本处置去向：正常（无设备）/ 隔离留存 / 已放行
DISPOSITION=('normal','quarantined','released')
DISPOSITION_LABELS={'normal':'正常','quarantined':'隔离留存','released':'已放行'}
# GRR 判定默认阈值（AIAG MSA 口径，建试验时可覆盖）
DEFAULT_GRR_PERCENT_MAX=10.0
DEFAULT_NDC_MIN=5
DEFAULT_MAX_MISSING_RATIO=0.1
