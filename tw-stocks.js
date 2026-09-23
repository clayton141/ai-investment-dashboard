'use strict';

(function(){
  let twData={watchlist:[]};
  let twQuotes={};
  let lastLive=null;

  const $=id=>document.getElementById(id);
  const twd=n=>n==null?'—':'NT$'+Number(n).toLocaleString('zh-TW',{maximumFractionDigits:2});
  const pct=n=>n==null?'—':(Number(n)>0?'+':'')+Number(n).toFixed(2)+'%';
  const safe=n=>n==null?'—':Number(n).toFixed(1);

  function twClock(){
    const parts=new Intl.DateTimeFormat('en-US',{
      timeZone:'Asia/Taipei',
      hour12:false,weekday:'short',hour:'2-digit',minute:'2-digit'
    }).formatToParts(new Date());
    const m=Object.fromEntries(parts.map(p=>[p.type,p.value]));
    return {weekday:m.weekday,h:Number(m.hour),m:Number(m.minute)};
  }

  function isTwRegular(){
    const c=twClock();
    if(['Sat','Sun'].includes(c.weekday))return false;
    const mins=c.h*60+c.m;
    return mins>=540&&mins<810;
  }

  function render(){
    const box=$('twCards');
    const meta=$('twMarketAsOf');
    if(!box||!meta)return;

    const wl=Array.isArray(twData.watchlist)?twData.watchlist:[];
    const live=isTwRegular();
    meta.textContent='Taiwan market: '+(twData.asOf||'—')+
      (live?' · LIVE':' · CLOSED')+
      (lastLive?' · quotes '+new Date(lastLive).toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'');

    box.innerHTML=wl.length?wl.map(s=>{
      const q=twQuotes[s.ticker];
      const useLive=live&&q&&q.price!=null;
      const price=useLive?q.price:(q?.regularMarketPrice??s.price);
      const dp=useLive?q.changePct:(q?.regularMarketPct??s.dayPct);
      // Taiwan convention: up = red, down = green.
      const cls=dp>0?'neg':dp<0?'pos':'muted';
      const label=useLive?'<span class="pill">LIVE</span> ':'';
      return '<div class="card">'+
        '<div class="ticker">'+s.code+' <span class="small muted">'+s.name+'</span></div>'+
        '<div class="price">'+label+twd(price)+'</div>'+
        '<div class="'+cls+'">'+pct(dp)+'</div>'+
        '<div class="row"><span class="muted">RSI</span><b>'+safe(s.rsi14)+'</b></div>'+
        '<div class="row"><span class="muted">MA20/50/200</span><b>'+safe(s.ma20)+' / '+safe(s.ma50)+' / '+safe(s.ma200)+'</b></div>'+
        '<div class="row"><span class="muted">Market</span><b>'+s.market+'</b></div>'+
      '</div>';
    }).join(''):'<div class="notice muted">尚未加入台股。</div>';
  }

  async function loadStatic(){
    try{
      const r=await fetch('./tw-data.json?v='+Date.now(),{cache:'no-store'});
      if(!r.ok)throw new Error('tw-data '+r.status);
      twData=await r.json();
      render();
    }catch(e){
      console.warn('TW static data failed',e);
    }
  }

  async function loadLive(){
    try{
      const symbols=(twData.watchlist||[]).map(s=>s.ticker);
      if(!symbols.length)return;
      const url='https://rrxfqwfnubipbmoyoewj.supabase.co/functions/v1/market-quotes?symbols='+encodeURIComponent(symbols.join(','))+'&t='+Date.now();
      const ctl=new AbortController();
      const timer=setTimeout(()=>ctl.abort(),12000);
      let data;
      try{
        const r=await fetch(url,{cache:'no-store',signal:ctl.signal,headers:{Accept:'application/json'}});
        if(!r.ok)throw new Error('TW live HTTP '+r.status);
        data=await r.json();
      }finally{
        clearTimeout(timer);
      }
      const ok=(data?.quotes||[]).filter(q=>q&&q.symbol&&!q.error);
      if(ok.length){
        twQuotes=Object.fromEntries(ok.map(q=>[q.symbol,q]));
        lastLive=data.fetchedAt||new Date().toISOString();
        render();
      }
    }catch(e){
      console.warn('TW live data failed',e);
    }
  }

  async function start(){
    await loadStatic();
    await loadLive();
    setInterval(loadLive,30000);
    setInterval(loadStatic,300000);
    window.addEventListener('focus',loadLive);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)loadLive();});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);
  else start();
})();