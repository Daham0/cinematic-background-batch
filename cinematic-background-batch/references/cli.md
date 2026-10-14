# 辅助脚本与文件约定

阅读顺序：环境 → 1抽帧 → 2配置/初始化 → 2.1人物背景与规格确认 → 3真实请求与回执 → 4展示样图 → 5记录G1 → 6全部首帧/G2 → 7视频/Q1 → 恢复与升级。

## 环境

Python 3.10或以上；抽帧需要FFmpeg与FFprobe在PATH；规格/构图检查与审图页需要Pillow（`python3 -m pip install -r scripts/requirements.txt`）。脚本不联网、不调用模型、不做人脸识别、不自动判断生成画面质量。项目文件放在用户指定的工作目录，切勿写进技能本身。

以下命令从技能根目录执行。把路径换成用户本次已提供的素材路径。JSON中的相对路径按其文件所在目录解析，源片索引由脚本生成绝对路径。支持含空格及中文路径。执行命令用参数数组或正确shell引用，不拼接未经引用的文件名。

## 1. 抽帧

```bash
python3 scripts/extract_frames.py --input /path/to/videos --out /path/to/project/frames --candidates
```

返回`index.json`，其中每条有clip_id、源路径及哈希、真实首帧、规格、音轨数和候选帧。真实首帧不seek；候选按指定时间附近抽取，`requested_time_s`不是精确PTS。脚本没有切镜、黑场、质量筛选或角色识别，这些由代理查看素材并另行处理。失败条目会报告并返回非零退出码，不能静默跳过。

## 2. 配置并初始化

复制`assets/project-config.json`到项目目录。填写`roles`与`scene_groups`字符串列表，给索引每个clip_id填写`role_assignments`角色列表和`clip_groups`场景组。将实际人物/场景/提示词文件放入`reference_files`，用于版本绑定。

角色示例：`roles: ["A", "B"]`；同演员分饰两角也用A/B，演员关系写在附加字段中。`role_assignments: {"v_x": ["A","B"]}`表示双人同框。上述文字仅示例，不是可直接执行的完整JSON。

按[gates-and-settings.md](gates-and-settings.md)填写creative_brief、canvas、image_output、video_output，以及真实模型映射/规格证据。人物、造型、背景未确定时先整理，不盲填。核实入口后才verified=true；IMAGE2.0/2.5与原生1K为硬限制；视频模式为已验证的video_edit或source_composite。

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json init --config /path/to/project/config.json --index /path/to/project/frames/index.json
```

初始化不要求外部生成服务已连接，因此可以先完成本地准备。生成check会检查角色、场景和服务核实状态。

## 2.1 B0清单确认与G0用户规格选择

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json brief
python3 scripts/batch_guard.py --project /path/to/project/state.json settings
```

向用户展示brief返回的人物/角色/造型数、逐片对应关系、换造型范围、每组具体背景，以及settings视频型号/分辨率/画幅与构图卡。把真实用户回复原文保存，两个门可引用同一次明确回复。用各卡实际哈希记录，不能预先假造：

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json confirm-brief --brief-hash ACTUAL_BRIEF_HASH --evidence-file /path/to/project/user-brief.txt --message-ref '实际用户消息位置'
python3 scripts/batch_guard.py --project /path/to/project/state.json choose-settings --settings-hash ACTUAL_SETTINGS_HASH --evidence-file /path/to/project/user-settings.txt --message-ref '实际用户消息位置'
```

`brief/settings`只展示，不自动同意；`confirm-brief/choose-settings`变更确认会清空后续审批。配置里的视频字段为空时不能生成卡，代理应先展示实际支持的选项让用户选，不替用户填默认值。已有选择只补缺项。

## 3. 生成代表样图

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json check --action sample --clips v_x --count 2
python3 scripts/batch_guard.py --project /path/to/project/state.json begin --action sample --clip v_x --count 2 --request /path/to/project/request-sample.json
```

