#!/usr/bin/env python3
"""Extract actual first decoded frames and optional approximate-time candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

EXTS = {'.mp4','.mov','.mkv','.webm','.m4v','.avi','.mxf'}
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()
def run(cmd):
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=180)
    if p.returncode:raise RuntimeError(p.stderr.strip()[-1500:])
    return p.stdout

def extract(source,out,candidates=False):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'): raise RuntimeError('需要FFmpeg和FFprobe可执行程序。')
    root=Path(source).resolve(); dest=Path(out).resolve(); dest.mkdir(parents=True,exist_ok=True)
    paths=[root] if root.is_file() else sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in EXTS and dest not in p.parents)
    if not paths:raise RuntimeError('未找到支持的视频文件。')
    clips=[]
    for path in paths:
        rel=path.name if root.is_file() else path.relative_to(root).as_posix()
        cid='v_'+hashlib.sha256(rel.encode()).hexdigest()[:12]
        item={'clip_id':cid,'source_name':rel,'input_file':str(path),'source_sha256':sha(path)}
        try:
            info=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
            video=next(s for s in info['streams'] if s.get('codec_type')=='video')
            dur=float(info.get('format',{}).get('duration',video.get('duration',0)))
            item.update({'duration_s':dur,'width':video.get('width'),'height':video.get('height'),'avg_frame_rate':video.get('avg_frame_rate'),'r_frame_rate':video.get('r_frame_rate'),'audio_streams':len([s for s in info['streams'] if s.get('codec_type')=='audio'])})
            folder=dest/cid;folder.mkdir(exist_ok=True);first=folder/'first.png'
            run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(path),'-map','0:v:0','-frames:v','1','-update','1',str(first)])
            if not first.is_file():raise RuntimeError('视频没有可解码首帧。')
            item.update({'first_frame':str(first),'first_frame_kind':'first_decoded_frame_no_seek','candidates':[]})
            if candidates and dur>0:
                times=sorted({round(min(.5,dur/2),4),round(dur/2,4),round(max(0,dur-.2),4)})
                for n,t in enumerate(times,1):
                    target=folder/f'candidate_{n}.png'
                    try:
                        run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-ss',str(t),'-i',str(path),'-map','0:v:0','-frames:v','1','-update','1',str(target)])
                        if target.is_file():item['candidates'].append({'path':str(target),'requested_time_s':t,'note':'按请求时间附近抽取，非精确帧PTS；不能替代真实首帧。'})
                    except (RuntimeError,subprocess.TimeoutExpired) as e:
                        item.setdefault('warnings',[]).append(f'候选时间{t}: {e}')
        except (RuntimeError,subprocess.TimeoutExpired,ValueError,KeyError,StopIteration) as e:item['error']=str(e)
        clips.append(item)
    index={'schema_version':1,'note':'仅机械抽帧，没有AI生成、黑场检测、切镜检测或人物识别。','clips':clips}
    target=dest/'index.json';target.write_text(json.dumps(index,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return target,index

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);ap.add_argument('--candidates',action='store_true');a=ap.parse_args()
    try:
        target,data=extract(a.input,a.out,a.candidates)
        errors=[{'clip_id':c['clip_id'],'error':c['error']} for c in data['clips'] if c.get('error')]
        print(json.dumps({'index':str(target),'clips':len(data['clips']),'errors':errors},ensure_ascii=False,indent=2));return 2 if errors else 0
    except (OSError,RuntimeError) as e:print(str(e),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
