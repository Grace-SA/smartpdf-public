// Only the explicitly synthetic ruled.pdf is sent to public competitor tools.
import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
const out=process.argv[2];const fixture=process.argv[3];await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});const results=[];
for(const [name,url] of [['ilovepdf','https://www.ilovepdf.com/pdf_to_excel'],['smallpdf','https://smallpdf.com/pdf-to-excel'],['adobe','https://www.adobe.com/acrobat/online/pdf-to-excel.html']]){
 const page=await browser.newPage({viewport:{width:1280,height:900}});const row={name,url};
 try{
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
  await page.locator('input[type=file]').first().waitFor({state:'attached',timeout:12000}).catch(()=>{});
  await page.screenshot({path:out+'/'+name+'-entry.png'});
  row.entry=(await page.locator('body').innerText()).slice(0,18000);
  const input=page.locator('input[type=file]').first();
  if(await input.count()){
   await input.setInputFiles(fixture);await page.waitForTimeout(3500);
   row.selected=(await page.locator('body').innerText()).slice(0,18000);
   await page.screenshot({path:out+'/'+name+'-selected.png'});
   const button=page.getByRole('button',{name:/^convert$|^convert (to )?excel$/i}).first();
   await button.waitFor({state:'visible',timeout:12000}).catch(()=>{});
   if(await button.count()&&await button.isVisible()){
    await button.click();await page.waitForTimeout(5000);row.converted=(await page.locator('body').innerText()).slice(0,18000);await page.screenshot({path:out+'/'+name+'-converted.png'});
   }
   await page.getByText(/Download Excel|Download file|Download XLSX/i).first().waitFor({timeout:25000}).catch(()=>{});
   row.final=(await page.locator('body').innerText()).slice(0,18000);
   const downloadControl=page.getByRole('link',{name:/^download( excel| file| xlsx)?$/i}).or(page.getByRole('button',{name:/^download( excel| file| xlsx)?$/i})).first();
   if(await downloadControl.count() && await downloadControl.isVisible()){
    try {const pending=page.waitForEvent('download',{timeout:15000});await downloadControl.click();const downloaded=await pending;await downloaded.saveAs(out+'/'+name+'-result.xlsx');row.downloaded=true;}catch(e){row.downloadBlocker=e.message;}
   }
   await page.screenshot({path:out+'/'+name+'-final.png'});
  }else row.blocker='No accessible file input after 12 seconds in this browser session';
 }catch(e){row.blocker=e.message;}
 results.push(row);await page.close();
}
await browser.close();await writeFile(out+'/results.json',JSON.stringify(results,null,2));
console.log(results.map(r=>({name:r.name,uploaded:!!r.selected,converted:!!r.converted,blocker:r.blocker})));
