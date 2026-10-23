async function api(url,options) {
  const response=await fetch(url,options),result=await response.json();
  if(!response.ok)throw Error(result.error||'No se pudo convertir el archivo.');
  return result;
}
const post=(url,value)=>api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
export async function inspectSource(file) {
  return api('/api/convert/source',{method:'POST',headers:{'X-Filename':encodeURIComponent(file.name)},body:file});
}
export async function convertSource(source,options,progress) {
  const {job}=await post('/api/convert/start',{token:source.token,options});
  for(;;) {
    const status=await api('/api/convert/job?id='+encodeURIComponent(job));
    if(status.state==='error')throw Error(status.error);
    progress(status);
    if(status.state==='complete')return status.result;
    await new Promise(resolve=>setTimeout(resolve,350));
  }
}
export function discardSource(source) {return post('/api/convert/discard',{token:source.token});}
