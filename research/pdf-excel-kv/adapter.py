"""Opt-in research factory. No production route imports this module."""
from dataclasses import dataclass,field
from pathlib import Path
import hashlib,importlib.metadata,json,threading

@dataclass
class Selection:
    converter:object
    active:bool=False
    reason:str='disabled'
    states:list=field(default_factory=list)

def compatible():
    try:
        records=json.loads(Path(__file__).with_name('runtime-lock.json').read_text())
        for item in records:
            dist=importlib.metadata.distribution(item['package'])
            if dist.version!=item['version']:return False
            path=Path(dist.locate_file(item['path']))
            if path.stat().st_size>2*1024*1024:return False
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:return False
        return True
    except (OSError,ValueError,TypeError,AttributeError,KeyError,importlib.metadata.PackageNotFoundError):return False

class PredictorBusy(RuntimeError):pass

def guard_predictor(predictor,max_cache_bytes):
    """Own one predictor; reject concurrent entry rather than mixing model state."""
    from torch import nn
    from budget import CacheBudget
    from cached_attention import CachedAttention
    if "_kv_research_state" in predictor.__dict__:raise ValueError("Predictor already guarded")
    CacheBudget(max_cache_bytes) # validate before any mutation
    model=predictor._model;layers=list(model._tag_transformer._decoder.layers)
    if len(layers)!=6 or any(type(l.multihead_attn)is not nn.MultiheadAttention for l in layers):raise ValueError('Unsupported decoder graph')
    previous=predictor.predict;lock=threading.Lock()
    state=dict(calls=0,setup_fallbacks=0,operator_fallbacks=0,failures=0,budget_declines=0,peak_cache_bytes=0,live_cache_bytes=0,busy_rejections=0)
    def guarded(*args,**kwargs):
        if not lock.acquire(blocking=False):
            state['busy_rejections']+=1;raise PredictorBusy('Research predictor is already in use')
        installed=[];budget=None
        try:
            budget=CacheBudget(max_cache_bytes);state['calls']+=1
            try:
                for layer in layers:
                    old=layer.multihead_attn;new=CachedAttention(old,budget=budget)
                    installed.append((layer,old,new));layer.multihead_attn=new
            except (RuntimeError,ValueError,MemoryError):
                for layer,old,new in reversed(installed):layer.multihead_attn=old;new.clear()
                installed=[];state['setup_fallbacks']+=1
            return previous(*args,**kwargs)
        finally:
            # The lock covers initialization, execution and all cleanup.
            try:
                for layer,old,new in reversed(installed):
                    try:layer.multihead_attn=old
                    finally:new.clear()
                    state['operator_fallbacks']+=new.fallbacks;state['failures']+=new.failures;state['budget_declines']+=new.budget_declines
                if budget is not None:
                    state['peak_cache_bytes']=max(state['peak_cache_bytes'],budget.peak)
                    state['live_cache_bytes']=budget.used
            finally:lock.release()
    predictor.predict=guarded
    predictor._kv_research_state=state
    return state

def _baseline(models):
    from layout_tables import converter_for
    return converter_for(models)

def build_converter(models,*,enabled=False,max_cache_bytes=32*1024*1024):
    """False by default; no environment switch and no change to service wiring."""
    baseline=_baseline(models);result=Selection(baseline)
    if enabled is not True:return result
    if not compatible():result.reason='dependency mismatch';return result
    from budget import CacheBudget
    CacheBudget(max_cache_bytes)
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter,PdfFormatOption
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    class ResearchPipeline(StandardPdfPipeline):
        def _init_models(self):
            super()._init_models()
            try:
                state=guard_predictor(self.table_model.tf_predictor,max_cache_bytes)
                result.states.append(state)
            except (AttributeError,TypeError,ValueError,RuntimeError):
                result.reason='unsupported model graph';result.active=False
    options=baseline.format_to_options[InputFormat.PDF].pipeline_options.model_copy(deep=True)
    result.converter=DocumentConverter(allowed_formats=[InputFormat.PDF],format_options={InputFormat.PDF:PdfFormatOption(pipeline_cls=ResearchPipeline,pipeline_options=options)})
    result.active=True;result.reason='research enabled'
    return result
