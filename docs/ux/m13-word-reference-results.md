# Microsoft Word 参考输出与逐页对比结果

日期：2026-10-28。范围：已冻结的 16 份合成 DOCX。已补齐全部 Word 参考，产品尚未开发。

## 结论

桌面 Microsoft Word 实际导出 16 份 PDF、34 页，与原生 Gotenberg 的首轮两组输出逐页对照。
固定 Noto 环境的 16/16 份页数一致，34/34 页的合成标记所属页一致；605 个原始 ASCII 标记均完整。
另核对清单要求的重复表头、页眉页脚，未发现缺失。默认字体环境 13/16 份页数一致，
中文长表格、跨页长行、中文自动分页分别为 3/1/3 页，Word 为 4/2/4 页。

这证明字体配置影响分页，支持采用固定字体的自建路线；它不证明任意 DOCX 保真。
固定字体下标记边界框的最大分量差异为 0.156–11.958 pt（最大约 4.22 mm），
中文标题字形、行距和表格累计高度有可见差异，不能称为像素一致。
正式产品边界与实施安排见[正式产品与技术方案](m13-cloud-product-technical-plan.md)。

## 参考输出来源与方法

- Microsoft Word for Microsoft 365，WINWORD 文件版本 `16.0.20430.20182`，桌面 UI 的 PDF 导出，Standard 质量。
  没有使用 LibreOffice 生成 Word 参考，也没有用系统打印 PDF 冒充 Word 导出。
- 使用原 6 份及新增 10 份固定源文件，未重建或调整内容。关闭本次打开的合成文档后，16/16 源 SHA-256 与冻结清单一致。
- 本轮补出剩余 14 份，保留此前中文标点和中文长表格两份。每份 Word 参考只有一次导出，未声称完成 Word 重复运行稳定性测试。
- 候选为[原 PoC](m13-gotenberg-poc-results.md)的默认字体与固定 Noto 首轮输出，未重跑或覆盖原 64 份输出及负例结果。
- pypdf 核对文件来源与页数，pdfplumber 读取页面、标记与边界框；Poppler 100 DPI 渲染。
  已逐页查看 34 组 Word/Noto 并排图，并放大查看中文标点、跨页行第二页等页面。该目视审核是作者自审。
- 每个标记允许提取器在字符组之间插入空白，例如 Word 的 `LONGROW -001` 与源标记 `LONGROW-001`。
  原始提取文本仍保留；不规范化汉字、数字、标点为“相同”。所有预期 ASCII 标记在两端都实际找到，避免双方同时缺失被误判为通过。
- 位置差异取同一页同一标记首次出现的 `x0/top/x1/bottom` 最大绝对差，含字宽差；不是整页像素差，也不是所有字形的最大位移。
  每页计数包含重复表头/页眉页脚，可能高于原始标记集合在该页的数量。

## 字体与中文文字提取限制

这是“本机 Word 实际输出”对照，**不是控制了同一字体文件的引擎实验**。
Word PDF 中的字体包含 Arial、Calibri、Cambria、MS Gothic、Microsoft YaHei，
容器中正文实际命中 Noto Sans SC，主题标题仍可能回退 Noto CJK。
源文档声明字体与最终 PDF 使用字体不能混为一谈。

仓库 Noto 文件为 Version 2.004-H2，SHA-256 为
`a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`；
本机同名文件为 Version 2.04 非正式构建，SHA-256 为
`763146584cf0710223441356b4395e279021b0806c196614377a7a0174ae074a`。
两者若干布局/名称表不同，不能只依据文件名或版本文字判定度量相同。
没有为本轮改动系统字体，也没有将 Windows 商业字体复制到转换服务。

Word 参考中文标点页面视觉上的“测试”等字正确，但 PDF 提取结果存在重复错误映射，例如提取为“标标”。
因此本轮用 ASCII 标记检查内容位置，用实际页面检查中文可见内容；不将 Word 的错误 ToUnicode 当作候选缺字。
Word PDF 还包含许多非源图片的图像对象（中文标点样本有 26 个），不能按图片对象数比较源图片完整性。
原始图文样本的可见图片已逐页对照；固定 Noto 输出的中文可提取性由原 PoC 独立检查另行验证。
这些限制使参考适合版式比较，不能作为中文全文搜索正确性的唯一 oracle。

## 全部样本与逐页记录

以下先列每份文档页数，再列全部 34 页的比较记录。所有列出的 Noto 页都实际存在，
同页标记集合无差异；横向/纵向页框方向一致。Word 的 A4 页框为 595.440 × 841.680 pt，
候选约为 595.304 × 841.890 pt，横向互换；存在约 0.210 pt 的页面尺寸舍入差。

| 样本                       | Word 页 | 默认字体页 | 固定 Noto 页 | Noto 标记框最大差异 pt |
| -------------------------- | ------: | ---------: | -----------: | ---------------------: |
| explicit-pages-table-image |       2 |          2 |            2 |                  0.156 |
| automatic-pagination       |       4 |          4 |            4 |                  1.696 |
| mixed-orientation          |       2 |          2 |            2 |                  0.156 |
| cjk                        |       1 |          1 |            1 |                  0.746 |
| missing-font               |       1 |          1 |            1 |                 11.820 |
| long-table                 |       4 |          4 |            4 |                  0.167 |
| chinese-punctuation        |       1 |          1 |            1 |                  6.938 |
| chinese-sizes              |       1 |          1 |            1 |                  5.009 |
| chinese-merged-table       |       1 |          1 |            1 |                  3.482 |
| nested-table               |       1 |          1 |            1 |                  6.203 |
| chinese-long-table         |       4 |          3 |            4 |                 11.528 |
| long-row-split             |       2 |          1 |            2 |                 11.958 |
| chinese-explicit-pages     |       3 |          3 |            3 |                  4.072 |
| landscape-wide-table       |       1 |          1 |            1 |                  3.462 |
| separate-section-headers   |       2 |          2 |            2 |                  3.462 |
| chinese-auto-pagination    |       4 |          3 |            4 |                  8.798 |

