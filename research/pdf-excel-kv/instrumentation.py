"""Scoped research instrumentation. Caller must own one immutable predictor."""
from contextlib import contextmanager
from cached_attention import CachedAttention
from budget import CacheBudget
@contextmanager
def install(model,mode,on_logits,on_prediction):
    installed=[];hook=None;previous=model.predict;changed=False
    budget=CacheBudget()
    had_instance_predict="predict" in model.__dict__
    instance_predict=model.__dict__.get("predict")
    try:
        if mode in ('cached','shadow'):
            for layer in model._tag_transformer._decoder.layers:
                original=layer.multihead_attn;wrapper=CachedAttention(original,shadow=mode=='shadow',budget=budget)
                installed.append((layer,original,wrapper));layer.multihead_attn=wrapper
        hook=model._tag_transformer._fc.register_forward_hook(lambda mod,args,out:on_logits(out))
        def record(*args,**kwargs):
            out=previous(*args,**kwargs);on_prediction(out);return out
        model.predict=record;changed=True
        yield [wrapper for _,_,wrapper in installed]
    finally:
        if changed:
            if had_instance_predict:model.predict=instance_predict
            else:delattr(model,"predict")
        if hook is not None:hook.remove()
        for layer,original,wrapper in reversed(installed):
            layer.multihead_attn=original;wrapper.clear()
