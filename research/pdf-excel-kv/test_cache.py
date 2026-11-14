import unittest,torch
from torch import nn
from cached_attention import CachedAttention
class Tests(unittest.TestCase):
 def test_shapes_bias(self):
  torch.set_num_threads(2);torch.manual_seed(31)
  with torch.no_grad():
   for E,H in [(16,1),(32,4),(64,8),(512,8)]:
    for B,S,T in [(1,1,1),(1,37,1),(2,19,1)]:
     for bias in [False,True]:
      m=nn.MultiheadAttention(E,H,bias=bias).eval();c=CachedAttention(m,True);k=torch.randn(S,B,E)
      for _ in range(3):c(torch.randn(T,B,E),k,k,need_weights=False)
      self.assertEqual((c.misses,c.hits,c.compared),(1,2,3));c.clear();self.assertIsNone(c.entry)
 def test_mutations(self):
  with torch.no_grad():
   m=nn.MultiheadAttention(32,4).eval();c=CachedAttention(m,True);q=torch.randn(1,1,32);k=torch.randn(13,1,32)
   c(q,k,k,need_weights=False);c(q,k,k,need_weights=False)
   k.data.add_(1);c(q,k,k,need_weights=False)
   k.numpy()[0,0,0]+=1;c(q,k,k,need_weights=False)
   m.in_proj_weight.data[32:]+=0.1;c(q,k,k,need_weights=False)
   m.in_proj_bias.data[32:]+=0.1;c(q,k,k,need_weights=False)
   self.assertEqual(c.misses,5);self.assertEqual(c.hits,1)
 def test_fallbacks(self):
  m=nn.MultiheadAttention(32,4).eval();c=CachedAttention(m,True);q=torch.randn(1,1,32);k=torch.randn(13,1,32)
  c(q,k,k,need_weights=False) # grad enabled
  with torch.no_grad():
   c(q,k,k);c(q,k,k,need_weights=False,attn_mask=torch.zeros(1,13));c(k,k,k,need_weights=False)
   handle=m.register_forward_hook(lambda *a:None);c(q,k,k,need_weights=False);handle.remove()
   with torch.autocast('cpu'):c(q,k,k,need_weights=False)
  self.assertEqual(c.fallbacks,6);self.assertIsNone(c.entry)
 def test_identity_signed_zero_and_strides(self):
  from cached_attention import bits_equal
  with torch.no_grad():
   m=nn.MultiheadAttention(32,4).eval();c=CachedAttention(m,True);q=torch.randn(1,1,64)[...,::2];k=torch.randn(13,1,64)[...,::2]
   c(q,k,k,need_weights=False);c(q,k,k,need_weights=False);self.assertEqual(c.hits,1)
   k=k.clone();c(q,k,k,need_weights=False);self.assertEqual(c.misses,2)
   k.zero_();c(q,k,k,need_weights=False);k.data[0,0,0]=-0.0;c(q,k,k,need_weights=False);self.assertEqual(c.misses,4)
   self.assertFalse(bits_equal(torch.tensor([0.]),torch.tensor([-0.])))
 def test_training_override_budget(self):
  from unittest.mock import patch
  m=nn.MultiheadAttention(32,4);c=CachedAttention(m);self.assertTrue(m.training);self.assertTrue(c.training)
  q=torch.randn(1,1,32);k=torch.randn(13,1,32)
  with torch.no_grad():c(q,k,k,need_weights=False)
  self.assertEqual(c.fallbacks,1)
  m.eval();c.eval()
  with patch.object(m,'forward',wraps=m.forward),torch.no_grad():c(q,k,k,need_weights=False)
  self.assertEqual(c.fallbacks,2)
  m=nn.MultiheadAttention(64,4).eval();c=CachedAttention(m);q=torch.randn(1,4,64);k=torch.randn(4096,4,64)
  with torch.no_grad():self.assertFalse(c.eligible(q,k,k,{'need_weights':False}))
 def test_install_restoration(self):
  from types import SimpleNamespace
  from unittest.mock import patch
  from instrumentation import install
  from cached_attention import CachedAttention
  layers=[SimpleNamespace(multihead_attn=nn.MultiheadAttention(32,4).eval())for _ in range(2)];originals=[l.multihead_attn for l in layers]
  f=lambda:None;fc=nn.Linear(32,3);model=SimpleNamespace(predict=f,_tag_transformer=SimpleNamespace(_decoder=SimpleNamespace(layers=layers),_fc=fc))
  for failure in ['second','hook','body']:
   count=[0]
   def factory(*a,**kw):
    count[0]+=1
    if failure=='second'and count[0]==2:raise RuntimeError('setup')
    return CachedAttention(*a,**kw)
   with patch('instrumentation.CachedAttention',side_effect=factory):
    hookpatch=patch.object(fc,'register_forward_hook',side_effect=RuntimeError('hook')) if failure=='hook'else patch.object(fc,'register_forward_hook',wraps=fc.register_forward_hook)
    with hookpatch:
     with self.assertRaises(RuntimeError):
      with install(model,'cached',lambda x:None,lambda x:None):raise RuntimeError('body')
   self.assertIs(model.predict,f);self.assertFalse(fc._forward_hooks)
   self.assertTrue(all(l.multihead_attn is o for l,o in zip(layers,originals)))
 def test_class_method_state_restoration(self):
  from types import SimpleNamespace
  from instrumentation import install
  class Model:
   def predict(self):return 1
  model=Model();model._tag_transformer=SimpleNamespace(_decoder=SimpleNamespace(layers=[]),_fc=nn.Linear(2,2));before=set(model.__dict__)
  with install(model,'reference',lambda x:None,lambda x:None):self.assertEqual(model.predict(),1)
  self.assertEqual(set(model.__dict__),before)
  with self.assertRaises(RuntimeError):
   with install(model,'cached',lambda x:None,lambda x:None):raise RuntimeError('body')
  self.assertEqual(set(model.__dict__),before)
if __name__=='__main__':unittest.main()
