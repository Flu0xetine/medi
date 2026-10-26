# D1 前置复发判定设计

状态：已确认（用户于 2026-10-25 要求实施）。

## 目标与边界

新增原始布尔事实 `hypotension_recurred_after_recovery`，表示低血压恢复后是否再次发生。其 `true`、`false`、未提及的提取说明按用户本次提供的文字登记。未提及时默认值为 `null`，保留真假两种可能；已知值不能被默认值覆盖。

保留当前 D1 候选条件（低血压短暂或满足现有 `hypotension_recovered` 定义）及旧字段提示词。仅当已进入 D1 候选路径时，新事实为 `true` 改判 D0，为 `false` 保持 D1；未提及时同时保留 D0、D1。原本进入 D0 的路径不受影响。D0 固定 `has_r=false`，D1 继续按 D-R 判定。其他等级和分支不变。

`recurrent_or_persistent_hypotension` 仍只负责 `H=true, L=true` 的 E1/D2 分支；新字段不复用或替代它。

## 同步范围

注册表、严格输入 Schema、规则引擎、网页字段配置、提取与规则规范、README 字段数、回归测试一起更新。公开结果结构保持不变，输入 JSON 增加一项必备事实对象。
