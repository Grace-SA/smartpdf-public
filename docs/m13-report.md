# M13 Word 转 PDF研究报告

日期：2026-10-26—27。状态：**Design / 本地技术门槛未通过**。
已完成竞品入口/部分任务研究、公开源码选型、产品方案、自审和隔离研究原型测试。
尚未开发正式产品入口，不标记 Testing、Accepted 或可发布。
详见 [产品与技术方案](ux/m13-word-to-pdf-design.md)。

## 基线与范围

从 main `6c24dee` 新建 `feature/m13-word-to-pdf`，工作副本为
`smartworks-pdf-m13`，不改变现有M11/M12分支及验收服务。
新增研究脚本、文档和合成测试证据摘要；没有更改 src、生产依赖、路由或部署。
研究时发现仓库扫描器将`.git`必须为目录作为根目录判断，导致标准linked worktree
被误拒绝；改用Git根路径校验，保留全部内容扫描规则，并验证根目录通过、子目录
拒绝及原有三个敏感路径/凭据/未审阅二进制探针拒绝。不绕过仓库防护。
本轮研究输入全为自制DOCX；仅该合成文件用于竞品上传。

## 实验结果

环境：Windows，现有 Playwright Chromium1248 / WebKit2370。
这是桌面浏览器，不是真实iPhone；引擎资源从本机HTTP加载，启用COOP/COEP。
候选锁定 `@matbee/libreoffice-converter` 2.7.2、docx-preview0.4.1、Mammoth1.13.0，
使用已有OFL Noto Sans SC变量字体；没有加载系统商业字体。

| 原始冻结样本                     | Chromium LibreOffice WASM | 独立输出核对                                   | docx-preview页面容器  |
| -------------------------------- | ------------------------- | ---------------------------------------------- | --------------------- |
| 显式两页、合并格、图片、页眉页脚 | 输出2页                   | 文字标记、图片、尺寸通过，已看两页渲染         | 2页                   |
| 120段自动分页                    | 输出4页                   | 120个唯一标记各1次，已看4页                    | 1个约3494px高的长容器 |
| 横竖版分节                       | 输出2页                   | A4竖向→横向，已看两页                          | 2页                   |
| 中文与短日文                     | 输出1页                   | 字符可提取，已看单页，无缺字框                 | 1页                   |
| 故意不存在的字体                 | 输出1页                   | 标记保留，已看单页；发生字体替代，不是字体保真 | 1页                   |
| 80行长表、重复表头               | 输出4页                   | 80个行标记各1次，已看4页                       | 1个约1493px高的长容器 |

六份/14页通过的是结构和初步渲染检查。没有与 Microsoft Word 的参考PDF做精确
字框/分页比较，不能据此宣称“100%保留Word版式”。原始六份均未被定位样本替换。
Mammoth六次可生成HTML仅验证其语义转换可运行，不算PDF转换成功。

初轮Chromium初始化1499ms，六份转换约82—1405ms；不含远程下载，不是手机速度。
首份端到端取文件/处理约1444ms，其余93—211ms（两种计时定义分别记录）。
空输入返回Empty document；损坏ZIP返回无法载入，未生成成功文件。
初轮本地上下文拦截并统计外网请求，计数0；此结论仅适用于本轮合成输入。
轻量HTML对照上下文没有相同拦截，不将其计入零外网的证明。

### WebKit与清理失败

完整原始样本首份含表/图/页眉页脚转换等待60秒超时；新上下文复测15秒仍超时。
独立简单中文样本成功。为定位问题增补4份最小合成稿（不改原始分母）：

| 增补输入     | WebKit新上下文         |
| ------------ | ---------------------- |
| 单表格       | 成功                   |
| 仅PNG图片    | 15秒超时，停在文档导入 |
| 仅页眉页脚   | 15秒超时，停在文档导入 |
| 简单显式两页 | 成功                   |

这只能定位触发类别，未证明根因，也不能泛化成所有Safari图片都不支持。
`destroy()`复查的两个浏览器都未在2秒内清理完成，日志捕获
`PThread was not exported`，其后触发WASM abort。关闭整个测试上下文用于隔离，
不把它写成已实现产品取消。必须有独立的强制终止机制及线程释放证据。

### 资源和内存

| 文件                     |             解压后字节 |        本机gzip6字节 |
| ------------------------ | ---------------------: | -------------------: |
| soffice.wasm             |              147416331 |             48766176 |
| soffice.data             |               99735918 |             28604370 |
| soffice.js               |                 444153 |                88823 |
| soffice.worker.js        |                   3221 |                 1358 |
| browser.js               |                  73956 |                16005 |
| browser.worker.global.js |                 110190 |                25019 |
| Noto Sans SC变量字体     |               17772300 |             11296746 |
| 合计                     | 265556069（253.25MiB） | 88798497（84.68MiB） |

这是独立压缩测算；研究HTTP服务实际提供未压缩资源，不混称实际网络传输量。
不含页面、额外预检器、PDF复核器及其他字体，也没有测量Brotli后的版本。
npm归档本身79515284字节，其sha256为
`14d670936fe220ee49becbfd40bf233ceabb94981fa9987fccde345449ee2c3a`。

