'use strict';
const $ = id => document.getElementById(id);
let capabilities, selected, job, uploading, timer, busy = false, generation = 0;
const messages = {provider_not_configured:'Editable conversion is not configured. Please try later.',invalid_pdf:'This file could not be read as a PDF. Please choose another file.',encrypted_pdf:'This PDF is password-protected. Upload an unlocked copy.',page_limit:'This PDF has too many pages.',file_size_limit:'This PDF is too large.',queue_full:'The service is busy. Please try again shortly.',provider_auth:'The conversion service needs attention. Please try later.',provider_timeout:'Conversion timed out. The conversion service may still be finishing; please check before retrying.',job_timeout:'Conversion timed out. Please try a smaller PDF.',worker_interrupted:'Conversion was interrupted. Please retry.',provider_rate_limit:'The conversion service is busy. Please try later.',xfa_unsupported:'This interactive PDF form is not supported.',job_expired:'Your files have expired. Please upload again.'};
const mode = () => document.querySelector('input[name="mode"]:checked').value;
function refresh() {
  const editable = mode() === 'editable';
  $('language-row').hidden = !editable || !capabilities?.ocr_available || !capabilities?.ocr_language_selection;
  $('availability').textContent = editable && capabilities && !capabilities.editable_available ? messages.provider_not_configured : '';
  $('convert').disabled = busy || !selected || !capabilities || (editable && !capabilities.editable_available);
  $('privacy').textContent = capabilities ? `${editable && capabilities.cloud_provider ? 'Your file will be sent to Adobe PDF Services for conversion. ' : 'Your file will be processed by our self-hosted service. '}${editable && !capabilities.ocr_available ? 'Scanned text remains an image; OCR is unavailable. ' : ''}Files on this server expire after ${Math.round(capabilities.retention_seconds/60)} minutes. You can delete them earlier.` : '';
  document.querySelectorAll('input[name="mode"],#language,#file').forEach(x=>x.disabled=busy);
}
function choose(file) {
  if (busy || !file) return;
  if (!/\.pdf$/i.test(file.name)) { $('status').textContent='Please choose a PDF file.'; return; }
  if (capabilities && file.size > capabilities.max_bytes) { $('status').textContent=messages.file_size_limit; return; }
  selected=file; $('filename').textContent=`${file.name} · ${(file.size/1048576).toFixed(2)} MB`;
  $('status').textContent=''; refresh();
}
async function api(path, options={}) {
  const response=await fetch(path,{...options,headers:{...(job?{Authorization:`Bearer ${job.token}`} : {}),...options.headers}});
  if (!response.ok) { const body=await response.json().catch(()=>({})); throw new Error(messages[body.detail]||'The request could not be completed. Please try again.'); }
  return response;
}
async function poll(epoch) {
  if (epoch!==generation || !job) return;
  try {
    const data=await (await api(`/api/jobs/${job.id}`)).json();
    if (epoch!==generation) return;
    $('progress').removeAttribute('value');
    const states={queued:'Waiting to convert…',processing:'Converting your PDF…',validating:'Checking the PowerPoint file…'};
    if (states[data.state]) { $('status').textContent=states[data.state]; timer=setTimeout(()=>poll(epoch),1500); return; }
    busy=false; $('cancel').hidden=true; $('progress-area').hidden=true;
    if (['ready','needs_review'].includes(data.state)) {
      $('result').hidden=false;
      $('page-review').replaceChildren();
      $('status').textContent=data.mode==='preserve' ? 'Ready. Each slide contains a page image; its text and objects are not editable.' : 'Converted — review required. Check the layout, numbers and scanned text before using this file.';
      if (data.report?.assistance) {
        $('status').textContent += ' Graphics remain images.';
        for (const page of data.report.assistance.pages) {
          let detail = '';
          if (page.route === 'source-image-fallback') detail = 'Kept as a page image because text or numbers could not be recovered reliably. This page is not editable.';
          else if (page.route === 'native-regions') detail = `${page.editable_runs} text runs are editable. Other text and graphics remain images. Review fonts, numbers and reading order.`;
          else if (page.route === 'paddle-ocr') detail = `${page.editable_lines} of ${page.detected_lines} detected text lines are editable. Check scanned text against the source.`;
          else if (page.route === 'stirling-table') detail = 'Check table rows, columns and merged cells.';
          else if (page.text_granularity === 'word') detail = 'Text is editable in separate text boxes. Tables are not editable as cells; charts and graphics remain images.';
          if (detail) { const item = document.createElement('li'); item.textContent = `Page ${page.page}: ${detail}`; $('page-review').append(item); }
        }
        if (data.report.assistance.pages.some(p => p.route === 'paddle-ocr' && p.editable_lines < p.detected_lines)) {
          $('status').textContent += ' Some scanned text remains an image because recognition or placement could not be verified.';
        }
      }
    } else { $('status').textContent=messages[data.error] || (data.state==='cancelled'?'Conversion cancelled.':'Conversion failed. Please try another PDF.'); }
    refresh();
  } catch(error) { if(epoch===generation){busy=false;$('status').textContent=error.message;$('cancel').hidden=false;refresh();} }
}
$('file').addEventListener('change',e=>choose(e.target.files[0]));
document.querySelectorAll('[name="mode"]').forEach(x=>x.addEventListener('change',refresh));
for(const event of ['dragenter','dragover']) $('drop').addEventListener(event,e=>{e.preventDefault();$('drop').classList.add('drag');});
for(const event of ['dragleave','drop']) $('drop').addEventListener(event,e=>{e.preventDefault();$('drop').classList.remove('drag');});
$('drop').addEventListener('drop',e=>{if(e.dataTransfer.files.length!==1){$('status').textContent='Please choose one PDF at a time.';return;}choose(e.dataTransfer.files[0]);});
$('convert').addEventListener('click',async()=>{
  if (!selected || busy) return;
  // Retain a known job until deletion succeeds, so its files remain user-deletable.
  if(job){try{await api(`/api/jobs/${job.id}`,{method:'DELETE'});}catch(e){$('status').textContent=e.message;return;}}
  const epoch=++generation; job=null; busy=true; refresh(); $('result').hidden=true;$('cancel').hidden=false;$('progress-area').hidden=false;
  $('status').textContent='Uploading your PDF…';$('progress').value=0;
  uploading=new XMLHttpRequest();
  uploading.open('POST',`/api/jobs?mode=${mode()}&language=${encodeURIComponent($('language').value)}`);
  uploading.setRequestHeader('Content-Type','application/pdf');uploading.timeout=95000;
  uploading.upload.onprogress=e=>{if(e.lengthComputable)$('progress').value=e.loaded/e.total*100;};
  uploading.onload=()=>{
    if(epoch!==generation)return;
    let data;try{data=JSON.parse(uploading.responseText||'{}');}catch{data={};}uploading=null;
    if(data.id&&data.token){job=data;poll(epoch);}else{busy=false;refresh();$('cancel').hidden=true;$('progress-area').hidden=true;$('status').textContent=messages[data.detail]||'Upload failed. Please try again.';}
  };
  uploading.onerror=uploading.ontimeout=()=>{if(epoch!==generation)return;busy=false;refresh();$('status').textContent='Upload interrupted. Please try again.';$('cancel').hidden=true;};
  uploading.send(selected);
});
async function cancel(){
  ++generation;clearTimeout(timer);if(uploading){uploading.abort();uploading=null;}
  try{if(job)await api(`/api/jobs/${job.id}`,{method:'DELETE'});job=null;$('status').textContent='Cancelled. Files on this server are scheduled for deletion.';$('result').hidden=true;$('cancel').hidden=true;$('progress-area').hidden=true;}
  catch(e){$('status').textContent=e.message;}
  busy=false;refresh();
}
$('cancel').addEventListener('click',cancel);$('delete').addEventListener('click',cancel);
$('download').addEventListener('click',async()=>{try{const response=await api(`/api/jobs/${job.id}/download`);const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=(selected?.name.replace(/\.pdf$/i,'')||'converted')+'.pptx';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(e){$('status').textContent=e.message;}});
fetch('/api/capabilities').then(r=>{if(!r.ok)throw Error();return r.json();}).then(c=>{capabilities=c;refresh();}).catch(()=>{$('availability').textContent='Cannot connect to the conversion service.';});
