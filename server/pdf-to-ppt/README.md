# PDF → PPT 实验服务

独立的本机验收服务，尚未接入生产网站。默认可编辑引擎必须显式配置；所有可编辑输出为 `needs_review`，不承诺无损还原。图形仍可能是图片，OCR 不确定区域保留原图。

## 已实现

- 固定 Stirling 3.2.2 Java API 适配；不自动重试转换 POST，不自动切换云服务。
- PDFium 原生文字和坐标修复，包含字体矩阵缩放、页面旋转、字重和东亚字体标记。
- 内容检查保留有可信文字/数字的原生表格；复杂图形采用原稿栅格，不把图片冒充可编辑图表。
- PP-OCRv6 medium 官方 ONNX 检测/识别；Unlimited OCR 2 可选离线交叉校验。分歧、低置信度、非均匀背景、倾斜区域保留原图并提示复核。
- LibreOffice 独立渲染原结果与候选结果，逐页拒绝会使视觉差异明显增大的坐标修复。像素分数仅为筛查，不是正确率。
- 上传限制、独立 worker、下载令牌、取消、过期清理；POSIX 取消会终止 worker 的 OCR 子进程组。

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

`SMARTPPT_STIRLING_KEY` 为可选的服务端 API key。HTTP 仅支持回环地址，远端引擎需 HTTPS。模型目录可通过 `SMARTPPT_OCR_MODELS` 改写。模型下载脚本固定 URL、版本、大小及 SHA-256；权重不进 Git，运行时无需模型 API。

字体目录需提供实际字体。这里的 OCR 字号校准使用 Arial/Arial Bold 度量；其他字体/平台需重新验收，缺失度量会报告。Noto Sans SC 可使用仓库已有 OFL 字体；输出明确写入东亚字体，但没有嵌入字体，因此接收端也需字体或合适替代。不得默认复制受限系统字体到服务器。

## 可选的 Unlimited OCR 2

当前实测是 Apple Silicon 的 MLX 0.32.4 / mlx-vlm 0.7.12，使用已验证 BF16 转换权重。它是可选的独立环境，Paddle CPU 路线不依赖 MLX。Linux/NVIDIA 路线尚未做本项目部署验收。

配置 `SMARTPPT_OCR_VERIFIER_PYTHON`、`SMARTPPT_OCR_VERIFIER_RUNNER`（本目录 `ocr/unlimited_runner.py`）和 `SMARTPPT_U2_MODEL`（离线模型目录）即可启用。脚本禁用在线模型访问和远程代码执行。不要在通用 Linux 环境安装 Mac MLX 包。

固定模型：`mlx-community/Unlimited-OCR-2-bf16`，revision `850d1e483f5a82a0597f0a45aac31b07ba840df2`；官方底座 `baidu/Unlimited-OCR-2`，revision `0480966938291445591f69f08a13b041c073a96a`。模型许可及依赖见本目录 `THIRD_PARTY.md`。

## 验证与边界

```sh
.venv/bin/python -m pytest -q
```

测试全部使用程序生成的合成输入，不依赖真实用户文档或线上 OCR。公开样本、权重和真实渲染证据只保存在本机；批量实测结论见仓库 `docs/pdf-to-ppt-ocr-improvement.md`。

这是实验模块，不接生产路由、不修改现有 Office→PDF 引擎、不部署。公开发布仍需网站鉴权/配额、Linux 固定镜像、并发负载、PowerPoint/WPS、字体交付、扫描质量与真实设备验收。OCR 脚本退出和取消本机 worker 不代表远端 Stirling 的任务也已取消；引擎临时文件清理需另外验收。
