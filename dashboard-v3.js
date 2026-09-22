'use strict';

let sb=null;
let session=null;
let userRole='viewer';
let market=window.MARKET_DATA || {watchlist:[]};
let liveQuotes={};
let liveFetchedAt=null;

const $=id=>document.getElementById(id);
const money=n=>n==null?'—':'$'+Number(n).toLocaleString(undefined,{maximumFractionDigits:2});
const pct=n=>n==null?'—':(Number(n)>0?'+':'')+Number(n).toFixed(1)+'%';
const x=n=>n==null?'—':Number(n).toFixed(1)+'x';
const safe=n=>n==null?'—':Number(n).toFixed(1);
const days=(a,b)=>a&&b?Math.round((new Date(b)-new Date(a))/86400000):'—';
function marketClock(){
  const now=new Date();
  const parts=new Intl.DateTimeFormat('en-US',{
    timeZone:'America/New_York',
    hour12:false,weekday:'short',hour:'2-digit',minute:'2-digit'
  }).formatToParts(now);
  const map=Object.fromEntries(parts.map(p=>[p.type,p.value]));
  return {weekday:map.weekday,h:Number(map.hour),m:Number(map.minute)};
}

function premarketHtml(s){
  const q=liveQuotes[s?.ticker];
  const clock=marketClock();
  const mins=clock.h*60+clock.m;
  const weekday=!['Sat','Sun'].includes(clock.weekday);
  const inPre=weekday&&mins>=240&&mins<570;

  const price=(q&&q.preMarketPrice!=null)?q.preMarketPrice:null;
  const pp=(q&&q.preMarketPct!=null)?q.preMarketPct:null;
  const stamp=(q&&q.preMarketAsOf)?q.preMarketAsOf:null;

  if(inPre){
    if(price==null){
      return '<div class="row premarket-row"><span class="muted"><span class="pill">PRE</span> 盤前</span><b class="muted">抓取中…</b></div>';
    }
    const cls=Number(pp)>=0?'pos':'neg';
    const p=pp==null?'—':(Number(pp)>0?'+':'')+Number(pp).toFixed(2)+'%';
    return '<div class="row premarket-row"><span class="muted"><span class="pill">PRE</span> 盤前</span><b class="'+cls+'">'+money(price)+' · '+p+'</b></div>'+
      '<div class="small muted" style="text-align:right;margin-top:3px">'+(stamp||'')+'</div>';
  }

  return '<div class="row premarket-row"><span class="muted"><span class="pill">PRE</span> 盤前</span><b class="muted">16:00 TPE 開始</b></div>';
}

function afterHoursHtml(s){
  const q=liveQuotes[s?.ticker];
  if(!q||q.postMarketPrice==null||!['POST','CLOSED'].includes(q.state))return '';
  const cls=Number(q.postMarketPct)>=0?'pos':'neg';
  const p=q.postMarketPct==null?'—':(Number(q.postMarketPct)>0?'+':'')+Number(q.postMarketPct).toFixed(2)+'%';
  return '<div class="row"><span class="muted"><span class="pill">AH</span> 盤後</span><b class="'+cls+'">'+money(q.postMarketPrice)+' · '+p+'</b></div>'+
    '<div class="small muted" style="text-align:right;margin-top:3px">'+(q.postMarketAsOf||'')+'</div>';
}

function liveQuoteHealth(){
  if(!liveFetchedAt)return '';
  const age=(Date.now()-new Date(liveFetchedAt).getTime())/1000;
  if(age>90)return ' · ⚠ quote stale';
  return '';
}

function currentDisplay(s){
  const q=liveQuotes[s?.ticker];
  if(q){
    if(q.state==='REGULAR'&&q.price!=null){
      return {price:q.price,pct:q.changePct,label:'<span class="pill">LIVE</span> '};
    }
    if(q.regularMarketPrice!=null){
      return {price:q.regularMarketPrice,pct:q.regularMarketPct,label:''};
    }
  }
  return {price:s?.price,pct:s?.dayPct,label:''};
}

