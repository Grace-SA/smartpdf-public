"""Validate page normalization and restore the original visual orientation."""
import hashlib,json,math,os,subprocess
from pathlib import Path
from PIL import Image
from .config import ConversionError


def validate_orientation(source,target,record):
    angle=record.get('angle');confidence=record.get('confidence')
    if (type(angle)!=int or angle not in (0,90,180,270) or type(confidence) not in (float,int)
        or not math.isfinite(confidence) or not 0<=confidence<=1 or (angle and confidence<.9)):
        raise ConversionError('invalid_orientation')
    if (record.get('input_sha256')!=hashlib.sha256(source.read_bytes()).hexdigest()
        or record.get('output_sha256')!=hashlib.sha256(target.read_bytes()).hexdigest()):
        raise ConversionError('orientation_provenance_mismatch')
    with Image.open(source) as original,Image.open(target) as result:
        if record.get('input_size')!=list(original.size):raise ConversionError('orientation_geometry_mismatch')
        expected=original.transpose({90:Image.Transpose.ROTATE_90,180:Image.Transpose.ROTATE_180,270:Image.Transpose.ROTATE_270}[angle]) if angle else original
        if expected.size!=result.size or expected.convert('RGB').tobytes()!=result.convert('RGB').tobytes():
            raise ConversionError('orientation_pixels_mismatch')
    return angle


def prepare_images(images,folder,settings):
    if not settings.orientation_runner:return images,{}
    python=Path(settings.ocr_python);runner=Path(settings.orientation_runner)
    if not python.is_file() or not runner.is_file():raise ConversionError('orientation_not_configured')
    dest=folder/'oriented';dest.mkdir()
    try:
        subprocess.run([str(python),str(runner),'--out',str(dest),*[str(p) for p in images.values()]],
                       check=True,timeout=settings.job_timeout,capture_output=True,
                       env=dict(os.environ,HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1'))
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as error:
        raise ConversionError('orientation_failed') from error
    prepared={};angles={}
    for index,source in images.items():
        target=dest/source.name
        try:record=json.loads(target.with_suffix('.orientation.json').read_text());angles[index]=validate_orientation(source,target,record)
        except (OSError,ValueError,TypeError) as error:raise ConversionError('invalid_orientation_result') from error
        prepared[index]=target
    return prepared,angles


def restore_point(x,y,angle,width,height):
    if angle==90:return height-y,x
    if angle==180:return width-x,height-y
    if angle==270:return y,width-x
    return x,y


def restore_shapes(slide,angle,upright_width,upright_height):
    """Inverse of PIL's counterclockwise transpose, in PowerPoint EMUs."""
    if angle not in (0,90,180,270):raise ConversionError('invalid_orientation')
    if not angle:return
    for shape in slide.shapes:
        x=shape.left+shape.width/2;y=shape.top+shape.height/2
        x,y=restore_point(x,y,angle,upright_width,upright_height)
        shape.left=round(x-shape.width/2);shape.top=round(y-shape.height/2)
        shape.rotation=(shape.rotation+angle)%360
