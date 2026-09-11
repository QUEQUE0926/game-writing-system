# 14_MVP_TASKS

## 必须从第一天具备

- SQLite schema version
- Migration runner
- DEV / TEST / PROD 隔离
- 稳定日志
- 数据备份
- Golden Project
- 自动测试
- 一键 verify
- Git 分支规则

## MVP 功能链

1. Series / Game / Version 建档（已完成：CLI 建档 + 别名 + rename + find 查询）
2. 导入 merged TXT（已完成：拖放弹窗 / prepare / auto-import / import-txt，
   预告确认 + 副本隔离 + 幂等去重；排列组合与批量组合测试全绿）
3. Source / Segment（已完成：编码探测 + raw 归档 + 逐行 Segment，speaker=unknown 待分类）
4. Speaker / Content classification（进行中：规则轮 classify_speakers.py 支持
   --source 过滤；dev 29 源中 14 源已分类）
5. Episode（进行中：make_episodes.py 支持 --source 过滤；已知坑：幂等跳过是
   版本级，同版本多源时第二个源会被跳过，待改为源级）
6. Material Card
7. 人工确认
8. Tag / Cross Reference
9. Project
10. Asset Recall
11. Claim
12. Angle
13. Topic
14. Outline
15. Author Manuscript
16. Usage Record