| 样本                       |  页 | 同页匹配标记数 | 标记框最大差异 pt | 页框最大差异 pt |
| -------------------------- | --: | -------------: | ----------------: | --------------: |
| explicit-pages-table-image |   1 |              5 |             0.146 |           0.210 |
| explicit-pages-table-image |   2 |              3 |             0.156 |           0.210 |
| automatic-pagination       |   1 |             31 |             1.696 |           0.210 |
| automatic-pagination       |   2 |             31 |             1.696 |           0.210 |
| automatic-pagination       |   3 |             31 |             1.696 |           0.210 |
| automatic-pagination       |   4 |             27 |             1.436 |           0.210 |
| mixed-orientation          |   1 |              1 |             0.156 |           0.210 |
| mixed-orientation          |   2 |              1 |             0.156 |           0.210 |
| cjk                        |   1 |              1 |             0.746 |           0.210 |
| missing-font               |   1 |              1 |            11.820 |           0.210 |
| long-table                 |   1 |             26 |             0.167 |           0.210 |
| long-table                 |   2 |             26 |             0.167 |           0.210 |
| long-table                 |   3 |             27 |             0.167 |           0.210 |
| long-table                 |   4 |              1 |             0.167 |           0.210 |
| chinese-punctuation        |   1 |              3 |             6.938 |           0.210 |
| chinese-sizes              |   1 |              5 |             5.009 |           0.210 |
| chinese-merged-table       |   1 |             15 |             3.482 |           0.210 |
| nested-table               |   1 |              9 |             6.203 |           0.210 |
| chinese-long-table         |   1 |             34 |            11.528 |           0.210 |
| chinese-long-table         |   2 |             34 |            11.528 |           0.210 |
| chinese-long-table         |   3 |             34 |            11.528 |           0.210 |
| chinese-long-table         |   4 |              2 |             3.482 |           0.210 |
| long-row-split             |   1 |             69 |            11.958 |           0.210 |
| long-row-split             |   2 |             23 |             3.482 |           0.210 |
| chinese-explicit-pages     |   1 |              3 |             4.072 |           0.210 |
| chinese-explicit-pages     |   2 |              3 |             4.072 |           0.210 |
| chinese-explicit-pages     |   3 |              3 |             4.072 |           0.210 |
| landscape-wide-table       |   1 |             96 |             3.462 |           0.210 |
| separate-section-headers   |   1 |              2 |             3.462 |           0.210 |
| separate-section-headers   |   2 |              2 |             3.462 |           0.210 |
| chinese-auto-pagination    |   1 |             23 |             8.798 |           0.210 |
| chinese-auto-pagination    |   2 |             23 |             8.798 |           0.210 |
| chinese-auto-pagination    |   3 |             23 |             8.798 |           0.210 |
| chinese-auto-pagination    |   4 |              1 |             3.582 |           0.210 |

## 视觉判断与支持决策

英文正文、图文合并表格和横竖混排保持相同分页。英文长表格跨页处的拆行与重复表头可见内容对应。
中文长表格每页行号为 1–33、34–66、67–99、100；两端一致，但候选表格高度略小。
跨页行两列均在第 1 页保留 0–33、第 2 页保留 34–44，并重复表头，未见漏行或列串位。
中文自动分页每页段号为 0–22、23–45、46–68、69，两端一致。
合并单元格、嵌套表格、96 个宽表格单元格与分节独立页眉在所测页面中无明显结构损坏。
中文标点页的标题与正文纵向位置有差异，固定字体也不能消除所有 Word/LibreOffice 排版差异。

首版可支持这些受限结构并提供结果预览。缺失字体必须提示，复杂表格需明确核对；
严格 Word 排版、未验证复杂域、修订和浮动对象不纳入承诺范围。
不能仅凭 16 份合成样本计算真实用户文档的成功率，也不能由本机速度推导云吞吐或 SLA。

## 证据与复现

本机忽略目录 `.research/m13/word-reference/` 包含 16 份 Word PDF、各 PDF 哈希、
字体核查、源哈希复核、完整逐页提取信息、34 页 PNG 和 6 张并排总览。
这些原始文件不加入 Git 或云端代码库。
[可共享合成数值摘要](public-synthetic-only/m13-word-reference-summary.json)仅包含已审阅的合成名称、哈希和比较数字。

运行 `python scripts/m13/gotenberg/compare_word.py` 读取现有本地参考和候选，
再运行 `python scripts/m13/gotenberg/summarize_word.py` 导出有限字段摘要；后者拒绝缺样本、源哈希变化或标记缺失。
此前默认字体标点提取失败、跨页最少页数失败、空文件 HTTP 200 与损坏包 HTTP 500 均保持原记录，
此次 Word 对比没有将原 PoC 改写为“全套验收通过”。

后续产品测试仍需恶意包/限流/取消/清理边界、真实云容量、授权代表性文档、实机交互、全站累计回归及提交对应 CI。
当前完成的是正式开发前的研究与方案，不是产品验收构建。
