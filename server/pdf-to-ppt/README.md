# PDF → PPT 实验服务

独立的本机验收服务，尚未接入生产网站。默认可编辑引擎必须显式配置；所有可编辑输出为 `needs_review`，不承诺无损还原。图形仍可能是图片，OCR 不确定区域保留原图。

## 已实现

- 固定 Stirling 3.2.2 Java API 适配；不自动重试转换 POST，不自动切换云服务。
- PDFium 原生文字和坐标修复，包含字体矩阵缩放、页面旋转、字重和东亚字体标记。
- 内容检查保留有可信文字/数字的原生表格；复杂图形采用原稿栅格，不把图片冒充可编辑图表。
- PP-OCRv6 medium 官方 ONNX 检测/识别；Unlimited OCR 2 与 OXR 可配置为离线区域复核。至少一个复核器确认位置和有序文字后才替换文字；配置两者时取共同通过的区域。无独立复核时保留扫描原图。
- 简单网格逐行逐列核对文字与数字，生成定位文本框；不宣称恢复原生 PowerPoint 表格。合并、空白、多行单元格或重叠/分歧区域保留图像。
- 支持均匀浅色纸张、估计文字颜色，并从已安装字体中比较拉丁文字的衬线、无衬线、等宽及粗体字形。字体为估计和替代，不嵌入、不保证接收端完全一致。
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

字体目录需提供实际字体。这里的 OCR 字号校准使用 Arial/Arial Bold 度量；其他字体/平台需重新验收，缺失度量会报告。Noto Sans SC 可使用仓库已有 OFL 字体；输出明确写入东亚字体，但没有嵌入字体，因此接收端也需字体或合适替代。不得默认复制受限系统字体到服务器。

## 可选的 Unlimited OCR 2

当前实测是 Apple Silicon 的 MLX 0.32.4 / mlx-vlm 0.7.12，使用已验证 BF16 转换权重。它是可选的独立环境，Paddle CPU 路线不依赖 MLX。Linux/NVIDIA 路线尚未做本项目部署验收。

配置 `SMARTPPT_OCR_VERIFIER_PYTHON`、`SMARTPPT_OCR_VERIFIER_RUNNER`（本目录 `ocr/unlimited_runner.py`）和 `SMARTPPT_U2_MODEL`（离线模型目录）即可启用。脚本禁用在线模型访问和远程代码执行。不要在通用 Linux 环境安装 Mac MLX 包。

固定模型：`mlx-community/Unlimited-OCR-2-bf16`，revision `850d1e483f5a82a0597f0a45aac31b07ba840df2`；官方底座 `baidu/Unlimited-OCR-2`，revision `0480966938291445591f69f08a13b041c073a96a`。模型许可及依赖见本目录 `THIRD_PARTY.md`。

启动前使用源码中的 `ocr/u2-manifest.json` 校验权重、配置、模板与 tokenizer 的大小和 SHA-256；额外的可加载配置或权重也会拒绝。模型目录必须是已完整物化的独立目录，不能使用指向目录外部的 Hugging Face 缓存符号链接。新清单的权重哈希来自固定 revision 的 Git LFS 元数据，配置/tokenizer 字节另行下载并核对 Git blob；本轮未下载权重或重跑 MLX 推理，新增校验不能代替模型实测。

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

通过原有独立模型区域复核的小角度扫描行（最多 8°）可在识别框内校正字体度量，按原角度生成旋转文本框，原页面不整体旋转。固定 3° 样本已验收；并不保证范围内任意模糊、透视或复杂背景都通过。90° 横转、竖排、模型分歧和无法安全擦除的区域保留图像。现有数字/字符校验不因提高可编辑覆盖率而关闭。

真实 Office 区域恢复验收可通过 `SMARTPPT_TEST_RENDERER=/absolute/path/to/soffice .venv/bin/python -m pytest -q` 启用；未配置时该验收测试明确跳过，普通单元测试继续运行。服务器字体仍需单独交付与验收，不引入在线 OCR API 或新的付费依赖。

## 验证与边界

```sh
.venv/bin/python -m pytest -q
```

测试全部使用程序生成的合成输入，不依赖真实用户文档或线上 OCR。公开样本、权重和真实渲染证据只保存在本机；批量实测结论见仓库 `docs/pdf-to-ppt-ocr-improvement.md`。

本轮代码审查、独立渲染证据、通用上线质量目标及未完成门禁见 `docs/pdf-to-ppt-review-2026-11-11.md`。新增测试不替代主站累计回归和真实模型/生产运行时验收。

这是实验模块，不接生产路由、不修改现有 Office→PDF 引擎、不部署。公开发布仍需网站鉴权/配额、Linux 固定镜像、并发负载、PowerPoint/WPS、字体交付、扫描质量与真实设备验收。OCR 脚本退出和取消本机 worker 不代表远端 Stirling 的任务也已取消；引擎临时文件清理需另外验收。
