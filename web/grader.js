'use strict';
// Disposable worker; the host denies external resource requests. No native bridge here.
onmessage = event => {
 const {source,fn,tests}=event.data;
 if(typeof source!=='string'||source.length>30000||!['summarize','makeReceipt'].includes(fn)||!Array.isArray(tests)||tests.length>10){postMessage({passed:false,message:'Invalid test request'});return;}
 try {
  const solution=new Function('"use strict";\n'+source+'\nreturn '+fn+';')();
  const equal=(a,b)=>{if(a===b)return true;if(!a||!b||typeof a!=='object'||typeof b!=='object')return false;const ka=Object.keys(a).sort(),kb=Object.keys(b).sort();return JSON.stringify(ka)===JSON.stringify(kb)&&ka.every(k=>equal(a[k],b[k]));};
  const outcomes=tests.map((t,i)=>{try{return equal(solution(...structuredClone(t.input)),t.out)?`Test ${i+1}: passed`:`Test ${i+1}: failed`;}catch{return`Test ${i+1}: error`;}});
  postMessage({passed:outcomes.every(x=>x.endsWith('passed')),message:outcomes.join('\n')});
 }catch(e){postMessage({passed:false,message:String(e.message).slice(0,1000)});}
};
