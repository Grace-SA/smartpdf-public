# PDF 转 Excel 研究与实现基线（2026-11-11）

范围：仅 PDF → XLSX；PDF → PPT 由另一个任务处理。基于 main 8f2e8bb 的独立 checkout/分支开发。托管 worktree 工具无法识别系统 Git，改用独立本地 clone；原工作区未修改。生产发布另行授权。

## 竞品与来源

以下为官网及公开交互说明核查，不冒充已完成付费转换实测。没有向第三方上传个人文件。

| 产品 | 优点 | 缺点/需要验证 |
|---|---|---|
| [iLovePDF](https://www.ilovepdf.com/pdf_to_excel) | 拖放入口、扫描件提示；单工作表/多个工作表；明确普通/OCR Premium | 扫描件有付费门槛；官网没有逐单元格质量证据；单表易被误解成语义合并 |
| [Smallpdf](https://smallpdf.com/pdf-to-excel) | 上传→Basic/Advanced OCR→转换→下载；结果可分享 | OCR 属于 Pro；额外分享不是本产品首要任务；需验证复杂表格准确性 |
| [Adobe](https://www.adobe.com/acrobat/online/pdf-to-excel.html) | 单入口、服务器处理说明、XLSX 输出 | 账号/商业服务约束；无法仅凭营销页面确认准确率 |
| [Tabula](https://tabula.technology/) | 框选区域、提取预览、可返回修正，流程适合表格核对 | 不支持扫描 PDF；每页框选成本高；不是页面排版还原器 |

本产品借鉴：上传前说明服务器处理；一键默认转换；保留页码来源、工作表预览和警告；完成页下载为唯一主操作。把“单表”定义为按顺序堆叠，绝不自动混合不同表的列。

## 选型与实证

- [Stirling 3.2.2 XLSX controller](https://github.com/Stirling-Tools/Stirling-PDF/blob/v3.2.2/app/core/src/main/java/stirling/software/SPDF/controller/api/converters/ConvertPDFToExcelController.java)：已有 `/api/v1/convert/pdf/xlsx`，`useStirlingOfficeConvert=true` 使用 OfficeConvert，false 为 Tabula；不是 CSV 改扩展名。
- 本机独立实例 8768 对 13 种合成 PDF 进行了两种模式的实际转换并以 openpyxl 重开。OfficeConvert 保留 A1:C1 合并、能读旋转表格，Tabula 不保留合并且旋转表格输出空单元格。两者对无框线、纯扫描件返回 204。混合 PDF 仅导出文本页，故必须逐页覆盖检查，不能将其算完整成功。
- OfficeConvert 将 `1.234,50` 解释为数字，存在地区格式歧义。提供默认保留源文本的路径，禁止推断日期、长整数、前导零、公式。
- [pdfplumber](https://github.com/jsvine/pdfplumber)：MIT，可获取单元格坐标、原文字、行列；适合文字型 PDF，无内置 OCR。用作文字与几何提取/无框线补充，并独立核对 Stirling。
- [Camelot](https://github.com/camelot-dev/camelot)：表格专用、多种提取策略；需额外依赖与评估，不把解析评分当准确率。
- [PaddleOCR PP-Structure](https://paddlepaddle.github.io/PaddleOCR/v2.10.0/en/ppstructure/model_train/train_table.html)：可提取表格结构及中文；较大模型与服务资源预算，需要真实部署验证。
- [Docling](https://github.com/docling-project/docling)：可用于版面和结构分析；模型部署、冷启动与模型许可证需单独审核。
- [Azure Layout](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)：有表格结构和 OCR，属于付费外部处理，本次不启用。

实现方向：自托管 Node 任务网关 + 独立 Python 转换进程；Stirling 可复用为结构引擎，pdfplumber 保留文本/补充无框线，扫描页使用独立开源 OCR 路径。默认数据不外发第三方。保留依赖和资源隔离，不能让转换阻塞 Web 主线程。

## 产品与交互基线

1. 选择一份 PDF（30 MiB / 200 页）；选择时不上传。页范围默认全部，支持 `1-3,5`。
2. 选项：每表一张工作表（默认）/合并到一张（顺序堆叠，保留来源分隔）；自动识别扫描页。保留文本及数字原写法，不自动执行公式。
3. 点击 Upload and convert 才上传；展示上传、排队、提取、验证状态。取消必须终止本任务，不显示迟到结果。
4. 成功页：下载 XLSX；显示表格数量、来源页码、前若干行预览和明确警告。无表格/扫描识别失败不产空白“成功”文件。未提取页必须明确列出。
5. 服务不可用可重连；错误可重新转换/换文件；完成后可删除服务端文件/新任务。离开时提醒并清理。
6. 工作表保留合并单元格、相对列宽、行高、换行。PDF 中图表、图片、非表格正文不承诺全部重建；不能声称像素级还原。OCR 数字需要复核。

设计自审：默认操作最少；不暴露引擎名给普通用户；不能悄悄忽略扫描页；不把模糊表格猜成可靠数据；不因为凑 200 样本而放宽门槛。

## 冻结测试口径

- 200 个网上下载、按 SHA256 去重的真实上游 fixture；manifest 包含仓库、commit、URL、字节、hash。仅本地研究，不自动提交或再分发。含表格与困难/非表格负例，不称为 200 个高质量表格。
- 单独的可复现合成 golden：有线/无线、多行、合并、中英文、前导零、20 位整数、公式样文本、混合方向、旋转、多页、扫描、混合扫描、无表格、空白、加密、损坏、空文件。
- Golden 的文字/关键数字必须逐值精确相等；合并范围与行列数精确核对。网页样本缺少真值，不以“能打开”为文字准确率，只报告状态和结构检查，保真结论需人工标注集。
- 质量门槛：不得空输出成功；不得执行源公式；不吞页；所有明确支持的 golden 通过；所有拒绝路径有原因；单元/API/浏览器/累计回归通过后才可首版验收。
- 性能目标（待测）：普通 10 页 <30 秒；单任务硬超时 180 秒；队列/上传/输出都有上限。真实手机、200 份人工逐格校对不由浏览器模拟替代。

## 实现后复核与明确取舍

早期原型采用 pdfplumber 原文和坐标为主；真实标注暴露正文误检、拆表和错位后，最终改为 **Docling/Heron 版面检测 + TableFormer V1 accurate 结构识别 + PDF 原文匹配**。只有表格位置、行列数和全部单元格文字集合与模型一致时，才优先采用 pdfplumber 原始框线结构。清晰扫描页继续使用 RapidOCR/OpenCV，旋转页暂由 Stirling OfficeConvert 补充，openpyxl 输出真实 XLSX。

模型预测结构，不用语言模型改写或补猜正文。默认所有值写成 Excel 文本，因此用户进行运算前可能需要转换数字类型；这是保留编号前导零、长整数和地区小数格式的明确取舍。单工作表是按来源顺序堆叠，不能称为跨页表格语义合并。重叠或越界网格被明确拒绝，不能为了提高转换率生成可能错位的表。

扫描件已验证清晰网格、中文/英文、横向和纵向合并；无框线扫描、倾斜/模糊扫描、手写、多层嵌套表格仍未达到可承诺保真程度。自动 OCR 的逐格识别不可能由“文件成功打开”证明。

[RapidOCR](https://github.com/RapidAI/RapidOCR) 搭配 PP-OCRv4 和 ONNX Runtime，模型随固定 wheel 安装，转换时不下载。[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE) 与 [OpenCV](https://github.com/opencv/opencv/blob/4.11.0/LICENSE) 的许可证及依赖元数据纳入 `server/pdf-to-excel/runtime-provenance.json`；[openpyxl](https://openpyxl.readthedocs.io/en/stable/) 采用 MIT。提供运行依赖锁定版本与模型 SHA-256。生产 Docker 构建、Linux 资源预算、容器基础镜像 digest 和部署区域仍需上线前实测。

用户进一步确认“继续自托管，优先改善准确性”，不接入商业 API。按 [Docling 离线部署说明](https://docling-project.github.io/docling/usage/advanced_options/) 预下载固定 revision 模型，并验证 SHA-256；转换时禁止远程推理和模型下载。生产模式缺少模型时不接单。部署只安装 PDF/本地模型所需的 `docling-slim` extras；Linux 使用官方 PyTorch CPU wheel，避免 CUDA 依赖。

同一 7 份困难样本的 1,005 个标注单元格，V1 accurate + 原始 PDF 单元格匹配取得 949 个文字/位置/跨度匹配；关闭匹配为 824，新版 TableFormer V2 为 736，因此选型基于实测，不因版本较新就替换。完整 67 份、14,114 个单元格的结果及定义在验证报告中，不能外推成任意文档准确率。

小型无框线表格只有连续列间距、数值内容和文字表头同时成立才进入补充路径，避免将图表两侧纯数字坐标轴当成表格。源字体大小、相对列宽、换行内容决定行高；独立 LibreOffice 渲染发现并修复了长文字被行高遮挡的问题。超过 Excel 可读显示边界的单元格明确拒绝，不隐藏文字后宣称完成。

2026-11-11 竞品实测补充（仅上传自行生成的 3×3 合成表格）：

- iLovePDF：选择→普通转换/布局→Convert to EXCEL→下载流程完成，实际 XLSX 已本地重新打开。三行三列正确；编号底层变成数值 123/987，但单元格格式 `00000` 保留显示前导零；金额是可计算数值、保留小数格式。不能误称其丢了前导零。优势是直接可计算；导出 CSV 或后续改变格式时，编号语义需要用户注意。
- Smallpdf：选择文件后出现 Basic conversion 与 Edit PDF directly 分支，已触发 Convert；当前自动化会话没有取得可核验的 XLSX 下载，不能声称转换准确或不准确。此限制写入结果，不推导为产品普遍缺陷。
- Adobe：当前测试浏览器返回 Access Denied。功能分析限于官网资料，未伪造实际转换结论。
- 我方实测：直接进入默认单表/多表设置；上传前无文件请求；取消、防双击、重试、跨任务清理、过期删除和桌面/手机尺寸都纳入测试。截图复查修复了共享导航样式未继承的问题；独立 LibreOffice 复查中补齐渲染器中文字体，确认中文并非输出丢失。
