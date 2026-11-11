"""Offline native MLX Unlimited OCR 2, used for independent structure evidence."""
import argparse,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
from u2_parser import parse_blocks
from integrity import verify_u2_model
from PIL import Image

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('images',type=Path,nargs='+');a=p.parse_args()
    model_path=Path(os.getenv('SMARTPPT_U2_MODEL',str(ROOT/'models/u2')))
    if not model_path.is_dir():raise ValueError('Set SMARTPPT_U2_MODEL to the verified offline model directory')
    verify_u2_model(model_path,json.loads((ROOT/'u2-manifest.json').read_text()))
    from mlx_vlm import apply_chat_template,generate,load
    import mlx.core as mx
    start=time.monotonic();model,processor=load(str(model_path),trust_remote_code=False)
    print('loaded',round(time.monotonic()-start,3),flush=True);a.out.mkdir(parents=True,exist_ok=True)
    for image in a.images:
        start=time.monotonic();mx.reset_peak_memory()
        prompt=apply_chat_template(processor,model.config,'Multi page parsing.',num_images=1)
        result=generate(model,processor,prompt,image=[str(image)],max_tokens=4096,temperature=0)
        with Image.open(image) as im:image_size=list(im.size)
        record={'engine':'Unlimited-OCR-2-MLX-BF16','input_sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
            'image_size':image_size,'coordinate_space':'normalized-1000',
            'blocks':parse_blocks(result.text),'raw':result.text,'capped':result.generation_tokens>=4096,
            'tokens':result.generation_tokens,'seconds':time.monotonic()-start,'mlx_peak_bytes':mx.get_peak_memory()}
        (a.out/(image.stem+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
        print(image.name,record['tokens'],round(record['seconds'],3),'capped',record['capped'],flush=True)
if __name__=='__main__':main()
