'use strict';
(() => {
 const $=id=>document.getElementById(id), native=window.chrome?.webview;
 let grading=false, finishing=false, revision=0, sessionId='', signedIn=false, adminEdition=false;
 let adminBusy=false,adminStarting=false,intakeBusy=false,intakeRunning=false,intakePending=null;
 let sitesConnected=false,sitesBusy='',sitesFailed=false,sitesEpoch=0,sitesShareEpoch=-1;
 // Test selection. Each session is bound to one known {testId, testVersion, questionCount} tuple, confirmed by
 // the host on start or load, until the next start or load. The welcome selector only picks the next start.
 const assessments=Array.isArray(window.assessments)?window.assessments:[];
 const knownTest=(id,version,count)=>assessments.find(a=>a.testId===id&&a.testVersion===version&&a.questionCount===count&&a.questions.length===count)||null;
 const tuple=a=>({testId:a.testId,testVersion:a.testVersion,questionCount:a.questionCount});
 // No checked option (synthetic stubs) means the original test, as before selection existed.
 const selectedTest=()=>assessments.find(a=>$('test-'+a.testId)?.checked===true)||assessments[0]||null;
 let active=assessments[0],questions=active.questions,pendingTest=null,rejectedStart=false;
 let running=false, mode='human', current=0, seq=0, started=0, batch=[], answers=questions.map(q=>q.starter||''), grades={}, count=0;
 // Fresh answers, grades and navigation for every bound session; nothing carries over between tests or sessions.
 function bind(test,id){active=test;questions=test.questions;answers=questions.map(q=>q.starter||'');grades={};current=0;window.assessmentSession=Object.freeze({...tuple(test),sessionId:id,questions});const r=$('test-'+test.testId);if(r)r.checked=true;syncAdminPrompt(test);}
 function updateSelector(){const locked=running||finishing||grading||adminBusy||adminStarting;for(const a of assessments){const r=$('test-'+a.testId);if(r)r.disabled=locked;}}
 const post=(command,extra={})=>native?.postMessage({command,...extra});
 const toast=message=>{$('toast').textContent=message;};
 function updateIntakeControls(){
  const blocked=!adminEdition||adminBusy||running||intakeBusy||sitesIntakeActive();
  for(const id of ['intake-refresh','intake-catchup'])$(id).disabled=blocked;
  $('intake-start').disabled=blocked||intakeRunning;
  $('intake-stop').disabled=!adminEdition||!intakeRunning;
  for(const button of $('intake-queue').querySelectorAll('button'))button.disabled=blocked;
  // Its Stop must stay reachable while the earlier GitHub worker runs.
  if(intakeRunning)$('intake-github').open=true;
  updateSitesIntake();
 }
 function requestIntake(command,extra={}){
  if(!adminEdition||((running||adminBusy||intakeBusy||sitesIntakeActive())&&command!=='stop'))return;
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
 // Sites collection (Admin; the default in Submissions). Posts sites-intake-start {capability} and
 // sites-intake-stop; the host relays worker lines and its own results as {kind:'sites-intake-result',data}.
 // The read grant leaves the field before it is posted and is never kept, logged or shown here.
 const sitesCapabilityFormat=/^[A-Za-z0-9_-]{43}$/;
 const sitesCountLimits={downloads:3,retained:10000,calls:100,errors:10000,skipped:10000};
 const sitesIntakeMessages={recipient_key_setup_invalid:'The local recipient key on this computer could not be verified. The organizer must repair the key setup on this computer. Participants do not need to resend anything.',worker_already_running:'Sites collection is already running.',sites_not_authorized:'The Sites service did not accept this read grant. It may have expired or been revoked. Copy a new one from the owner-only Sites page, then start again.',sites_http_failed:'The Sites service returned an error.',sites_transport_failed:'Could not reach the Sites service.',sites_transport_busy:'The Sites connection was busy.',sites_corpus_quota:'Local Sites storage is full.',sites_pin_quota:'Local Sites storage is full.',sites_record_quota:'Local Sites storage is full.',sites_backoff_capacity:'Too many uploads are waiting for a later retry. Review the private collection state.',sites_list_invalid:'The Sites service sent an upload list this app could not read. Nothing from it was stored.',sites_validation_unavailable:'Upload validation is unavailable on this computer. Nothing was accepted.',sites_local_unavailable:'The local Sites collection folder is unavailable.',sites_intake_failed:'The Sites collection worker failed. Check the private runtime.',sites_partial_failure:'Some recordings could not be verified; they were not accepted.',sites_intake_busy:'Sites collection cannot start while a recording, Codex run, sharing or another collection is active.',sites_stop_failed:'Sites collection could not be stopped. Close this Admin window to stop its worker.',sites_worker_not_owned:'A collection worker started from another Admin window or terminal is running. Stop it in that original window.'};
 // Pending start and pending stop are separate: a run or cycle never clears a requested stop, and a
 // malformed message never clears either one while the worker's state is unknown.
 let sitesIntakeRunning=false,sitesStartPending=false,sitesStopPending=false,sitesIntakeUncertain=false,sitesIntakeStopped=false,sitesIntakeError='';
 const sitesIntakeActive=()=>sitesIntakeRunning||sitesStartPending||sitesStopPending||sitesIntakeUncertain;
 const sitesIntakeBlocked=()=>!adminEdition||running||finishing||grading||adminBusy||adminStarting||intakeBusy||intakeRunning||!!intakePending;
 const sitesIntakeText=code=>(typeof code==='string'&&Object.hasOwn(sitesIntakeMessages,code)?sitesIntakeMessages[code]:'')||'Sites collection could not complete. Check the private runtime and try again.';
 function sitesIntakeStatus(state,text){const s=$('sites-intake-status');s.dataset.state=state;s.textContent=text;}
 function sitesIntakeShow(){
  if(sitesStopPending)sitesIntakeStatus('pending','Stopping Sites collection…');
  else if(sitesStartPending)sitesIntakeStatus('pending','Starting Sites collection…');
  else if(sitesIntakeUncertain)sitesIntakeStatus('warn','Could not read the latest Sites collection status. Press Stop to make sure it has ended.');
  else if(sitesIntakeRunning)sitesIntakeStatus(sitesIntakeError?'warn':'running',sitesIntakeError?sitesIntakeError+' Collection is still running.':'Running. Checks about every five minutes while this app is open.');
  else if(sitesIntakeError)sitesIntakeStatus('error',sitesIntakeError);
  else sitesIntakeStatus('idle',sitesIntakeStopped?'Sites collection stopped.':'Not running');
 }
 function updateSitesIntake(){
  const input=$('sites-intake-capability'),value=input.value.trim(),valid=sitesCapabilityFormat.test(value),active=sitesIntakeActive(),blocked=sitesIntakeBlocked();
  input.disabled=blocked||active;
  $('sites-intake-start').disabled=input.disabled||!valid;
  // Stop stays available while a start is unacknowledged, the worker runs or its state is unknown.
  $('sites-intake-stop').disabled=!adminEdition||sitesStopPending||!(sitesIntakeRunning||sitesStartPending||sitesIntakeUncertain);
  // No recording or Codex run may start while Sites collection is pending or active.
  $('start-session').disabled=!$('consent').checked||active;
  $('admin-run').disabled=adminBusy||adminStarting||active;
  const note=$('sites-intake-cap-note');let state='idle';
  if(active)note.textContent='Sites collection is active. Stop it to use a different read grant.';
  else if(blocked&&adminEdition)note.textContent='Unavailable while a recording, Codex run or GitHub collection is active.';
  else if(!value)note.textContent='43 characters: letters, numbers, - and _.';
  else if(valid){state='ok';note.textContent='Format looks right.';}
  else{state='bad';note.textContent=/[^A-Za-z0-9_-]/.test(value)?'Use only letters, numbers, - and _.':value.length+' of 43 characters.';}
  note.dataset.state=state;input.setAttribute('aria-invalid',String(state==='bad'));
 }
 function sitesIntakeLog(state,text){
  const log=$('sites-intake-log'),item=document.createElement('li'),time=document.createElement('time'),body=document.createElement('span');
  const now=new Date();item.className='sites-log-item';item.dataset.state=state;time.className='sites-log-time';time.dateTime=now.toISOString();
  time.textContent=String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0');body.className='sites-log-text';body.textContent=text;
  item.append(time,body);log.prepend(item);while(log.children.length>6)log.lastElementChild.remove();
 }
 function sitesIntakeCounts(counts){
  if(!counts||typeof counts!=='object'||Array.isArray(counts)||Object.keys(counts).length!==5)return null;
  const checked={};
  for(const [name,limit] of Object.entries(sitesCountLimits)){const n=Object.hasOwn(counts,name)?counts[name]:NaN;if(!Number.isSafeInteger(n)||n<0||n>limit)return null;checked[name]=n;}
  return checked;
 }
 function sitesIntakeValid(d){
  if(!d||typeof d!=='object'||Array.isArray(d)||d.schemaVersion!==1||d.transport!=='sites'||!['run','cycle','stop'].includes(d.command)||typeof d.ok!=='boolean'||typeof d.running!=='boolean')return false;
  if(d.ok?d.error!==null:typeof d.error!=='string'||!/^[a-z_]{1,64}$/.test(d.error))return false;
  return !Object.hasOwn(d,'counts')||d.command==='cycle'&&!!sitesIntakeCounts(d.counts);
 }
 // Literal numbers from the most recent check. Without new counts the old ones stay, marked stale.
 function sitesIntakeTally(counts,ok){
  const tally=$('sites-intake-tally');
  if(counts){
   for(const name of Object.keys(sitesCountLimits))$('sites-count-'+name).textContent=String(counts[name]);
   tally.dataset.state=ok?'ok':'warn';tally.dataset.tick=String((Number(tally.dataset.tick)||0)%2+1);
  }
  const stale=!counts&&tally.dataset.state!=='empty';tally.dataset.stale=String(stale);$('sites-intake-stale').hidden=!stale;
 }
 function requestSitesIntake(command){
  if(!adminEdition)return;
  if(command==='stop'){
   if(sitesStopPending||!(sitesIntakeRunning||sitesStartPending||sitesIntakeUncertain))return;
   sitesStopPending=true;sitesIntakeShow();updateIntakeControls();post('sites-intake-stop');return;
  }
  const input=$('sites-intake-capability'),capability=input.value.trim();input.value='';
  if(sitesIntakeBlocked()||sitesIntakeActive()||!sitesCapabilityFormat.test(capability)){updateIntakeControls();return;}
  sitesStartPending=true;sitesIntakeError='';sitesIntakeStopped=false;sitesIntakeTally(null);sitesIntakeShow();updateIntakeControls();
  post('sites-intake-start',{capability});
 }
 function sitesIntakeResult(data){
  if(!sitesIntakeValid(data)){
   // Fail closed: nothing is cleared or claimed. Start stays blocked and Stop stays available.
   sitesIntakeUncertain=true;sitesIntakeShow();updateIntakeControls();return;
  }
  const {command,ok,running:workerRunning}=data,wasActive=sitesIntakeRunning||sitesStartPending||sitesStopPending,text=ok?'':sitesIntakeText(data.error);
  if(command==='run'){
   if(!sitesStartPending)return; // Stale: no start is waiting for this reply.
   sitesStartPending=false;sitesIntakeUncertain=false;sitesIntakeRunning=workerRunning;
   if(ok&&workerRunning){sitesIntakeError='';$('sites-intake-capability').value='';sitesIntakeLog('start','Collection started');}
   else{sitesIntakeError=text||sitesIntakeText(null);sitesIntakeLog('error','Could not start');}
  }else if(command==='cycle'){
   if(!sitesIntakeRunning)return; // Checks count only while the worker is known to run.
   sitesIntakeUncertain=false;sitesIntakeRunning=workerRunning;
   sitesIntakeTally(Object.hasOwn(data,'counts')?sitesIntakeCounts(data.counts):null,ok);
   // A generic failure after a specific one keeps the specific explanation.
   if(ok)sitesIntakeError='';else if(!(data.error==='sites_intake_failed'&&sitesIntakeError))sitesIntakeError=text;
   sitesIntakeLog(ok?'ok':workerRunning?'warn':'error',ok?'Check finished':workerRunning?'Check reported an error':'Collection ended with an error');
  }else{
   sitesStopPending=false;sitesIntakeUncertain=false;sitesIntakeRunning=workerRunning;
   if(workerRunning){
    // Only running:false means stopped, even when ok is true.
    sitesIntakeError=ok?'Sites collection did not stop.':text;sitesIntakeLog('error','Stop did not complete');
   }else{
    sitesStartPending=false;if(!ok)sitesIntakeError=text;
    if(wasActive){sitesIntakeStopped=true;sitesIntakeLog('stop','Collection stopped');}
   }
  }
  sitesIntakeShow();updateIntakeControls();
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
 // Private Admin edition only: answers one host nonce query with owned-editor metadata (element token, IME
 // composition, caret/selection, length, digests before/after the selection, caret-line indentation whitespace,
 // input count) so the host can gate and verify an optional synthetic correction. Answer text is never sent.
 const ownedField=t=>['code-editor','text-answer'].includes(t?.id),editorTargets=new WeakMap();
 const fnv=s=>{let h=0x811c9dc5;for(let i=0;i<s.length;i++)h=Math.imul(h^s.charCodeAt(i),0x01000193)>>>0;return h;};
 let composing=false,editorInputs=0,editorTarget=0;
 document.addEventListener('compositionstart',()=>{composing=true;},true);document.addEventListener('compositionend',()=>{composing=false;},true);
 document.addEventListener('input',e=>{if(ownedField(e.target))editorInputs++;},true);
 native?.addEventListener('message',e=>{const m=e.data;if(m?.kind!=='admin-editor-query'||!adminEdition||!/^[a-f0-9]{32}$/.test(m.id))return;
  const f=document.activeElement,owned=document.hasFocus()&&ownedField(f)&&f.isConnected!==false,v=owned?String(f.value):'',start=owned?f.selectionStart:0,end=owned?f.selectionEnd:0;
  if(owned&&!editorTargets.has(f))editorTargets.set(f,++editorTarget);const line=v.slice(0,start).split('\n').pop();
  post('admin-editor-state',{id:m.id,owned,composing,target:owned?editorTargets.get(f):0,multiline:owned&&f.id==='code-editor',start,end,length:v.length,
   head:fnv(v.slice(0,start)),tail:fnv(v.slice(end)),lead:line.match(/^\s*/)[0],blank:line.trim()==='',open:line.trimEnd().endsWith('{'),inputs:editorInputs});});
 window.addEventListener('blur',()=>{flush();});
 setInterval(flush,100);
 setInterval(()=>{if(running){const s=Math.max(0,1800-Math.floor((performance.now()-started)/1000));$('timer').textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;}},1000);
 function tasks(){const coding=questions.filter(q=>q.type==='Coding').length;$('basics-count').textContent=`${questions.length-coding} questions`;$('coding-count').textContent=`${coding} questions`;const list=$('task-list');list.replaceChildren();questions.forEach((q,i)=>{const tr=document.createElement('tr');tr.className='task-row';for(const text of [`${i+1}. ${q.title}`,q.type,grades[i]?.passed?'Passed':answers[i]&&answers[i]!==q.starter?'In progress':'Not started']){const td=document.createElement('td');td.textContent=text;tr.append(td);}const td=document.createElement('td'),b=document.createElement('button');b.className='solve-button';b.textContent='Solve';b.onclick=()=>show(i);td.append(b);tr.append(td);list.append(tr);});}
 function save(){const e=$('code-editor')||$('text-answer')||$('choice-answer');if(e)answers[current]=e.value;else{const checked=document.querySelector('input[name=answer]:checked');if(checked)answers[current]=checked.value;}}
 function show(i){save();current=i;page('workspace');$('question-title').textContent=questions[i].type==='Coding'?'JavaScript · '+questions[i].title:questions[i].title;
  $('question-nav').replaceChildren();questions.forEach((q,n)=>{const b=document.createElement('button');b.className='question-link'+(i===n?' active':'');if(n===0||(questions[n-1].type==='Coding')!==(q.type==='Coding')){b.className+=' section-start';b.dataset.section=q.type==='Coding'?'S2':'S1';}b.textContent=String(n+1);b.title=q.title;b.onclick=()=>show(n);$('question-nav').append(b);});
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
 const snapshot=()=>({...tuple(active),values:answers,grades,score:Object.values(grades).filter(g=>g.passed).length,total:questions.length,grading:'client-reported; not evidence of authentic human activity'});
 function hostStopped(){
  // Native Stop has already revoked capture. Preserve current answers without
  // executing code or restarting capture; stale grading replies cannot mutate it.
  if(running){save();running=false;revision++;finishing=false;batch=[];post('finalized',{sessionId,answers:snapshot()});}
  else if(rejectedStart){rejectedStart=false;page('welcome');updateSharing();return;}
  results();
 }
 async function finish(gradeAll=true){if(!running)return;finishing=true;const finishRevision=++revision,finishedSession=sessionId;save();flush();running=false;
  // Revoke native capture before waiting for any participant code to execute.
  post('finish',{answers:snapshot()});results();
  try{if(gradeAll){for(let i=0;i<questions.length;i++){const result=await grade(i);if(revision!==finishRevision)return;grades[i]=result;}post('finalized',{sessionId:finishedSession,answers:snapshot()});results();}}
  finally{if(revision===finishRevision){finishing=false;updateSharing();}}}
 function updateSharing(){updateSelector();$('share-session').disabled=!signedIn||!$('share-consent').checked||finishing||!!sitesBusy;$('export-session').disabled=finishing;$('sign-out').disabled=!signedIn;updateSites();updateIntakeControls();}
 for(const [id,action] of [['github-create-repo','create'],['github-install-app','install'],['github-invite-organizer','invite']])$(id)?.addEventListener('click',()=>post('github-setup',{action}));
 function resetSharing(){$('share-consent').checked=false;$('receipt').textContent='';resetSites();$('sites-intake-capability').value='';updateSharing();}
 // Invitation sharing. The host keeps the connection in memory and re-checks every gate. The code
 // is cleared from the field before it is posted and is never stored, logged or echoed here.
 // sitesBusy is this page's own pending marker: the host sends no busy message, so it clears on an
 // account update, an upload status, or a matching operation-tagged failure notice/error.
 const sitesCodeFormat=/^[A-Za-z0-9_-]{43}$/;
 const sitesEligible=()=>!running&&!finishing&&!grading&&!adminBusy&&mode==='human'&&/^[a-f0-9]{32}$/.test(sessionId);
 function sitesUpload(state,text=''){$('sites-upload-status').textContent=text;$('sites-upload').dataset.state=state;}
 function updateSites(){
  const input=$('sites-code'),code=input.value.trim(),valid=sitesCodeFormat.test(code),consent=$('sites-share-consent'),eligible=sitesEligible();
  input.disabled=sitesConnected||!!sitesBusy||running||finishing||grading||adminBusy;
  $('sites-connect').disabled=!valid||input.disabled;
  // Disconnect stays available while anything is pending so it can cancel and clear memory.
  $('sites-disconnect').disabled=!sitesConnected&&!sitesBusy;
  consent.disabled=!sitesConnected||!!sitesBusy||!eligible;
  $('sites-share').disabled=consent.disabled||!consent.checked;
  const note=$('sites-code-note');let noteState='idle';
  if(sitesConnected)note.textContent='Connected. Disconnect to use a different code.';
  else if(sitesFailed&&!code){noteState='bad';note.textContent='Could not connect. Check the code and paste it again.';}
  else if(!code)note.textContent='43 characters: letters, numbers, - and _.';
  else if(valid){noteState='ok';note.textContent='Code format looks right.';}
  else{noteState='bad';note.textContent=/[^A-Za-z0-9_-]/.test(code)?'Use only letters, numbers, - and _.':code.length+' of 43 characters.';}
  note.dataset.state=noteState;input.setAttribute('aria-invalid',String(noteState==='bad'&&!!code));
  const signal=$('sites-account');
  $('sites-signal').dataset.state=sitesBusy==='connect'||sitesBusy==='disconnect'?'pending':sitesConnected?'on':'off';
  signal.textContent=sitesBusy==='connect'?'Connecting…':sitesBusy==='disconnect'?'Disconnecting…':sitesConnected?'Connected with your invitation':'Not connected';
  $('sites-share-hint').textContent=sitesBusy==='share'?'Keep the app open. Disconnect cancels.':sitesBusy?'':
   !sitesConnected?'Connect an invitation first.':
   running?'Finish or stop the recording first.':finishing||grading?'Wait until grading finishes.':adminBusy?'Wait until the Codex run stops.':
   !/^[a-f0-9]{32}$/.test(sessionId)?'Open a finished recording to share it.':mode!=='human'?'Only your own practice recordings can be shared, not Codex or test runs.':
   !consent.checked?'Tick the consent box to enable sharing.':'Shares only this recording.';
 }
 // New, started or loaded session: no consent or status may carry over to a different recording.
 function resetSites(){sitesEpoch++;$('sites-share-consent').checked=false;$('sites-code').value='';sitesFailed=false;sitesUpload('none');}
 $('sites-code').addEventListener('input',()=>{sitesFailed=false;updateSites();});
 $('sites-code').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();$('sites-connect').click();}});
 $('sites-connect').onclick=()=>{
  const input=$('sites-code'),code=input.value.trim();input.value='';
  if(!sitesCodeFormat.test(code)||sitesConnected||sitesBusy||running||finishing||grading||adminBusy){updateSites();return;}
  sitesBusy='connect';sitesFailed=false;updateSharing();post('sites-connect',{code});
 };
 $('sites-disconnect').onclick=()=>{
  if(!sitesConnected&&!sitesBusy)return;
  if(sitesBusy==='share'&&sitesShareEpoch===sitesEpoch)sitesUpload('failed','Sharing was cancelled. The upload may not have completed.');
  $('sites-code').value='';sitesBusy='disconnect';updateSharing();post('sites-disconnect');
 };
 $('sites-share-consent').onchange=updateSites;
 $('sites-share').onclick=()=>{
  if(!sitesConnected||sitesBusy||!sitesEligible()||!$('sites-share-consent').checked)return;
  sitesBusy='share';sitesShareEpoch=sitesEpoch;sitesUpload('sending','Encrypting and uploading this recording…');updateSharing();post('sites-share',{consent:true});
 };
 function sitesMessage(m){
  const shareShown=sitesBusy==='share'&&sitesShareEpoch===sitesEpoch;
  if(m.kind==='sites-account'){
   const connected=m.connected===true&&typeof m.participantId==='string'&&/^[a-f0-9]{32}$/.test(m.participantId);
   if(sitesBusy==='connect'&&!connected)sitesFailed=true;
   if(shareShown&&!connected)sitesUpload('failed','Sharing was cancelled. The upload may not have completed.');
   // A connection change never carries consent over, including a fresh connection.
   sitesConnected=connected;sitesBusy='';$('sites-share-consent').checked=false;updateSharing();
  }else if(m.kind==='sites-upload'&&(m.status==='stored'||m.status==='received_by_organizer')){
   const fromThisRecording=sitesShareEpoch===sitesEpoch;
   if(sitesBusy==='share')sitesBusy='';
   if(fromThisRecording)sitesUpload(m.status==='stored'?'stored':'received',m.status==='stored'
    ?'Stored: the study service holds the encrypted upload. The organizer has not downloaded it yet.'
    :'Received: the organizer has downloaded the encrypted upload. This confirms delivery only, not that the recording was checked.');
   updateSharing();
  }else if((m.kind==='notice'||m.kind==='error')&&sitesBusy&&m.operation==='sites-'+sitesBusy){
   if(sitesBusy==='connect')sitesFailed=true;
   if(shareShown)sitesUpload('failed','Sharing was not confirmed. The upload may be stored; see the message below.');
   sitesBusy='';updateSharing();
  }
 }
 $('new-session').addEventListener('click',resetSharing);
 function results(){running=false;page('results');$('recording-status').textContent='Recording stopped';$('recording-status').dataset.state='stopped';$('results-test').textContent=`${active.name} · ${active.questionCount} questions`;$('score-summary').textContent=`${Object.values(grades).filter(g=>g?.passed===true).length} / ${questions.length} questions passed`;$('metrics-summary').textContent=`${count.toLocaleString()} interaction events collected. Review the local files before sharing.`;updateSharing();}
 $('consent').onchange=()=>{$('start-session').disabled=!$('consent').checked||sitesIntakeActive();};
 $('start-session').onclick=()=>{const t=selectedTest();if($('consent').checked&&!sitesIntakeActive()&&!running&&t){pendingTest=t;post('start',{consent:true,...tuple(t)});}};
 // Admin default prompts follow the selected test until the prompt is edited.
 const adminPrompts={'practice-js-5':'Complete all five practice questions correctly. Use the personalized input tools and inspect results. Get 5/5.','practice-js-13':'Complete all thirteen practice questions correctly. Use the personalized input tools and inspect results. Get 13/13.'};
 function syncAdminPrompt(t){const p=$('admin-prompt');if(t&&Object.hasOwn(adminPrompts,t.testId)&&Object.values(adminPrompts).includes(p.value))p.value=adminPrompts[t.testId];}
 for(const a of assessments){const r=$('test-'+a.testId);if(r)r.onchange=()=>syncAdminPrompt(selectedTest());}
 $('resume-last').disabled=true;$('resume-last').title='Sessions are immutable; start a new recording.';
 $('open-data').onclick=()=>post('open');$('open-first').onclick=()=>show(0);$('back-overview').onclick=()=>{save();tasks();page('overview');};$('previous').onclick=()=>show(Math.max(0,current-1));$('next').onclick=()=>show(Math.min(questions.length-1,current+1));$('run-code').onclick=check;$('finish-session').onclick=()=>finish();$('stop-recording').onclick=()=>{if(!running)return;save();flush();revision++;finishing=true;updateSharing();post('stop');};
 $('sign-in').onclick=()=>{$('sign-in').disabled=true;post('signin');};$('sign-out').onclick=()=>post('signout');$('share-session').disabled=true;$('share-consent').onchange=updateSharing;$('share-session').onclick=()=>{if(signedIn&&!finishing&&!sitesBusy&&$('share-consent').checked)post('share',{consent:true});};$('export-session').onclick=()=>{if(!finishing)post('export');};$('new-session').onclick=()=>{revision++;finishing=false;answers=questions.map(q=>q.starter||'');grades={};current=0;page('welcome');$('consent').checked=false;$('start-session').disabled=true;post('list-sessions');};
 $('refresh-sessions').onclick=()=>post('list-sessions');$('saved-session').onchange=()=>{$('load-session').disabled=!$('saved-session').value;};$('load-session').onclick=()=>{const id=$('saved-session').value;if(/^[a-f0-9]{32}$/.test(id))post('load-session',{sessionId:id});};
 $('admin-run').onclick=()=>{const t=selectedTest();if(adminEdition&&!running&&!finishing&&!adminStarting&&!sitesIntakeActive()&&t){adminStarting=true;pendingTest=t;$('admin-run').disabled=true;updateIntakeControls();updateSelector();post('admin-start',{...tuple(t),model:$('admin-model').value,effort:$('admin-effort').value,prompt:$('admin-prompt').value,syntheticCorrections:$('admin-corrections').checked===true});}};
 $('sites-intake-capability').addEventListener('input',updateSitesIntake);$('sites-intake-capability').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();requestSitesIntake('start');}});
 $('sites-intake-start').onclick=()=>requestSitesIntake('start');$('sites-intake-stop').onclick=()=>requestSitesIntake('stop');
 $('intake-refresh').onclick=()=>requestIntake('queue');$('intake-catchup').onclick=()=>requestIntake('catchup');$('intake-start').onclick=()=>requestIntake('start');$('intake-stop').onclick=()=>requestIntake('stop');
 $('admin-stop').onclick=$('admin-stop-active').onclick=()=>{if(adminEdition)post('admin-stop');};
 native?.addEventListener('message',e=>{const m=e.data;
  sitesMessage(m);
  if(m.kind==='started')resetSharing();
  if(m.kind==='receipt')$('github-sharing').open=true;
  if(m.kind==='edition'){adminEdition=m.mode==='admin';$('admin-controls').hidden=!adminEdition;updateIntakeControls();}
  if(m.kind==='admin-status'&&adminEdition){adminBusy=m.running===true;adminStarting=m.starting===true;$('admin-status').textContent=m.message||'';$('admin-run').disabled=adminBusy;$('admin-stop').disabled=!(adminBusy||adminStarting);$('admin-stop-active').hidden=!(adminBusy||adminStarting);updateIntakeControls();updateSharing();}
  if(m.kind==='intake-result'&&adminEdition)intakeResult(m.data,m.stream===true);
  if(m.kind==='sites-intake-result'&&adminEdition)sitesIntakeResult(m.data);
  if(m.kind==='account'){signedIn=typeof m.login==='string'&&!!m.login;$('github-account').textContent=signedIn?'Signed in to GitHub as '+m.login:'Not signed in to GitHub';$('sign-in').disabled=false;updateSharing();}
  if(m.kind==='error'){$('sign-in').disabled=false;if(adminStarting){adminStarting=false;updateIntakeControls();}}
  if(m.kind==='sessions'){const select=$('saved-session');select.replaceChildren();const placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose an earlier recording';select.append(placeholder);for(const s of m.sessions||[]){if(!/^[a-f0-9]{32}$/.test(s.id))continue;const option=document.createElement('option');option.value=s.id;const t=knownTest(s.testId,s.testVersion,s.questionCount);option.textContent=(s.startedAt||s.id)+' · '+s.mode+(t?' · '+t.name:'');select.append(option);}$('load-session').disabled=true;}
  if(m.kind==='loaded'){const t=knownTest(m.testId,m.testVersion,m.questionCount);if(!t){toast('This recording names an unknown test and was not opened.');return;}revision++;finishing=false;sessionId=m.sessionId;mode=m.mode;bind(t,sessionId);count=Number(m.events)||0;grades=m.answers?.grades&&typeof m.answers.grades==='object'?m.answers.grades:{};$('receipt').textContent='';$('share-consent').checked=false;resetSites();results();}
 });
 native?.addEventListener('message',e=>{const m=e.data;if(m.kind==='started'){
  // Accept only a known tuple, and only the one this page asked for. Otherwise stop the host recording.
  const t=knownTest(m.testId,m.testVersion,m.questionCount);
  if(!t||(pendingTest&&t!==pendingTest)){pendingTest=null;rejectedStart=true;running=false;post('stop');toast('The recording did not match the selected test and was stopped. Start a new session.');page('welcome');updateSharing();return;}
  pendingTest=null;rejectedStart=false;sessionId=m.sessionId||'';bind(t,sessionId);revision++;finishing=false;running=true;mode=m.mode;started=performance.now();seq=count=0;batch=[];$('recording-status').textContent='Recording this test only';$('recording-status').dataset.state='recording';tasks();page('overview');updateSharing();}else if(m.kind==='stopped')hostStopped();else if(m.kind==='notice'||m.kind==='error')toast(m.message);else if(m.kind==='receipt'){$('receipt').textContent='Submitted successfully: '+m.url;}else if(m.kind==='admin-start'){answers=questions.map(q=>q.starter||'');grades={};post('admin-record-ready',{startId:m.startId});}});
 post('ready');
})();
