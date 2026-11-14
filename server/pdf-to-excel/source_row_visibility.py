"""Bounded final-render text contribution for optional native row recovery."""
import io,math
import numpy as np
from pypdf import PdfReader,PdfWriter
from pypdf.errors import PyPdfError
from pdfplumber.utils.exceptions import MalformedPDFException
from pypdf.generic import ArrayObject,ContentStream,NameObject
from source_hidden_ocr import resolve,read_operations,resource,numbers

_ALLOWED={b'q',b'Q',b'cm',b'w',b'J',b'j',b'M',b'd',b'ri',b'i',b'gs',
 b'm',b'l',b'c',b'v',b'y',b'h',b're',b'S',b's',b'f',b'F',b'f*',b'B',b'B*',b'b',b'b*',b'n',
 b'BT',b'ET',b'Tc',b'Tw',b'Tz',b'TL',b'Tf',b'Tr',b'Ts',b'Td',b'TD',b'Tm',b'T*',b'Tj',b'TJ',b"'",b'"',
 b'CS',b'cs',b'SC',b'SCN',b'sc',b'scn',b'RG',b'rg',b'K',b'k',b'G',b'g'}
_SHOW={b'Tj',b'TJ',b"'",b'"'}

def opaque_state(state):
    for key,value in state.items():
        value=resolve(value)
        if key=='/Type' and value=='/ExtGState':continue
        if key in ('/BG2','/UCR2') and value=='/Default':continue
        if key in ('/TR','/TR2') and value in ('/Default','/Identity'):continue
        if key in ('/OP','/op','/SA','/AIS') and value==False:continue
        if key=='/OPM' and value in (0,1):continue
        if key=='/SM' and 0<=numbers([value],1)[0]<=1:continue
        if key in ('/ca','/CA') and numbers([value],1)[0]==1:continue
        if key=='/SMask' and value=='/None':continue
        if key=='/BM' and value=='/Normal':continue
        return False
    return True


def contribution(page):
    """Decline unsupported graphics; never treat unrelated ink as text proof."""
    try:return _contribution(page)
    except (PyPdfError,MalformedPDFException,ValueError,TypeError,KeyError,AttributeError,OSError,RuntimeError,OverflowError):return None


def _contribution(page):
    if math.ceil(page.width*2)*math.ceil(page.height*2)>20_000_000:return None
    stream=page.pdf.stream;position=stream.tell()
    try:
        reader=PdfReader(stream);source=reader.pages[page.page_number-1]
        if source.get('/Annots') or source.get('/UserUnit',1)!=1:return None
        raw=resolve(source.get('/Contents'))
        ops=read_operations(list(raw)if isinstance(raw,ArrayObject)else[raw],reader,dict(bytes=0,streams=0,ops=0,forms=0))
        resources=resolve(source['/Resources']);depth=0
        for args,op in ops:
            if op not in _ALLOWED:return None
            if op==b'q':
                depth+=1
                if depth>64:return None
            elif op==b'Q':
                depth-=1
                if depth<0:return None
            elif op==b'cm':
                a,b,c,d,_,_=numbers(args,6)
                if any(abs(v-e)>1e-9 for v,e in zip((a,b,c,d),(1,0,0,1))):return None
            elif op==b'M':
                if not 0<numbers(args,1)[0]<=10:return None
            elif op==b'w':
                if not 0<=numbers(args,1)[0]<=100:return None
            elif op==b'Tr':
                if numbers(args,1)!=(0.,):return None
            elif op==b'gs':
                if len(args)!=1 or not opaque_state(resource(resources,'/ExtGState',args[0])):return None
            elif op in (b'CS',b'cs'):
                if len(args)!=1 or args[0] not in ('/DeviceGray','/DeviceRGB','/DeviceCMYK'):return None
            elif op==b'Tf':
                if len(args)!=2 or resource(resources,'/Font',args[0]).get('/Subtype') not in ('/Type1','/TrueType','/Type0'):return None
        if depth:return None
        writer=PdfWriter();target=writer.add_page(source)
        original=io.BytesIO();writer.write(original)
        stripped=ContentStream(None,writer);stripped.operations=[(args,op)for args,op in ops if op not in _SHOW]
        target[NameObject('/Contents')]=writer._add_object(stripped)
        without=io.BytesIO();writer.write(without)
        if original.tell()>40_000_000 or without.tell()>40_000_000:return None
        def render(data):
            import pypdfium2 as pdfium
            with pdfium.PdfDocument(data)as doc:
                p=doc[0];bitmap=p.render(scale=2,no_smoothtext=True,no_smoothpath=True,no_smoothimage=True,prefer_bgrx=True)
                image=np.array(bitmap.to_pil().convert('L'));bitmap.close();p.close();return image
        actual=np.asarray(page.to_image(resolution=144).original.convert('L'))
        copied=render(original.getvalue())
        if not np.array_equal(actual,copied):return None
        removed=render(without.getvalue())
        if removed.shape!=actual.shape:return None
        return actual,(removed.astype('int16')-actual.astype('int16')>=25)&(actual<200)
    finally:stream.seek(position)
