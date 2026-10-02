'use strict';
(() => {
 const $=id=>document.getElementById(id), native=window.chrome?.webview;
 let grading=false, finishing=false, revision=0, sessionId='', signedIn=false, adminEdition=false;
 let adminBusy=false,intakeBusy=false,intakeRunning=false,intakePending=null;
 let running=false, mode='human', current=0, seq=0, started=0, batch=[], answers=questions.map(q=>q.starter||''), grades={}, count=0;
 const post=(command,extra={})=>native?.postMessage({command,...extra});
 const toast=message=>{$('toast').textContent=message;};
 function updateIntakeControls(){
  const blocked=!adminEdition||adminBusy||running||intakeBusy;
  for(const id of ['intake-refresh','intake-catchup'])$(id).disabled=blocked;
  $('intake-start').disabled=blocked||intakeRunning;
  $('intake-stop').disabled=!adminEdition||!intakeRunning;
  for(const button of $('intake-queue').querySelectorAll('button'))button.disabled=blocked;
 }
 function requestIntake(command,extra={}){
  if(!adminEdition||((running||adminBusy||intakeBusy)&&command!=='stop'))return;
  intakePending=command;intakeBusy=true;updateIntakeControls();$('intake-status').textContent=command==='stop'?'Stopping collection…':'Working…';
  post('intake-'+command,extra);
 }
 function intakeResult(data,stream=false){
  const expected=intakePending==='start'?'run':intakePending;
  const acknowledged=!!expected&&data?.command===expected&&(!stream||intakePending==='start');
  if(!stream&&!acknowledged)return;
  if(acknowledged){intakePending=null;intakeBusy=false;}
  if(!data||data.schemaVersion!==1||typeof data.command!=='string'){ $('intake-status').textContent='Could not read collection status.';updateIntakeControls();return; }
  if(data.ok!==true){
   const messages={setup_required:'Organizer setup is not initialized. Choose Check invitations, Collect now, or Start collection to verify the organizer account and initialize it.',organizer_account_mismatch:'GitHub is signed in to a different account. Sign the GitHub CLI in to the organizer account Dhruvsa1, then try again.',organizer_github_unavailable:'Could not verify the organizer GitHub account. Check the GitHub CLI sign-in and connection, then try again.',invalid_organizer_setup:'The existing organizer setup is invalid or belongs to a different account. It was not changed. Ask the organizer to repair the local setup.',python_unavailable:'The Admin Python runtime is unavailable.',intake_busy:'Another collection action is still running.',recording_active:'Stop the practice session before changing collection settings.',intake_unavailable:'The private collection components are unavailable.',worker_not_owned_by_this_window:'This collection worker was started elsewhere. Stop it from that window or terminal.',worker_already_running:'Automatic collection is already running.',intake_unavailable_or_failed:'Collection could not start. Check the private runtime and organizer GitHub sign-in.',intake_stop_failed:'Collection could not be stopped. Close this Admin window to stop its worker.',intake_migration_required:'Collection state is from an older version and was left unchanged. The organizer must run the private intake_worker.py migrate command once on this computer; this app never migrates it automatically. Then try again.',migration_backup_conflict:'Migration stopped: a different migration backup already exists. The original collection state and that backup were both preserved unchanged. The organizer must repair the conflicting backup before migrating.',recipient_key_setup_invalid:'Collection stopped: the local recipient key on this computer could not be verified. The organizer must repair the key setup on this computer. Participants do not need to resend anything.'};
   // Own keys only, so inherited names such as "constructor" still get the generic message.
   $('intake-status').textContent=(typeof data.error==='string'&&Object.hasOwn(messages,data.error)?messages[data.error]:'')||'Collection could not complete. Check the organizer GitHub sign-in and try again.';updateIntakeControls();return;
  }
  if(typeof data.running==='boolean')intakeRunning=data.running;
  if(Number.isSafeInteger(data.approvedOwnerCount)&&data.approvedOwnerCount>=0)$('intake-approved-count').textContent=String(data.approvedOwnerCount);
  if(data.command==='queue'){
   const list=$('intake-queue');list.replaceChildren();const seen=new Set();
   for(const participant of (Array.isArray(data.participants)?data.participants:[]).slice(0,200)){
    if(!Number.isSafeInteger(participant.ownerId)||participant.ownerId<=0||typeof participant.ownerLogin!=='string'||!/^[-a-zA-Z0-9]{1,39}$/.test(participant.ownerLogin)||seen.has(participant.ownerId))continue;
    if(!['approved','approval_required'].includes(participant.eligibility))continue;seen.add(participant.ownerId);
    const row=document.createElement('div'),identity=document.createElement('span'),button=document.createElement('button');row.className='intake-participant';identity.className='intake-identity';identity.textContent=participant.ownerLogin+' · GitHub ID '+participant.ownerId;
    const approved=participant.eligibility==='approved';button.className='intake-approve';button.type='button';button.textContent=approved?'Revoke approval':'Approve';button.setAttribute('aria-label',button.textContent+' '+participant.ownerLogin);button.onclick=()=>requestIntake(approved?'revoke':'approve',{ownerId:participant.ownerId});row.append(identity,button);list.append(row);
   }
   $('intake-status').textContent=data.truncated?'Showing a limited invitation list. Check again after processing.':'Invitation check complete.';
  }else if(data.command==='status')$('intake-status').textContent=(intakeRunning?'Automatic collection is running.':'Automatic collection is stopped.')+' '+(Number.isSafeInteger(data.approvedOwnerCount)?data.approvedOwnerCount+' approved accounts.':'');
  else if(data.command==='run')$('intake-status').textContent='Automatic collection is running.';
  else if(data.command==='stop')$('intake-status').textContent=data.stopRequested&&data.running?'Stopping collection…':'Collection stopped.';
  else if(data.command==='catchup')$('intake-status').textContent='Collection check finished. '+(Number.isSafeInteger(data.ingested)?data.ingested+' submissions processed.':'');
  else $('intake-status').textContent='Participant approval updated.';
  updateIntakeControls();
  if(acknowledged&&['approve','revoke'].includes(data.command))requestIntake('queue');
  else if(acknowledged&&['queue','catchup'].includes(data.command)&&!intakeRunning)requestIntake('status');
 }
 function page(id){for(const name of ['welcome','overview','workspace','results'])$(name).hidden=name!==id;}
 function event(type,extra={}) { if(!running||!document.hasFocus()||document.hidden)return; batch.push({id:++seq,type,t:Math.round((performance.now()-started)*100)/100,question:questions[current].id,viewport:{width:innerWidth,height:innerHeight,scale:devicePixelRatio},...extra});count++; if(batch.length>=100)flush();return seq; }
 function flush(){if(batch.length){post('events',{events:batch.splice(0,512)});}}
 const region=e=>e.target.closest?.('#problem,#answer-area,#question-nav,#test-output')?.id||'navigation';
 for(const type of ['pointermove','pointerdown','pointerup'])document.addEventListener(type,e=>{const id=event(type,{x:Math.max(0,Math.min(innerWidth,e.clientX)),y:Math.max(0,Math.min(innerHeight,e.clientY)),outsideViewport:e.clientX<0||e.clientY<0||e.clientX>innerWidth||e.clientY>innerHeight,button:e.button,buttons:e.buttons,region:region(e)});if(type==='pointerdown'&&id){flush();post('snapshot',{eventId:id});}},true);
 for(const type of ['keydown','keyup'])document.addEventListener(type,e=>{if(e.target.closest('#welcome,#results'))return;event(type,{key:e.key,code:e.code,repeat:e.repeat,ctrl:e.ctrlKey,alt:e.altKey,shift:e.shiftKey,meta:e.metaKey,region:region(e)});},true);
 document.addEventListener('wheel',e=>event('wheel',{dx:e.deltaX,dy:e.deltaY,deltaMode:e.deltaMode,region:region(e)}),{passive:true,capture:true});
 document.addEventListener('scroll',e=>event('scroll',{top:e.target.scrollTop||0,left:e.target.scrollLeft||0,region:region(e)}),true);
 document.addEventListener('focusin',e=>event('focus',{region:region(e)}),true);
 document.addEventListener('selectionchange',()=>{const e=document.activeElement;if(e?.id==='code-editor')event('selection',{start:e.selectionStart,end:e.selectionEnd,region:'answer-area'});});
 window.addEventListener('blur',()=>{flush();});
 setInterval(flush,100);
 setInterval(()=>{if(running){const s=Math.max(0,1800-Math.floor((performance.now()-started)/1000));$('timer').textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;if(s===0)finish(false);}},1000);
 function tasks(){const list=$('task-list');list.replaceChildren();questions.forEach((q,i)=>{const tr=document.createElement('tr');tr.className='task-row';for(const text of [`${i+1}. ${q.title}`,q.type,grades[i]?.passed?'Passed':answers[i]&&answers[i]!==q.starter?'In progress':'Not started']){const td=document.createElement('td');td.textContent=text;tr.append(td);}const td=document.createElement('td'),b=document.createElement('button');b.className='solve-button';b.textContent='Solve';b.onclick=()=>show(i);td.append(b);tr.append(td);list.append(tr);});}
 function save(){const e=$('code-editor')||$('text-answer')||$('choice-answer');if(e)answers[current]=e.value;else{const checked=document.querySelector('input[name=answer]:checked');if(checked)answers[current]=checked.value;}}
 function show(i){save();current=i;page('workspace');$('question-title').textContent=questions[i].type==='Coding'?'JavaScript · '+questions[i].title:questions[i].title;
  $('question-nav').replaceChildren();questions.forEach((q,n)=>{const b=document.createElement('button');b.className='question-link'+(i===n?' active':'');b.textContent=String(n+1);b.title=q.title;b.onclick=()=>show(n);$('question-nav').append(b);});
  const q=questions[i],problem=$('problem');problem.replaceChildren();const h=document.createElement('h1');h.textContent=q.title;problem.append(h);const p=document.createElement('p');p.className='problem-copy';p.textContent=q.prompt;problem.append(p);
  for(const detail of q.details||[]){const p=document.createElement('p');p.className='problem-copy';p.textContent=detail;problem.append(p);}if(q.example){const pre=document.createElement('pre');pre.className='example';pre.textContent=q.example;problem.append(pre);}
  const area=$('answer-area');area.replaceChildren();$('run-code').textContent=q.type==='Coding'?'Run code':'Check answer';
  if(q.type==='Coding'){const shell=document.createElement('div');shell.className='editor-shell';const lines=document.createElement('pre');lines.className='line-numbers';lines.setAttribute('aria-hidden','true');const editor=document.createElement('textarea');editor.id='code-editor';editor.className='code-editor';editor.spellcheck=false;editor.setAttribute('aria-label','JavaScript code editor');editor.setAttribute('aria-describedby','editor-keys');editor.value=answers[i];
   const update=()=>{lines.textContent=editor.value.split('\n').map((_,i)=>i+1).join('\n');answers[current]=editor.value;};editor.addEventListener('input',e=>{update();event('input',{inputType:e.inputType||'',length:editor.value.length,selectionStart:editor.selectionStart,selectionEnd:editor.selectionEnd,region:'answer-area'});});editor.addEventListener('scroll',()=>lines.scrollTop=editor.scrollTop);editor.addEventListener('keydown',e=>{if(e.key==='Escape'&&!e.isComposing&&!e.shiftKey&&!e.ctrlKey&&!e.altKey&&!e.metaKey){e.preventDefault();$('run-code').focus();return;}if(e.key==='Tab'){e.preventDefault();editor.setRangeText('    ',editor.selectionStart,editor.selectionEnd,'end');editor.dispatchEvent(new InputEvent('input',{inputType:'insertText',bubbles:true}));}if(e.key==='Enter'){e.preventDefault();const before=editor.value.slice(0,editor.selectionStart).split('\n').pop();const indent=before.match(/^\s*/)[0]+(before.trimEnd().endsWith('{')?'    ':'');editor.setRangeText('\n'+indent,editor.selectionStart,editor.selectionEnd,'end');editor.dispatchEvent(new InputEvent('input',{inputType:'insertLineBreak',bubbles:true}));}});shell.append(lines,editor);area.append(shell);update();}
  else if(q.type==='Dropdown'){const c=document.createElement('select');c.id='choice-answer';c.className='answer-input';c.setAttribute('aria-label','Choose an answer');for(const x of ['',...q.options]){const o=document.createElement('option');o.value=x;o.textContent=x||'Choose an answer';c.append(o);}c.value=answers[i];c.onchange=save;area.append(c);}
  else if(q.options){for(const text of q.options){const label=document.createElement('label');label.className='option';const radio=document.createElement('input');radio.type='radio';radio.name='answer';radio.value=text;radio.checked=answers[i]===text;radio.onchange=save;label.append(radio,document.createTextNode(text));area.append(label);}}
  else{const text=document.createElement('input');text.id='text-answer';text.className='answer-input';text.setAttribute('aria-label','Your answer');text.value=answers[i];text.oninput=save;area.append(text);}
  $('test-output').textContent=grades[i]?.message||'Run the checks when you are ready.';event('question',{index:i});
 }
 async function grade(i){const q=questions[i];if(q.type!=='Coding'){const passed=answers[i].trim()===q.answer;return{passed,message:passed?'Answer correct.':'Answer is not correct yet.'};}
  // Solutions run in a separate worker, never in the host or on the ingestion server.
  return await new Promise(resolve=>{const worker=new Worker('grader.js');let ended=false;const done=r=>{if(ended)return;ended=true;clearTimeout(timer);worker.terminate();resolve(r);};const timer=setTimeout(()=>done({passed:false,message:'Execution timed out after 2 seconds.'}),2000);worker.onmessage=e=>{const r=e.data;done({passed:r?.passed===true,message:String(r?.message||'Invalid result').slice(0,4000)});};worker.onerror=()=>done({passed:false,message:'Code could not run. Check syntax.'});worker.postMessage({source:answers[i],fn:q.fn,tests:q.tests});});
 }
 async function check(){if(!running||grading||finishing)return;grading=true;save();$('test-output').textContent='Running checks…';const i=current,requestRevision=revision;try{const result=await grade(i);if(!running||finishing||revision!==requestRevision)return;grades[i]=result;if(i===current)$('test-output').textContent=result.message;event('grade',{index:i,passed:result.passed});}finally{grading=false;}}
 const snapshot=()=>({values:answers,grades,score:Object.values(grades).filter(g=>g.passed).length,total:questions.length,grading:'client-reported; not evidence of authentic human activity'});
 function hostStopped(){
  // Native Stop has already revoked capture. Preserve current answers without
  // executing code or restarting capture; stale grading replies cannot mutate it.
  if(running){save();running=false;revision++;finishing=false;batch=[];post('finalized',{sessionId,answers:snapshot()});}
  results();
 }
 async function finish(gradeAll=true){if(!running)return;finishing=true;const finishRevision=++revision,finishedSession=sessionId;save();flush();running=false;
  // Revoke native capture before waiting for any participant code to execute.
  post('finish',{answers:snapshot()});results();
  try{if(gradeAll){for(let i=0;i<questions.length;i++){const result=await grade(i);if(revision!==finishRevision)return;grades[i]=result;}post('finalized',{sessionId:finishedSession,answers:snapshot()});results();}}
  finally{if(revision===finishRevision){finishing=false;updateSharing();}}}
 function updateSharing(){$('share-session').disabled=!signedIn||!$('share-consent').checked||finishing;$('export-session').disabled=finishing;$('sign-out').disabled=!signedIn;}
 for(const [id,action] of [['github-create-repo','create'],['github-install-app','install'],['github-invite-organizer','invite']])$(id)?.addEventListener('click',()=>post('github-setup',{action}));
 function resetSharing(){$('share-consent').checked=false;$('receipt').textContent='';updateSharing();}
 $('new-session').addEventListener('click',resetSharing);
 function results(){running=false;page('results');$('recording-status').textContent='Recording stopped';$('recording-status').dataset.state='stopped';$('score-summary').textContent=`${Object.values(grades).filter(g=>g?.passed===true).length} / ${questions.length} questions passed`;$('metrics-summary').textContent=`${count.toLocaleString()} interaction events collected. Review the local files before sharing.`;updateSharing();}
 $('consent').onchange=()=>{$('start-session').disabled=!$('consent').checked;};
 $('start-session').onclick=()=>{if($('consent').checked)post('start',{consent:true});};
 $('resume-last').disabled=true;$('resume-last').title='Sessions are immutable; start a new recording.';
 $('open-data').onclick=()=>post('open');$('open-first').onclick=()=>show(0);$('back-overview').onclick=()=>{save();tasks();page('overview');};$('previous').onclick=()=>show(Math.max(0,current-1));$('next').onclick=()=>show(Math.min(questions.length-1,current+1));$('run-code').onclick=check;$('finish-session').onclick=()=>finish();$('stop-recording').onclick=()=>finish(false);
 $('sign-in').onclick=()=>{$('sign-in').disabled=true;post('signin');};$('sign-out').onclick=()=>post('signout');$('share-session').disabled=true;$('share-consent').onchange=updateSharing;$('share-session').onclick=()=>{if(signedIn&&!finishing&&$('share-consent').checked)post('share',{consent:true});};$('export-session').onclick=()=>{if(!finishing)post('export');};$('new-session').onclick=()=>{revision++;finishing=false;answers=questions.map(q=>q.starter||'');grades={};current=0;page('welcome');$('consent').checked=false;$('start-session').disabled=true;post('list-sessions');};
 $('refresh-sessions').onclick=()=>post('list-sessions');$('saved-session').onchange=()=>{$('load-session').disabled=!$('saved-session').value;};$('load-session').onclick=()=>{const id=$('saved-session').value;if(/^[a-f0-9]{32}$/.test(id))post('load-session',{sessionId:id});};
 $('admin-run').onclick=()=>{if(adminEdition&&!running&&!finishing){$('admin-run').disabled=true;post('admin-start',{model:$('admin-model').value,effort:$('admin-effort').value,prompt:$('admin-prompt').value});}};
 $('intake-refresh').onclick=()=>requestIntake('queue');$('intake-catchup').onclick=()=>requestIntake('catchup');$('intake-start').onclick=()=>requestIntake('start');$('intake-stop').onclick=()=>requestIntake('stop');
 $('admin-stop').onclick=$('admin-stop-active').onclick=()=>{if(adminEdition)post('admin-stop');};
 native?.addEventListener('message',e=>{const m=e.data;
  if(m.kind==='started')resetSharing();
  if(m.kind==='edition'){adminEdition=m.mode==='admin';$('admin-controls').hidden=!adminEdition;updateIntakeControls();}
  if(m.kind==='admin-status'&&adminEdition){adminBusy=m.running===true;$('admin-status').textContent=m.message||'';$('admin-run').disabled=adminBusy;$('admin-stop').disabled=!adminBusy;$('admin-stop-active').hidden=!adminBusy;updateIntakeControls();}
  if(m.kind==='intake-result'&&adminEdition)intakeResult(m.data,m.stream===true);
  if(m.kind==='account'){signedIn=typeof m.login==='string'&&!!m.login;$('github-account').textContent=signedIn?'Signed in to GitHub as '+m.login:'Not signed in to GitHub';$('sign-in').disabled=false;updateSharing();}
  if(m.kind==='error')$('sign-in').disabled=false;
  if(m.kind==='sessions'){const select=$('saved-session');select.replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose an earlier recording';select.append(placeholder);for(const s of m.sessions||[]){if(!/^[a-f0-9]{32}$/.test(s.id))continue;const option=document.createElement('option');option.value=s.id;option.textContent=(s.startedAt||s.id)+' · '+s.mode;select.append(option);}$('load-session').disabled=true;}
  if(m.kind==='loaded'){revision++;finishing=false;sessionId=m.sessionId;mode=m.mode;count=Number(m.events)||0;grades=m.answers?.grades&&typeof m.answers.grades==='object'?m.answers.grades:{};$('receipt').textContent='';$('share-consent').checked=false;results();}
 });
 native?.addEventListener('message',e=>{const m=e.data;if(m.kind==='started'){sessionId=m.sessionId||'';revision++;finishing=false;running=true;mode=m.mode;started=performance.now();seq=count=0;batch=[];$('recording-status').textContent='Recording this test only';$('recording-status').dataset.state='recording';tasks();page('overview');}else if(m.kind==='stopped')hostStopped();else if(m.kind==='notice'||m.kind==='error')toast(m.message);else if(m.kind==='receipt'){$('receipt').textContent='Submitted successfully: '+m.url;}else if(m.kind==='admin-start'){answers=questions.map(q=>q.starter||'');grades={};post('admin-record-ready',{startId:m.startId});}});
 post('ready');
})();
