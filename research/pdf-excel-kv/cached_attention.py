"""Research-only bounded CPU cross-attention cache; never imported by production.

Operation order follows torch 2.15 functional multi_head_attention_forward's
unmasked, need_weights=False encoder-decoder path. See PyTorch's BSD-3-Clause
license. No installed dependency is edited. Unsupported paths use the original.
"""
import torch
from torch import nn
from torch.nn import functional as F
from budget import CacheBudget,CacheDeclined

def bits_equal(a,b):
    return a.shape==b.shape and torch.equal(a.contiguous().view(torch.int32),b.contiguous().view(torch.int32))

class CachedAttention(nn.Module):
    def __init__(self, original, shadow=False, budget=None):
        super().__init__();self.original=original;self.shadow=shadow;self.entry=None
        self.hits=0;self.misses=0;self.fallbacks=0;self.compared=0;self.maxbytes=0
        self.training=original.training
        self.budget=budget if budget is not None else CacheBudget()
        self.reserved=0;self.disabled=False;self.failures=0;self.budget_declines=0
    def clear(self):
        self.entry=None
        if self.reserved:self.budget.release(self.reserved);self.reserved=0
    def eligible(self,q,k,v,kw):
        m=self.original
        if 'forward'in m.__dict__:return False
        if type(m)is not nn.MultiheadAttention or self.training or m.training or torch.is_grad_enabled() or torch.is_autocast_enabled('cpu'):return False
        if any(kw.get(x)is not None for x in ('key_padding_mask','attn_mask')) or kw.get('need_weights',True) is not False or kw.get('is_causal',False):return False
        if set(kw)-{'key_padding_mask','attn_mask','need_weights','average_attn_weights','is_causal'}:return False
        if m.batch_first or not m._qkv_same_embed_dim or m.bias_k is not None or m.bias_v is not None or m.add_zero_attn:return False
        if any(type(t)is not torch.Tensor or t.device.type!='cpu' or t.dtype!=torch.float32 or t.is_nested for t in (q,k,v)):return False
        if k is not v or q is k or q.dim()!=3 or k.dim()!=3 or q.shape[1]!=k.shape[1] or q.shape[2]!=k.shape[2] or q.shape[2]!=m.embed_dim:return False
        if not (q.shape[0]==1 and 1<=k.shape[0]<=4096 and 1<=q.shape[1]<=4 and 1<=m.embed_dim<=1024 and m.embed_dim%m.num_heads==0):return False
        if any(getattr(mod,name) for mod in (m,m.out_proj) for name in ('_forward_hooks','_forward_pre_hooks','_backward_hooks','_backward_pre_hooks')):return False
        glob=nn.modules.module
        if any(getattr(glob,name,{})for name in ('_global_forward_hooks','_global_forward_pre_hooks','_global_backward_hooks','_global_backward_pre_hooks')):return False
        if type(m.out_proj)is not nn.modules.linear.NonDynamicallyQuantizableLinear:return False
        for t in (m.in_proj_weight,m.in_proj_bias,m.out_proj.weight,m.out_proj.bias):
            if t is not None and (type(t)is not nn.Parameter or t.device.type!='cpu' or t.dtype!=torch.float32):return False
        if m.in_proj_weight is None or m.in_proj_weight.shape!=(3*m.embed_dim,m.embed_dim):return False
        if m.in_proj_bias is not None and m.in_proj_bias.shape!=(3*m.embed_dim,):return False
        # One per-layer entry, <=8MiB, held only until this table prediction ends.
        size=4*(3*k.numel()+2*m.embed_dim*m.embed_dim+2*m.embed_dim)
        return size<=8*1024*1024
    def forward(self,q,k,v,**kw):
        try:eligible=not self.disabled and self.eligible(q,k,v,kw)
        except (RuntimeError,ValueError,MemoryError):eligible=False;self.disabled=True
        if not eligible:
            self.fallbacks+=1;self.clear();return self.original(q,k,v,**kw)
        try:result=self._cached(q,k,v,kw)
        except CacheDeclined:
            self.budget_declines+=1
        except (RuntimeError,ValueError,MemoryError):
            self.failures+=1
        else:
            if self.shadow:
                expected,_=self.original(q,k,v,**kw)
                if not bits_equal(result[0],expected):raise AssertionError('Cross-attention output is not bit exact')
                self.compared+=1
            return result
        self.disabled=True;self.fallbacks+=1;self.clear()
        # Original exceptions propagate: never retry the original operator itself.
        return self.original(q,k,v,**kw)
    def _cached(self,q,k,v,kw):
        m=self.original;E=m.embed_dim;T,B,_=q.shape;S=k.shape[0];H=m.num_heads;D=E//H
        wq,wkv=m.in_proj_weight.split([E,2*E]);bq=bkv=None
        if m.in_proj_bias is not None:bq,bkv=m.in_proj_bias.split([E,2*E])
        qp=F.linear(q,wq,bq)
        old=self.entry
        # Strong references avoid identity reuse. Full snapshots also detect .data
        # and external alias writes, which tensor._version alone cannot detect.
        hit=(old is not None and old[0]is k and old[1]is m.in_proj_weight and old[2]is m.in_proj_bias and bits_equal(k,old[3]) and bits_equal(wkv,old[4]) and ((bkv is None and old[5]is None)or(bkv is not None and old[5]is not None and bits_equal(bkv,old[5]))))
        if hit:kp,vp=old[6:8];self.hits+=1
        else:
            self.clear();old=None
            size=4*(3*k.numel()+2*E*E+(0 if bkv is None else 2*E))
            if not self.budget.reserve(size):raise CacheDeclined()
            self.reserved=size
            kv=F.linear(k,wkv,bkv).unflatten(-1,(2,E)).unsqueeze(0).transpose(0,-2).squeeze(-2).contiguous()
            kp,vp=kv[0],kv[1]
            entry=(k,m.in_proj_weight,m.in_proj_bias,k.clone(memory_format=torch.contiguous_format),wkv.clone(memory_format=torch.contiguous_format),None if bkv is None else bkv.clone(memory_format=torch.contiguous_format),kp,vp)
            self.entry=entry;self.misses+=1
            self.maxbytes=max(self.maxbytes,sum(t.numel()*t.element_size()for t in entry[3:]if t is not None))
        qp=qp.view(T,B*H,D).transpose(0,1).view(B,H,T,D)
        kp=kp.view(S,B*H,D).transpose(0,1).view(B,H,S,D)
        vp=vp.view(S,B*H,D).transpose(0,1).view(B,H,S,D)
        out=F.scaled_dot_product_attention(qp,kp,vp,None,0.0,False)
        out=out.permute(2,0,1,3).contiguous().view(B*T,E)
        out=F.linear(out,m.out_proj.weight,m.out_proj.bias).view(T,B,E)
        return out,None
