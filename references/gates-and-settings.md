# 人物、造型、背景与规格清单

## 开始时集中收集

| 必填项目 | 需要明确 | 不能自行推断 |
|---|---|---|
| 人物 | 用户标注的人物P01/P02及总数 | 戴帽就等于另一个人 |
| 角色 | A/B角色与人物对应、每片同框关系 | 角色数等于演员数 |
| 原造型 | 衣服、帽子、发型、配饰的不同组合 | 不同视频同一衣服就证明同一现实身份 |
| 目标造型 | 各原造型保留或更换，目标设计及允许部位 | “高级”就允许换衣、换脸 |
| 背景 | 每组具体空间、材质、灯光、摄影构图与融合 | 只因用户说换背景就自动选办公室 |
| 视频 | 用户选实际模型、分辨率、画幅 | 自动选Wan、1080p或16:9 |

先查看全批原帧、用户标签和多视角资料，提出可核对的清单。遇到未知人物或遮挡，不作现实身份断言，把未定对应关系集中让用户标注。获授权的衣帽变化只作用于对应角色和片段，不能自动传播到其他造型。

## creative_brief结构

配置保留`roles`、`role_assignments`、`scene_groups`、`clip_groups`。新增`creative_brief`：

```json
{
  "people": [{"person_id":"P01","label":"用户确认的演员一"}],
  "role_people": {"A":"P01","B":"P01"},
  "looks": [
    {"look_id":"L01","person_id":"P01","source_description":"黑帽、白T恤","change":"keep","change_scope":[],"target_look_id":"L01","target_description":"黑帽、白T恤","reference_files":[]},
    {"look_id":"L02","person_id":"P01","source_description":"不戴帽、灰衬衫","change":"change","change_scope":["clothing"],"target_look_id":"T02","target_description":"不戴帽、深蓝亚麻衬衫，款式由用户参考确定","reference_files":[]}
  ],
  "clip_looks": {"实际clip_id":{"A":"L01","B":"L02"}},
  "backgrounds": [{"group_id":"restaurant","description":"深木饰面餐厅，人物后方留走道与用餐区纵深","materials":["深木","哑光织物","少量玻璃"],"lighting":"左前侧大柔光塑形，弱补光保留层次，后方暖色吊灯和较冷环境光","photography":"沿用原机位与人物尺度，前中后景分层，不增加低角度或倾斜机位","integration":"脸、颈、衣服同光向，桌椅接触阴影连续，玻璃反射与环境一致","reference_files":[]}]
}
```

以上是结构示例，实际人物关系、换装和背景都需用户确认。`change=keep`要求原/目标描述及ID相同；`change=change`需明确`change_scope`，可选clothing、hat、accessories、hairstyle、makeup。不存在改五官、年龄或表演的授权选项。目标造型ID对应统一设计，可让多个原造型映射同一个目标造型，但必须同人且同一描述。

`brief`命令计算视频数、人物数、角色数、原造型数、目标造型数与背景组数；检查每片每角色对应关系完整。用户确认这张清单后才运行`confirm-brief`。

## IMAGE与1K的硬规则

允许的用户型号标签只有`IMAGE2.0`、`IMAGE2.5`。实际平台和API型号必须先核实映射，不能只因任何模型带2.0或2.5就放行。没有确定用户所指平台时先核实，不能静默归到即梦、GPT、Qwen或其他系列。

`image_output.resolution`硬编码检查为`1K`；宽高与目标画幅必须匹配，并存在于该真实模型已核实的`native_outputs`列表。1K采用所选平台真实的原生档位及尺寸定义，不虚构全部平台都用同一组宽高。`quality=low`与输出分辨率不是同一件事；用户要低分辨率审图，不要求把人脸故意画糊。不能用2K/4K原生输出再缩小来合规。

`providers.image`需填platform、真实model、model_family、verified_model、verified_model_family、verification.evidence/checked_at及native_outputs。最后两个verified字段记录核实过的映射，不能根据想用的型号盲填。`native_outputs`每项严格为resolution、aspect_ratio、width、height四个键。

## 视频选择卡

先根据实际入口列出可用组合，每项写清模型/模式、支持画幅、分辨率与真实宽高；用户选择后才填`providers.video`、`video_output`和`canvas`。不把示例分辨率写成默认选择。核实所选模式真的能保留输入视频表演；普通图生视频不能直接替代口播编辑。

`canvas.framing`为preserve、background_extend或crop_approved。preserve与实际抽取原帧显示比例核对，含手机旋转信息；换比例通常需扩背景或经批准裁切。扩背景不重塑/拉伸人物；裁切须先展示人物、手、产品和字幕安全范围。

仅图片项目明确`deliverable=frames`，不问视频模型，但仍由用户选画幅。不得把视频项目偷偷改成frames绕过G0。

## 执行前后

`check`检查当前关卡；`begin --request`对照实际请求规格，绑定提示词、输入文件、型号、分辨率和画幅；`finish --receipt`记录提供方原生规格并检查结果文件像素。请求与回执不能由“希望它用了哪个模型”反推填写。外部入口不能返回/确认规格时阻塞，报告能力缺口。

这些记录不是不可篡改认证：脚本不证明消息作者、实际远端模型或画面内容。执行代理负责依据真实消息、工具参数与回执填入，不能绕过检查或伪造文件。通过规格验收后仍须展示完整合成首帧让用户看。
