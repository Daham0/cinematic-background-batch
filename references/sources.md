# 资料来源与阅读状态

整理日期：2026-09-15。知识库为原创工作流程归纳，模板为针对本任务写作的设计建议，尚未用用户素材实测。未复制完整教程，不把官方营销措辞当效果保证。

| 一手资料 | 用途 | 状态 |
|---|---|---|
| [Runway Edit Studio](https://help.runwayml.com/hc/en-us/articles/51683104370451-Creating-with-Edit-Studio) | 关键帧预览后应用到视频 | 已读正文；规格会变化 |
| [Aleph 2.0提示词](https://help.runwayml.com/hc/en-us/articles/52150503729171-Aleph-2-0-Prompting-Guide) | 简洁编辑、背景与灯光 | 已读正文 |
| [Runway换环境教程](https://academy.runwayml.com/tutorial/change-environments-with-aleph) | 官方教程入口 | 已核对页面，未完整观看视频 |
| [Google图像提示词](https://developers.googleblog.com/en/how-to-prompt-gemini-2-5-flash-image-generation-for-the-best-results/) | 摄影描述、商业图、编辑与一致性局限 | 已读正文，借鉴写法，不作为当前型号结论 |
| [Seedream中文提示词](https://www.volcengine.com/docs/82379/1829186) | 中文图像编辑入口 | 仅官方摘要，动态正文未完整读取 |
| [Seedance 2.5](https://seed.bytedance.com/zh/seedance2_5) | 视频型号与参考/编辑定位 | 已读产品页，不证明用户账户/API能力 |
| [即梦](https://jimeng.jianying.com/) | 图像、智能画布、视频入口 | 已读公开说明，未查看用户登录界面 |
| [IC-Light](https://github.com/lllyasviel/IC-Light) | 图像重打光 | 已读正文，不能推断视频逐帧稳定 |
| [Adobe Roto Brush](https://helpx.adobe.com/after-effects/desktop/roto-brush-and-refine-matte/roto-brush/roto-brush-refine-matte.html) | 发丝、运动模糊、边缘染色和抖动 | 已读相关正文 |
| [RVM中文](https://github.com/PeterL1n/RobustVideoMatting/blob/master/README_zh_Hans.md) | 有时间记忆的视频抠像 | 已读正文，未安装模型测试 |
| [ByteTrack](https://arxiv.org/abs/2110.06864) | 镜头内轨迹关联 | 已读摘要，轨迹不等于跨片身份 |
| [ArcFace](https://arxiv.org/abs/1801.07698) | 区分比对与跟踪 | 已读摘要，不内置识别或阈值 |
| [NIST FRTE](https://pages.nist.gov/frvt/html/frvt11.html) | 相似度阈值与误匹配/漏匹配 | 已核对官方说明 |
| [DeepSeek V2.5](https://huggingface.co/deepseek-ai/DeepSeek-V2.5) | 区分文本/代码与视频型号 | 已读模型卡 |

用户抖音链接未能读取，未观看；本知识库不是该视频的转录或复刻。Wan 3.0是用户确认的候选，尚未核实该账户的入口、联合参考和自动化API。

本包不含第三方模型权重或代码。后续引入组件时，分别核对代码、权重与托管服务的实际使用条件。

## 1.1用户参考与新增规则依据

2026-09-15用户明确要求：首帧仅IMAGE2.0/2.5原生1K；视频模型/分辨率/画幅由用户选；人物数、造型数、是否换造型、目标背景先确认；完整带背景首帧再确认。这里的硬门来自用户工作要求，不冒充平台通用规范。

本次三张截图均已逐张查看，原样作为风格参考保存在assets/style-references；画面可见灯光与置景的观察见[tvc-art-direction.md](tvc-art-direction.md)。未声称知道完整广告拍摄参数或看过该广告完整视频。

IMAGE2.0/2.5命名的在线检索未核实到用户实际账号/API的确切映射，故未预填模型ID或原生1K宽高。执行时必须按实际入口验证，检索结果或模型名称本身不等于该账号具有指定能力。
