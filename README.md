# 口播批量换背景 · 商业场景与灯光批处理 Skill

> 作者：Daham ｜ 版本：1.1

批量为**单人 / 双人固定机位口播**视频批量更换真实 TVC 广告背景、灯光，以及用户明确批准的造型。保留原视频的表演、五官结构、口型、表情、眨眼、动作、原音轨与时序，只允许合理的曝光、白平衡与重打光调整。

## 功能特性

- 批量口播换背景：按镜头拆分素材，逐视频建立人物 / 角色 / 造型对应表
- TVC 广告级布光：可解释主光、克制补光、实景光源、前中后景、真实材质与接触阴影
- 硬性关卡控制：B0 / G0 / M1 / G1 / G2 / Q1 六道关卡，未确认不放行
- 生图硬约束：仅 IMAGE2.0 / IMAGE2.5 原生 1K，禁止替代模型或高分辨率缩水冒充
- 完整知识库：工作流、提示词设计、摄影置景、布光合成、平台适配、质量验收等 10 份文档
- 配套脚本：抽帧、关卡记录、审图页生成、本地测试

## 目录结构

```
├── skill.md                 # 技能主入口（必读）
├── agents/
│   └── openai.yaml          # 显示信息配置
├── assets/
│   ├── icon.svg
│   ├── project-config.json
│   ├── prompt-templates.json   # 14 套原创提示词模板
│   ├── style-presets.json      # 6 套场景布光预设
│   └── style-references/       # 风格参考图（PNG）
├── references/                 # 10 份知识文档
│   ├── workflow-gates.md
│   ├── gates-and-settings.md
│   ├── roles-and-references.md
│   ├── prompt-design.md
│   ├── tvc-art-direction.md
│   ├── lighting-and-compositing.md
│   ├── provider-adapters.md
│   ├── quality-control.md
│   ├── cli.md
│   └── sources.md
└── scripts/                   # 本地辅助脚本
    ├── requirements.txt
    ├── batch_guard.py
    ├── extract_frames.py
    ├── review_board.py
    └── test_tools.py
```

## 安装

将本仓库整体导入支持文件夹技能的工具（如 Marvis），按工具规定放入技能目录，**不要只复制 skill.md**。

依赖：Python 3.10+、Pillow、FFmpeg/FFprobe

```bash
python3 -m pip install -r scripts/requirements.txt
python3 scripts/test_tools.py
```

## 使用

可这样调用：

> 使用 $cinematic-background-batch。这里有一批口播视频、人物多视角照片和风格参考。先整理人物、角色、造型与逐片对应表，让我确认是否换造型及目标背景。让我选择视频模型、分辨率与画幅，再用 IMAGE2.0 或 IMAGE2.5 原生 1K 制作带人物的完整首帧样图。样图确认后批量出全部首帧，全部首帧再次确认后再处理视频。

## 关卡规则

| 关卡 | 放行条件 |
|---|---|
| B0 人物/造型/背景 | 用户确认人物数、角色数、原/目标造型数、逐视频对应关系、目标背景与布光 |
| G0 规格选择 | 用户明确选择视频模型、分辨率、画幅及构图适配 |
| M1 生图硬约束 | 仅 IMAGE2.0 / IMAGE2.5 原生 1K，核实真实型号映射 |
| G1 代表合成首帧 | 用户看过带人物、背景、灯光、获准造型的完整样图并选定 |
| G2 全部合成首帧 | 用户逐条看过完整首帧并选定，之后才开始视频任务 |
| Q1 动态技术验收 | 短样通过原脸、表演、边缘、灯光、场景、音轨验收后才批量 |

修改人物 / 造型 / 背景需重审 B0 和首帧；修改视频规格需重选 G0 并重审首帧；不允许伪造用户确认记录。

## 执行边界

本包提供工作流、知识库与本地辅助脚本，**不包含**图像/视频服务的 API 适配器、账号、密钥或模型权重。实际生成需用户提供可明确指定 / 核实模型与规格的生成入口。

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。
