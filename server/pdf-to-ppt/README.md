# PDF → PPT 实验服务

独立的本机验收服务，尚未接入生产网站。默认可编辑引擎必须显式配置；所有可编辑输出为 `needs_review`，不承诺无损还原。图形仍可能是图片，OCR 不确定区域保留原图。

## 已实现

- 固定 Stirling 3.2.2 Java API 适配；不自动重试转换 POST，不自动切换云服务。
- PDFium 原生文字和坐标修复，区分斜体剪切与基线旋转，按有效字符矩阵计算垂直字号。PDFium 自动补出的空格只从同一对象的相邻真实字符继承变换，保留嵌套表单缩放与整段文字。
- 内容检查保留有可信文字/数字的原生表格；复杂图形采用原稿栅格，不把图片冒充可编辑图表。
- PP-OCRv6 medium 官方 ONNX 检测/识别；Unlimited OCR 2 与 OXR 可配置为离线区域复核。至少一个复核器确认位置和有序文字后才替换文字；配置两者时取共同通过的区域。无独立复核时保留扫描原图。
- 段落存在局部分歧时，仅恢复顺序、边界和文字均明确一致的完整行；数字前后缀仍参与核对。重复的整段/单行检测只在纯文字区域互相嵌套、每个区域的全部文字分别完全一致时放行，结构重叠或冲突继续拦截。
- 简单网格逐行逐列核对文字与数字，生成定位文本框；不宣称恢复原生 PowerPoint 表格。合并、空白、多行单元格或重叠/分歧区域保留图像。
- 支持均匀浅色纸张及均匀深色标题背景，估计文字颜色，并从已安装字体中比较拉丁文字的衬线、无衬线、等宽及粗体字形。深色区域需额外通过前景颜色一致性检查；混色文字、照片及渐变不因此放行。字体仍为估计和替代。
- 按词恢复复杂原生版面，保留源字符、数字及对象来源；失败区域保留原稿。支持经独立渲染验证的四方向文字。异常 Unicode 映射只允许隔离区域恢复，不猜测未知字形。
- 首次按词修复失败后，可追加一次字距校准；已经通过的页面保持不变。追加渲染失败时保留已完成的文件与诊断，不放宽完整文字、数字和 2pt 位置门槛。
- 使用字符原点在文字基线方向分组，避免引号或下伸字母的墨迹底边差异把同一行错误拆开。字号和真实基线改变仍会分段。
- 局部恢复可以保留既有文本框，追加不相交的原生词语。原文本 XML 和其实际墨迹像素必须保持不变；新增词语仍需通过来源、位置、局部像素与整页检查。所有追加尝试共用首次整页误差基准，不能累计放宽阈值。
- 对实际使用的、通过固定 SHA-256 校验的 Noto Sans SC、Noto Serif SC 和可选 CMU 字体，生成完整静态 EOT 字体并嵌入 PPT；保留完整 OFL 通知、可新增字符。中英文交界、细字重英文长行与扫描小字号文字可按实测位置拆分，减少客户端自动字距差异。失败时保留原文件并报告原因。
- LibreOffice 独立渲染原结果与候选结果，明确启用无损图片导出且不降低图片分辨率，避免验证器的 JPEG 重压缩干扰局部判断。逐页拒绝会使视觉差异明显增大的坐标修复。像素分数仅为筛查，不是正确率。
- 上传限制、独立 worker、下载令牌、取消、过期清理；POSIX 取消会终止 worker 的 OCR 子进程组。
- OCR、OXR 图块、独立渲染临时文件都置于任务目录，取消/过期清理包含这些派生文件。
- 原生文字恢复出现已知数字/字符缺失时逐页退回原稿图片；保留失败诊断，并在下载前列出不可编辑的页。兜底不是恢复成功。

## 配置和运行

