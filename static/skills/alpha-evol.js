(()=>{
  // Alpha Evol module: exposes init and update
  const state = {chart:null, kchart:null, data:null, mobile:false}

  function formatRadarData(scores){
    const indicator = [
      {name:'技术分析',max:100},
      {name:'基本面',max:100},
      {name:'情绪分析',max:100},
      {name:'风险控制',max:100},
      {name:'执行力',max:100}
    ];
    const values = [scores.technical||0,scores.fundamental||0,scores.sentiment||0,scores.risk||0,scores.execution||0];
    return {indicator,values};
  }

  function initRadar(el, scores){
    const chart = echarts.init(el);
    const {indicator,values} = formatRadarData(scores);
    const option = {
      backgroundColor:'transparent',
      radar:{indicator,shape:'circle',splitNumber:4,axisName:{color:'#9aa9c0'},splitLine:{lineStyle:{color:'rgba(124,77,255,0.08)'}},splitArea:{show:false}},
      series:[{type:'radar',data:[{value:values,name:'能力'}],areaStyle:{color:'rgba(124,77,255,0.12)'},lineStyle:{color:'#7c4dff'},symbol:'circle'}]
    };
    chart.setOption(option);
    state.chart=chart;
  }

  function updateRadar(scores){
    if(!state.chart) return;
    const {values} = formatRadarData(scores);
    state.chart.setOption({series:[{data:[{value:values}]}]});
  }

  // Try to mount existing global K-line functions if available (dashboard.js style)
  function mountKline(kline){
    try{
      if(window.updateChart && typeof window.updateChart==='function'){
        window.updateChart(kline);
        return;
      }
    }catch(e){}
    // fallback: render simple ECharts candlestick if echarts available
    const el = document.getElementById('ae-kline'); if(!el) return;
    const chart = echarts.init(el);
    const dates = kline.map(d=>d[0]);
    const ohlc = kline.map(d=>[d[1],d[2],d[3],d[4]]); // [open,high,low,close]
    const option = {
      grid:{left:40,right:10,top:10,bottom:30},
      xAxis:{type:'category',data:dates,boundaryGap:false,axisLine:{lineStyle:{color:'#223'}}},
      yAxis:{scale:true,axisLine:{lineStyle:{color:'#223'}}},
      series:[{type:'candlestick',data:ohlc,itemStyle:{color:'#00ff9f',color0:'#ff5c7a',borderColor:'#00ff9f',borderColor0:'#ff5c7a'}}]
    };
    chart.setOption(option);
    state.kchart=chart;
  }

  function renderLog(list){
    const el = document.getElementById('ae-log'); if(!el) return;
    el.innerHTML='';
    (list||[]).slice(0,20).forEach(it=>{
      const d=document.createElement('div'); d.className='p-2 bg-[rgba(255,255,255,0.01)] rounded';
      d.innerHTML=`<div class="text-xs text-slate-300">${new Date(it.time).toLocaleString()}</div><div class="text-sm">${it.desc} <span class="text-xs text-slate-400">(${it.delta_exp>0? '+'+it.delta_exp+' EXP':it.delta_exp+' EXP'})</span></div>`;
      el.appendChild(d);
    });
  }

   function renderAnalysis(analysis){
     const s=document.getElementById('ae-analysis-summary'); if(s) s.textContent=analysis.summary||'';
     const signals=document.getElementById('ae-signals'); if(signals){
       signals.innerHTML=''; (analysis.signals||[]).forEach(sig=>{
         const el=document.createElement('div'); el.className='p-2 rounded mt-2 bg-[rgba(255,255,255,0.01)] text-sm';
         el.innerHTML=`<strong class="text-neon">${sig.type.toUpperCase()}</strong> ${sig.price || ''} <span class="text-xs text-slate-400">${sig.time||''}</span><div class="text-xs text-slate-300">${sig.note||''}</div>`;
         signals.appendChild(el);
       });
     }
     // Render K-line if data provided
     if(analysis.kline && analysis.kline.length > 0){
       const klineEl = document.getElementById('ae-kline');
       if(klineEl){
         // Try to use existing global chart update function
         try{
           if(window.updateChart && typeof window.updateChart==='function'){
             window.updateChart(analysis.kline);
             return;
           }
         }catch(e){}
         // Fallback: render simple ECharts candlestick
         const chart = echarts.init(klineEl);
         const dates = analysis.kline.map(d=>d[0]);
         const ohlc = analysis.kline.map(d=>[d[1],d[2],d[3],d[4]]); // [open,high,low,close]
         const option = {
           grid:{left:40,right:10,top:10,bottom:30},
           xAxis:{type:'category',data:dates,boundaryGap:false,axisLine:{lineStyle:{color:'#223'}}},
           yAxis:{scale:true,axisLine:{lineStyle:{color:'#223'}}},
           series:[{type:'candlestick',data:ohlc,itemStyle:{color:'#00ff9f',color0:'#ff5c7a',borderColor:'#00ff9f',borderColor0:'#ff5c7a'}}]
         };
         chart.setOption(option);
       }
     }
   }

  function renderExp(level,exp,exp_to_next,gain){
    const lvl=document.getElementById('ae-level'); if(lvl) lvl.textContent=`Lv. ${level}`;
    const bar=document.getElementById('ae-exp-bar'); if(bar){
      const w = exp_to_next? Math.max(4, Math.min(100, Math.round(exp/exp_to_next*100))):0;
      bar.style.width = w+'%';
    }
    const text=document.getElementById('ae-exp-text'); if(text) text.textContent = `${exp} / ${exp_to_next}`;
    const gainEl=document.getElementById('ae-exp-gain'); if(gainEl) gainEl.textContent = (gain? (gain>0? '+'+gain+' EXP':gain+' EXP') : '+0 EXP');
  }

  function updateAvatar(level){
    const img=document.getElementById('ae-avatar-img'); const wrap=document.getElementById('ae-avatar');
    if(!img||!wrap) return;
    const lvl = Math.max(1, Math.min(5, level||1));
    img.src = `/static/skills/avatar_lvl${lvl}.png`;
    if(lvl>=3) wrap.classList.add('evolved'); else wrap.classList.remove('evolved');
  }

  // simple particle background (very light)
  function startParticles(){
    if(state.mobile) return; // skip on mobile
    const c=document.getElementById('ae-particles'); if(!c) return; const ctx=c.getContext('2d');
    function resize(){c.width=c.clientWidth;c.height=c.clientHeight}
    resize(); window.addEventListener('resize',resize);
    const particles=[]; for(let i=0;i<30;i++) particles.push({x:Math.random()*c.width,y:Math.random()*c.height,r:Math.random()*1.6,dx:(Math.random()-0.5)*0.3,dy:(Math.random()-0.5)*0.3});
    let rafId=null; function tick(){ctx.clearRect(0,0,c.width,c.height); particles.forEach(p=>{p.x+=p.dx; p.y+=p.dy; if(p.x<0) p.x=c.width; if(p.x>c.width) p.x=0; if(p.y<0) p.y=c.height; if(p.y>c.height) p.y=0; ctx.fillStyle='rgba(124,77,255,0.9)'; ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2); ctx.fill();}); rafId=requestAnimationFrame(tick);} tick();
    document.addEventListener('visibilitychange',()=>{ if(document.hidden){ cancelAnimationFrame(rafId);} else { tick(); } });
  }

  window.initAlphaEvol = function(containerSelector, jsonData){
    // jsonData may contain config.mobile to force mobile mode
    if(jsonData && jsonData.config && jsonData.config.mobile) state.mobile = true;
    const root = typeof containerSelector==='string'? document.querySelector(containerSelector):containerSelector;
    if(!root) root = document.getElementById('alpha-evol-root');
    // init radar
    const radarEl = document.getElementById('ae-radar'); if(radarEl) initRadar(radarEl, jsonData.ability_scores||{});
    renderLog(jsonData.evolution_log||[]);
    renderAnalysis(jsonData.analysis||{});
    // Update meta info
    const metaEl = document.getElementById('ae-meta');
    if (metaEl) {
      metaEl.textContent = `${jsonData.symbol || '--'} · ${new Date(jsonData.timestamp || Date.now()).toLocaleString()}`;
    }
    renderExp(jsonData.level||1,jsonData.exp||0,jsonData.exp_to_next||100,jsonData.gain||0);
    updateAvatar(jsonData.level||1);
    startParticles();
    state.data=jsonData;
  }

  window.updateAlphaEvol = function(jsonData){
    state.data = Object.assign({}, state.data, jsonData);
    if(jsonData.ability_scores) updateRadar(jsonData.ability_scores);
    if(jsonData.level || jsonData.exp) renderExp(state.data.level, state.data.exp, state.data.exp_to_next, jsonData.gain);
    if(jsonData.evolution_log) renderLog(state.data.evolution_log||[]);
    if(jsonData.analysis) renderAnalysis(state.data.analysis||{});
    if(jsonData.symbol || jsonData.timestamp) {
      const metaEl = document.getElementById('ae-meta');
      if (metaEl) {
        metaEl.textContent = `${state.data.symbol || '--'} · ${new Date(state.data.timestamp || Date.now()).toLocaleString()}`;
      }
    }
    if(jsonData.level) updateAvatar(state.data.level);
  }

})();
// Alpha Evol frontend logic — init, fetch data, render ECharts radar and UI
(function(){
  function fmtPct(v){ return Math.round(v*100) + '%'; }

  function createRadarOption(scores){
    return {
      backgroundColor: 'transparent',
      tooltip: {},
      radar: {
        indicator: [
          { name: '技术分析', max: 1 },
          { name: '基本面', max: 1 },
          { name: '情绪分析', max: 1 },
          { name: '风险控制', max: 1 },
          { name: '执行力', max: 1 }
        ],
        shape: 'circle',
        axisLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
        splitLine: { lineStyle: { color: 'rgba(255,255,255,0.03)' } },
        splitArea: { areaStyle: { color: ['transparent'] } }
      },
      series: [{
        name: '能力雷达',
        type: 'radar',
        data: [{ value: [scores.technical, scores.fundamental, scores.sentiment, scores.risk_control, scores.execution], name: 'Alpha' }],
        areaStyle: { color: 'rgba(124,58,237,0.18)' },
        lineStyle: { color: '#7c3aed' },
        symbolSize:8
      }]
    };
  }

  function render(data, root){
    // Avatar and level
    const avatar = root.querySelector('#ae-avatar');
    const level = root.querySelector('#ae-level');
    const expBar = root.querySelector('#ae-exp-bar');
    const expLabel = root.querySelector('#ae-exp-label');
    const updated = root.querySelector('#ae-updated');

    level.textContent = 'Lv.' + data.level;
    const pct = Math.min(100, Math.round(data.exp / Math.max(1,data.exp_next) * 100));
    expBar.style.width = pct + '%';
    expLabel.textContent = `${data.exp} / ${data.exp_next}`;
    updated.textContent = new Date().toLocaleString();

    // avatar selection by level buckets
    let bucket = 'lv1';
    if(data.level >= 10) bucket = 'lv10';
    else if(data.level >=5) bucket = 'lv5';
    const src = `/static/skills/images/avatar_${bucket}.svg`;
    avatar.src = src;
    if(data.level >= 5) avatar.classList.add('evolved');

    // Radar
    const radarDom = root.querySelector('#ae-radar');
    const radar = echarts.init(radarDom);
    radar.setOption(createRadarOption(data.ability_scores));

    // Evolution log
    const log = root.querySelector('#ae-log'); log.innerHTML = '';
    (data.evolution_log||[]).slice(0,8).forEach(item=>{
      const li = document.createElement('li');
      li.innerHTML = `<div class="text-xs text-gray-400">${new Date(item.ts).toLocaleString()}</div><div class="text-sm">${item.note}</div>`;
      log.appendChild(li);
    });

    // Analysis
    root.querySelector('#ae-title').textContent = data.analysis.title || '分析结果';
    root.querySelector('#ae-summary').textContent = data.analysis.summary || '';
    const signals = root.querySelector('#ae-signals'); signals.innerHTML = '';
    (data.analysis.buy_signals||[]).forEach(s=>{
      const el = document.createElement('div'); el.className='p-3 bg-gradient-to-r from-blue-900/30 to-transparent rounded';
      el.innerHTML = `<div class="font-medium text-sm">买入 · ${s.type}</div><div class="text-xs text-gray-300">价格 ${s.price}  概率 ${Math.round(s.prob*100)}%</div>`;
      signals.appendChild(el);
    });
    (data.analysis.sell_signals||[]).forEach(s=>{
      const el = document.createElement('div'); el.className='p-3 bg-gradient-to-r from-red-900/20 to-transparent rounded';
      el.innerHTML = `<div class="font-medium text-sm">卖出 · ${s.type}</div><div class="text-xs text-gray-300">价格 ${s.price}  概率 ${Math.round(s.prob*100)}%</div>`;
      signals.appendChild(el);
    });
  }

  function load(root){
    const api = root.getAttribute('data-api') || '/static/skills/alpha-evol.sample.json';
    fetch(api).then(r=>r.json()).then(data=>render(data, root)).catch(err=>{
      console.error('AlphaEvol load error',err);
      root.querySelector('#ae-summary').textContent = '加载失败';
    });
  }

  window.AlphaEvol = {
    init(selector){
      const root = document.querySelector(selector||'#alpha-evol');
      if(!root) return;
      // lazy init when visible
      if('IntersectionObserver' in window){
        const io = new IntersectionObserver(entries=>{ if(entries[0].isIntersecting){ load(root); io.disconnect(); } },{threshold:0.1});
        io.observe(root);
      } else { load(root); }
    }
  };

  // auto init
  document.addEventListener('DOMContentLoaded', ()=>{ AlphaEvol.init('#alpha-evol'); });

})();