function showLogin(msg=''){
  $('loginView').classList.remove('hidden');
  $('appView').classList.add('hidden');
  $('loginMsg').textContent=msg;
}

function showApp(){
  $('loginView').classList.add('hidden');
  $('appView').classList.remove('hidden');
}

function renderMarket(){
  const wl=Array.isArray(market.watchlist)?market.watchlist:[];
  const states=Object.values(liveQuotes).map(q=>q?.state).filter(Boolean);
  const state=states.includes('REGULAR')?'REGULAR':states.includes('PRE')?'PRE':states.includes('POST')?'POST':'CLOSED';
  const stateLabel=state==='REGULAR'?'LIVE':state==='PRE'?'PRE LIVE':state==='POST'?'AH LIVE':'MARKET CLOSED';
  $('marketAsOf').textContent='Market data: '+(market.asOf||'—')+' · Updated: '+(market.updatedAt||'—')+
    ' · '+stateLabel+
    (liveFetchedAt?' · quotes '+new Date(liveFetchedAt).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}):'')+liveQuoteHealth();
  $('cards').innerHTML=wl.map(s=>{
    const pre=premarketHtml(s);
    const ah=afterHoursHtml(s);
    const d=currentDisplay(s);
    return '<div class="card"><div class="ticker">'+s.ticker+' <span class="small muted">'+(s.name||'')+'</span></div>'+
      '<div class="price">'+d.label+money(d.price)+'</div><div class="'+(d.pct>=0?'pos':'neg')+'">'+pct(d.pct)+'</div>'+pre+ah+
      '<div class="row"><span class="muted">RSI</span><b>'+safe(s.rsi14)+'</b></div>'+
      '<div class="row"><span class="muted">MA20/50/200</span><b>'+safe(s.ma20)+' / '+safe(s.ma50)+' / '+safe(s.ma200)+'</b></div>'+
      '<div class="row"><span class="muted">Risk/Reward</span><b>'+safe(s.riskReward)+'/10</b></div></div>';
  }).join('') || '<div class="notice muted">No market data.</div>';

  $('fund').innerHTML=wl.map(s=>'<tr><td><b>'+s.ticker+'</b></td><td>'+pct(s.revenueGrowth)+'</td><td>'+pct(s.fcfMargin)+'</td><td>'+pct(s.sbcRevenue)+'</td><td>'+x(s.forwardPE)+'</td><td>'+x(s.evSales)+'</td><td>'+x(s.pFcf)+'</td><td>'+safe(s.companyQuality)+'</td><td>'+safe(s.valuation)+'</td><td><b>'+safe(s.riskReward)+'</b></td></tr>').join('');
}

function renderHoldings(list){
  const m=Object.fromEntries((market.watchlist||[]).map(s=>[s.ticker,s]));
  $('holdings').innerHTML=list.length?list.map(h=>{
    const s=m[h.ticker]||{};
    const d=currentDisplay(s);
    const u=h.entry_avg&&d.price?100*(d.price-h.entry_avg)/h.entry_avg:null;
    return '<div class="card"><div class="ticker">'+h.ticker+' <span class="pill">HOLDING</span></div>'+
      '<div class="price">'+d.label+money(d.price)+'</div>'+premarketHtml(s)+afterHoursHtml(s)+
      '<div class="row"><span class="muted">進場日期</span><b>'+(h.entry_date||'—')+'</b></div>'+
      (userRole==='owner'?'<div class="row"><span class="muted">進場均價</span><b>'+money(h.entry_avg)+'</b></div>':'')+
      (userRole==='owner'?'<div class="row"><span class="muted">未實現</span><b class="'+(u>=0?'pos':'neg')+'">'+pct(u)+'</b></div>':'')+
      (userRole==='owner'?'<div class="actions" style="margin-top:10px"><button class="btn secondary" data-edit-holding="'+h.id+'">Edit</button><button class="btn danger" data-delete-holding="'+h.id+'">Delete</button></div>':'')+
      '</div>';
  }).join(''):'<div class="notice muted">No holdings yet.</div>';
}

