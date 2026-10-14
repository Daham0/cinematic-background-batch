#!/usr/bin/env python3
"""Create a self-contained HTML review board. This never records approval."""
import argparse
import base64
import html
import io
import json
from pathlib import Path
import sys
from PIL import Image, ImageOps
from batch_guard import read, snapshot, filehash, GuardError, brief_payload, output_settings

def esc(x):return html.escape(str(x),quote=True)
def uri(path):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1400,1400))
        b=io.BytesIO();im.save(b,format='JPEG',quality=90)
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()
def render(project,stage,out):
    p=read(project);r=p['reviews'].get(stage)
    if not r:raise GuardError('请先登记审图清单。')
    h=snapshot(p,stage)
    if h!=r['registered_hash']:raise GuardError('登记后图片已变化，请重新登记。')
    cfg=read(p['config_file']);counts=brief_payload(p)['counts'];image_spec=output_settings(cfg,'image');sources={c['clip_id']:c for c in p['clips']};cards=[]
    for x in r['items']:
        c=sources[x['clip_id']];source=uri(c['first_frame']);candidate=uri(x['path'])
        faces=''.join('<figure><img loading="lazy" src="'+uri(f['path'])+'" alt="'+esc(f.get('label','面部对照'))+'"><figcaption>'+esc(f.get('label','面部对照'))+'</figcaption></figure>' for f in x.get('face_crops',[]))
        assignments=cfg['creative_brief']['clip_looks'][x['clip_id']]
        look_by_id={v['look_id']:v for v in cfg['creative_brief']['looks']}
        look_text='；'.join(role+'：'+look_by_id[lid]['source_description']+' → '+look_by_id[lid]['target_description'] for role,lid in assignments.items())
        cards.append('<article><div class="row"><h2>'+esc(x['item_id'])+'</h2><span>'+esc(x.get('variant','候选'))+'</span></div><p class="meta">'+esc(c.get('source_name',c['clip_id']))+' · '+esc(x.get('scene',''))+'</p><div class="pair"><figure><img loading="lazy" src="'+source+'" alt="原始首帧"><figcaption>原始首帧</figcaption></figure><figure><img loading="lazy" src="'+candidate+'" alt="候选效果"><figcaption>完整合成首帧 · '+esc(x['item_id'])+'</figcaption></figure></div><p>'+esc(look_text)+'<br>'+esc(x.get('notes',''))+'</p><div class="faces">'+faces+'</div></article>')
    title='代表首帧样图' if stage=='samples' else '全部首帧效果'
    notice='请按编号选择样图；明确确认后，才会批量制作全部首帧。' if stage=='samples' else '请逐条确认首帧；全部通过后，才会开始视频短样与批处理。'
    summary=f"{counts['videos']}条视频 · {counts['people']}个人物 · {counts['roles']}个角色 · {counts['source_looks']}种原造型 → {counts['target_looks']}种目标造型 · {counts['backgrounds']}组背景"
    specs=f"首帧：{image_spec['model_family']} · 原生{image_spec['resolution']} · {image_spec['width']}×{image_spec['height']} · {image_spec['aspect_ratio']}"
    if cfg['deliverable']=='video':
        video=output_settings(cfg,'video');specs+=f"；已选视频：{video['model']} · {video['resolution']} · {video['width']}×{video['height']} · {video['aspect_ratio']}"
    document='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="review-hash" content="'''+h+'''"><title>'''+esc(title)+'''</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f4f1;color:#1d2726;font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif}header,main{max-width:1240px;margin:auto;padding:28px}header{padding-top:42px;padding-bottom:8px}.eyebrow{font-size:12px;font-weight:650;letter-spacing:.14em;color:#547069}h1{font-size:32px;line-height:1.25;margin:12px 0}header p{line-height:1.8}.notice{padding:14px 18px;background:#e3ece6;border-left:4px solid #367963;border-radius:4px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}article{background:white;border:1px solid #dce2dc;border-radius:12px;padding:20px}.row{display:flex;align-items:center;justify-content:space-between;gap:8px}.row span{font-size:12px;padding:5px 10px;border-radius:20px;background:#eef2ed}h2{font-size:18px;margin:0}.meta{font-size:12px;color:#62716c;overflow-wrap:anywhere}.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}figure{margin:0;min-width:0}img{display:block;width:100%;height:260px;object-fit:contain;background:#edf0ec;cursor:zoom-in;border-radius:5px}figcaption{font-size:12px;color:#62716c;padding-top:8px}article p{font-size:13px;line-height:1.7}.faces{display:flex;gap:10px;flex-wrap:wrap}.faces figure{width:calc(50% - 5px)}.faces img{height:140px}footer{color:#687870;font-size:12px;margin-top:26px;line-height:1.7}dialog{border:0;border-radius:12px;padding:12px;max-width:96vw;max-height:96vh}dialog::backdrop{background:#10221bcc}dialog img{width:auto;max-width:90vw;height:auto;max-height:85vh}button{padding:8px 15px;border:0;border-radius:6px;margin-bottom:10px;cursor:pointer;background:#e3ece6}@media(max-width:800px){.grid{grid-template-columns:1fr}header,main{padding:18px}h1{font-size:27px}}@media print{.grid{display:block}article{break-inside:avoid;margin-bottom:15px}}
</style></head><body><header><div class="eyebrow">COMMERCIAL SCENE REVIEW</div><h1>'''+esc(title)+'''</h1><p>'''+esc(cfg.get('project_name','项目'))+''' · '''+str(len(r['items']))+''' 个候选</p><p>'''+esc(summary)+'''<br>'''+esc(specs)+'''</p><div class="notice">'''+esc(notice)+'''</div></header><main><div class="grid">'''+''.join(cards)+'''</div><footer>点击图片放大。此页面仅供审图，浏览或关闭页面不会自动批准任何任务。请在对话中回复选中的编号与确认意见。<br>核查：人物五官与原表演、获准造型/帽子/服装/产品、场景与灯光、发丝边缘、接触与透视。</footer></main><dialog id="zoom"><button id="close">关闭</button><img id="large" alt="放大查看"></dialog><script>const d=document.getElementById('zoom');document.querySelectorAll('article img').forEach(i=>i.addEventListener('click',()=>{document.getElementById('large').src=i.src;d.showModal()}));document.getElementById('close').onclick=()=>d.close();d.addEventListener('click',e=>{if(e.target===d)d.close()});</script></body></html>'''
    target=Path(out);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(document,encoding='utf-8');return {'file':str(target.resolve()),'review_hash':h,'count':len(r['items'])}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',required=True);ap.add_argument('--stage',choices=['samples','frames'],required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    try:print(json.dumps(render(a.project,a.stage,a.out),ensure_ascii=False,indent=2));return 0
    except (OSError,KeyError,ValueError,GuardError) as e:print(str(e),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