用不改动原包的诊断Worker包装WebAssembly.Memory，两个浏览器均观察到
`initial=16384`个64KiB页，即**1073741824字节（1GiB）共享线性内存**，
maximum65536页。此值不是进程峰值RSS或实际常驻物理内存。
尝试提供512MiB时，模块导入因小于声明最小内存而LinkError，初始化无法完成。
因此需重新编译/更换构建，不能只改wrapper配置。

## GitHub源码与许可证核对

记录核对时的提交，不把主分支未来状态视为本轮证据。

| 候选                                                                                                         | 提交/版本                                                         | 实际阅读链和结论                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [LibreOffice WASM wrapper](https://github.com/matbeedotcom/libreoffice-document-converter)                   | npm2.7.2；gitHead `b72a3d584bc28c5111afafcf25def7a24fb5fcb0`      | [browser.ts](https://github.com/matbeedotcom/libreoffice-document-converter/blob/b72a3d584bc28c5111afafcf25def7a24fb5fcb0/src/browser.ts)：WorkerBrowserConverter→worker init/convert→LOK；包声明MPL-2.0，但下载包无LICENSE文件，分发清单待核验 |
| [docxjs/docx-preview](https://github.com/VolodymyrBaydalka/docxjs)                                           | npm0.4.1；查看仓库HEAD `c533f383069008d4a1e05c6171ef8777fd078385` | renderAsync→HTML，文档说明不自动执行完整Word分页；Apache-2.0；发布包与仓库HEAD不混为同一个构建                                                                                                                                                  |
| [Mammoth](https://github.com/mwilliamson/mammoth.js)                                                         | npm1.13.0；查看HEAD `5171a9072f8b7343ab1c9ed3a15d6d372cb59b67`    | convertToHtml保语义而非完整样式；BSD-2-Clause；原始HTML需防护，不能直接用于不可信文档                                                                                                                                                           |
| [PDFCraft](https://github.com/PDFCraftTool/pdfcraft/tree/60907250a9e71609b4bc6272dfe40355656475c3)           | `60907250a9e71609b4bc6272dfe40355656475c3`                        | `src/lib/pdf/processors/word-to-pdf.ts`→`src/lib/libreoffice/converter.ts`→WorkerBrowserConverter；非隔离时Pyodide分支；AGPL-3.0，只研究、不复制产品实现                                                                                        |
| [Gotenberg](https://github.com/gotenberg/gotenberg/tree/764c7f2c256af9100787d40d2306c2bd0d7b2990)            | `764c7f2c256af9100787d40d2306c2bd0d7b2990`                        | `pkg/modules/libreoffice/routes.go`服务端路由；MIT；不替代浏览器本地契约                                                                                                                                                                        |
| [Stirling-PDF](https://github.com/Stirling-Tools/Stirling-PDF/tree/684608d143779bf3a8ffc67639f077a1202c62ff) | `684608d143779bf3a8ffc67639f077a1202c62ff`                        | `OfficeToPdfService.java`调用Java OfficeToPdf并保留LibreOffice fallback；GitHub API许可NOASSERTION，未按宽松许可引入                                                                                                                            |

这些项目核对时未标记archived，不等于质量背书。npm归档、本地引擎与字体未加入Git。
源文件初读若来自main，提交记录用于定位当时版本；生产选型前还须从锁定提交重新
导出、核对构建及完整传递依赖，不能用本报告替代软件物料清单。

## 证据、复现与缺口

可分享摘要：[纯合成研究摘要](ux/public-synthetic-only/m13-research-summary.json)。
详细结果、固定fixture、独立PDF与逐页PNG在本机忽略目录`.research/m13/`，
包括results、diagnostics、webkit-isolation、reduced-memory、independent-checks和resources。
不提交源DOCX、渲染图、下载PDF或第三方引擎二进制。

复现脚本位于`scripts/m13/`：download.py校验registry完整性并解包；fixtures.py只在
没有冻结manifest时生成；probe.mjs运行本地服务及双浏览器研究；diagnose.mjs逐案隔离；
verify.py用pypdf独立检查。需项目Playwright与现成浏览器、Python的python-docx/Pillow/pypdf。
字体来自仓库现有vendor-fonts。跨副本依赖可通过M13_DEPENDENCY_PACKAGE传入，不记录私人绝对路径。
不要让普通用户文档进入这个没有完整预检的研究原型。

已执行Node语法检查、真实Chromium转换、WebKit成功/超时定位、空/损坏输入、
源sha256核验、pypdf结构/文字/图片检查、Poppler渲染及14页目视初查、资源压缩测量、
WASM内存探测与512MiB导入失败验证。自审是作者自审，没有称独立评审。

未执行：真实iPhone、进程峰值内存、慢网/后台、全部恶意包边界、Microsoft Word
参考输出精确对齐、正式交互、全站累计回归与CI。没有产品代码变更，不把旧测试结果
覆盖本轮，也不把研究原型作为第一版验收包。

当前结论：继续完整本地引擎的兼容/资源攻关；正式UI开发以技术门槛通过为前提。
不因阻塞而静默引入上传、付费依赖、桌面安装或删除图片/页眉页脚支持。
