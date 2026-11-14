"""Self-contained synthetic glyph for isolated counterexamples, not source truth."""
import numpy as np
from PIL import Image,ImageDraw,ImageFont

def digit_image():
    image=Image.new('RGB',(20,24),'white')
    ImageDraw.Draw(image).text((4,0),'3',font=ImageFont.load_default(size=16),fill='black')
    # Trim only outer whitespace, then add a three-pixel white guard.
    gray=np.array(image.convert('L'));ys,xs=np.where(gray<245)
    image=image.crop((int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1))
    out=Image.new('RGB',(image.width+6,image.height+6),'white');out.paste(image,(3,3))
    return np.array(out)
