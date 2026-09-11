# 04_SOURCE_PIPELINE

## 输入

主要输入为用户已确认 Game / Version 下的 merged TXT。只支持 .txt（docx 支持已明确撤销）。

当前已实现的三个入口（均走统一匹配 _resolve_target：显式系列严格系列内匹配，
默认系列先找同名系列再全局主名/别名唯一命中，多命中报错不猜）：

- 拖放弹窗（drop-import-*.bat）：源文件不动，复制副本到 data/<env>/inbox/drop-import/
  按规范名存放，导入成功后副本自动清理；提交前弹"归档预告"（复用/新建/重复/冲突）。
- prepare / auto-import：inbox/auto/ 目录扫描。
- import-txt：显式指定 version_id 的全手动档。

## 处理链

Source → Normalize → Segment → Speaker / Content Classification → Episode。

## Normalize

- 检测编码（strict：utf-8 → gbk → gb18030）
- 生成 sha256（同 Version + 同 sha256 直接跳过，幂等去重）
- 保留原始换行与原文
- Raw 归档到 data/<env>/raw/<指纹前2位>/<指纹>.txt，永不覆盖
- 生成标准 UTF-8 派生文本
- Raw 不覆盖

## Segment

必须拥有稳定定位字段，例如 source_id + line range / ordinal。

## Speaker / Content

识别 author / teammate / NPC / UI / subtitle / game audio / unrelated chat / unknown。

## Episode

将连续证据组织成体验过程，例如困惑 → 尝试 → 失败 → 理解 → 爽点。

第一版不将 Moment 升级为正式表。
