"""Bounded whole-show contribution evidence for structural refusal only."""
import io,math
from collections import Counter
import numpy as np
from pdfminer.converter import PDFPageAggregator
from pdfminer.pdfinterp import PDFResourceManager,PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pypdf import PdfReader,PdfWriter
from pypdf.generic import ArrayObject,ContentStream,NameObject,NumberObject,TextStringObject,ByteStringObject,DictionaryObject
from source_hidden_ocr import resolve,read_operations,numbers,resource,bounded_content
from source_row_visibility import _ALLOWED,opaque_state

def color_space(value):
    value=resolve(value)
    if value in ('/DeviceGray','/DeviceRGB','/DeviceCMYK'):return True
    if not isinstance(value,ArrayObject)or len(value)!=4 or value[0]!='/Separation':return False
    if not isinstance(value[1],NameObject)or len(value[1])>128:return False
    alt=resolve(value[2]);n={'/DeviceGray':1,'/DeviceRGB':3,'/DeviceCMYK':4}.get(str(alt))
    if isinstance(alt,ArrayObject)and len(alt)==2 and alt[0]=='/ICCBased':
        profile=resolve(alt[1]);n=profile.get('/N')
        if type(n)is bool or n not in(1,3,4)or set(profile)-{'/N','/Length','/Filter','/Alternate','/Range'}:return False
        if profile.get('/Alternate')not in(None,{1:'/DeviceGray',3:'/DeviceRGB',4:'/DeviceCMYK'}[n]):return False
        if '/Range'in profile and numbers(profile['/Range'],2*n)!=tuple([0.,1.]*n):return False
        blob=bounded_content(profile,1_048_576)
        if len(blob)<132 or int.from_bytes(blob[:4],'big')!=len(blob)or blob[36:40]!=b'acsp'or blob[16:20]!={1:b'GRAY',3:b'RGB ',4:b'CMYK'}[n]:return False
        # The declared tag table and every tag extent must stay inside this profile.
        tags=int.from_bytes(blob[128:132],'big')
        if tags>64 or 132+12*tags>len(blob):return False
        for off in range(132,132+12*tags,12):
            start=int.from_bytes(blob[off+4:off+8],'big');size=int.from_bytes(blob[off+8:off+12],'big')
            if start<132+12*tags or size<8 or start+size>len(blob):return False
    if n not in(1,3,4):return False
    f=resolve(value[3])
    if type(f)is not DictionaryObject or set(f)-{'/FunctionType','/Domain','/Range','/C0','/C1','/N'}or f.get('/FunctionType')!=2:return False
    if numbers(f.get('/Domain',[]),2)!=(0.,1.):return False
    if '/Range'in f and numbers(f['/Range'],n*2)!=tuple([0.,1.]*n):return False
    a=numbers(f.get('/C0',[]),n);b=numbers(f.get('/C1',[]),n);power=numbers([f.get('/N')],1)[0]
    return all(0<=v<=1 for v in a+b)and .1<=power<=10

def validate(source,reader):
    if resolve(source.get('/Annots'))or source.get('/Group')or source.get('/UserUnit',1)!=1:return None
    raw=resolve(source.get('/Contents'));ops=read_operations(list(raw)if isinstance(raw,ArrayObject)else[raw],reader,dict(bytes=0,streams=0,ops=0,forms=0))
    res=resolve(source['/Resources']);spaces=resolve(res.get('/ColorSpace',DictionaryObject()))
    if not isinstance(spaces,DictionaryObject)or len(spaces)>16:return None
    if any(not color_space(v)for v in spaces.values()):return None
    depth=0;intext=False;shows=[]
    for index,(args,op)in enumerate(ops):
        if op not in _ALLOWED or op in(b"'",b'"'):return None
        if op==b'q':
            depth+=1
            if depth>32:return None
        elif op==b'Q':
            depth-=1
            if depth<0:return None
        elif op==b'cm':
            a,b,c,d,_,_=numbers(args,6)
            if b or c or a!=d or not .001<=a<=1000:return None
        elif op==b'BT':
            if intext:return None
            intext=True
        elif op==b'ET':
            if not intext:return None
            intext=False
        elif op==b'Tr':
            if numbers(args,1)!=(0.,):return None
        elif op==b'gs':
            if len(args)!=1:return None
            state=resource(res,'/ExtGState',args[0]);safe=dict(state)
            for key in('/TK','/SA'):
                if key in safe:
                    if resolve(safe[key])!=True:return None
                    del safe[key]
            if not opaque_state(safe):return None
        elif op in(b'cs',b'CS'):
            if len(args)!=1 or not isinstance(args[0],NameObject):return None
            if args[0]not in('/DeviceGray','/DeviceRGB','/DeviceCMYK')and args[0]not in spaces:return None
        elif op==b'Tf':
            if len(args)!=2 or resource(res,'/Font',args[0]).get('/Subtype')not in('/Type1','/TrueType','/Type0'):return None
        elif op in(b'Tj',b'TJ'):
            if not intext or len(args)!=1:return None
            seq=list(args[0])if op==b'TJ'else args
            raw=[]
            for value in seq:
                if isinstance(value,TextStringObject):raw.append(value.original_bytes.hex())
                elif isinstance(value,ByteStringObject):raw.append(bytes(value).hex())
                else:raw.append(numbers([value],1)[0])
            shows.append((index,raw))
    if depth or intext or not 1<=len(shows)<=500:return None
    return ops,shows

