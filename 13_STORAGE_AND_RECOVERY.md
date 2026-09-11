# 13_STORAGE_AND_RECOVERY

## 存储职责

SQLite：身份、状态、关系、结构化资产。
Filesystem：Raw、附件、缓存、导出、备份。
Markdown：阅读 / 审核 / 导出视图。

## SQLite 建议

- PRAGMA foreign_keys = ON
- PRAGMA journal_mode = WAL
- PRAGMA synchronous = NORMAL

## 备份

危险操作前自动备份；可使用 SQLite Backup API 或 VACUUM INTO。

## 恢复

损坏数据库重命名保存为 .damaged-<timestamp>，再从备份恢复，保留事故现场。