需要 Python 3.12、已运行的固定 Stirling core、LibreOffice 和字体。Stirling core 使用仓库现有版本/校验清单，不包含在此目录。其 `configs/custom_settings.yml` 需启用 `system.stirlingOfficeConversion: true`。

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-lock.txt
python3.12 -m venv .ocr-venv
.ocr-venv/bin/pip install -r ocr/requirements-lock.txt
.ocr-venv/bin/python ocr/download_models.py

export SMARTPPT_EDITABLE_PROVIDER=stirling
export SMARTPPT_STIRLING_URL=http://127.0.0.1:8766
export SMARTPPT_LAYOUT_ASSISTANCE=1
export SMARTPPT_OCR_PYTHON="$PWD/.ocr-venv/bin/python"
export SMARTPPT_OCR_RUNNER="$PWD/ocr/paddle_runner.py"
export SMARTPPT_RENDERER=/absolute/path/to/soffice
export SMARTPPT_FONT_DIR=/absolute/path/to/fonts
export SMARTPPT_CJK_FONT=/absolute/path/to/NotoSansSC-variable.ttf
export SMARTPPT_CJK_SERIF_FONT=/absolute/path/to/NotoSerifSC-variable.ttf
export SMARTPPT_CMU_FONT_DIR=/absolute/path/to/cm-unicode-0.7.0

