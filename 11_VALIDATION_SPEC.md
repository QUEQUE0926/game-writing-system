# 11_VALIDATION_SPEC

## 必查错误

- Evidence Error：证据不存在或定位错误
- Attribution Error：NPC/队友/UI 被误认成作者
- Inference Error：结论超出证据
- Source Error：外部资料冒充亲历
- Reference Error：Cross Reference / Usage 指向无效对象
- Lifecycle Error：trashed 对象被重新作为正常引用目标

## 写入顺序

Model Output → Schema Validation → Reference Validation → Domain Validation → Transaction → Database。
