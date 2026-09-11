# 12_TESTING_STRATEGY

## 测试层级

- Unit Tests：领域规则、ID、状态机、Validator
- Integration Tests：SQLite、migration、repository、文件导入
- Golden Project：端到端回归
- Smoke Tests：启动、导入、检索、写入

## Golden Project 必含

作者发言、NPC、队友、UI 朗读、ASR 噪声、重复反应、体验反转、Material Card、Claim、Cross Reference。

## 回归原则

每个严重 Bug 必须新增对应测试；事故本身变成测试资产。
