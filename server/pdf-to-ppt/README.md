# PDF → PPT 实验服务

独立的本机验收服务，尚未接入生产网站。默认可编辑引擎必须显式配置；所有可编辑输出为 `needs_review`，不承诺无损还原。图形仍可能是图片，OCR 不确定区域保留原图。

## 已实现

- 固定 Stirling 3.2.2 Java API 适配；不自动重试转换 POST，不自动切换云服务。
- PDFium 原生文字和坐标修复，包含字体矩阵缩放、页面旋转、字重和东亚字体标记。
- 内容检查保留有可信文字/数字的原生表格；复杂图形采用原稿栅格，不把图片冒充可编辑图表。
- PP-OCRv6 medium 官方 ONNX 检测/识别；Unlimited OCR 2 与 OXR 可配置为离线区域复核。至少一个复核器确认位置和有序文字后才替换文字；配置两者时取共同通过的区域。无独立复核时保留扫描原图。
- 简单网格逐行逐列核对文字与数字，生成定位文本框；不宣称恢复原生 PowerPoint 表格。合并、空白、多行单元格或重叠/分歧区域保留图像。
- 支持均匀浅色纸张、估计文字颜色，并从已安装字体中比较拉丁文字的衬线、无衬线、等宽及粗体字形。字体仍为估计和替代。
- 按词恢复复杂原生版面，保留源字符、数字及对象来源；失败区域保留原稿。支持经独立渲染验证的四方向文字。异常 Unicode 映射只允许隔离区域恢复，不猜测未知字形。
- 对实际使用的、通过固定 SHA-256 校验的 Noto Sans SC，生成完整静态 EOT 字体并嵌入 PPT；保留完整 OFL 通知、可新增字符。中英文交界与扫描小字号文字可按实测位置拆分，避免客户端自动字距差异。失败时保留原文件并报告原因。
- LibreOffice 独立渲染原结果与候选结果，逐页拒绝会使视觉差异明显增大的坐标修复。像素分数仅为筛查，不是正确率。
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

# 在分别继承以上环境的两个终端中运行：
PYTHONPATH=src .venv/bin/python -m uvicorn smartppt.api:app --host 127.0.0.1 --port 8765
PYTHONPATH=src .venv/bin/python -m smartppt.worker
```

`SMARTPPT_STIRLING_KEY` 为可选的服务端 API key。HTTP 仅支持回环地址，远端引擎需 HTTPS。模型目录可通过 `SMARTPPT_OCR_MODELS` 改写。模型下载脚本固定 URL、版本、大小及 SHA-256；Paddle 启动时以源码中的 `ocr/model-manifest.json` 独立复核必需文件，不信任模型目录自报的 `provenance.json`。权重不进 Git，运行时无需模型 API。识别字典写入任务临时目录并在整批识别后清理，运行时不写模型目录，可将模型只读挂载。

字体目录需提供实际字体。这里的 OCR 字号校准使用 Arial/Arial Bold 度量；其他字体/平台需重新验收，缺失度量会报告。`SMARTPPT_CJK_FONT` 应指向仓库已有 Noto Sans SC（SHA-256 `a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da`）。嵌入使用固定 FontTools 4.68.0，只处理该许可开放的字体；不复制系统字体或任意上传 PDF 中的字体。未使用 Noto 的保留页面不会自动变成可移植字体页面。字体嵌入不代表原字体完全一致，也不代表所有客户端布局已通过。

最新验证及未通过项见 [本轮质量报告](../../docs/pdf-to-ppt-quality-round2-2026-11-12.md)。本模块仍是独立验收服务，尚未达到通用上线标准。

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

扫描文字现在估计 Arial、Times New Roman、Courier New 的常规、粗体、斜体及粗斜体。配置渲染器后，以实际 Office 字形校准字号、基线和字距；小角度行先逆旋转测量。候选必须同时满足几何门槛和不降低页面比较结果，否则恢复校准前的文本框。校准位图最长边限制为 2400px。字体仍未嵌入，中文细字重与不同客户端字体替换仍需人工检查。

原生 PDF 的相邻字符对象仅在源顺序、字体/样式、基线、间距和缺口内容均满足要求时合并。生成的空白边界可以依据位置修复；所有非空白源字符必须保持原序完全一致。列间距、不同样式、缺失字符和真实换行不能被拼接掩盖。局部恢复仍按完整原始对象验证，不因合并文本框而放宽删除背景的条件。

真实 Office 区域恢复验收可通过 `SMARTPPT_TEST_RENDERER=/absolute/path/to/soffice .venv/bin/python -m pytest -q` 启用；未配置时该验收测试明确跳过，普通单元测试继续运行。服务器字体仍需单独交付与验收，不引入在线 OCR API 或新的付费依赖。

## 验证与边界

```sh
.venv/bin/python -m pytest -q
```

测试全部使用程序生成的合成输入，不依赖真实用户文档或线上 OCR。公开样本、权重和真实渲染证据只保存在本机；批量实测结论见仓库 `docs/pdf-to-ppt-ocr-improvement.md`。

本轮代码审查、独立渲染证据、通用上线质量目标及未完成门禁见 `docs/pdf-to-ppt-review-2026-11-11.md`。新增测试不替代主站累计回归和真实模型/生产运行时验收。

后续 400 个公开输入、固定基准、真实三模型扫描回归、文字准确率与审查修复见 `docs/pdf-to-ppt-acceptance-2026-11-12.md`。当前生成成功率已较高，但真实文档的可编辑文字完整性和扫描文字位置精度仍未达到通用上线标准。

新的本地准确率评估器支持位置绑定的字符编辑距离、缺失/额外文字、数字区域一致性和几何误差。输入必须注明独立参考来源；未知结果保留 `null`，整页图片不能计为可编辑成功：

```sh
PYTHONPATH=src .venv/bin/python -m smartppt.acceptance --input /path/to/local-evaluation.json --output /path/to/local-report.json
```

输入结构为 `documents` 数组，每份包含 `eligible`、`generated` 和 `pages`；每页包含 `truth`、`predictions`、`truth_verified`。参考区域含 `id/text/bbox`，预测含 `text/bbox`，bbox 使用同一页坐标的 `[left,top,right,bottom]`。可提供唯一整数 `reading_order` 表示独立渲染器的字符顺序，区域分配始终使用几何。默认位置阈值 2pt。`structure_verified`、`render_verified` 未完成时，文档级完整成功率仍为未知；已验证成功数量的下限单独提供。不要把数据集的自动提取参考文本称为人工 OCR 真值。

这是实验模块，不接生产路由、不修改现有 Office→PDF 引擎、不部署。公开发布仍需网站鉴权/配额、Linux 固定镜像、并发负载、PowerPoint/WPS、字体交付、扫描质量与真实设备验收。OCR 脚本退出和取消本机 worker 不代表远端 Stirling 的任务也已取消；引擎临时文件清理需另外验收。