function renderTrades(list){
  $('trades').innerHTML=list.length?list.map(t=>{
    const r=t.exit_avg?100*(t.exit_avg-t.entry_avg)/t.entry_avg:null;
    return '<tr><td><b>'+t.ticker+'</b></td><td>'+(t.entry_date||'—')+'</td><td>'+money(t.entry_avg)+'</td><td>'+(t.exit_date||'—')+'</td><td>'+money(t.exit_avg)+'</td>'+
      '<td class="'+(r==null?'':r>=0?'pos':'neg')+'">'+pct(r)+'</td><td>'+days(t.entry_date,t.exit_date)+'</td><td>'+(t.strategy||'—')+'</td><td>'+(t.exit_reason||'—')+'</td>'+
      '<td>'+(userRole==='owner'?'<button class="btn secondary" data-edit-trade="'+t.id+'">Edit</button> <button class="btn danger" data-delete-trade="'+t.id+'">Delete</button>':'')+'</td></tr>';
  }).join(''):'<tr><td colspan="10" class="muted">No trades yet.</td></tr>';
}

async function loadAccountData(){
  try{
    const [h,t]=await Promise.all([
      sb.from('holdings').select('*').order('created_at'),
      sb.from('trades').select('*').order('entry_date',{ascending:false})
    ]);
    if(h.error) throw h.error;
    if(t.error) throw t.error;
    window.__holdings=h.data||[];
    window.__trades=t.data||[];
    renderHoldings(window.__holdings);
    renderTrades(window.__trades);
  }catch(e){
    console.error(e);
    $('holdings').innerHTML='<div class="notice muted">Holdings temporarily unavailable.</div>';
    $('trades').innerHTML='<tr><td colspan="10" class="muted">Trades temporarily unavailable.</td></tr>';
  }
}

async function enterApp(){
  const email=session?.user?.email;
  if(!email){showLogin();return;}
  const {data:member,error}=await sb.from('app_members').select('role,display_name').eq('email',email).maybeSingle();
  if(error||!member){showLogin('This email is not approved for this dashboard.');return;}
  userRole=member.role||'viewer';
  $('roleBadge').textContent=userRole.toUpperCase();
  if(userRole==='owner'){
    $('addHoldingBtn').classList.remove('hidden');
    $('addTradeBtn').classList.remove('hidden');
  }
  showApp();
  renderMarket();
  await Promise.allSettled([refreshMarketSnapshot(),loadAccountData(),refreshLiveQuotes()]);
}

async function sendMagicLink(){
  const email=$('loginEmail').value.trim();
  if(!email){$('loginMsg').textContent='Enter your email.';return;}
  $('loginBtn').disabled=true;
  $('loginMsg').textContent='Sending…';
  try{
    const {error}=await sb.auth.signInWithOtp({email,options:{emailRedirectTo:location.origin+location.pathname}});
    if(error)throw error;
    $('loginMsg').textContent='Check your email for the sign-in link.';
  }catch(e){
    $('loginMsg').textContent=e.message||'Unable to send sign-in link.';
  }finally{
    $('loginBtn').disabled=false;
  }
}

function openHoldingForm(h={}){
  $('editor').classList.remove('hidden');
  $('editor').innerHTML='<h2>'+(h.id?'Edit':'Add')+' Holding</h2><div class="formgrid">'+
    '<div><label>Ticker</label><input id="hTicker" value="'+(h.ticker||'')+'"></div>'+
    '<div><label>Entry date</label><input id="hDate" type="date" value="'+(h.entry_date||'')+'"></div>'+
    '<div><label>Entry avg</label><input id="hAvg" type="number" step="0.01" value="'+(h.entry_avg||'')+'"></div>'+
    '<div><label>Strategy</label><input id="hStrategy" value="'+(h.strategy||'')+'"></div></div>'+
    '<label>Notes</label><textarea id="hNotes">'+(h.notes||'')+'</textarea>'+
    '<div class="actions" style="margin-top:12px"><button id="saveHoldingBtn" class="btn">Save</button><button id="cancelEditorBtn" class="btn secondary">Cancel</button></div>';
  $('saveHoldingBtn').onclick=()=>saveHolding(h.id||'');
  $('cancelEditorBtn').onclick=()=>$('editor').classList.add('hidden');
  $('editor').scrollIntoView({behavior:'smooth'});
}

