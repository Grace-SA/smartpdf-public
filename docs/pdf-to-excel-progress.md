# PDF → Excel 开发进度

## PDF → Excel（2026-11-11）

- 范围已确认，PDF → PPT 属于另一个任务。独立 checkout，基线 `8f2e8bb`，未改动原工作区。
- 竞品调研、自托管技术评估、产品交互、转换服务、前端流程、单元/集成/专项浏览器测试及 200 份公开样本批测已完成。
- 用户已确认继续自托管、优先改善准确性。依据公开标注测试，将原规则主引擎升级为离线 Docling/Heron + TableFormer，并保留原文和经过交叉核对的框线结构。
- 当前阶段：**代码审查候选；复杂文档保真与生产环境仍需验收**。生产开关关闭，最终指标见验证报告，不能把输出率当准确率。
- 已推送独立分支并创建[草稿 PR #14](https://github.com/Grace-SA/smartpdf/pull/14)。GitHub Actions 因账号付款/支出额度问题未启动任何步骤；Linux CI 和容器冒烟尚未验证，需恢复额度后重跑。
- [设计与调研](pdf-to-excel-design.md)；[验证结果与剩余工作](pdf-to-excel-report.md)；[运行方式](../server/pdf-to-excel/README.md)。
- 生产开关关闭；无生产发布、无发布 tag、未合并 main。下一步先解决检测质量，不能以自动化测试数量代替转换保真验收。
