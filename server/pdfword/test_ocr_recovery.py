"""Bounded text retries preserve pixels and reject any incomplete partition."""
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from ocr_recovery import text_bands, recognize_block, recovery_options


class RecoveryTests(unittest.TestCase):
    def image(self):
        image=Image.new('RGB',(200,160),'#fff0df');draw=ImageDraw.Draw(image)
        for top in [10,60,110]:
            draw.rectangle((10,top,150,top+3), fill='black')
            draw.rectangle((10,top+7,180,top+25), fill='black')
        return image

    def test_partition_retains_every_pixel_and_attached_small_annotations(self):
        source=self.image();bands=text_bands(source)
        self.assertEqual(len(bands),3)
        restored=Image.new('RGB',source.size);y=0
        for band in bands:restored.paste(band,(0,y));y+=band.height
        self.assertEqual(y,source.height)
        self.assertEqual(restored.tobytes(),source.tobytes())

    def test_underlined_dense_lines_keep_rules_with_preceding_text(self):
        image=Image.new('RGB',(300,196),'white');draw=ImageDraw.Draw(image)
        for top,bottom in [(8,23),(25,61),(64,68),(73,88),(91,123),(129,133),(139,153),(156,188)]:
            draw.rectangle((10,top,280,bottom),fill='black')
        bands=text_bands(image)
        self.assertEqual([b.height for b in bands],[71,65,60])
        restored=Image.new('RGB',image.size);offset=0
        for band in bands:restored.paste(band,(0,offset));offset+=band.height
        self.assertEqual(restored.tobytes(),image.tobytes())

    def test_blank_or_unseparated_content_is_not_split(self):
        self.assertEqual(text_bands(Image.new('RGB',(200,160),'white')),[])
        self.assertEqual(text_bands(Image.new('RGB',(200,160),'black')),[])
        self.assertEqual(text_bands(Image.new('RGB',(20,160),'white')),[])

    def test_first_attempt_reserves_budget_and_retry_requires_every_band(self):
        calls=[]
        def infer(image,prompt,cap,options):
            calls.append((image.size,cap,options));return str(len(calls)),len(calls)==2
        prompt='Recognize the content of the image.'
        recognize_block(infer,self.image(),prompt,8192)
        self.assertEqual(calls[0][1],2048)
        calls.clear()
        text,truncated=recognize_block(infer,self.image(),prompt,8192,{'repetition_penalty':1.1})
        self.assertEqual(text,'1\n2\n3');self.assertTrue(truncated)
        self.assertEqual(len(calls),3)
        self.assertTrue(all(c[1]==2048 and c[2]=={'repetition_penalty':1.1} for c in calls))

    def test_formula_and_table_prompts_keep_original_geometry_and_budget(self):
        for prompt in ['Formula recognition','Table recognition']:
            calls=[]
            def infer(image,prompt,cap,options):calls.append((image.size,cap));return 'complete',False
            self.assertEqual(recognize_block(infer,self.image(),prompt,8192,{'repetition_penalty':1.1}),('complete',False))
            self.assertEqual(calls,[((200,160),8192)])

    def test_invalid_penalty_and_sampling_override(self):
        self.assertEqual(recovery_options({'temperature':1,'max_tokens':99999}),{})
        for value in [True,'1.1',float('nan'),float('inf'),.9,100]:
            with self.subTest(value=value),self.assertRaises(ValueError):recovery_options({'repetition_penalty':value})


class RepetitionTests(unittest.TestCase):
    def test_original_eos_is_success_and_does_not_mark_a_cycle(self):
        from ocr_recovery import RepetitionStop
        guard=RepetitionStop(lambda token:token==0,lambda tokens:'word')
        self.assertTrue(guard(0));self.assertFalse(guard.repeated)

    def test_only_sustained_letter_cycles_request_retry(self):
        from ocr_recovery import RepetitionStop
        for pattern in [(1,), (1,2,3), tuple(range(1,17))]:
            guard=RepetitionStop(lambda token:False,lambda tokens:'repeated words')
            hits=[i+1 for i in range(256) if guard(pattern[i%len(pattern)])]
            self.assertTrue(hits);self.assertGreaterEqual(hits[0],128)
            self.assertTrue(guard.repeated)
        for decode,tokens in [(lambda ids:'0000',[1]*512),(lambda ids:'-- --',[1]*512),(lambda ids:'normal words',list(range(512)))]:
            guard=RepetitionStop(lambda token:False,decode)
            self.assertFalse(any(guard(t) for t in tokens))

    def test_generation_restores_eos_and_flags_early_stop_as_incomplete(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from ocr_recovery import bounded_generate
        original=Mock(side_effect=lambda token:token==0)
        tokenizer=SimpleNamespace(stopping_criteria=original,decode=lambda ids:'they')
        processor=SimpleNamespace(tokenizer=tokenizer);model=SimpleNamespace(config=SimpleNamespace(eos_token_id=0))
        def generate(*args,**kwargs):
            tokenizer.stopping_criteria=kwargs['stopping_criteria']
            for i in range(128):tokenizer.stopping_criteria(1)
            return SimpleNamespace(text='discard this attempt',generation_tokens=128)
        out,incomplete=bounded_generate(generate,model,processor,'prompt',None,8192,guard_repetition=True)
        self.assertTrue(incomplete);self.assertIs(tokenizer.stopping_criteria,original)
        original.reset.assert_called_once_with(0)
        def failed(*args,**kwargs):
            tokenizer.stopping_criteria=kwargs['stopping_criteria'];raise RuntimeError('failed inference')
        with self.assertRaises(RuntimeError):bounded_generate(failed,model,processor,'prompt',None,8192,guard_repetition=True)
        self.assertIs(tokenizer.stopping_criteria,original)

    def test_non_text_inference_does_not_override_stopping_or_cap(self):
        from types import SimpleNamespace
        from ocr_recovery import bounded_generate
        calls=[]
        def generate(*args,**kwargs):calls.append(kwargs);return SimpleNamespace(generation_tokens=8192)
        _,incomplete=bounded_generate(generate,None,None,'table',None,8192)
        self.assertTrue(incomplete);self.assertNotIn('stopping_criteria',calls[0]);self.assertEqual(calls[0]['max_tokens'],8192)