async function saveHolding(id){
  const payload={ticker:$('hTicker').value.trim().toUpperCase(),entry_date:$('hDate').value||null,entry_avg:$('hAvg').value?Number($('hAvg').value):null,strategy:$('hStrategy').value||null,notes:$('hNotes').value||null,updated_at:new Date().toISOString()};
  const q=id?sb.from('holdings').update(payload).eq('id',id):sb.from('holdings').insert(payload);
  const {error}=await q;
  if(error){alert(error.message);return;}
  $('editor').classList.add('hidden');
  await loadAccountData();
}

function openTradeForm(t={}){
  $('editor').classList.remove('hidden');
  $('editor').innerHTML='<h2>'+(t.id?'Edit':'Add')+' Trade</h2><div class="formgrid">'+
    '<div><label>Ticker</label><input id="tTicker" value="'+(t.ticker||'')+'"></div>'+
    '<div><label>Strategy</label><input id="tStrategy" value="'+(t.strategy||'')+'"></div>'+
    '<div><label>Entry date</label><input id="tEntryDate" type="date" value="'+(t.entry_date||'')+'"></div>'+
    '<div><label>Entry avg</label><input id="tEntryAvg" type="number" step="0.01" value="'+(t.entry_avg||'')+'"></div>'+
    '<div><label>Exit date</label><input id="tExitDate" type="date" value="'+(t.exit_date||'')+'"></div>'+
    '<div><label>Exit avg</label><input id="tExitAvg" type="number" step="0.01" value="'+(t.exit_avg||'')+'"></div></div>'+
    '<label>Exit reason</label><input id="tReason" value="'+(t.exit_reason||'')+'"><label>Notes</label><textarea id="tNotes">'+(t.notes||'')+'</textarea>'+
    '<div class="actions" style="margin-top:12px"><button id="saveTradeBtn" class="btn">Save</button><button id="cancelEditorBtn" class="btn secondary">Cancel</button></div>';
  $('saveTradeBtn').onclick=()=>saveTrade(t.id||'');
  $('cancelEditorBtn').onclick=()=>$('editor').classList.add('hidden');
  $('editor').scrollIntoView({behavior:'smooth'});
}

async function saveTrade(id){
  const payload={ticker:$('tTicker').value.trim().toUpperCase(),entry_date:$('tEntryDate').value,entry_avg:Number($('tEntryAvg').value),exit_date:$('tExitDate').value||null,exit_avg:$('tExitAvg').value?Number($('tExitAvg').value):null,strategy:$('tStrategy').value||null,exit_reason:$('tReason').value||null,notes:$('tNotes').value||null,updated_at:new Date().toISOString()};
  const q=id?sb.from('trades').update(payload).eq('id',id):sb.from('trades').insert(payload);
  const {error}=await q;
  if(error){alert(error.message);return;}
  $('editor').classList.add('hidden');
  await loadAccountData();
}

async function fetchJson(url,timeoutMs=6000){
  const ctl=new AbortController();
  const timer=setTimeout(()=>ctl.abort(),timeoutMs);
  try{
    const r=await fetch(url,{cache:'no-store',signal:ctl.signal});
    if(!r.ok)throw new Error(url+' '+r.status);
    return await r.json();
  }finally{clearTimeout(timer);}
}