先制作request-sample.json。结构如下；settings逐字段等于配置经output_settings计算的当前规格，原生1K宽高必须填真实已核实值，不能直接使用未验证示例：

```json
{"action":"sample","clip_id":"v_x","count":2,"settings":{"platform":"实际平台","model":"实际模型ID","model_family":"IMAGE2.0","resolution":"1K","width":null,"height":null,"aspect_ratio":"用户所选比例"},"prompt_file":"prompts/sample.txt","input_files":["frames/v_x/first.png","references/person-A.png"]}
```

null为待填项，不可直接执行。原始首帧是必需输入；人物/造型/场景参考按任务所需绑定。视频settings去掉model_family，增加实际mode，resolution/width/height用用户视频选择；输入至少包含原视频和该镜头G2选中的完整首帧。

`begin`再次检查实际请求规格并占用额度，返回本地job_id。然后按记录的实际参数调用授权图像工具，不额外引入默认模型或尺寸。记录提供方任务ID，完成后验证回执：

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json job --id ACTUAL_LOCAL_JOB_ID --status submitted --provider-id ACTUAL_PROVIDER_JOB_ID
python3 scripts/batch_guard.py --project /path/to/project/state.json finish --id ACTUAL_LOCAL_JOB_ID --receipt /path/to/project/receipt.json
```

receipt.json为`{"settings":完整实际原生输出规格对象,"evidence":"实际工具返回/界面回执的可复核位置","outputs":["results/sample-A.png","results/sample-B.png"]}`。settings须与请求相同且来自实际回执；输出数量等于count，结果原始像素由脚本核查。IMAGE规格无法核实、文件尺寸不同或疑似平台降级，先停止，不缩放/伪造回执放行。

ACTUAL字段用真实返回值；同步工具不返回provider ID可以跳过submitted，但仍必须finish验证回执。直接`job --status done`会拒绝。状态不明填unknown，先查询，不重复提交。额度按提交数量累计，失败也计入，默认最多4张样图；同阶段同镜头有未结束任务时拒绝再次登记。

## 4. 登记并展示样图

创建`sample-review.json`，item_id唯一；同一clip_id可有多个候选。以下路径需对应真实图片：

```json
{"items":[
  {"item_id":"s01-A","clip_id":"v_x","kind":"composite_first_frame","job_id":"ACTUAL_LOCAL_JOB_ID","path":"results/sample-A.png","variant":"A","scene":"暖灰访谈空间","notes":"左前侧大柔光","face_crops":[{"label":"角色A原脸与结果对照","path":"results/face-A.png"}]},
  {"item_id":"s01-B","clip_id":"v_x","kind":"composite_first_frame","job_id":"ACTUAL_LOCAL_JOB_ID","path":"results/sample-B.png","variant":"B","scene":"明亮品牌空间"}
]}
```

每个item必须有已finish的同镜头/同阶段job_id、kind=composite_first_frame和对应原生结果路径。kind标签由代理按实际图像填写；脚本不看图，代理不能把空景标成完整合成首帧。face_crops可省略字段，但技能实际审图仍应提供必要面部对照。脚本不生成这些对照，也不会辨认人物。

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json register --stage samples --manifest /path/to/project/sample-review.json
python3 scripts/review_board.py --project /path/to/project/state.json --stage samples --out /path/to/project/sample-review.html
```

展示HTML/图片给用户，等待G1。浏览页面不算确认。审图脚本只缩放图片用于显示，原结果文件保持不变。

## 5. 记录真实G1，批量制作首帧

