#!/usr/bin/env python3
"""Local behavioural tests; synthetic files only, no model/API invocation."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from PIL import Image
import batch_guard as g
import extract_frames
import review_board

ROOT=Path(__file__).resolve().parent
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.state=self.root/'state.json';self.cfg=self.root/'config.json'
        for name,color in [('first1.png','red'),('first2.png','blue'),('s1.png','green'),('s2.png','orange'),('f1.png','yellow'),('f2.png','purple')]:Image.new('RGB',(1024,576),color).save(self.root/name)
        self.clips=[]
        for n in (1,2):
            src=self.root/f'source{n}.mp4';src.write_bytes(b'synthetic fixture '+str(n).encode())
            self.clips.append({'clip_id':f'v{n}','input_file':str(src),'source_sha256':g.filehash(src),'first_frame':str(self.root/f'first{n}.png'),'source_name':f'source{n}.mp4','duration_s':3,'width':1024,'height':576})
        self.config={'sample_generation_limit':4,'roles':['A','B'],'scene_groups':['room'],'reference_files':[],'role_assignments':{'v1':['A'],'v2':['B']},'clip_groups':{'v1':'room','v2':'room'},'providers':{'image':{'verified':True},'video':{'verified':True,'mode':'video_edit'}}}
        # Deliberately synthetic provider capabilities; never a real model claim.
        native={'resolution':'1K','aspect_ratio':'16:9','width':1024,'height':576}
        video_native={**native,'resolution':'test-576p'}
        self.config.update({'deliverable':'video','canvas':{'aspect_ratio':'16:9','framing':'preserve'},
                            'image_output':{'resolution':'1K','width':1024,'height':576},
                            'video_output':{'resolution':'test-576p','width':1024,'height':576}})
        self.config['providers']['image'].update({'platform':'synthetic','model':'fixture-image-2','model_family':'IMAGE2.0','verified_model':'fixture-image-2','verified_model_family':'IMAGE2.0','verification':{'evidence':'synthetic fixture only','checked_at':'2026-09-15'},'native_outputs':[native]})
        self.config['providers']['video'].update({'platform':'synthetic','model':'fixture-video','verification':{'evidence':'synthetic fixture only','checked_at':'2026-09-15'},'native_outputs':[video_native]})
        self.config['creative_brief']={'people':[{'person_id':'P1','label':'User-labelled person 1'},{'person_id':'P2','label':'User-labelled person 2'}],
          'role_people':{'A':'P1','B':'P2'},'looks':[{'look_id':f'L{n}','person_id':f'P{n}','source_description':f'look {n}','target_description':f'look {n}','target_look_id':f'L{n}','change':'keep','change_scope':[]} for n in (1,2)],
          'clip_looks':{'v1':{'A':'L1'},'v2':{'B':'L2'}},'backgrounds':[{'group_id':'room','description':'real wood interview room','materials':['wood'],'lighting':'large soft key from frame left','photography':'source perspective, layered depth','integration':'coherent face and body light with contact shadows'}]}
        g.write(self.cfg,self.config);g.write(self.root/'index.json',{'clips':self.clips})
        self.cli('init','--config',str(self.cfg),'--index',str(self.root/'index.json'))
        (self.root/'user-g1.txt').write_text('TEST FIXTURE: approve sample s1 only',encoding='utf-8')
        (self.root/'user-g2.txt').write_text('TEST FIXTURE: approve all final frames f1 f2',encoding='utf-8')
        self.preflight()
    def preflight(self):
        (self.root/'user-settings.txt').write_text('SYNTHETIC USER: choose fixture-video, test-576p, 16:9, preserve framing')
        (self.root/'user-brief.txt').write_text('SYNTHETIC USER: confirm two people, two looks unchanged, wood room')
        r=self.cli('brief');self.cli('confirm-brief','--brief-hash',r['brief_hash'],'--evidence-file',str(self.root/'user-brief.txt'),'--message-ref','synthetic B0')
        r=self.cli('settings');self.cli('choose-settings','--settings-hash',r['settings_hash'],'--evidence-file',str(self.root/'user-settings.txt'),'--message-ref','synthetic G0')
    def request(self,action,cid,count=1):
        kind='video' if action in ('video-pilot','batch-video') else 'image'
        prompt=self.root/'prompt.txt';prompt.write_text('SYNTHETIC TVC lighting prompt')
        source=next(c for c in self.clips if c['clip_id']==cid)['input_file' if kind=='video' else 'first_frame']
        path=self.root/f'request-{action}-{cid}-{count}.json'
        g.write(path,{'action':action,'clip_id':cid,'count':count,'settings':g.output_settings(g.read(self.cfg),kind),'prompt_file':str(prompt),'input_files':[source]+([x['path'] for x in g.read(self.state)['reviews'].get('frames',{}).get('items',[]) if x['clip_id']==cid and x['item_id'] in g.read(self.state)['approvals'].get('frames',{}).get('selected',[])] if kind=='video' else [])})
        return path
    def produce(self,stage,item):
        action='sample' if stage=='samples' else 'batch-frames'
        req=self.request(action,item['clip_id'])
        j=self.cli('begin','--action',action,'--clip',item['clip_id'],'--request',str(req))
        receipt=self.root/f"receipt-{j['job_id']}.json"
        g.write(receipt,{'settings':g.read(req)['settings'],'evidence':'synthetic receipt, no real model','outputs':[str(self.root/item['path'])]})
        self.cli('finish','--id',j['job_id'],'--receipt',str(receipt))
        return {**item,'job_id':j['job_id'],'kind':'composite_first_frame'}
    def tearDown(self):self.tmp.cleanup()
    def cli(self,*args,expected=0):
        args=list(args)
        if args[0]=='begin' and '--request' not in args:
            action=args[args.index('--action')+1];cid=args[args.index('--clip')+1];count=int(args[args.index('--count')+1]) if '--count' in args else 1
            args+=['--request',str(self.request(action,cid,count))]
        p=subprocess.run([sys.executable,str(ROOT/'batch_guard.py'),'--project',str(self.state),*args],capture_output=True,text=True)
        self.assertEqual(p.returncode,expected,p.stdout+p.stderr)
        return json.loads(p.stdout if p.returncode==0 else p.stderr)
    def reg(self,stage,items):
        items=[self.produce(stage,x) if not x.get('job_id') else x for x in items]
        p=self.root/f'{stage}.json';g.write(p,{'items':items});return self.cli('register','--stage',stage,'--manifest',str(p))
    def g1(self):
        r=self.reg('samples',[{'item_id':'s1','clip_id':'v1','path':'s1.png'},{'item_id':'s2','clip_id':'v2','path':'s2.png'}])
        self.cli('approve','--stage','samples','--review-hash',r['review_hash'],'--selected','s1','s2','--evidence-file',str(self.root/'user-g1.txt'),'--message-ref','synthetic test fixture')
    def g2(self):
        p=g.read(self.state)
        if not p['approvals'].get('samples'): self.g1()
        r=self.reg('frames',[{'item_id':'f1','clip_id':'v1','path':'f1.png'},{'item_id':'f2','clip_id':'v2','path':'f2.png'}])
        self.cli('approve','--stage','frames','--review-hash',r['review_hash'],'--selected','f1','f2','--evidence-file',str(self.root/'user-g2.txt'),'--message-ref','synthetic test fixture')
        return r
    def qdata(self):
        outputs=[]
        for n in (1,2):
            path=self.root/f'pilot{n}.mp4'
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi','-i','color=c=black:s=1024x576:r=10:d=2','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(path)],check=True)
            req=self.request('video-pilot',f'v{n}')
            j=self.cli('begin','--action','video-pilot','--clip',f'v{n}','--request',str(req))
            receipt=self.root/f"receipt-{j['job_id']}.json"
            g.write(receipt,{'settings':g.read(req)['settings'],'evidence':'synthetic video output, not a real service','outputs':[str(path)]})
            self.cli('finish','--id',j['job_id'],'--receipt',str(receipt))
            outputs.append({'clip_id':f'v{n}','job_id':j['job_id'],'path':str(path),'source_start_s':0,'source_end_s':2})
        return {'passed':True,'clip_ids':['v1','v2'],'outputs':outputs,'checks':{k:{'result':'pass','notes':'synthetic unit test record; no visual assessment claimed'} for k in g.CHECKS}}
    def qpass(self):
        path=self.root/'qc.json';g.write(path,self.qdata());self.cli('qc','--report',str(path));return path
    def test_initial_gates_block(self):
        self.cli('check','--action','sample')
        for action in ('batch-frames','video-pilot','batch-video'):self.cli('check','--action',action,expected=2)
    def test_complete_gates_in_sequence(self):
        self.g1();self.cli('check','--action','batch-frames');self.cli('check','--action','video-pilot',expected=2)
        self.g2();self.cli('check','--action','video-pilot');self.cli('check','--action','batch-video',expected=2)
        self.qpass();self.cli('check','--action','batch-video')
    def test_no_implicit_approval_when_registering(self):
        self.reg('samples',[{'item_id':'s1','clip_id':'v1','path':'s1.png'}]);self.cli('check','--action','batch-frames',expected=2)
    def test_edited_frame_invalidates(self):
        self.g2();Image.new('RGB',(1024,576),'black').save(self.root/'f2.png');self.cli('check','--action','video-pilot',expected=2)
        self.cli('check','--action','batch-frames')
    def test_config_reference_and_source_changes_invalidate(self):
        self.g2();cfg=copy.deepcopy(self.config);cfg['roles']=['A','B','C'];g.write(self.cfg,cfg);self.cli('check','--action','batch-frames',expected=2)
        g.write(self.cfg,self.config);(self.root/'source1.mp4').write_bytes(b'changed');self.cli('check','--action','sample',expected=2)
    def test_missing_frames_or_duplicate_choice_rejected(self):
        self.g1();path=self.root/'bad.json';g.write(path,{'items':[{'item_id':'f1','clip_id':'v1','path':'f1.png'}]});self.cli('register','--stage','frames','--manifest',str(path),expected=2)
        r=self.reg('frames',[{'item_id':'f1','clip_id':'v1','path':'f1.png'},{'item_id':'f1b','clip_id':'v1','path':'f1.png'},{'item_id':'f2','clip_id':'v2','path':'f2.png'}])
        self.cli('approve','--stage','frames','--review-hash',r['review_hash'],'--selected','f1','f1b','f2','--evidence-file',str(self.root/'user-g2.txt'),'--message-ref','test',expected=2)
    def test_empty_or_stale_confirmation_rejected(self):
        r=self.reg('samples',[{'item_id':'s1','clip_id':'v1','path':'s1.png'}]);(self.root/'empty.txt').write_text('')
        base=['approve','--stage','samples','--review-hash',r['review_hash'],'--selected','s1','--evidence-file',str(self.root/'empty.txt'),'--message-ref','test']
        self.cli(*base,expected=2);Image.new('RGB',(1024,576),'black').save(self.root/'s1.png');base[-3]=str(self.root/'user-g1.txt');self.cli(*base,expected=2)
    def test_sample_quota_and_duplicate_reservation(self):
        j=self.cli('begin','--action','sample','--clip','v1','--count','2')
        self.cli('begin','--action','sample','--clip','v1','--count','1',expected=2)
        self.cli('job','--id',j['job_id'],'--status','unknown');self.cli('begin','--action','sample','--clip','v1',expected=2)
        self.cli('job','--id',j['job_id'],'--status','failed')
        self.cli('begin','--action','sample','--clip','v2','--count','3',expected=2)
        self.cli('begin','--action','sample','--clip','v2','--count','2')
    def test_unknown_provider_blocks_generation(self):
        self.config['providers']['image']['verified']=False;g.write(self.cfg,self.config);self.cli('check','--action','sample',expected=2)
    def test_qc_coverage_and_staleness(self):
        self.g2();data=self.qdata();data['outputs']=data['outputs'][:1];path=self.root/'qc.json';g.write(path,data);self.cli('qc','--report',str(path),expected=2)
        self.qpass();(self.root/'pilot2.mp4').write_bytes(b'changed');self.cli('check','--action','batch-video',expected=2)
    def test_reference_bytes_bound_to_approval(self):
        ref=self.root/'reference.txt';ref.write_text('v1');self.config['reference_files']=['reference.txt'];g.write(self.cfg,self.config);self.g1();ref.write_text('v2');self.cli('check','--action','batch-frames',expected=2)
    def test_board_escapes_and_does_not_approve(self):
        self.reg('samples',[{'item_id':'s1','clip_id':'v1','path':'s1.png','notes':'<script>alert(1)</script>'}]);out=self.root/'board.html'
        review_board.render(self.state,'samples',out);s=out.read_text();self.assertIn('&lt;script&gt;',s);self.assertNotIn('<script>alert(1)</script>',s)
        self.assertIn('data:image/jpeg;base64,',s);self.cli('check','--action','batch-frames',expected=2)
    def test_lock_prevents_concurrent_write(self):
        lock=Path(str(self.state)+'.lock');lock.write_text('test');self.cli('status',expected=2);lock.unlink()

    def test_missing_b0_and_g0_block_samples(self):
        p=g.read(self.state);p.pop('brief_approval');g.write(self.state,p)
        self.assertIn('B0',self.cli('check','--action','sample',expected=2)['error'])
        self.preflight();p=g.read(self.state);p.pop('settings_choice');g.write(self.state,p)
        self.assertIn('G0',self.cli('check','--action','sample',expected=2)['error'])
    def test_image_model_and_native_1k_locked(self):
        base=copy.deepcopy(self.config)
        for family,resolution in [('other-2.5','1K'),('IMAGE2.0','2K'),('IMAGE2.0','4K')]:
            cfg=copy.deepcopy(base);cfg['providers']['image']['model_family']=family;cfg['image_output']['resolution']=resolution;g.write(self.cfg,cfg)
            self.cli('check','--action','sample',expected=2)
        g.write(self.cfg,base);self.cli('check','--action','sample')
    def test_image_25_requires_verified_mapping(self):
        self.config['providers']['image'].update({'model_family':'IMAGE2.5','model':'fixture-25'})
        g.write(self.cfg,self.config);self.cli('check','--action','sample',expected=2)
        self.config['providers']['image'].update({'verified_model_family':'IMAGE2.5','verified_model':'fixture-25'})
        g.write(self.cfg,self.config);self.cli('check','--action','sample')
    def test_video_choice_change_invalidates(self):
        self.g2();self.config['providers']['video']['model']='different-model';g.write(self.cfg,self.config)
        self.assertIn('G0',self.cli('check','--action','video-pilot',expected=2)['error'])
    def test_missing_video_specs_cannot_be_confirmed(self):
        for key in ('resolution','width','height'):
            cfg=copy.deepcopy(self.config);cfg['video_output'][key]=None;g.write(self.cfg,cfg)
            self.cli('settings',expected=2)
        cfg=copy.deepcopy(self.config);cfg['canvas']['aspect_ratio']=None;g.write(self.cfg,cfg);self.cli('settings',expected=2)
    def test_native_dimensions_and_aspect_validated(self):
        self.config['canvas']['aspect_ratio']='9:16';g.write(self.cfg,self.config);self.cli('settings',expected=2)
    def test_request_cannot_override_generation_settings(self):
        req=self.request('sample','v1');data=g.read(req);data['settings']['resolution']='4K';g.write(req,data)
        self.cli('begin','--action','sample','--clip','v1','--request',str(req),expected=2)
    def test_done_cannot_bypass_receipt(self):
        j=self.cli('begin','--action','sample','--clip','v1')
        self.cli('job','--id',j['job_id'],'--status','done',expected=2)
    def test_output_size_and_native_receipt_mismatch_rejected(self):
        req=self.request('sample','v1');j=self.cli('begin','--action','sample','--clip','v1','--request',str(req))
        Image.new('RGB',(2048,1152),'green').save(self.root/'high.png')
        receipt=self.root/'receipt.json';data={'settings':g.read(req)['settings'],'evidence':'synthetic','outputs':['high.png']};g.write(receipt,data)
        self.cli('finish','--id',j['job_id'],'--receipt',str(receipt),expected=2)
        data['outputs']=['s1.png'];data['settings']['resolution']='2K';g.write(receipt,data)
        self.cli('finish','--id',j['job_id'],'--receipt',str(receipt),expected=2)
    def test_review_requires_verified_result(self):
        path=self.root/'unverified.json';g.write(path,{'items':[{'item_id':'s1','clip_id':'v1','path':'s1.png'}]})
        self.cli('register','--stage','samples','--manifest',str(path),expected=2)
    def test_same_person_two_looks_counts_separately(self):
        b=self.config['creative_brief'];b['people']=b['people'][:1];b['role_people']['B']='P1';b['looks'][1]['person_id']='P1';g.write(self.cfg,self.config)
        counts=self.cli('brief')['counts'];self.assertEqual(counts['people'],1);self.assertEqual(counts['roles'],2);self.assertEqual(counts['source_looks'],2)
        self.cli('check','--action','sample',expected=2)
    def test_unresolved_look_and_background_block_brief(self):
        base=copy.deepcopy(self.config)
        cfg=copy.deepcopy(base);cfg['creative_brief']['looks'][0]['change']=None;g.write(self.cfg,cfg);self.cli('brief',expected=2)
        cfg=copy.deepcopy(base);cfg['creative_brief']['backgrounds'][0]['description']='';g.write(self.cfg,cfg);self.cli('brief',expected=2)
    def test_appearance_changes_require_scope_and_confirmation(self):
        look=self.config['creative_brief']['looks'][0];look.update({'change':'change','target_look_id':'L3','target_description':'navy jacket','change_scope':['face']})
        g.write(self.cfg,self.config);self.cli('brief',expected=2)
        look['change_scope']=['clothing'];g.write(self.cfg,self.config);self.cli('brief');self.cli('check','--action','sample',expected=2)
        self.preflight();self.cli('check','--action','sample')
    def test_sample_approval_covers_every_look(self):
        r=self.reg('samples',[{'item_id':'s1','clip_id':'v1','path':'s1.png'}])
        self.cli('approve','--stage','samples','--review-hash',r['review_hash'],'--selected','s1','--evidence-file',str(self.root/'user-g1.txt'),'--message-ref','synthetic',expected=2)

    def test_empty_background_is_not_a_composite_review(self):
        item=self.produce('samples',{'item_id':'s1','clip_id':'v1','path':'s1.png'});item['kind']='empty_background'
        path=self.root/'empty-scene.json';g.write(path,{'items':[item]});self.cli('register','--stage','samples','--manifest',str(path),expected=2)
    def test_video_request_requires_selected_frame(self):
        self.g2();req=self.request('video-pilot','v1');data=g.read(req);data['input_files']=data['input_files'][:1];g.write(req,data)
        self.cli('begin','--action','video-pilot','--clip','v1','--request',str(req),expected=2)

    def test_qc_requires_finished_pilot_job(self):
        self.g2();data=self.qdata();data['outputs'][0].pop('job_id');path=self.root/'qc-unbound.json';g.write(path,data)
        self.cli('qc','--report',str(path),expected=2)
    def test_changed_pilot_receipt_invalidates_qc(self):
        self.g2();self.qpass();state=g.read(self.state);job=next(j for j in state['jobs'] if j['action']=='video-pilot')
        receipt=Path(job['receipt_file']);data=g.read(receipt);data['evidence']='changed receipt';g.write(receipt,data)
        self.cli('check','--action','batch-video',expected=2)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg/FFprobe not installed')
class ExtractTests(unittest.TestCase):
    def test_first_decoded_frame_and_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'input'/'one').mkdir(parents=True);(root/'input'/'two').mkdir()
            src=root/'input'/'one'/'片段.mp4'
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi','-i','color=c=red:s=160x120:r=10:d=0.4','-f','lavfi','-i','color=c=blue:s=160x120:r=10:d=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]','-map','[v]','-c:v','libx264','-pix_fmt','yuv420p',str(src)],check=True)
            shutil.copy2(src,root/'input'/'two'/'片段.mp4')
            target,data=extract_frames.extract(root/'input',root/'frames',True)
            self.assertEqual(len(data['clips']),2);self.assertNotEqual(data['clips'][0]['clip_id'],data['clips'][1]['clip_id'])
            for c in data['clips']:
                self.assertNotIn('error',c);self.assertGreater(len(c['candidates']),0)
                with Image.open(c['first_frame']) as im:r,g,b=im.convert('RGB').getpixel((80,60));self.assertGreater(r,200);self.assertLess(b,30)
            self.assertTrue(target.is_file())

if __name__=='__main__':unittest.main(verbosity=2)
