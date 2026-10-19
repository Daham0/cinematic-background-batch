#!/usr/bin/env python3
"""Version-bound local workflow guard. No AI/API calls or identity recognition."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import uuid

ACTIONS = ('sample', 'batch-frames', 'video-pilot', 'batch-video')
IMAGE_MODELS = ('IMAGE2.0', 'IMAGE2.5')
CHECKS = ('face_structure', 'performance', 'temporal_edges', 'lighting', 'scene', 'audio_timing')
class GuardError(Exception): pass

def utc(): return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(data): return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
def filehash(path):
    p = Path(path)
    if not p.is_file(): raise GuardError(f'文件不存在: {p}')
    h = hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()
def full(path, parent): return str((Path(parent) / path).resolve())
def write(path, data):
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=p.name + '.', dir=p.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
@contextlib.contextmanager
def locked(project):
    p = Path(str(project) + '.lock'); p.parent.mkdir(parents=True, exist_ok=True)
    try: fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError: raise GuardError('项目正在被其他任务操作；若进程已结束，请检查遗留锁再人工清理。')
    try:
        os.write(fd, str(os.getpid()).encode()); os.close(fd); yield
    finally: p.unlink(missing_ok=True)
def event(p, kind, **data): p['events'].append({'time': utc(), 'kind': kind, **data})
def config(p): return read(p['config_file'])
def context(p):
    cfg = config(p); base = Path(p['config_file']).parent
    ref_paths=list(cfg.get('reference_files', []))
    for item in cfg.get('creative_brief',{}).get('looks',[])+cfg.get('creative_brief',{}).get('backgrounds',[]): ref_paths+=item.get('reference_files',[])
    refs = [{'path': full(x, base), 'sha256': filehash(full(x, base))} for x in sorted(set(ref_paths))]
    sources = []
    for c in p['clips']:
        actual = filehash(c['input_file'])
        if actual != c['source_sha256']: raise GuardError(f"源视频内容已变，请重新整理并建立新项目版本: {c['clip_id']}")
        sources.append({'clip_id': c['clip_id'], 'source_sha256': actual, 'first_frame_sha256': filehash(c['first_frame'])})
    return digest({'config': cfg, 'references': refs, 'sources': sources})
def validate_scope(p):
    cfg = config(p); roles = cfg.get('roles', []); groups = cfg.get('scene_groups', [])
    if not roles or not groups or not all(isinstance(x, str) and x for x in roles + groups):
        raise GuardError('先填写已确认的角色标签roles和场景组scene_groups。')
    for c in p['clips']:
        cid = c['clip_id']; assigned = cfg.get('role_assignments', {}).get(cid, [])
        if not assigned or not set(assigned) <= set(roles): raise GuardError(f'角色分配待确认: {cid}')
        if cfg.get('clip_groups', {}).get(cid) not in groups: raise GuardError(f'场景组待确认: {cid}')
    return cfg

def nonempty(value): return isinstance(value, str) and bool(value.strip())
def dimensions(spec):
    w, h = spec.get('width'), spec.get('height')
    if type(w) is not int or type(h) is not int or min(w,h) <= 0:
        raise GuardError('必须填写实际生成的width/height像素尺寸。')
    try: a,b = (int(x) for x in spec['aspect_ratio'].split(':'))
    except (ValueError,KeyError,AttributeError): raise GuardError('画幅必须写成16:9、9:16等明确比例。')
    if min(a,b) <= 0 or abs(w/h-a/b)/(a/b) > 0.01: raise GuardError('像素尺寸与选择画幅不一致（容许1%编码对齐误差）。')

def output_settings(cfg, kind):
    provider = cfg.get('providers', {}).get(kind, {})
    out = cfg.get(kind+'_output', {})
    spec = {'platform':provider.get('platform'), 'model':provider.get('model'),
            'resolution':out.get('resolution'), 'width':out.get('width'), 'height':out.get('height'),
            'aspect_ratio':cfg.get('canvas', {}).get('aspect_ratio')}
    if kind == 'image': spec['model_family'] = provider.get('model_family')
    else: spec['mode'] = provider.get('mode')
    return spec

def validate_provider(cfg, kind):
    provider=cfg.get('providers',{}).get(kind,{})
    spec=output_settings(cfg,kind)
    if provider.get('verified') is not True: raise GuardError(f'{kind}执行入口能力尚未核实；不能提交生成。')
    if not all(nonempty(spec.get(k)) for k in ('platform','model','resolution')): raise GuardError('模型和分辨率必须明确，不能使用空值或auto。')
    if any(str(spec.get(k,'')).lower() in ('auto','default','unknown') for k in ('model','resolution')): raise GuardError('不能自动选择模型或分辨率。')
    proof=provider.get('verification',{})
    if not nonempty(proof.get('evidence')) or not nonempty(proof.get('checked_at')):
        raise GuardError('必须记录实际入口、模型映射和原生输出规格的核实依据及日期。')
    if kind=='image':
        if spec['model_family'] not in IMAGE_MODELS: raise GuardError('首帧模型硬限制：只能使用IMAGE2.0或IMAGE2.5；不得用其他2.0/2.5同名模型代替。')
        if spec['resolution']!='1K': raise GuardError('首帧只能按原生1K档生成；不能2K/4K生成后缩小。')
        if provider.get('verified_model_family')!=spec['model_family'] or provider.get('verified_model')!=spec['model']:
            raise GuardError('IMAGE系列名称与实际模型ID的核实映射不匹配。')
    elif spec['mode'] not in ('video_edit','source_composite'):
        raise GuardError('口播需验证video_edit或source_composite模式；普通图生视频不放行。')
    dimensions(spec)
    native={k:spec[k] for k in ('resolution','aspect_ratio','width','height')}
    if native not in provider.get('native_outputs',[]): raise GuardError('所选分辨率、画幅和尺寸组合尚未核实为该模型原生支持；不能默认裁切、缩放或升级替代。')
    return spec

def brief_payload(p):
    cfg=validate_scope(p); b=cfg.get('creative_brief',{})
    people=b.get('people',[]);looks=b.get('looks',[]);backgrounds=b.get('backgrounds',[])
    person_ids=[x.get('person_id') for x in people];look_ids=[x.get('look_id') for x in looks]
    if not person_ids or not all(nonempty(x) for x in person_ids) or len(person_ids)!=len(set(person_ids)):
        raise GuardError('B0需明确人物清单；不得将帽子、位置或角色数自动当成人物数。')
    if not all(nonempty(x.get('label')) for x in people): raise GuardError('每个人物需有用户提供或确认的称呼。')
    role_people=b.get('role_people',{})
    if set(role_people)!=set(cfg['roles']) or not set(role_people.values())<=set(person_ids): raise GuardError('每个角色必须对应已确认的人物；不确定项先请用户标注。')
    if set(role_people.values())!=set(person_ids): raise GuardError('人物清单含未分配角色的人物，请核对批次范围。')
    if not look_ids or not all(nonempty(x) for x in look_ids) or len(look_ids)!=len(set(look_ids)): raise GuardError('需列出全部不同原造型，look_id不可为空或重复。')
    bylook={x['look_id']:x for x in looks}; refs=[]
    for look in looks:
        if look.get('person_id') not in person_ids or not all(nonempty(look.get(k)) for k in ('source_description','target_description','target_look_id')):
            raise GuardError('每种造型需明确所属人物、原造型和目标造型。')
        if look.get('change') not in ('keep','change'): raise GuardError('必须逐造型确认是否换造型；不可留空或默认猜测。')
        scope=look.get('change_scope',[])
        if look['change']=='keep' and (scope or look['target_look_id']!=look['look_id'] or look['source_description']!=look['target_description']):
            raise GuardError('保留造型时，目标造型与原造型必须一致，change_scope应为空。')
        if look['change']=='change' and (not scope or not set(scope)<=set(('clothing','hat','accessories','hairstyle','makeup'))):
            raise GuardError('换造型必须明确允许改动部位；脸型、五官、年龄和表演不在可改范围。')
        refs+=look.get('reference_files',[])
    # A target look is a stable per-person design across all clips.
    targets={}
    for look in looks:
        key=(look['person_id'],look['target_look_id'])
        if key in targets and targets[key]!=look['target_description']: raise GuardError('同一目标造型ID出现不同设计描述，请统一后确认。')
        targets[key]=look['target_description']
    clip_ids={c['clip_id'] for c in p['clips']};mapping=b.get('clip_looks',{})
    if set(mapping)!=clip_ids: raise GuardError('造型表必须逐条覆盖本批视频。')
    used=set()
    for cid in clip_ids:
        if set(mapping[cid])!=set(cfg['role_assignments'][cid]): raise GuardError('每条视频中每个角色都必须对应一种原造型。')
        for role,lid in mapping[cid].items():
            if lid not in bylook or bylook[lid]['person_id']!=role_people[role]: raise GuardError('角色与造型所属人物不匹配。')
            used.add(lid)
    if used!=set(look_ids): raise GuardError('造型清单有未使用项，请核对本批造型数。')
    group_ids=[x.get('group_id') for x in backgrounds]
    if len(group_ids)!=len(set(group_ids)) or set(group_ids)!=set(cfg['scene_groups']): raise GuardError('每个场景组必须有且只有一套明确目标背景。')
    for bg in backgrounds:
        if not all(nonempty(bg.get(k)) for k in ('description','lighting','photography','integration')) or not bg.get('materials'):
            raise GuardError('目标背景需写清空间、材质、TVC灯光、摄影构图及人物融合，不接受只填“高级”。')
        refs+=bg.get('reference_files',[])
    source=[]
    for c in p['clips']:
        actual=filehash(c['input_file'])
        if actual!=c['source_sha256']: raise GuardError('源视频已变，重新建立项目。')
        source.append({'clip_id':c['clip_id'],'source_sha256':actual,'first_frame_sha256':filehash(c['first_frame'])})
    base=Path(p['config_file']).parent
    refs=[{'path':full(x,base),'sha256':filehash(full(x,base))} for x in sorted(set(refs))]
    return {'counts':{'videos':len(clip_ids),'people':len(person_ids),'roles':len(cfg['roles']),'source_looks':len(look_ids),'target_looks':len(targets),'backgrounds':len(group_ids)},
            'creative_brief':b,'role_assignments':cfg['role_assignments'],'clip_groups':cfg['clip_groups'],'sources':source,'references':refs}

def confirm_brief(p, brief_hash, evidence, message_ref):
    payload=brief_payload(p)
    if brief_hash!=digest(payload): raise GuardError('B0人物/造型/背景清单已变，请展示当前清单。')
    if not nonempty(Path(evidence).read_text(encoding='utf-8')) or not nonempty(message_ref): raise GuardError('B0需记录用户明确确认原文与引用。')
    p['brief_approval']={'brief_hash':brief_hash,'counts':payload['counts'],'evidence_file':str(Path(evidence).resolve()),'evidence_sha256':filehash(evidence),'message_ref':message_ref,'time':utc()}
    p['approvals']={};p['pilot_qc']=None
    event(p,'brief_confirmed',counts=payload['counts'])
    return {'recorded':True,'gate':'B0','counts':payload['counts']}

def confirmed_brief(p):
    a=p.get('brief_approval')
    if not a: raise GuardError('B0未完成：先确认人物数、造型数、是否换造型及每组目标背景。')
    if a['brief_hash']!=digest(brief_payload(p)): raise GuardError('人物、造型或目标背景已变，B0及后续审图失效。')
    if filehash(a['evidence_file'])!=a['evidence_sha256']: raise GuardError('B0用户确认原文已变化。')
    return a

def settings_payload(p):
    cfg=config(p); deliverable=cfg.get('deliverable')
    if deliverable not in ('video','frames'): raise GuardError('填写deliverable为video或frames；不能把视频项目改成frames来绕过选择。')
    canvas=cfg.get('canvas',{})
    if canvas.get('framing') not in ('preserve','background_extend','crop_approved'):
        raise GuardError('先明确画幅适配：保留、只扩展背景，或用户批准的裁切。')
    if canvas['framing']=='preserve':
        for c in p['clips']:
            from PIL import Image
            with Image.open(c['first_frame']) as im: width,height=im.size
            dimensions({'width':width,'height':height,'aspect_ratio':canvas.get('aspect_ratio')})
    payload={'deliverable':deliverable,'canvas':canvas}
    if deliverable=='video': payload['video']=validate_provider(cfg,'video')
    else:
        # Image-only tasks still need the user to choose the target canvas.
        dimensions(output_settings(cfg,'image'))
    return payload

def choose_settings(p, settings_hash, evidence, message_ref):
    payload=settings_payload(p)
    if settings_hash!=digest(payload): raise GuardError('选择对应的参数卡已变化，请重新展示当前参数。')
    if not nonempty(Path(evidence).read_text(encoding='utf-8')) or not nonempty(message_ref):
        raise GuardError('G0必须记录用户明确选择的真实消息原文和引用。')
    p['settings_choice']={'settings_hash':settings_hash,'selection':payload,'evidence_file':str(Path(evidence).resolve()),
                          'evidence_sha256':filehash(evidence),'message_ref':message_ref,'time':utc()}
    p['approvals']={};p['pilot_qc']=None
    event(p,'settings_chosen',settings_hash=settings_hash)
    return {'recorded':True,'gate':'G0','selection':payload}

def chosen_settings(p):
    choice=p.get('settings_choice')
    if not choice: raise GuardError('G0未完成：视频项目必须先由用户选择视频模型、分辨率和画幅；只出图片也要选择画幅。')
    if choice['settings_hash']!=digest(settings_payload(p)): raise GuardError('视频参数或画幅已变，G0选择失效，请用户重新选择并重新审图。')
    if filehash(choice['evidence_file'])!=choice['evidence_sha256']: raise GuardError('G0用户选择原文已变化。')
    return choice

def request_check(p, action, cid, count, request):
    if not request: raise GuardError('提交前必须提供--request实际任务规格清单。')
    data=read(request);kind='video' if action.startswith('video') or action=='batch-video' else 'image'
    if data.get('action')!=action or data.get('clip_id')!=cid or data.get('count')!=count:
        raise GuardError('实际请求的阶段、镜头或数量与任务不一致。')
    expected=validate_provider(config(p),kind)
    if data.get('settings')!=expected: raise GuardError('实际请求模型、分辨率、画幅或尺寸不等于批准配置；拒绝自动替换。')
    if not nonempty(data.get('prompt_file')) or not data.get('input_files'): raise GuardError('请求必须绑定真实提示词文件与输入素材。')
    base=Path(request).parent
    if not Path(full(data['prompt_file'],base)).read_text(encoding='utf-8').strip(): raise GuardError('提示词不能为空。')
    inputs=[{'path':full(x,base),'sha256':filehash(full(x,base))} for x in data['input_files']]
    clip=next(c for c in p['clips'] if c['clip_id']==cid)
    required=clip['input_file'] if kind=='video' else clip['first_frame']
    if required not in {x['path'] for x in inputs}: raise GuardError('任务必须携带该镜头的原视频或抽取首帧，不能只凭人物参考重造表演。')
    if kind=='video':
        selected=set(approved(p,'frames')['selected'])
        frame=next(x['path'] for x in p['reviews']['frames']['items'] if x['clip_id']==cid and x['item_id'] in selected)
        if frame not in {x['path'] for x in inputs}: raise GuardError('视频请求必须携带用户为该镜头选定的完整首帧。')
    prompt=full(data['prompt_file'],base)
    return {'path':str(Path(request).resolve()),'sha256':filehash(request),'settings':expected,
            'prompt_file':prompt,'prompt_sha256':filehash(prompt),'inputs':inputs}

def request_unchanged(j):
    r=j.get('request')
    if not r: raise GuardError('旧任务未绑定1.1规格，不可直接完成或用于审图。')
    for path,sha in [(r['path'],r['sha256']),(r['prompt_file'],r['prompt_sha256'])]+[(x['path'],x['sha256']) for x in r['inputs']]:
        if filehash(path)!=sha: raise GuardError('实际任务请求、提示词或输入文件已变化。')

def finish(p, job_id, receipt):
    jobs=[j for j in p['jobs'] if j['job_id']==job_id]
    if not jobs: raise GuardError('未知任务ID。')
    j=jobs[0]
    if j['status'] in ('done','failed','cancelled'): raise GuardError('任务已结束。')
    request_unchanged(j)
    if j['context_hash']!=context(p): raise GuardError('任务执行期间项目配置改变，结果不能直接采用。')
    confirmed_brief(p); chosen_settings(p)
    token=context(p) if j['action']=='sample' else approval_token(p,'samples' if j['action']=='batch-frames' else 'frames')
    if j['approval_token']!=token: raise GuardError('任务所属批准版本已变化，不能采用该输出。')
    data=read(receipt);spec=j['request']['settings']
    if data.get('settings')!=spec: raise GuardError('提供方回执的原生模型/规格与请求不同，拒绝降级或缩小后冒充。')
    if not nonempty(data.get('evidence')): raise GuardError('需记录工具返回或界面回执的可复核位置；不能自行猜测模型。')
    outputs=data.get('outputs',[])
    if len(outputs)!=j['count']: raise GuardError('结果数量与请求不一致。')
    paths=[]
    for name in outputs:
        path=full(name,Path(receipt).parent)
        if path in [x['path'] for x in paths]: raise GuardError('结果文件重复。')
        if j['action'] in ('sample','batch-frames'):
            from PIL import Image
            with Image.open(path) as im: w,h=im.size
        else:
            probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',path],check=True,capture_output=True,text=True)
            stream=json.loads(probe.stdout)['streams'][0];w,h=stream['width'],stream['height']
        if (w,h)!=(spec['width'],spec['height']): raise GuardError('输出实际像素尺寸与选择不一致；不得缩放补救后登记原生结果。')
        paths.append({'path':path,'sha256':filehash(path)})
    j.update({'status':'done','updated_at':utc(),'receipt_file':str(Path(receipt).resolve()),'receipt_sha256':filehash(receipt),'outputs':paths})
    event(p,'job_result_verified',job_id=job_id)
    return {'recorded':True,'job_id':job_id,'outputs':paths,'note':'核对规格与文件，尚未判定视觉质量。'}

def review_result(p, item, stage):
    expected='sample' if stage=='samples' else 'batch-frames'
    jobs=[j for j in p['jobs'] if j['job_id']==item.get('job_id')]
    if not jobs: raise GuardError('首帧审图必须绑定生成任务job_id及已验证的原生1K结果。')
    j=jobs[0]
    if j['status']!='done' or j['action']!=expected or j['clip_id']!=item['clip_id']: raise GuardError('首帧任务阶段、镜头或完成状态不匹配。')
    if j['context_hash']!=context(p): raise GuardError('首帧来自旧项目配置，需按当前模型/画幅重新制作。')
    request_unchanged(j)
    if stage=='frames' and j['approval_token']!=approval_token(p,'samples'): raise GuardError('批量首帧并非基于当前G1批准版本。')
    if filehash(j['receipt_file'])!=j['receipt_sha256']: raise GuardError('原生生图回执已变化。')
    if {'path':item['path'],'sha256':filehash(item['path'])} not in j['outputs']: raise GuardError('审图文件不等于已验收的生成结果。')

def pilot_output(p, cid, path, job_id):
    jobs=[j for j in p['jobs'] if j['job_id']==job_id]
    if not jobs: raise GuardError('Q1输出必须关联真实的video-pilot任务job_id。')
    j=jobs[0]
    if j['action']!='video-pilot' or j['status']!='done' or j['clip_id']!=cid: raise GuardError('Q1短样任务阶段、镜头或完成状态不匹配；先finish验收原生规格。')
    if j['context_hash']!=context(p) or j['approval_token']!=approval_token(p,'frames'): raise GuardError('Q1短样并非当前批准版本。')
    request_unchanged(j)
    if filehash(j['receipt_file'])!=j['receipt_sha256']: raise GuardError('Q1短样原生规格回执已变化。')
    if {'path':path,'sha256':filehash(path)} not in j['outputs']: raise GuardError('Q1文件不属于该已验证短样任务的原始输出。')
    return j

def snapshot(p, stage):
    confirmed_brief(p); chosen_settings(p)
    r = p['reviews'].get(stage)
    if not r: raise GuardError(f'尚未登记{stage}审图。')
    items = []
    for x in r['items']:
        review_result(p,x,stage)
        y = dict(x); y['sha256'] = filehash(x['path'])
        y['face_crops'] = [{**c, 'sha256': filehash(c['path'])} for c in x.get('face_crops', [])]
        items.append(y)
    return digest({'context': context(p), 'stage': stage, 'items': items})

def approved(p, stage):
    a = p['approvals'].get(stage)
    if not a: raise GuardError(f'{stage}尚未获用户确认。')
    if a['review_hash'] != snapshot(p, stage): raise GuardError(f'{stage}内容或项目设置已变，旧确认失效。')
    if filehash(a['evidence_file']) != a['evidence_sha256']: raise GuardError('确认原文文件已变化。')
    return a

def approval_token(p, stage):
    a = approved(p, stage)
    return digest({'review_hash': a['review_hash'], 'selected': a['selected'], 'time': a['time'], 'evidence': a['evidence_sha256']})

def target_ids(p, ids):
    valid = {c['clip_id'] for c in p['clips']}
    wanted = set(ids or valid)
    if not wanted or not wanted <= valid: raise GuardError('任务含未知或空的素材范围。')
    return wanted

def check(p, action, ids=None, count=1):
    if action not in ACTIONS: raise GuardError('未知阶段。')
    if count < 1: raise GuardError('数量必须大于零。')
    wanted = target_ids(p, ids); cfg = validate_scope(p); confirmed_brief(p); chosen_settings(p); ctx = context(p)
    kind = 'video' if action in ('video-pilot', 'batch-video') else 'image'
    if kind=='video' and cfg.get('deliverable')!='video': raise GuardError('当前只批准图片交付，视频需重新选择G0。')
    validate_provider(cfg,kind)
    if action == 'sample':
        used = sum(j['count'] for j in p['jobs'] if j['action'] == 'sample')
        if used + count > cfg.get('sample_generation_limit', 4): raise GuardError('代表样图提交限额已达；增加额度需用户明确授权。')
        token = ctx
    else:
        approved(p, 'samples'); token = approval_token(p, 'samples')
        if action in ('video-pilot', 'batch-video'):
            approved(p, 'frames'); token = approval_token(p, 'frames')
        if action == 'batch-video':
            q = p.get('pilot_qc')
            if not q or q['approval_token'] != token: raise GuardError('当前首帧版本尚未通过Q1动态验收。')
            if filehash(q['report_file']) != q['report_sha256']: raise GuardError('Q1验收记录已变。')
            for f in q['outputs']:
                if filehash(f['path']) != f['sha256']: raise GuardError('Q1短样输出已变。')
                pilot_output(p,f['clip_id'],f['path'],f.get('job_id'))
    return {'allowed': True, 'action': action, 'clip_ids': sorted(wanted), 'context_hash': ctx, 'approval_token': token}

def register(p, stage, manifest):
    confirmed_brief(p); chosen_settings(p); validate_provider(config(p),'image')
    if stage == 'frames': approved(p, 'samples')
    data = read(manifest); raw = data.get('items', [])
    if not raw: raise GuardError('审图清单不能为空。')
    valid = target_ids(p, None); seen = set(); items = []
    for item in raw:
        x = dict(item)
        if x.get('kind')!='composite_first_frame': raise GuardError('审图必须是人物+目标背景+布光的完整首帧，不能仅用空景。')
        if not x.get('item_id') or x['item_id'] in seen: raise GuardError('item_id为空或重复。')
        seen.add(x['item_id'])
        if x.get('clip_id') not in valid: raise GuardError('审图项目含未知clip_id。')
        x['path'] = full(x['path'], Path(manifest).parent); filehash(x['path'])
        review_result(p,x,stage)
        crops = []
        for c in x.get('face_crops', []):
            c = dict(c); c['path'] = full(c['path'], Path(manifest).parent); filehash(c['path']); crops.append(c)
        x['face_crops'] = crops; items.append(x)
    if stage == 'samples' and len(items) > config(p).get('sample_generation_limit', 4): raise GuardError('样图清单超过项目限额。')
    if stage == 'frames' and {x['clip_id'] for x in items} != valid: raise GuardError('全批首帧清单必须覆盖所有素材；需要分批请先拆项目。')
    p['reviews'][stage] = {'registered_at': utc(), 'items': items}
    for s in (('samples', 'frames') if stage == 'samples' else ('frames',)):
        p['approvals'].pop(s, None)
    if stage == 'samples': p['reviews'].pop('frames', None)
    p['pilot_qc'] = None
    h = snapshot(p, stage); p['reviews'][stage]['registered_hash'] = h
    event(p, 'review_registered', stage=stage, review_hash=h)
    return {'stage': stage, 'review_hash': h, 'item_ids': sorted(seen)}

def approve(p, stage, review_hash, selected, evidence, message_ref):
    if stage == 'frames': approved(p, 'samples')
    h = snapshot(p, stage)
    if review_hash != h: raise GuardError('确认的审图哈希与当前实际文件不一致，请重新展示。')
    if h != p['reviews'][stage]['registered_hash']: raise GuardError('图片登记后已变，请重新登记并展示。')
    if not Path(evidence).read_text(encoding='utf-8').strip(): raise GuardError('用户确认原文不能为空。')
    lookup = {x['item_id']: x for x in p['reviews'][stage]['items']}
    if len(selected) != len(set(selected)) or not set(selected) <= set(lookup): raise GuardError('选中的版本无效或重复。')
    clip_ids = [lookup[i]['clip_id'] for i in selected]
    expected = {x['clip_id'] for x in lookup.values()}
    if len(clip_ids) != len(set(clip_ids)) or set(clip_ids) != expected:
        raise GuardError('每个展示的镜头必须且只能选择一个版本。')
    cfg = validate_scope(p)
    if stage == 'samples' and {cfg['clip_groups'][x] for x in clip_ids} != set(cfg['scene_groups']):
        raise GuardError('代表样图需覆盖所有场景组；可将不同组拆项目。')
    if stage=='samples':
        look_map=cfg['creative_brief']['clip_looks']
        covered=set().union(*(set(look_map[c].values()) for c in clip_ids))
        required={x['look_id'] for x in cfg['creative_brief']['looks']}
        if covered!=required: raise GuardError('代表样图需覆盖每种原造型及目标方案；样图不足时先拆组或获准调整样图额度。')
        dual_groups={cfg['clip_groups'][c] for c in cfg['role_assignments'] if len(cfg['role_assignments'][c])>1}
        shown_dual={cfg['clip_groups'][c] for c in clip_ids if len(cfg['role_assignments'][c])>1}
        if not dual_groups<=shown_dual: raise GuardError('双人同框场景需展示同框样图，不能用两张单人图代替。')
    p['approvals'][stage] = {'review_hash': h, 'selected': sorted(selected), 'evidence_file': str(Path(evidence).resolve()), 'evidence_sha256': filehash(evidence), 'message_ref': message_ref, 'time': utc()}
    p['pilot_qc'] = None
    if stage == 'samples': p['approvals'].pop('frames', None)
    event(p, 'user_approval_recorded', stage=stage, selected=selected)
    return {'recorded': True, 'stage': stage, 'note': '仅记录代理核对过的用户确认；不构成独立身份认证。'}

def qc(p, report):
    check(p, 'video-pilot'); data = read(report); cfg = config(p)
    if data.get('passed') is not True: raise GuardError('Q1未通过，不放行批量视频。')
    for key in CHECKS:
        item = data.get('checks', {}).get(key, {})
        if item.get('result') != 'pass' or not item.get('notes', '').strip(): raise GuardError(f'Q1缺少通过结果或具体观察: {key}')
    ids = target_ids(p, data.get('clip_ids') or [])
    if not data.get('clip_ids'): raise GuardError('Q1必须明确短样clip_ids。')
    roles = set().union(*(set(cfg['role_assignments'][i]) for i in ids))
    if not set(cfg['roles']) <= roles or {cfg['clip_groups'][i] for i in ids} != set(cfg['scene_groups']):
        raise GuardError('Q1短样未覆盖全部角色或场景组。')
    look_map=cfg['creative_brief']['clip_looks']
    if set().union(*(set(look_map[i].values()) for i in ids))!={x['look_id'] for x in cfg['creative_brief']['looks']}: raise GuardError('Q1短样未覆盖全部原造型及目标方案。')
    if not data.get('outputs'): raise GuardError('Q1必须附真实短样文件。')
    outputs = []; covered = set()
    duration = {c['clip_id']: c.get('duration_s', 0) for c in p['clips']}
    for x in data['outputs']:
        cid = x.get('clip_id')
        if cid not in ids: raise GuardError('Q1输出关联了未知或未列入短样范围的镜头。')
        start, end = x.get('source_start_s'), x.get('source_end_s')
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not 0 <= start < end <= duration[cid]:
            raise GuardError('Q1输出必须标注有效的原片时间范围。')
        path = full(x['path'], Path(report).parent)
        pilot_output(p,cid,path,x.get('job_id'))
        outputs.append({'clip_id': cid, 'job_id':x['job_id'], 'path': path, 'sha256': filehash(path), 'source_start_s': start, 'source_end_s': end}); covered.add(cid)
    if covered != ids: raise GuardError('Q1每个声明的短样镜头都必须有关联输出。')
    p['pilot_qc'] = {'approval_token': approval_token(p, 'frames'), 'report_file': str(Path(report).resolve()), 'report_sha256': filehash(report), 'outputs': outputs, 'time': utc()}
    event(p, 'pilot_qc_recorded', clip_ids=sorted(ids))
    return {'recorded': True, 'note': '脚本未评判视觉；记录的是执行代理的实看片验收。'}

def begin(p, action, cid, count, request=None):
    r = check(p, action, [cid], count)
    req = request_check(p,action,cid,count,request)
    if any(j['action'] == action and j['clip_id'] == cid and j['status'] in ('reserved', 'submitted', 'unknown') for j in p['jobs']):
        raise GuardError('该素材已有未结束任务，请先查询并更新原任务。')
    j = {'job_id': uuid.uuid4().hex, 'action': action, 'clip_id': cid, 'count': count, 'status': 'reserved', 'provider_job_id': None, 'approval_token': r['approval_token'], 'context_hash': r['context_hash'], 'created_at': utc(), 'request': req}
    p['jobs'].append(j); event(p, 'job_reserved', job_id=j['job_id']); return j

def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--project', required=True, help='项目状态JSON')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('init'); s.add_argument('--config', required=True); s.add_argument('--index', required=True)
    sub.add_parser('status'); sub.add_parser('settings'); sub.add_parser('brief')
    s = sub.add_parser('confirm-brief'); s.add_argument('--brief-hash',required=True); s.add_argument('--evidence-file',required=True); s.add_argument('--message-ref',required=True)
    s = sub.add_parser('choose-settings'); s.add_argument('--settings-hash',required=True); s.add_argument('--evidence-file',required=True); s.add_argument('--message-ref',required=True)
    s = sub.add_parser('finish'); s.add_argument('--id',required=True); s.add_argument('--receipt',required=True)
    s = sub.add_parser('register'); s.add_argument('--stage', choices=['samples','frames'], required=True); s.add_argument('--manifest', required=True)
    s = sub.add_parser('approve'); s.add_argument('--stage', choices=['samples','frames'], required=True); s.add_argument('--review-hash', required=True); s.add_argument('--selected', nargs='+', required=True); s.add_argument('--evidence-file', required=True); s.add_argument('--message-ref', required=True)
    s = sub.add_parser('check'); s.add_argument('--action', choices=ACTIONS, required=True); s.add_argument('--clips', nargs='*'); s.add_argument('--count', type=int, default=1)
    s = sub.add_parser('qc'); s.add_argument('--report', required=True)
    s = sub.add_parser('begin'); s.add_argument('--action', choices=ACTIONS, required=True); s.add_argument('--clip', required=True); s.add_argument('--count', type=int, default=1); s.add_argument('--request',required=True)
    s = sub.add_parser('job'); s.add_argument('--id', required=True); s.add_argument('--status', required=True, choices=['submitted','unknown','done','failed','cancelled']); s.add_argument('--provider-id')
    args = ap.parse_args(); project = Path(args.project).resolve()
    try:
        with locked(project):
            if args.cmd == 'init':
                if project.exists(): raise GuardError('项目文件已存在，不覆盖；建立新文件或继续原项目。')
                idx = read(args.index); clips = idx.get('clips', [])
                if not clips or any(c.get('error') for c in clips): raise GuardError('素材索引为空或有失败条目。')
                ids = [c['clip_id'] for c in clips]
                if len(ids) != len(set(ids)): raise GuardError('clip_id重复。')
                for c in clips:
                    for k in ('input_file','first_frame'): c[k] = full(c[k], Path(args.index).parent)
                p = {'schema_version':2, 'project_id':uuid.uuid4().hex, 'created_at':utc(), 'config_file':str(Path(args.config).resolve()), 'clips':clips, 'reviews':{}, 'approvals':{}, 'pilot_qc':None, 'jobs':[], 'events':[]}
                context(p); event(p, 'initialized'); result = {'created':True, 'clip_count':len(clips)}
            else:
                p = read(project)
                if args.cmd == 'register': result = register(p,args.stage,args.manifest)
                elif args.cmd == 'approve': result = approve(p,args.stage,args.review_hash,args.selected,args.evidence_file,args.message_ref)
                elif args.cmd == 'check': result = check(p,args.action,args.clips,args.count)
                elif args.cmd == 'qc': result = qc(p,args.report)
                elif args.cmd == 'begin': result = begin(p,args.action,args.clip,args.count,args.request)
                elif args.cmd == 'brief':
                    payload=brief_payload(p); result={'brief_hash':digest(payload),**payload,'gate':'B0; display counts, mappings, appearance changes and target backgrounds'}
                elif args.cmd == 'confirm-brief': result=confirm_brief(p,args.brief_hash,args.evidence_file,args.message_ref)
                elif args.cmd == 'settings':
                    payload=settings_payload(p); result={'settings_hash':digest(payload),'selection':payload,'gate':'G0; display this card and record actual user selection'}
                elif args.cmd == 'choose-settings': result=choose_settings(p,args.settings_hash,args.evidence_file,args.message_ref)
                elif args.cmd == 'finish': result=finish(p,args.id,args.receipt)
                elif args.cmd == 'job':
                    matches = [j for j in p['jobs'] if j['job_id'] == args.id]
                    if not matches: raise GuardError('未知任务ID。')
                    if args.status=='done': raise GuardError('完成任务必须使用finish --receipt核对实际模型与像素尺寸。')
                    j = matches[0]
                    if j['status'] in ('done','failed','cancelled'): raise GuardError('任务已结束，不可恢复；重试需新登记。')
                    j['status'] = args.status; j['updated_at'] = utc()
                    if args.provider_id: j['provider_job_id'] = args.provider_id
                    event(p,'job_updated',job_id=args.id,status=args.status); result=j
                else:
                    result={'project_id':p['project_id'],'clip_count':len(p['clips']),'approvals':{},'jobs':p['jobs']}
                    try: confirmed_brief(p); result['B0']='valid'
                    except GuardError as e: result['B0']=str(e)
                    try: chosen_settings(p); result['G0']='valid'
                    except GuardError as e: result['G0']=str(e)
                    for stage in ('samples','frames'):
                        try: approved(p,stage); result['approvals'][stage]='valid'
                        except GuardError as e: result['approvals'][stage]=str(e)
            if args.cmd not in ('check','status','settings','brief'): write(project,p)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    except (GuardError, OSError, ValueError, KeyError, TypeError, IndexError, subprocess.CalledProcessError) as e:
        print(json.dumps({'allowed':False,'error':str(e)},ensure_ascii=False),file=sys.stderr); return 2
if __name__ == '__main__': sys.exit(main())