async function refreshLiveQuotes(){
  try{
    const symbols=(market.watchlist||[]).map(s=>s.ticker);
    if(!symbols.length)return;
    const url='https://rrxfqwfnubipbmoyoewj.supabase.co/functions/v1/market-quotes?symbols='+encodeURIComponent(symbols.join(','))+'&t='+Date.now();
    const ctl=new AbortController();
    const timer=setTimeout(()=>ctl.abort(),12000);
    let data;
    try{
      const r=await fetch(url,{cache:'no-store',signal:ctl.signal,headers:{'Accept':'application/json'}});
      if(!r.ok)throw new Error('Live endpoint HTTP '+r.status);
      data=await r.json();
    }finally{
      clearTimeout(timer);
    }
    const ok=(data?.quotes||[]).filter(q=>q&&q.symbol&&!q.error);
    if(!ok.length)throw new Error('No live quotes returned');
    liveQuotes=Object.fromEntries(ok.map(q=>[q.symbol,q]));
    liveFetchedAt=data.fetchedAt||new Date().toISOString();
    renderMarket();
    if(window.__holdings)renderHoldings(window.__holdings);
  }catch(e){
    console.warn('Live quote refresh failed',e);
    const header=$('marketAsOf');
    if(header&&!header.textContent.includes('Live quote error')){
      header.textContent += ' · Live quote error';
    }
  }
}

async function refreshMarketSnapshot(){
  let fresh=null;
  try{
    fresh=await fetchJson('./data.json?v='+Date.now(),5000);
  }catch(localErr){
    console.warn('Pages data.json refresh failed',localErr);
  }
  if(!fresh||!Array.isArray(fresh.watchlist)){
    try{
      fresh=await fetchJson('https://raw.githubusercontent.com/clayton141/ai-investment-dashboard/main/data.json?v='+Date.now(),7000);
    }catch(rawErr){
      console.warn('Raw GitHub data refresh failed',rawErr);
    }
  }
  if(fresh&&Array.isArray(fresh.watchlist)){
    market=fresh;
    renderMarket();
    if(window.__holdings)renderHoldings(window.__holdings);
  }
}

async function init(){
  renderMarket();
  $('loginBtn').addEventListener('click',sendMagicLink);
  $('logoutBtn').addEventListener('click',async()=>{if(sb)await sb.auth.signOut();showLogin();});
  $('addHoldingBtn').addEventListener('click',()=>openHoldingForm());
  $('addTradeBtn').addEventListener('click',()=>openTradeForm());
  document.addEventListener('click',async e=>{
    const el=e.target;
    if(el.dataset.editHolding){openHoldingForm((window.__holdings||[]).find(x=>x.id===el.dataset.editHolding)||{});}
    if(el.dataset.editTrade){openTradeForm((window.__trades||[]).find(x=>x.id===el.dataset.editTrade)||{});}
    if(el.dataset.deleteHolding&&confirm('Delete holding?')){const {error}=await sb.from('holdings').delete().eq('id',el.dataset.deleteHolding);if(error)alert(error.message);else loadAccountData();}
    if(el.dataset.deleteTrade&&confirm('Delete trade?')){const {error}=await sb.from('trades').delete().eq('id',el.dataset.deleteTrade);if(error)alert(error.message);else loadAccountData();}
  });

  if(!window.supabase||!window.SUPABASE_URL||!window.SUPABASE_ANON_KEY){
    showLogin('Login service failed to load. Refresh and try again.');
    return;
  }
  sb=window.supabase.createClient(window.SUPABASE_URL,window.SUPABASE_ANON_KEY);
  const {data,error}=await sb.auth.getSession();
  if(error){showLogin(error.message);return;}
  session=data.session;
  if(session)await enterApp();else showLogin();
  sb.auth.onAuthStateChange(async(_event,s)=>{
    session=s;
    if(s)await enterApp();else showLogin();
  });
  refreshMarketSnapshot();
  refreshLiveQuotes();
  setInterval(refreshMarketSnapshot,300000);
  setInterval(refreshLiveQuotes,30000);
  window.addEventListener('focus',refreshLiveQuotes);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshLiveQuotes();});
}

document.addEventListener('DOMContentLoaded',init);