# 在分别继承以上环境的两个终端中运行：
PYTHONPATH=src .venv/bin/python -m uvicorn smartppt.api:app --host 127.0.0.1 --port 8765
PYTHONPATH=src .venv/bin/python -m smartppt.worker
```

`SMARTPPT_STIRLING_KEY` 为可选的服务端 API key。HTTP 仅支持回环地址，远端引擎需 HTTPS。模型目录可通过 `SMARTPPT_OCR_MODELS` 改写。模型下载脚本固定 URL、版本、大小及 SHA-256；Paddle 启动时以源码中的 `ocr/model-manifest.json` 独立复核必需文件，不信任模型目录自报的 `provenance.json`。权重不进 Git，运行时无需模型 API。识别字典写入任务临时目录并在整批识别后清理，运行时不写模型目录，可将模型只读挂载。

字体目录需提供实际字体。这里的 OCR 字号校准使用 Arial/Arial Bold 度量；其他字体/平台需重新验收，缺失度量会报告。`SMARTPPT_CJK_FONT` 应指向仓库已有 Noto Sans SC（SHA-256 `a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`）。嵌入使用固定 FontTools 4.68.0，只处理该许可开放的字体；不复制系统字体或任意上传 PDF 中的字体。未使用 Noto 的保留页面不会自动变成可移植字体页面。字体嵌入不代表原字体完全一致，也不代表所有客户端布局已通过。

可选的 `SMARTPPT_CJK_SERIF_FONT` 用于明确标识的宋体/明体及其拉丁字符，指向 [Noto 官方固定版本](https://github.com/notofonts/noto-cjk/blob/985fa52c81c1d6692ccdd82bc3656e8fb932fd89/google-fonts/NotoSerifSC%5Bwght%5D.ttf)，文件 25,125,512 字节，SHA-256 `050080d9255a86808f2945bffac582b31ef32bc36411ce29563b4961670c66f9`。部署准备阶段下载并校验，服务运行时不联网下载；未配置或文件缺失时保留原字体策略。仅固定哈希的字体允许嵌入，完整版权/OFL 随字体元数据保留。字体名称仍标明替代关系，不承诺宋体字形完全相同。

最新验证及未通过项见 [本轮质量报告](../../../docs/pdf-to-ppt-quality-round8-11-2026-11-13.md)，前一阶段数据见[第六、七轮报告](../../../docs/pdf-to-ppt-quality-round6-7-2026-11-13.md)。本模块仍是独立验收服务，尚未达到通用上线标准。

## 可选的 Unlimited OCR 2

当前实测是 Apple Silicon 的 MLX 0.32.4 / mlx-vlm 0.7.12，使用已验证 BF16 转换权重。它是可选的独立环境，Paddle CPU 路线不依赖 MLX。Linux/NVIDIA 路线尚未做本项目部署验收。

配置 `SMARTPPT_OCR_VERIFIER_PYTHON`、`SMARTPPT_OCR_VERIFIER_RUNNER`（本目录 `ocr/unlimited_runner.py`）和 `SMARTPPT_U2_MODEL`（离线模型目录）即可启用。脚本禁用在线模型访问和远程代码执行。不要在通用 Linux 环境安装 Mac MLX 包。

固定模型：`mlx-community/Unlimited-OCR-2-bf16`，revision `850d1e483f5a82a0597f0a45aac31b07ba840df2`；官方底座 `baidu/Unlimited-OCR-2`，revision `0480966938291445591f69f08a13b041c073a96a`。模型许可及依赖见本目录 `THIRD_PARTY.md`。

启动前使用源码中的 `ocr/u2-manifest.json` 校验权重、配置、模板与 tokenizer 的大小和 SHA-256；额外的可加载配置或权重也会拒绝。模型目录必须是已完整物化的独立目录，不能使用指向目录外部的 Hugging Face 缓存符号链接。清单的权重哈希来自固定 revision 的 Git LFS 元数据，配置/tokenizer 字节另行下载并核对 Git blob。2026-11-11 校验改动时未重跑 MLX；2026-11-12 已用本地完整权重进行真实推理回归，结果与限制见最新验收报告。

## 可选的 SoMark OXR

项目方已确认满足当前免费使用门槛。页面底部包含 PaddleOCR、Unlimited OCR 2 来源与 OXR 指定引用。当前实测适配器为 Mac MLX BF16 识别 + 本机 CPU D-FINE，**不是已经验证的 Linux 生产镜像**。只接受回环检测服务，不调用公共演示站或免费托管 API。

预先准备 `ocr/oxr-manifest.json` 固定的源代码/权重及此前研究使用的独立 MLX、Torch CPU 环境。启动器和识别器会验证所用文件大小及 SHA-256，不会自动下载。模型目录不可由上传请求指定。

```sh
export SMARTPPT_OXR_SOURCE=/absolute/path/to/OXR-b2ee4ac12ed220bf7fefa74951babf0d3b05e766
export SMARTPPT_OXR_MODEL=/absolute/path/to/oxr-mlx-model
export SMARTPPT_OXR_LAYOUT_MODEL=/absolute/path/to/oxr-layout-model
export SMARTPPT_OXR_LAYOUT_PYTHON=/absolute/path/to/torch-cpu-env/bin/python
export SMARTPPT_OXR_PYTHON=/absolute/path/to/mlx-env/bin/python
export SMARTPPT_OXR_RUNNER="$PWD/ocr/oxr_runner.py"
# 单独监督这个常驻检测进程；默认端口 18081，仅监听 127.0.0.1。
.venv/bin/python ocr/start_oxr_layout.py
```

当前上游源代码 revision 为 `b2ee4ac12ed220bf7fefa74951babf0d3b05e766`；MLX 模型 revision 为 `bdbec15bad81efe04ff0e66f20d36931cce2340a`；官方检测权重 revision 为 `c708407f9d2b4df658f2543d9132b62bb7221df4`。不要把 MLX 实测当作通用 CPU/Linux 支持。生产部署仍需建立独立锁定镜像并重跑验收。

可选 `SMARTPPT_CMU_FONT_DIR` 用于明确标识的 Computer Modern 正文，提供 CMU Serif、Sans Serif、Typewriter Text 的普通、粗体、斜体和粗斜体。使用 [CMU 官方 0.7.0 发布](https://sourceforge.net/projects/cm-unicode/files/cm-unicode/0.7.0/)，归档 SHA-256 为 `2609c14450f42d0bcd40203900afcb1d693521a9b24a18c65e14b6b0585ff150`，逐字体哈希见 `src/smartppt/cmu-fonts.json`。仅嵌入通过固定哈希与权限检查的完整字体，保留完整 OFL；不联网自动下载。数学/符号字体和无法可靠映射的私用区字符保留原图，CMU 正文字体不代表公式可编辑。

## 局部恢复、字体与倾斜扫描（本地验收版）

已知文字/数字错误先保留整页原图，再尝试按 PDF 原生文字对象恢复。对象内任一字符缺失、旋转、裁剪/描边、透明或符号字体不用于局部恢复；源文字不自动补写。字体描述中的衬线、等宽、斜体信息用于选择替代字体，实际 Office 字形边界用于校准基线、字号与字距。

每一段文字必须通过独立 Office 渲染后的局部比较，整页还要与同一渲染器输出的原图基准比较。失败对象留在背景中，失败页面恢复原来的原图；原始错误诊断仍保留在 `content_gate`。`native-regions` 表示部分文字可编辑，界面显示段数，不能视为全文恢复、原生表格或图表恢复。渲染器失败时保留原图并记录错误。

通过原有独立模型区域复核的小角度扫描行（最多 8°）可在识别框内校正字体度量，按原角度生成旋转文本框，原页面不整体旋转。固定 3° 样本已实测；并不保证范围内任意模糊、透视或复杂背景都通过。竖排、模型分歧和无法安全擦除的区域保留图像。现有数字/字符校验不因提高可编辑覆盖率而关闭。

可选的四方向预处理使用 Paddle 官方 PP-LCNet，固定 revision 和文件哈希见 `ocr/orientation-manifest.json`。使用已有 ONNX Runtime CPU 环境，无新增付费服务：

```sh
.ocr-venv/bin/python ocr/download_models.py --orientation
export SMARTPPT_ORIENTATION_RUNNER="$PWD/ocr/orientation_runner.py"
export SMARTPPT_ORIENTATION_MODEL="${SMARTPPT_OCR_MODELS:-$PWD/ocr/models}/PP-LCNet_x1_0_doc_ori_onnx"
```

方向置信度低于 0.9 或分类间隔不足时不旋转。归正后的同一图像交给三种 OCR；原图、归正图的哈希及逐像素转置均需校验。输出的背景和可编辑文本恢复原页面方向。方向分类不作为文字正确的证据，旧 OCR 缓存不能用于不同像素。

扫描文字估计 Arial、Times New Roman、Courier New 的常规、粗体、斜体及粗斜体；配置开放中文字体后，还比较黑体/宋体及细、常规、粗字重。行内词距差异较大时，按词比较字形。字体估计不等于识别出原字体。

配置渲染器后，以实际 Office 字形校准字号、基线和字距；小角度行先逆旋转测量。单行 OCR 文本显式设置段落字体、结束字符字体和行距，并随校准后的字号同步，减少客户端继承默认值造成的基线偏差。最多三次拟合保留原有 2pt 门槛和整页视觉检查，单个失败行不会抹去其他经过验证的拟合结果。最终逐行核验，不通过的文字恢复原扫描像素。校准位图最长边限制为 2400px。只允许在完全空白的浅色间隙裁去检测框多余留白或容许擦除框相交，不能擦除相邻笔画。

Noto Sans SC 的 100 字重、Noto Serif SC 的 200 字重使用独立静态族名 `SmartPDF Sans100`、`SmartPDF Serif200`，保留原字体完整字符集及 OFL 通知。运行时渲染从同一固定字体生成任务专属静态文件，不安装系统字体，避免可变常规字重覆盖细体。系统 Arial/Times/Courier 不随文件分发；不同客户端的字体替换和基线仍需单独验收。

原生 PDF 的相邻字符对象仅在源顺序、字体/样式、基线、间距和缺口内容均满足要求时合并。生成的空白边界可以依据位置修复；所有非空白源字符必须保持原序完全一致。列间距、不同样式、缺失字符和真实换行不能被拼接掩盖。局部恢复仍按完整原始对象验证，不因合并文本框而放宽删除背景的条件。

真实 Office 区域恢复验收可通过 `SMARTPPT_TEST_RENDERER=/absolute/path/to/soffice .venv/bin/python -m pytest -q` 启用；未配置时该验收测试明确跳过，普通单元测试继续运行。服务器字体仍需单独交付与验收，不引入在线 OCR API 或新的付费依赖。

## 验证与边界

```sh
.venv/bin/python -m pytest -q
```

安装仓库已有 Playwright 浏览器后，可在本模块目录运行 `node tests/browser-report.mjs`，检查 Chromium/WebKit 中的合成结果报告。它单独验证定位文字、表格单元格不可编辑、部分 OCR 和保真提示，不冒充真实转换测试。

测试全部使用程序生成的合成输入，不依赖真实用户文档或线上 OCR。公开样本、权重和真实渲染证据只保存在本机；批量实测结论见仓库 `docs/pdf-to-ppt-ocr-improvement.md`。

本轮代码审查、独立渲染证据、通用上线质量目标及未完成门禁见 `docs/pdf-to-ppt-review-2026-11-11.md`。新增测试不替代主站累计回归和真实模型/生产运行时验收。

后续 400 个公开输入、固定基准、真实三模型扫描回归、文字准确率与审查修复见 `docs/pdf-to-ppt-acceptance-2026-11-12.md`。当前生成成功率已较高，但真实文档的可编辑文字完整性和扫描文字位置精度仍未达到通用上线标准。

新的本地准确率评估器支持位置绑定的字符编辑距离、缺失/额外文字、数字区域一致性和几何误差。输入必须注明独立参考来源；未知结果保留 `null`，整页图片不能计为可编辑成功：

```sh
PYTHONPATH=src .venv/bin/python -m smartppt.acceptance --input /path/to/local-evaluation.json --output /path/to/local-report.json
```

输入结构为 `documents` 数组，每份包含 `eligible`、`generated` 和 `pages`；每页包含 `truth`、`predictions`、`truth_verified`。参考区域含 `id/text/bbox`，预测含 `text/bbox`，bbox 使用同一页坐标的 `[left,top,right,bottom]`。可提供唯一整数 `reading_order` 表示独立渲染器的字符顺序，区域分配始终使用几何。默认位置阈值 2pt。`structure_verified`、`render_verified` 未完成时，文档级完整成功率仍为未知；已验证成功数量的下限单独提供。不要把数据集的自动提取参考文本称为人工 OCR 真值。

这是实验模块，不接生产路由、不修改现有 Office→PDF 引擎、不部署。公开发布仍需网站鉴权/配额、Linux 固定镜像、并发负载、PowerPoint/WPS、字体交付、扫描质量与真实设备验收。OCR 脚本退出和取消本机 worker 不代表远端 Stirling 的任务也已取消；引擎临时文件清理需另外验收。

局部文字恢复会继续尝试对象、合并字形和词语策略。后续策略只有在保留每个已验证源字符位置、增加覆盖范围且再次通过区域及整页渲染检查时才会替换前一结果；同样的页脚文字出现在正文中不能代替原页脚。追加后按源字符位置恢复文字形状顺序，只有渲染像素完全不变才保存。数字校验区分日期逗号与千位分组，并保留 Unicode 负号和前导小数点的数值意义。

按词定位可以改善文字和版面，但不会生成原生表格单元格或图表数据。结果页对此明确提示；保留下来的原生表格仍需检查行列与合并单元格，不能把文字准确等同于表格结构正确。


## 固定公开样本诊断

`tools/public-native-manifest.json` 固定 W3C、IRS、arXiv 三份公开文件的 URL、SHA-256 及八个抽样页（保留原六页，新增 W-9 第3页及论文第6页）。人工下载至独立目录后，工具先核对全部哈希，输出必须使用新目录；不会自动下载或把样本写进仓库：

```sh
.venv/bin/python tools/public-native-probe.py --inputs /path/to/public-pdfs --output /path/to/new-run --renderer /path/to/soffice
.venv/bin/python tools/public-native-compare.py --source /path/to/new-run/fw9/source.pdf --rendered /path/to/new-run/fw9/candidate.pdf --output /path/to/new-review.json
```

第二步需要 Poppler `pdftotext`。这是以原图为基线的原生恢复诊断，未调用 Stirling，不能代替服务验收。字符袋覆盖率不代表阅读顺序或准确率；独立字词按几何先配对再比较文字，边框差异与标点分词需人工核查。图片中的文字不计为可编辑文字，完整文档、扫描件和各客户端仍需独立测试。

明确的 CM-Super 常规/粗体/斜体族名可以选择已配置的固定 OFL CMU 字体；未知变体不推断。严格来源匹配的未嵌入 Helvetica 常规字形使用 `SmartPDF Base Sans`，完整 BSD 通知包含于运行包和嵌入字体，渲染与交付使用同一字体字节。字体替代后的内容及像素门槛保持不变。

## 可选的 Nimbus Roman / Termes 字体适配

明确的 Nimbus Roman No9 L、Nimbus Roman 和 TeX Gyre Termes 字体名可选择新的 `SmartPDF Termes` 替代族。配置 `SMARTPPT_TERMES_FONT_DIR`，提供 CTAN TeX Gyre Termes 2.004 的四个完整文件 `texgyretermes-regular.otf`、`texgyretermes-bold.otf`、`texgyretermes-italic.otf`、`texgyretermes-bolditalic.otf`。来源：[CTAN](https://ctan.org/pkg/tex-gyre-termes)；下载目录：`https://mirrors.ctan.org/fonts/tex-gyre/opentype/`。文件大小与 SHA-256 固定于 `src/smartppt/termes_font.py`，运行时不联网下载；缺少整族时保持既有策略，修改后的字体字节不能通过渲染/嵌入校验。

