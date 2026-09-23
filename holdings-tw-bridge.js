'use strict';

(function(){
  function moneyTW(n){
    return n==null?'—':'NT$'+Number(n).toLocaleString('zh-TW',{maximumFractionDigits:2});
  }
  function pct(n){
    return n==null?'—':(Number(n)>0?'+':'')+Number(n).toFixed(1)+'%';
  }
  function findTw(ticker){
    const tw=window.TW_DASHBOARD;
    const list=Array.isArray(tw?.data?.watchlist)?tw.data.watchlist:[];
    const raw=String(ticker||'').trim().toUpperCase();
    return list.find(s=>{
      const full=String(s.ticker||'').toUpperCase();
      const code=String(s.code||'').toUpperCase();
      const bare=full.replace(/\.(TW|TWO)$/,'');
      return raw===full||raw===code||raw===bare;
    })||null;
  }
  function twSnapshot(stock){
    const tw=window.TW_DASHBOARD;
    const q=tw?.quotes?.[stock.ticker];
    const live=Boolean(tw?.isRegular?.()&&q&&q.price!=null);
    return {
      price: live?q.price:(q?.regularMarketPrice??stock.price),
      dayPct: live?q.changePct:(q?.regularMarketPct??stock.dayPct),
      live
    };
  }
  function patch(){
    const root=document.getElementById('holdings');
    const list=window.__holdings;
    if(!root||!Array.isArray(list)||!list.length)return;

    const cards=[...root.querySelectorAll('.card')];
    cards.forEach((card,i)=>{
      const h=list[i];
      if(!h)return;
      const stock=findTw(h.ticker);
      if(!stock)return;

      const snap=twSnapshot(stock);
      const title=card.querySelector('.ticker');
      const price=card.querySelector('.price');

      if(title){
        title.innerHTML=(stock.code||h.ticker)+' <span class="small muted">'+(stock.name||'')+'</span> <span class="pill">HOLDING</span>';
      }
      if(price){
        price.innerHTML=(snap.live?'<span class="pill">LIVE</span> ':'')+moneyTW(snap.price);
      }

      // Remove any US PRE/AH rows accidentally rendered for Taiwan holdings.
      [...card.querySelectorAll('.premarket-row')].forEach(x=>x.remove());
      [...card.querySelectorAll('.row')].forEach(row=>{
        const t=row.textContent||'';
        if(t.includes('盤後')||t.includes('AH'))row.remove();
      });

      const rows=[...card.querySelectorAll('.row')];
      rows.forEach(row=>{
        const label=row.querySelector('.muted')?.textContent?.trim();
        const value=row.querySelector('b');
        if(label==='進場均價'&&value)value.textContent=moneyTW(h.entry_avg);
        if(label==='未實現'&&value){
          const u=h.entry_avg&&snap.price?100*(snap.price-h.entry_avg)/h.entry_avg:null;
          value.textContent=pct(u);
          value.classList.remove('pos','neg');
          if(u!=null)value.classList.add(u>=0?'pos':'neg');
        }
      });
    });
  }

  window.addEventListener('tw-market-updated',()=>setTimeout(patch,0));
  window.addEventListener('focus',()=>setTimeout(patch,0));

  function start(){
    patch();
    setInterval(patch,1000);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);
  else start();
})();