class Capture(PDFPageAggregator):
    def __init__(self,manager):super().__init__(manager);self.shows=[];self.count=0;self.active=None
    def begin_figure(self,*args):raise ValueError('Forms unsupported')
    def render_string(self,state,seq,ncs,gs):
        values=list(seq);row={'raw':[v.hex()if isinstance(v,bytes)else float(v)for v in values],'render':state.render,'glyphs':[]};self.shows.append(row)
        if len(self.shows)>500:raise ValueError('Show budget')
        self.active=row
        return super().render_string(state,values,ncs,gs)
    def render_char(self,matrix,font,size,scaling,rise,cid,ncs,gs):
        self.count+=1
        if self.count>10000:raise ValueError('Glyph budget')
        advance=super().render_char(matrix,font,size,scaling,rise,cid,ncs,gs);g=self.cur_item._objs[-1]
        self.active['glyphs'].append({'text':g.get_text(),'bbox':list(g.bbox),'matrix':list(matrix)})
        return advance

class Evidence:
    def __init__(self,page):
        self.page=page;self.calls=0;self.cache={};self.rendered_pixels=0;self.serialized=0
        if page.rotation or tuple(page.bbox)!=(0,0,page.width,page.height)or tuple(page.cropbox)!=tuple(page.mediabox)or not all(isinstance(v,(int,float))and math.isfinite(v)and v>0 for v in(page.width,page.height))or math.ceil(page.width*2)*math.ceil(page.height*2)>3_000_000:raise ValueError('Page bounds')
        stream=page.pdf.stream;position=stream.tell()
        try:
            reader=PdfReader(stream);source=reader.pages[page.page_number-1];validated=validate(source,reader)
            if validated is None:raise ValueError('Unsupported drawing state')
            self.ops,self.rawshows=validated;self.writer=PdfWriter();self.source=self.writer.add_page(source);buffer=io.BytesIO();self.writer.write(buffer)
            if buffer.tell()>40_000_000:raise ValueError('Copy budget')
            self.original=buffer.getvalue();self.serialized=len(self.original)
        finally:stream.seek(position)
        manager=PDFResourceManager();device=Capture(manager);interpreter=PDFPageInterpreter(manager,device)
        interpreter.process_page(next(PDFPage.get_pages(io.BytesIO(self.original))))
        if len(device.shows)!=len(self.rawshows)or any(a['raw']!=b[1]or a['render']!=0 for a,b in zip(device.shows,self.rawshows)):raise ValueError('Show identity mismatch')
        self.shows=device.shows
        def key(text,b):return(text,*(round(v,5)for v in b))
        actual=Counter(key(g['text'],(g['x0'],page.height-g['bottom'],g['x1'],page.height-g['top']))for g in page.chars)
        captured=Counter(key(g['text'],g['bbox'])for s in self.shows for g in s['glyphs'])
        if actual!=captured or any(v!=1 for k,v in actual.items()if k[0].strip()):raise ValueError('Glyph identity mismatch')
        self.actual=None
    def render(self,data):
        self.rendered_pixels+=math.ceil(self.page.height*2)*math.ceil(self.page.width*2)
        if self.rendered_pixels>21_000_000:raise ValueError('Total render budget')
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(data)as doc:
            p=doc[0];bitmap=p.render(scale=2,no_smoothtext=True,no_smoothpath=True,no_smoothimage=True,prefer_bgrx=True);im=np.array(bitmap.to_pil().convert('RGB'));bitmap.close();p.close()
        expected=(math.ceil(self.page.height*2),math.ceil(self.page.width*2),3)
        if im.shape!=expected or im.shape[0]*im.shape[1]>3_000_000:raise ValueError('Render dimensions')
        return im
    def visible(self,index):
        if type(index)is not int or not 0<=index<len(self.shows):raise ValueError('Target budget')
        if index in self.cache:return self.cache[index]
        self.calls+=1
        if self.calls>6:raise ValueError('Target budget')
        if self.actual is None:
            self.rendered_pixels+=math.ceil(self.page.height*2)*math.ceil(self.page.width*2)
            if self.rendered_pixels>21_000_000:raise ValueError('Total render budget')
            self.actual=np.asarray(self.page.to_image(resolution=144).original.convert('RGB'))
            if not np.array_equal(self.actual,self.render(self.original)):raise ValueError('Copy rendering mismatch')
        target=self.rawshows[index][0];ops=[]
        for i,(a,o)in enumerate(self.ops):
            if i==target:ops.append(([NumberObject(3)],b'Tr'))
            ops.append((a,o))
            if i==target:ops.append(([NumberObject(0)],b'Tr'))
        content=ContentStream(None,self.writer);content.operations=ops;self.source[NameObject('/Contents')]=self.writer._add_object(content);buf=io.BytesIO();self.writer.write(buf)
        self.serialized+=buf.tell()
        if buf.tell()>40_000_000 or self.serialized>80_000_000:raise ValueError('Modified copy budget')
        removed=self.render(buf.getvalue());diff=np.any(self.actual!=removed,axis=2);regions=np.zeros(diff.shape,dtype=bool)
        glyphs=[g for g in self.shows[index]['glyphs']if g['text'].strip()]
        for g in glyphs:
            x0,y0,x1,y1=g['bbox'];x0,y0,x1,y1=math.floor(x0*2),math.floor((self.page.height-y1)*2),math.ceil(x1*2),math.ceil((self.page.height-y0)*2)
            if not 0<=x0<x1<=diff.shape[1]or not 0<=y0<y1<=diff.shape[0]or np.count_nonzero(diff[y0:y1,x0:x1])<2:
                self.cache[index]=False;return False
            regions[max(0,y0-2):min(diff.shape[0],y1+2),max(0,x0-2):min(diff.shape[1],x1+2)]=True
        self.cache[index]=bool(glyphs)and not np.any(diff&~regions)
        return self.cache[index]