以固定 FontTools 将完整 CFF 转为重命名的 TrueType，保留 Unicode、布局表、字距和行度量、斜体/下划线信息；曲线整数化可能带来一个字体单位的极值差异，仍须通过实际像素门槛。渲染器与 EOT 嵌入共享相同字节，不复制上传字体。保留原 `fsType=12` 可编辑嵌入权限，不将它改成无限制安装权限。完整 GFL、LPPL 与变更清单包含于运行包及交付字体；不是原字体完全一致或各 Office 客户端已验收的承诺。

区域恢复增加一次受限的逐字符高度中位数校准，只追加新通过的完整词语；旋转、Unicode 展开、来源不明确或不匹配时不使用。既有文字、原始整页误差基准、局部像素与位置门槛保持不变。

独立固定网格墨迹诊断（POSIX + Poppler，仅诊断，不替换严格边框或转换门槛）：

```sh
.venv/bin/python tools/public-native-ink.py --source /path/to/new-run/fw9/source.pdf --rendered /path/to/new-run/fw9/candidate.pdf --output /path/to/new-ink-review.json
```

该工具不进行图像配准、平移或缩放；用几何位置而不是相同文本选择对应词。邻近词重叠、边界不纯、无墨迹或像素网格不一致时明确弃权。仅有少量可独立观察的词不能证明整页准确。原有 Poppler 严格边框失败仍保留：完整字体的 ascent/descent 与 PDF 子集不同可能改变解析框，但不能因此压缩字体指标、遮蔽重音符号或豁免真实错位。输入、页数、像素、词数及 XML 提取都有显式上限；缺少 POSIX 文件大小限制时拒绝执行。

