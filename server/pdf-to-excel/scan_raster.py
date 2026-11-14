"""Match a supported full-page scan's dimensions through final-PDF rendering."""
import math
from pypdf.errors import PyPdfError

MAX_PIXELS = 20_000_000


def raster_size(page, dpi):
    return math.ceil(page.width*dpi/72), math.ceil(page.height*dpi/72)


def resolution(page):
    """Otherwise retain the existing 144dpi path, never extract an image directly.

    Only one axis-aligned full-page image with a common native sampling interval
    is supported. PDF overlays are still rendered, including opaque covers.
    """
    fallback = 144
    if (getattr(page,'rotation',0) or tuple(page.bbox) != (0,0,page.width,page.height)
            or tuple(page.cropbox) != tuple(page.mediabox)
            or len(page.images) != 1):
        return fallback
    image = page.images[0]
    if any(abs(image.get(k, float('inf'))-v) > .01 for k,v in
           [('x0',0),('top',0),('x1',page.width),('bottom',page.height)]):
        return fallback
    size=image.get('srcsize')
    if (not isinstance(size,(tuple,list)) or len(size)!=2
            or any(not isinstance(n,int) or isinstance(n,bool) or n<=0 for n in size)
            or size[0]*size[1]>MAX_PIXELS):
        return fallback
    # ceil(page dimension * dpi / 72) must equal BOTH native dimensions.
    low=max((size[0]-1)*72/page.width,(size[1]-1)*72/page.height,144)
    high=min(size[0]*72/page.width,size[1]*72/page.height,300)
    if low>=high:
        return fallback
    dpi=(low+high)/2
    return dpi if raster_size(page,dpi)==tuple(size) and aligned_image(page,size) else fallback


def aligned_image(page, size):
    """Bounded content-stream proof; decline Forms, clipping, masks and skew."""
    try:
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject
        from source_hidden_ocr import resolve, read_operations, numbers, resource
        stream=page.pdf.stream; position=stream.tell()
        try:
            reader=getattr(page.pdf,'_scan_raster_reader',None)
            if reader is None:
                reader=PdfReader(stream);page.pdf._scan_raster_reader=reader
            source=reader.pages[page.page_number-1]
            if source.get('/UserUnit',1)!=1 or source.get('/Annots'):
                return False
            raw=resolve(source.get('/Contents'))
            operations=read_operations(list(raw) if isinstance(raw,ArrayObject) else [raw],reader,
                                       dict(bytes=0,streams=0,ops=0,forms=0))
            matrix=(1.,0.,0.,1.,0.,0.);stack=[];count=0
            for args,op in operations:
                if op==b'q':
                    if len(stack)>=64:return False
                    stack.append(matrix)
                elif op==b'Q':
                    if not stack:return False
                    matrix=stack.pop()
                elif op==b'cm':
                    a,b,c,d,e,f=numbers(args,6);A,B,C,D,E,F=matrix
                    matrix=numbers((a*A+b*C,a*B+b*D,c*A+d*C,c*B+d*D,e*A+f*C+E,e*B+f*D+F),6)
                elif op==b'Tr':
                    mode=numbers(args,1)[0]
                    if mode not in (0,1,2,3):return False
                elif op in (b'W',b'W*',b'gs',b'INLINE IMAGE'):
                    return False
                elif op==b'Do':
                    if len(args)!=1:return False
                    obj=resource(resolve(source['/Resources']),'/XObject',args[0]);count+=1
                    if (obj.get('/Subtype')!='/Image' or count!=1
                            or any(k in obj for k in ('/SMask','/Mask','/ImageMask'))
                            or (obj.get('/Width'),obj.get('/Height'))!=tuple(size)
                            or any(abs(a-b)>1e-6 for a,b in zip(matrix,(page.width,0,0,page.height,0,0)))):
                        return False
            return count==1 and not stack
        finally:
            stream.seek(position)
    except (PyPdfError,ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError,OSError):
        return False