将用户真实确认消息原文保存为UTF-8文本。`--message-ref`填写实际消息引用；没有平台ID时填可复核的对话时间位置。`--review-hash`使用刚刚展示版本的真实返回值，不能自己编。

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json approve --stage samples --review-hash ACTUAL_REVIEW_HASH --selected s01-A --evidence-file /path/to/project/user-g1.txt --message-ref '实际用户消息位置'
python3 scripts/batch_guard.py --project /path/to/project/state.json check --action batch-frames
```

每个样图镜头必须选一版，样图需覆盖所有原造型、场景组和存在双人同框的场景。`--selected`中的方案才获批准，未选方案不应用于其他镜头。代理从这些方案构建每条具体提示词；不得擅自换场景。对各镜头准备action=batch-frames请求，begin --request后调用IMAGE白名单原生1K工具，再finish验证。未经G1不得先提交。

## 6. 登记全部首帧并等待G2

准备相同结构的`frames-review.json`，覆盖全部clip_id，可给每条多个候选。运行register frames和review_board frames。G1通过不代表G2通过。

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json register --stage frames --manifest /path/to/project/frames-review.json
python3 scripts/review_board.py --project /path/to/project/state.json --stage frames --out /path/to/project/frames-review.html
```

用户逐条选定后再approve frames，`--selected`必须每个clip_id选且只选一个。图片或配置变化需重新登记、展示和确认。所有截图/提示词/参考变化如果影响批准视觉，都要加入配置reference_files或审图清单以参与绑定。

## 7. 视频短样、Q1、批量视频

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json check --action video-pilot --clips v_x
python3 scripts/batch_guard.py --project /path/to/project/state.json begin --action video-pilot --clip v_x --request /path/to/project/request-video-pilot.json
```

按用户选定规格处理短样，用finish检查回执与实际视频像素（需FFprobe），再实际检查画面。创建验收JSON，checks需要六项全部pass以及具体观察，不得照抄下例宣称实测：

```json
{
  "passed": true,
  "clip_ids": ["v_x"],
  "outputs": [{"clip_id":"v_x","job_id":"ACTUAL_VERIFIED_PILOT_JOB_ID","path":"results/pilot.mp4","source_start_s":0,"source_end_s":3}],
  "checks": {
    "face_structure": {"result":"pass","notes":"填写实际查看到的面部情况"},
    "performance": {"result":"pass","notes":"填写实际口型和动作核对结果"},
    "temporal_edges": {"result":"pass","notes":"填写实际边缘连续性观察"},
    "lighting": {"result":"pass","notes":"填写实际光线连续性观察"},
    "scene": {"result":"pass","notes":"填写实际背景与接触观察"},
    "audio_timing": {"result":"pass","notes":"填写实际音画对应结果"}
  }
}
```

短样集合必须覆盖全部角色、原/目标造型和场景组；每个声明的短样镜头必须有输出与有效源时间段，并绑定当前批准版本、已finish的video-pilot任务job_id。回执或输出改变使Q1失效。脚本只验证记录/文件，代理负责实际观看。

```bash
python3 scripts/batch_guard.py --project /path/to/project/state.json qc --report /path/to/project/pilot-qc.json
python3 scripts/batch_guard.py --project /path/to/project/state.json check --action batch-video
```

随后逐镜头准备action=batch-video请求，begin --request后调用真实服务，finish验证原生规格与文件。不应更改本地JSON来强行放行。校验与服务调用必须相邻执行；运行中不改项目或并发写状态。

## 恢复与检查

`status`查看审批是否仍有效和任务状态。脚本单项目串行使用，用排他锁避免覆盖写；崩溃遗留锁时确认进程已结束再人工清理，不自动抢占。日志保存在events内。

`python3 scripts/test_tools.py`运行本地测试；不调用生成API，不使用真实人物测试素材。审批脚本是工作流程工具，不是防恶意篡改的安全系统；确认文件必须来自真实用户，脚本不能认证消息作者。

## 从1.0升级

1.0状态缺少B0/G0、实际请求、原生1K回执及关联job_id，不能直接用旧图绕过新规则。保留源素材与标签，复制新配置并建立新的1.1项目，补齐真实选择后重新出图。