另有两次受限的 Base Sans 替代字体追加尝试，仅针对明确的 `Helvetica` 或 `HelveticaNeueLTStd-Roman` 常规字形；这不是源字体完全一致的声明。只有通过既有位置、局部及整页像素检查的新词才会追加，已验证文字与原始误差基准保持不变，报告明确标记字体替代。


碰撞词簇增量恢复：保护框相交的2–8个词作为一个不可拆分的候选，少于160个字符、范围不超过200×50pt。近邻行仍是独立原始文本框，不拼接数字、补写空格或跨越未知源字符。完整源字符/对象归属、原始墨迹不重叠、全部逐词几何/像素门槛、原有区域像素不变与原始整页基准均必须满足；任一成员失败则整簇保留原图。裁剪页障碍坐标与源区域统一；生成字符和不安全邻居不能参与。最多四次增量策略尝试，已经不可用的字体/校准路径不重复尝试。此机制只增加经验证的可编辑部分，不代表全文可编辑或通用上线验收。

### 多分辨率诊断及字体一致性

`tools/public-native-multires.py` 在144/216/288/432 DPI使用同一整数点坐标ROI，对候选与零可提取文字的原图基线分别测量。输入先做有界、带哈希的私有快照；固定几何配对和邻域，保留弃权，不配准、不减去基线误差、不输出验收结论。ROI策略与原216 DPI工具不同，不能覆盖或替代原结果。POSIX/Poppler资源上限及总600秒预算适用。

