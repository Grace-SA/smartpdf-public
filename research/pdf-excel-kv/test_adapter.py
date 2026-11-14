import threading,unittest
from types import SimpleNamespace
from unittest.mock import patch
import torch
from torch import nn
from adapter import build_converter,compatible,guard_predictor,PredictorBusy
from budget import CacheBudget,MAX_CACHE_BYTES
from cached_attention import CachedAttention,bits_equal
class Predictor:
    def __init__(self):
        self.layers=[SimpleNamespace(multihead_attn=nn.MultiheadAttention(32,4).eval())for _ in range(6)]
        self._model=SimpleNamespace(_tag_transformer=SimpleNamespace(_decoder=SimpleNamespace(layers=self.layers)))
        self.q=torch.randn(1,1,32);self.k=torch.randn(13,1,32);self.enter=None;self.leave=None;self.error=None
    @torch.no_grad()
    def predict(self):
        if self.enter:self.enter.set();self.leave.wait(3)
        out=[]
        for layer in self.layers:
            out.append(layer.multihead_attn(self.q,self.k,self.k,need_weights=False)[0])
            if self.error:raise self.error
        return out
class Tests(unittest.TestCase):
    def test_default_disabled_and_mismatch(self):
        sentinel=object()
        with patch('adapter._baseline',return_value=sentinel),patch('adapter.compatible',side_effect=AssertionError('must not probe')):
            r=build_converter('unused');self.assertIs(r.converter,sentinel);self.assertFalse(r.active)
        with patch('adapter._baseline',return_value=sentinel),patch('adapter.compatible',return_value=False):
            r=build_converter('unused',enabled=True);self.assertIs(r.converter,sentinel);self.assertEqual(r.reason,'dependency mismatch')
        with patch('adapter.importlib.metadata.distribution',return_value=SimpleNamespace(version='different')):self.assertFalse(compatible())
    def test_real_runtime_lock(self):self.assertTrue(compatible())
    def test_budget_and_fallback(self):
        torch.set_num_threads(2);b=CacheBudget(20000);q=torch.randn(1,1,32);k=torch.randn(13,1,32);m=nn.MultiheadAttention(32,4).eval();c=CachedAttention(m,budget=b)
        with torch.no_grad():
            c(q,k,k,need_weights=False);self.assertGreater(b.used,0)
            with patch.object(c,'_cached',side_effect=RuntimeError('cache failure')):
                got=c(q,k,k,need_weights=False);want=m(q,k,k,need_weights=False)[0]
            self.assertTrue(bits_equal(got[0],want));self.assertEqual(c.failures,1);self.assertEqual(b.used,0)
        for limit in [-1,True,MAX_CACHE_BYTES+1]:
            with self.assertRaises(ValueError):CacheBudget(limit)
        b=CacheBudget(0);c=CachedAttention(m,budget=b)
        with torch.no_grad():self.assertTrue(bits_equal(c(q,k,k,need_weights=False)[0],m(q,k,k,need_weights=False)[0]))
        self.assertEqual(c.budget_declines,1);self.assertEqual(b.used,0)
    def test_guard_releases_and_propagates(self):
        p=Predictor();originals=[l.multihead_attn for l in p.layers];expected=p.predict();state=guard_predictor(p,20000);actual=p.predict()
        self.assertTrue(all(bits_equal(a,b)for a,b in zip(actual,expected)));self.assertEqual(state['live_cache_bytes'],0);self.assertLessEqual(state['peak_cache_bytes'],20000)
        self.assertGreater(state['budget_declines'],0)
        for error in [RuntimeError('model failed'),KeyboardInterrupt()]:
            p.error=error
            with self.assertRaises(type(error)):p.predict()
            self.assertEqual(state['live_cache_bytes'],0);self.assertTrue(all(l.multihead_attn is o for l,o in zip(p.layers,originals)))
    def test_setup_fallback(self):
        p=Predictor();originals=[l.multihead_attn for l in p.layers];count=[0]
        def factory(*a,**kw):
            count[0]+=1
            if count[0]==3:raise MemoryError('setup')
            return CachedAttention(*a,**kw)
        with patch('cached_attention.CachedAttention',side_effect=factory):
            state=guard_predictor(p,20000);p.predict()
        self.assertEqual(state['setup_fallbacks'],1);self.assertEqual(state['live_cache_bytes'],0)
        self.assertTrue(all(l.multihead_attn is o for l,o in zip(p.layers,originals)))
        with self.assertRaises(ValueError):guard_predictor(p,20000)
    def test_concurrent_entry_rejected(self):
        p=Predictor();state=guard_predictor(p,20000);p.enter=threading.Event();p.leave=threading.Event();errors=[]
        def run():
            try:p.predict()
            except BaseException as e:errors.append(e)
        t=threading.Thread(target=run);t.start()
        try:
            self.assertTrue(p.enter.wait(2))
            with self.assertRaises(PredictorBusy):p.predict()
        finally:p.leave.set();t.join(3)
        self.assertFalse(t.is_alive());self.assertFalse(errors);self.assertEqual(state['busy_rejections'],1);self.assertEqual(state['live_cache_bytes'],0)
    def test_shadow_original_not_retried(self):
        m=nn.MultiheadAttention(32,4).eval();c=CachedAttention(m,shadow=True);q=torch.randn(1,1,32);k=torch.randn(13,1,32)
        with torch.no_grad(),patch.object(m,'_call_impl',side_effect=RuntimeError('original'))as original:
            with self.assertRaisesRegex(RuntimeError,'original'):c(q,k,k,need_weights=False)
        self.assertEqual(original.call_count,1);self.assertEqual(c.failures,0);c.clear()
    def test_budget_init_failure_releases_lock(self):
        for error in [MemoryError('allocation'),KeyboardInterrupt()]:
            p=Predictor();count=[0]
            def factory(limit):
                count[0]+=1
                if count[0]==2:raise error
                return CacheBudget(limit)
            with patch('budget.CacheBudget',side_effect=factory):
                state=guard_predictor(p,20000)
                with self.assertRaises(type(error)):p.predict()
                p.predict()
            self.assertEqual(state['busy_rejections'],0);self.assertEqual(state['live_cache_bytes'],0)
    def test_distinct_predictors_do_not_share_state(self):
        predictors=[Predictor(),Predictor()];expected=[p.predict()for p in predictors]
        states=[guard_predictor(p,20000)for p in predictors];release=threading.Event();results=[None,None];errors=[]
        for p in predictors:p.enter=threading.Event();p.leave=release
        def run(i):
            try:results[i]=predictors[i].predict()
            except BaseException as error:errors.append(error)
        workers=[threading.Thread(target=run,args=(i,))for i in range(2)]
        for worker in workers:worker.start()
        try:self.assertTrue(all(p.enter.wait(2)for p in predictors))
        finally:
            release.set()
            for worker in workers:worker.join(3)
        self.assertFalse(errors);self.assertTrue(all(not t.is_alive()for t in workers))
        for actual,want,state in zip(results,expected,states):
            self.assertTrue(all(bits_equal(a,b)for a,b in zip(actual,want)))
            self.assertEqual(state['calls'],1);self.assertEqual(state['busy_rejections'],0);self.assertEqual(state['live_cache_bytes'],0)
if __name__=='__main__':unittest.main()
