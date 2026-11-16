from smartppt.config import ConversionError
from smartppt.native_words import try_native_words

def test_optional_second_pass_failure_keeps_first_completed_package_and_report(tmp_path,settings,monkeypatch):
 import smartppt.native_words as module
 target=tmp_path/'result.pptx';target.write_bytes(b'original');calls=[]
 def repair(source,path,report,config,trim_spacing=False):
  calls.append(trim_spacing)
  if not trim_spacing:
   path.write_bytes(b'first verified package')
   report['pages'][0].update(route='native-coordinate',text_granularity='word')
  else:
   report['pages'][0]['route']='unwritten second attempt'
   raise ConversionError('layout_render_failed')
 monkeypatch.setattr(module,'repair_native_words',repair)
 report={'pages':[{'page':1,'route':'stirling-retained'}]}
 try_native_words(None,target,report,settings)
 assert calls==[False,True]
 assert target.read_bytes()==b'first verified package'
 assert report['pages']==[{'page':1,'route':'native-coordinate','text_granularity':'word'}]
 assert report['word_spacing_retry_error']=='layout_render_failed'