```sh
.venv/bin/python tools/public-native-multires.py --source /path/to/source.pdf --rendered /path/to/candidate.pdf --baseline /path/to/image-only-baseline.pdf --output /path/to/new-multires.json
```

CMU字体渲染现在使用与EOT嵌入相同、经过固定哈希验证的完整别名安全TTF，不再把原始目录直接交给Fontconfig。已使用CMU族但配置不完整或字体被修改时，渲染明确失败，不能静默替换后继续验证。CMU和Noto转换保留源字体时间戳，避免同一输入在不同时间产生不同字体字节。该一致性保护不代表跨Office客户端验收。

CMU Typewriter Text另按已验证源face的真实pitch元数据写入OOXML提示：regular/italic为49，bold/boldItalic为50，在本次Linux LibreOffice实测中修正regular被选成bold的问题。不是改变字形、字重、advance或套用于其他字体的规则。回归同时核对嵌入前后PDF每个可见字符的真实字体身份，不能只检查字体文件已存在。

### 可选的CMU Light增量替代

配置目录中的CMU 0.7.0 `cmunbtl.ttf`通过固定长度与SHA-256验证后，可生成独立常规族`SmartPDF CMU Typewriter Light`。完整字体除命名/许可声明及必要校验和外保留原始表字节，不改变字形、间距、字重、字体度量或嵌入权限；原始字体不随仓库提交。渲染与EOT嵌入使用同一份完整派生TTF，并在实际使用前重新核验输入。

