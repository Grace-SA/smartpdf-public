"""Offline PP-OCRv6 medium detection + recognition using official ONNX models."""
import argparse,hashlib,json,time,os
from pathlib import Path
import yaml
from PIL import Image
import onnxruntime as ort
ort.disable_telemetry_events()
from rapidocr import RapidOCR
ROOT=Path(__file__).resolve().parent

def engine():
    models=Path(os.getenv('SMARTPPT_OCR_MODELS',str(ROOT/'models')))
    for name in ('PP-OCRv6_medium_det_onnx','PP-OCRv6_medium_rec_onnx'):
        folder=models/name
        provenance=json.loads((folder/'provenance.json').read_text())
        for artifact in provenance['files']:
            if artifact['file'] in ('inference.onnx','inference.yml'):
                if hashlib.sha256((folder/artifact['file']).read_bytes()).hexdigest()!=artifact['sha256']:
                    raise ValueError('OCR model integrity check failed')
    rec=models/'PP-OCRv6_medium_rec_onnx'
    cfg=yaml.safe_load((rec/'inference.yml').read_text())
    keys=rec/'keys.txt';keys.write_text('\n'.join(cfg['PostProcess']['character_dict'])+'\n')
    return RapidOCR(params={
        'Global.use_cls':False,'Global.text_score':0.3,'Global.max_side_len':2400,
        'Global.log_level':'error','Det.limit_side_len':1600,'Det.limit_type':'max',
        'Det.mean':[0.485,0.456,0.406],'Det.std':[0.229,0.224,0.225],
        'Det.thresh':0.2,'Det.box_thresh':0.45,'Det.unclip_ratio':1.4,'Det.max_candidates':3000,
        'Det.model_path':str(models/'PP-OCRv6_medium_det_onnx/inference.onnx'),
        'Rec.model_path':str(rec/'inference.onnx'),'Rec.rec_keys_path':str(keys),
        'EngineConfig.onnxruntime.intra_op_num_threads':4,
        'EngineConfig.onnxruntime.inter_op_num_threads':1})

def run(images,out,resume=False):
    ocr=engine();out.mkdir(parents=True,exist_ok=True)
    for path in images:
        target=out/(path.stem+'.json')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if resume and target.exists() and json.loads(target.read_text()).get('input_sha256')==digest:continue
        start=time.monotonic();result=ocr(str(path));lines=[]
        if result.txts:
            for box,text,score in zip(result.boxes,result.txts,result.scores):
                lines.append({'polygon':box.tolist(),'text':text,'confidence':float(score)})
        with Image.open(path) as image:size=list(image.size)
        record={'engine':'PP-OCRv6-medium-ONNX','input_sha256':digest,
            'image_size':size,'lines':lines,'seconds':time.monotonic()-start}
        target.write_text(json.dumps(record,ensure_ascii=False,indent=2))
        print(path.name,len(lines),round(record['seconds'],3),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--resume',action='store_true');p.add_argument('images',nargs='+',type=Path)
    a=p.parse_args();run(a.images,a.out,a.resume)
