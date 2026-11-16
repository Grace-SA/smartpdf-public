"""Offline four-way page orientation; pixels are transposed without resampling.

Preprocessing follows Paddle's pinned inference.yml (RGB, short side 256,
center crop 224, ImageNet normalization). This is not OCR verification.
"""
import argparse,hashlib,json,os,shutil
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import onnxruntime as ort
from integrity import verify_files

ROOT=Path(__file__).resolve().parent


def tensor(image):
    a=np.asarray(image.convert('RGB'));h,w=a.shape[:2]
    a=cv2.resize(a,(int(w*256/min(w,h)),int(h*256/min(w,h))))
    h,w=a.shape[:2];a=a[(h-224)//2:(h-224)//2+224,(w-224)//2:(w-224)//2+224]
    a=(a.astype(np.float32)/255-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
    return a.transpose(2,0,1)[None]


def decision(scores):
    scores=np.asarray(scores).reshape(-1)
    if scores.shape!=(4,) or not np.isfinite(scores).all() or np.min(scores)<0 or np.max(scores)>1 or abs(scores.sum()-1)>.001:
        raise ValueError('Invalid orientation probabilities')
    order=np.argsort(scores);winner=int(order[-1]);confidence=float(scores[winner])
    return (winner*90 if confidence>=.9 and confidence-float(scores[order[-2]])>=.5 else 0),confidence


def run(images,out):
    root=Path(os.getenv('SMARTPPT_ORIENTATION_MODEL',str(ROOT/'models/PP-LCNet_x1_0_doc_ori_onnx')))
    manifest=json.loads((ROOT/'orientation-manifest.json').read_text());verify_files(root,manifest['files'])
    ort.disable_telemetry_events();opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1;opts.log_severity_level=3
    session=ort.InferenceSession(str(root/'inference.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
    out.mkdir(parents=True,exist_ok=True)
    for source in images:
        target=out/source.name
        if target.resolve()==source.resolve():raise ValueError('Orientation output must be separate')
        with Image.open(source) as image:
            angle,confidence=decision(session.run(None,{session.get_inputs()[0].name:tensor(image)})[0])
            before=list(image.size)
            if angle:image.transpose({90:Image.Transpose.ROTATE_90,180:Image.Transpose.ROTATE_180,270:Image.Transpose.ROTATE_270}[angle]).save(target)
            else:shutil.copyfile(source,target)
        record={'input_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                'input_size':before,'angle':angle,'confidence':confidence,'model_revision':manifest['revision']}
        target.with_suffix('.orientation.json').write_text(json.dumps(record,indent=2))
        print(source.name,angle,round(confidence,4),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('images',nargs='+',type=Path)
    a=p.parse_args();run(a.images,a.out)
