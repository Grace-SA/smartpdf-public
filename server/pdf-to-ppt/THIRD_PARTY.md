# 第三方组件与模型

本模块不打包模型、字体或第三方可执行文件。以下是本轮核对的主要组件；部署镜像仍需保留完整传递许可及通知。

| 组件 | 本轮用途 | 上游许可/来源 |
| --- | --- | --- |
| Stirling core 3.2.2 | 原始 PPTX | 复用仓库已固定审核的 core；`config/word-core.stirling-3.2.2.json` |
| PP-OCRv6 medium ONNX | 文本定位/识别 | 官方模型卡标 Apache-2.0；固定文件及 hash 见 `ocr/model-manifest.json` |
| RapidOCR 3.10.0 | 检测/识别编排 | Apache-2.0，[RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) |
| ONNX Runtime 1.31.1 | CPU 推理 | MIT，[microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) |
| Unlimited OCR 2 | 可选结构/内容复核 | MIT，[官方模型卡](https://huggingface.co/baidu/Unlimited-OCR-2/tree/0480966938291445591f69f08a13b041c073a96a) |
| MLX / mlx-vlm | 可选 Mac 推理 | 各自 MIT；不列入必需 CPU 运行环境 |
| pypdfium2 / PDFium | PDF 解析、几何和渲染 | 保留绑定包与 PDFium 二进制的许可证/第三方通知；[许可说明](https://github.com/pypdfium2-team/pypdfium2#licensing) |
| pypdf / python-pptx | 预检 / OOXML | BSD-3-Clause / MIT |
| Noto Sans SC | 中文字体候选 | SIL OFL 1.1，仓库 `vendor-fonts/NotoSansSC-OFL.txt` |
| LibreOffice | 独立渲染检查 | 按实际发行版许可及第三方通知部署，未捆绑 |

PaddleOCR-VL-1.6 已检查官方模型卡（Apache-2.0），本轮未推理，不计入效果比较。OXR 已复核其现行附加商业条款，不作为无条件免费生产依赖，也没有复制其实现或权重。此模块没有使用 PyMuPDF，不继承此前研究环境里的该依赖。