只有明确的常规`SFTTdddd`、`CMtt数字`或`CMU Typewriter Text`来源，且已映射为CMU Typewriter Text、无粗斜体/旋转、原文及NFKC字符均被字体覆盖，才可尝试。最后最多四次增量候选（两种校准，各尝试0或0.1pt纵向偏移），不能替换或删除先前已验证文字；来源、顺序、逐词位置、局部及原始整页像素和已保留区域像素检查全部沿用。缺失/篡改/不支持时保留原结果。这是明确标记的替代字体，不是源字体完全一致的声明，也不代表其他客户端已验收。

Light增量另须通过独立Poppler保护：最终组合输出在144/216/288/432 DPI逐区域MAE、前景误差及最大墨迹边界误差均不得比先前保留原图更差；编辑区域外全页像素必须完全相同。独立验证使用跨候选共享的120秒截止预算，页面/像素/区域/输入及子进程输出均有界；Office渲染仍受原有单次时限约束，可能晚于该截止返回，但过期后不得通过新候选。缺少Poppler、资源超限、尺寸不一致、脏边界或无法明确观测均拒绝追加。这不取消原PDFium局部0.035/0.16、2pt位置与原始整页门槛，也不把跨引擎比较解释为字形完全相同。0.1pt只是需要逐次验证的有限候选，不是通用修复常数。

### Inferred separator recovery

A final additive collision-component pass can omit a single PDFium-generated terminal ASCII separator from a copied source run, never real spaces or visible glyphs. Exact source ownership remains mandatory. Complete components must pass independent Poppler nonregression at 144/216/288/432 DPI, then be rebuilt and verified again; uncertain regions remain graphic. See [round 20 evidence](../../docs/pdf-to-ppt-quality-round20-2026-11-13.md).
