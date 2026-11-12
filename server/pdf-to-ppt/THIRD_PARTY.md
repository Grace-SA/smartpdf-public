# 第三方组件与模型

本模块源码不打包模型、字体二进制或第三方可执行文件。输出 PPT 可以包含经过校验的 Noto Sans SC 完整字体，字体元数据内保留完整版权和 OFL 许可。以下是本轮核对的主要组件；部署镜像仍需保留完整传递许可及通知。

| 组件 | 本轮用途 | 上游许可/来源 |
| --- | --- | --- |
| Stirling core 3.2.2 | 原始 PPTX | 复用仓库已固定审核的 core；`config/word-core.stirling-3.2.2.json` |
| PP-OCRv6 medium ONNX | 文本定位/识别 | 官方模型卡标 Apache-2.0；固定文件及 hash 见 `ocr/model-manifest.json` |
| PP-LCNet_x1_0_doc_ori ONNX | 可选 0/90/180/270° 页面方向判断 | [Paddle 官方模型](https://huggingface.co/PaddlePaddle/PP-LCNet_x1_0_doc_ori_onnx/tree/7330ab7039123e46af2dc03154b9969aa412c61d)，Apache-2.0；固定文件见 `ocr/orientation-manifest.json` |
| RapidOCR 3.10.0 | 检测/识别编排 | Apache-2.0，[RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) |
| ONNX Runtime 1.31.1 | CPU 推理 | MIT，[microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) |
| Unlimited OCR 2 | 可选结构/内容复核 | MIT，[官方模型卡](https://huggingface.co/baidu/Unlimited-OCR-2/tree/0480966938291445591f69f08a13b041c073a96a) |
| SoMark OXR 1.0 / D-FINE | 可选区域、阅读顺序、简单表格内容复核；本地推理 | OXR 为 Apache-2.0 加附加条款；D-FINE 有独立 Apache-2.0 通知。见 [OXR 许可](ocr/licenses/OXR-LICENSE.txt)、[通知](ocr/licenses/OXR-NOTICE.txt)及[官方仓库](https://github.com/SoMarkAI/OXR) |
| MLX / mlx-vlm | 可选 Mac 推理 | 各自 MIT；不列入必需 CPU 运行环境 |
| pypdfium2 / PDFium | PDF 解析、几何和渲染 | 保留绑定包与 PDFium 二进制的许可证/第三方通知；[许可说明](https://github.com/pypdfium2-team/pypdfium2#licensing) |
| pypdf / python-pptx | 预检 / OOXML | BSD-3-Clause / MIT |
| Noto Sans SC | 中文替代字体及完整字体嵌入 | SIL OFL 1.1，仓库 `vendor-fonts/NotoSansSC-OFL.txt`；运行包保留 `src/smartppt/OFL-NotoSansSC.txt` |
| Noto Serif SC | 可选宋体/明体替代及完整字体嵌入 | SIL OFL 1.1，[固定上游许可](https://github.com/notofonts/noto-cjk/blob/985fa52c81c1d6692ccdd82bc3656e8fb932fd89/Serif/LICENSE)；字体内 Adobe 版权及完整许可保留于 `src/smartppt/OFL-NotoSerifSC.txt`，文件与哈希见 README |
| FontTools 4.68.0 | 将固定可变字体实例化为静态字体，保留 Unicode 字形、许可和完整字符集 | MIT，[官方项目](https://github.com/fonttools/fonttools) |
| LibreOffice | 独立渲染检查 | 按实际发行版许可及第三方通知部署，未捆绑 |

PaddleOCR-VL-1.6 已检查官方模型卡（Apache-2.0），本轮未推理，不计入效果比较。项目方已确认目前满足 OXR 免费使用门槛，本轮据此接入；相关页面底部保留链接到官方仓库的 **Powered by SoMark OXR**。这不改变上游条款；分发上游代码、权重或镜像时须连同其完整许可和传递通知交付。本目录只包含适配器、校验清单和许可通知，不包含上游代码或权重。不要将其描述为无条件 Apache-2.0。

OXR 代码、MLX 权重和 D-FINE 权重的固定版本/哈希见 `ocr/oxr-manifest.json`。上游源代码来自 `SoMarkAI/OXR`，MLX 权重来自 `bxespinozar/OXR-1.0-mlx-bf16`，检测权重来自 `SoMarkAI/OXR-1.0`。部署还需保留模型仓库各自的许可证和通知。此转换模块使用 PDFium，不调用 PyMuPDF；主站原有独立验收脚本的测试依赖另行管理。

本地新增验收使用 [DocLayNet](https://github.com/DS4SD/DocLayNet) 的 test split，保留其 [CDLA-Permissive-1.0 许可](https://github.com/DS4SD/DocLayNet/blob/main/LICENSE)、来源、抽样规则与文件哈希。数据、参考文本及渲染图不进入仓库。其版面标注由人工完成，附带文字单元由原生 PDF 提取，不能当作人工 OCR 转录准确率。OmniDocBench 与 FUNSD 的资料检查发现非商业研究限制，本轮未把它们用于商业产品验收。
