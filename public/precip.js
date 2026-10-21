import { apiUrl } from './api-client.js';

const $ = selector => document.querySelector(selector);
const precipState = {visible: false, today: null, date: null, forecast: null, october: null,
                     period: 'all', method: 'amount', selectedYear: null, hourDay: null,
                     forecastRequest: 0, octoberRequest: 0};
const PALETTE = {teal:'#4dd7c1', violet:'#b2a4ff', lime:'#b8f178', amber:'#ffc779',
                 grid:'#2a4350', muted:'#8aabba', text:'#e8f5f5'};
const number = (value, places=1) => value == null ? '—' : Number(value).toFixed(places).replace('.', ',');

async function getJSON(path) {
  const response = await fetch(apiUrl(path), {cache:'no-store'});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Dati nav pieejami.');
  return data;
}
function canvasContext(canvas) {
  const width = canvas.clientWidth, height = canvas.clientHeight;
  if (!width || !height) return null;
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * pixelRatio);
  canvas.height = Math.round(height * pixelRatio);
  const ctx = canvas.getContext('2d');
  ctx.scale(pixelRatio, pixelRatio);
  ctx.clearRect(0,0,width,height);
  ctx.font = '11px DM Mono, monospace';
  ctx.lineWidth = 1;
  return {ctx,width,height,left:48,right:width-32,top:24,bottom:height-34};
}
function grid(g, maximum, count=4, rightAxis=false) {
  const {ctx,left,right,top,bottom} = g;
  ctx.textAlign='right';ctx.textBaseline='middle';
  for(let i=0;i<=count;i++){
    const y=bottom-(bottom-top)*i/count;
    ctx.strokeStyle=PALETTE.grid;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
    ctx.fillStyle=PALETTE.muted;ctx.fillText(number(maximum*i/count,maximum<=5?1:0),left-8,y);
    if(rightAxis){ctx.textAlign='left';ctx.fillText(`${Math.round(i/count*100)}%`,right+5,y);ctx.textAlign='right';}
  }
}
function hourLabels(g){
  const {ctx,left,right,bottom}=g;ctx.textAlign='center';ctx.fillStyle=PALETTE.muted;ctx.textBaseline='top';
  for(let hour of [0,6,12,18,23])ctx.fillText(String(hour).padStart(2,'0'),left+(hour+.5)*(right-left)/24,bottom+8);
}
function dayLabels(g){
  const {ctx,left,right,bottom}=g;ctx.textAlign='center';ctx.fillStyle=PALETTE.muted;ctx.textBaseline='top';
  for(let day of [1,5,10,15,20,25,31])ctx.fillText(`${day}.`,left+(day-.5)*(right-left)/31,bottom+8);
}
function forecastDraw(){
  const data=precipState.forecast,g=canvasContext($('#precipForecastChart'));
  if(!data||!g)return;
  const {ctx,left,right,top,bottom}=g;
  const maximum=Math.max(1,...data.hourlyAmount.map(point=>point[1]),...data.actual.map(point=>point[1]||0))*1.14;
  grid(g,maximum,4,true);hourLabels(g);
  const slot=(right-left)/24;
  for(let hour=0;hour<24;hour++){
    const x=left+hour*slot;
    const amount=data.hourlyAmount[hour][1],actual=data.actual[hour][1];
    ctx.fillStyle=PALETTE.violet;
    ctx.fillRect(x+slot*.13,bottom-amount/maximum*(bottom-top),slot*.33,amount/maximum*(bottom-top));
    if(actual!=null){ctx.fillStyle=PALETTE.lime;ctx.fillRect(x+slot*.54,bottom-actual/maximum*(bottom-top),slot*.33,actual/maximum*(bottom-top));}
  }
  ctx.strokeStyle=PALETTE.teal;ctx.lineWidth=2.6;ctx.beginPath();
  data.hourlyProbability.forEach(([_,probability],hour)=>{
    const x=left+(hour+.5)*slot,y=bottom-probability*(bottom-top);
    hour?ctx.lineTo(x,y):ctx.moveTo(x,y);
  });ctx.stroke();
  ctx.fillStyle=PALETTE.muted;ctx.font='10px DM Mono, monospace';ctx.textAlign='left';ctx.fillText('mm',left,12);
  ctx.textAlign='right';ctx.fillText('analogu daļa',right,12);
}
function selectedMatch(){return precipState.october?.matches.find(match=>match.year===precipState.selectedYear)||null;}
function monthDay(match, day, data){
  if(!match)return null;
  if(day<=data.endDay){const index=data.comparisonDays.indexOf(day);return index<0?null:match.comparisonDays[index];}
  return match.continuationDays[day-data.endDay-1]||null;
}
function dailyDraw(){
  const data=precipState.october,match=selectedMatch(),g=canvasContext($('#precipDailyChart'));
  if(!data||!g)return;
  const {ctx,left,right,top,bottom}=g;
  const target=Array.from({length:31},(_,i)=>data.targetDays[i]?data.targetDays[i].reduce((a,b)=>a+b,0):null);
  const historic=Array.from({length:31},(_,i)=>{const values=monthDay(match,i+1,data);return values?values.reduce((a,b)=>a+b,0):null;});
  const maximum=Math.max(1,...target.filter(v=>v!=null),...historic.filter(v=>v!=null))*1.15;
  grid(g,maximum);dayLabels(g);
  const slot=(right-left)/31;
  ctx.fillStyle='#b2a4ff0d';ctx.fillRect(left+data.endDay*slot,top,right-left-data.endDay*slot,bottom-top);
  ctx.setLineDash([4,4]);ctx.strokeStyle='#8d7fc2';ctx.beginPath();ctx.moveTo(left+data.endDay*slot,top);ctx.lineTo(left+data.endDay*slot,bottom);ctx.stroke();ctx.setLineDash([]);
  for(let i=0;i<31;i++){
    const x=left+i*slot;
    if(target[i]!=null){ctx.fillStyle=PALETTE.teal;ctx.fillRect(x+slot*.12,bottom-target[i]/maximum*(bottom-top),slot*.34,target[i]/maximum*(bottom-top));}
    if(historic[i]!=null){ctx.fillStyle=i>=data.endDay?'#ffc77999':PALETTE.amber;ctx.fillRect(x+slot*.53,bottom-historic[i]/maximum*(bottom-top),slot*.34,historic[i]/maximum*(bottom-top));}
  }
}
function cumulative(values, startDay){
  let total=0,complete=true;
  return values.map((day,index)=>{
    if(index+1<startDay)return null;
    if(!day)complete=false;
    if(!complete)return null;
    total+=day.reduce((a,b)=>a+b,0);
    return total;
  });
}
function cumulativeDraw(){
  const data=precipState.october,match=selectedMatch(),g=canvasContext($('#precipCumulativeChart'));
  if(!data||!g)return;
  const {ctx,left,right,top,bottom}=g;
  const targetDays=Array.from({length:31},(_,i)=>data.targetDays[i]||null);
  const historicDays=Array.from({length:31},(_,i)=>monthDay(match,i+1,data));
  const target=cumulative(targetDays,data.startDay),historic=cumulative(historicDays,data.startDay);
  const maximum=Math.max(1,...target.filter(v=>v!=null),...historic.filter(v=>v!=null))*1.14;
  grid(g,maximum);dayLabels(g);
  const slot=(right-left)/31;
  ctx.fillStyle='#b2a4ff0d';ctx.fillRect(left+data.endDay*slot,top,right-left-data.endDay*slot,bottom-top);
  const draw=(values,color,start,end,dashed)=>{
    ctx.strokeStyle=color;ctx.lineWidth=2.8;ctx.setLineDash(dashed?[6,5]:[]);ctx.beginPath();let started=false;
    for(let i=start;i<end;i++){
      if(values[i]==null){started=false;continue;}
      const x=left+(i+.5)*slot,y=bottom-values[i]/maximum*(bottom-top);
      started?ctx.lineTo(x,y):ctx.moveTo(x,y);started=true;
    }ctx.stroke();ctx.setLineDash([]);
  };
  draw(target,PALETTE.teal,0,data.endDay,false);
  draw(historic,PALETTE.amber,0,data.endDay,false);
  if(match)draw(historic,PALETTE.amber,Math.max(0,data.endDay-1),31,true);
}
function hourlyDraw(){
  const data=precipState.october,match=selectedMatch(),g=canvasContext($('#precipHourlyChart'));
  if(!data||!g)return;
  const day=precipState.hourDay||data.comparisonDays.at(-1);
  const target=data.targetDays[day-1]||null,historic=monthDay(match,day,data);
  const {ctx,left,right,top,bottom}=g;
  const maximum=Math.max(1,...(target||[]),...(historic||[]))*1.15;
  grid(g,maximum);hourLabels(g);
  const slot=(right-left)/24;
  for(let i=0;i<24;i++){
    const x=left+i*slot;
    if(target){ctx.fillStyle=PALETTE.teal;ctx.fillRect(x+slot*.12,bottom-target[i]/maximum*(bottom-top),slot*.34,target[i]/maximum*(bottom-top));}
    if(historic){ctx.fillStyle=day>data.endDay?'#ffc77999':PALETTE.amber;ctx.fillRect(x+slot*.53,bottom-historic[i]/maximum*(bottom-top),slot*.34,historic[i]/maximum*(bottom-top));}
  }
  if(day>data.endDay){ctx.fillStyle=PALETTE.amber;ctx.textAlign='right';ctx.fillText('VĒSTURISKAIS TURPINĀJUMS',right,13);}
  if((target||[]).every(value=>value===0) && (historic||[]).every(value=>value===0) && (target||historic)){
    ctx.fillStyle=PALETTE.muted;ctx.textAlign='center';ctx.textBaseline='middle';
    ctx.fillText('Abās pilnajās dienās: 0,0 mm', (left+right)/2, (top+bottom)/2);
  }
}
function drawAll(){if(!precipState.visible)return;forecastDraw();dailyDraw();cumulativeDraw();hourlyDraw();}
function renderForecast(data){
  $('#precipChance').textContent=`${number(data.dailyRainProbability*100,0)}%`;
  $('#precipExpected').textContent=`${number(data.expectedTotalMm,1)} mm`;
  $('#precipScenarios').textContent=`${number(data.totalScenariosMm.p10,1)}–${number(data.totalScenariosMm.p90,1)} mm`;
  $('#precipForecastStatus').textContent=`${data.inputDate} → ${data.forecastDate} · ${data.observedHours}/24 faktiskās stundas · līdz šim ${number(data.observedTotalMm,1)} mm · ${data.candidatePairs} pilni vēsturiskie pāri. Scenāriju mediāna ${number(data.totalScenariosMm.p50,1)} mm.`;
  $('#precipForecastMatches').innerHTML=`<ul>${data.matches.map((match,i)=>`<li>${String(i+1).padStart(2,'0')} · ${match.date} · ievade ${number(match.inputTotalMm,1)} mm → turpinājums ${number(match.continuationTotalMm,1)} mm</li>`).join('')}</ul>`;
  drawAll();
}
async function loadForecast(day){
  const request=++precipState.forecastRequest;precipState.date=day;
  $('#precipDate').value=day;$('#precipForecastStatus').textContent='Aprēķina HPRAB analogus…';
  try{
    const data=await getJSON(`/api/precipitation/forecast?date=${encodeURIComponent(day)}`);
    if(request!==precipState.forecastRequest)return;
    precipState.forecast=data;renderForecast(data);
  }catch(error){if(request!==precipState.forecastRequest)return;precipState.forecast=null;$('#precipForecastStatus').textContent=error.message;drawAll();}
}
function renderOctober(data){
  $('#precipWindow').textContent=`${data.startDay}.–${data.endDay}.10.${data.targetYear} · ${data.comparisonDays.length} pilnas salīdzināmas dienas`;
  $('#precipCandidates').textContent=`${data.candidateYears} Rīgas LU oktobri · HPRAB`;
  document.querySelectorAll('[data-precip-period]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.precipPeriod===data.period)));
  document.querySelectorAll('[data-precip-method]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.precipMethod===data.method)));
  const labels={amount:'Dienu summa un visa posma kopējais daudzums (mm/dienā)',episodes:'Slapjo stundu un epizožu atšķirība',rhythm:'Slapjo/sauso dienu secības atšķirība'};
  $('#precipMatches').innerHTML=data.matches.length?data.matches.map((match,i)=>`<button type="button" class="october-match" data-precip-year="${match.year}" aria-pressed="${match.year===precipState.selectedYear}" style="--analog-color:#ffc779"><span class="october-match-bar"></span><span class="october-match-rank">${String(i+1).padStart(2,'0')}</span><span><strong class="october-match-year">${match.year}</strong><span class="october-match-detail">Daudzums ${number(match.methodScores.amount,2)} mm/d · epizodes ${number(match.methodScores.episodes,3)}<br>Ritms ${number(match.methodScores.rhythm,3)} · turpinājumā ${match.completeContinuationDays}/${31-data.endDay} pilnas dienas</span></span><span class="october-match-score">${number(match.score,data.method==='amount'?2:3)}<small>vērtējums</small></span></button>`).join(''):'<p class="loading">Šim posmam nav pilnu vēsturisku oktobru.</p>';
  $('#precipMethodExplanation').textContent=`${labels[data.method]}. Nokrišņu epizode sākas pie ≥0,1 mm stundā; slapja diena ir ≥1 mm. HPRAB neatšķir lietu no sniega. Mazāks vērtējums nozīmē lielāku līdzību. Vērtē tikai izvēlētā perioda vienādās pilnās kalendāra dienas; vēlākais turpinājums rangā nepiedalās. Nokrišņu dati neveido temperatūras prognozi.`;
  const options=[...data.comparisonDays,...Array.from({length:31-data.endDay},(_,i)=>data.endDay+i+1)];
  if(!options.includes(precipState.hourDay))precipState.hourDay=data.comparisonDays.at(-1);
  $('#precipHourDay').innerHTML=options.map(day=>`<option value="${day}" ${day===precipState.hourDay?'selected':''}>${day}. oktobris${day>data.endDay?' · turpinājums':''}</option>`).join('');
  drawAll();
}
async function loadOctober(period,method){
  const request=++precipState.octoberRequest;
  precipState.period=period;precipState.method=method;precipState.selectedYear=null;
  $('#precipWindow').textContent='Pārrēķina nokrišņu analogus…';
  try{
    const data=await getJSON(`/api/precipitation/october?period=${encodeURIComponent(period)}&method=${encodeURIComponent(method)}`);
    if(request!==precipState.octoberRequest)return;
    precipState.october=data;precipState.selectedYear=data.matches[0]?.year||null;
    renderOctober(data);
  }catch(error){if(request!==precipState.octoberRequest)return;precipState.october=null;$('#precipWindow').textContent=error.message;$('#precipMatches').innerHTML='';drawAll();}
}
function setMode(precipitation){
  precipState.visible=precipitation;
  $('#temperatureShell').hidden=precipitation;
  $('#precipitationShell').hidden=!precipitation;
  $('#modeTemperature').setAttribute('aria-pressed',String(!precipitation));
  $('#modePrecipitation').setAttribute('aria-pressed',String(precipitation));
  if(precipitation){if(!precipState.today)initializePrecip();else drawAll();}
}
async function initializePrecip(){
  try{
    const status=await getJSON('/api/status');
    precipState.today=status.today;$('#precipDate').max=status.today;
    if(status.snapshotFirstPrecipDate)$('#precipDate').min=status.snapshotFirstPrecipDate;
    await Promise.allSettled([loadForecast(status.today),loadOctober('all','amount')]);
  }catch(error){$('#precipForecastStatus').textContent=error.message;}
}
$('#modeTemperature').addEventListener('click',()=>setMode(false));
$('#modePrecipitation').addEventListener('click',()=>setMode(true));
$('#precipDate').addEventListener('change',event=>{if(event.target.value)loadForecast(event.target.value);});
$('#precipToday').addEventListener('click',()=>{if(precipState.today)loadForecast(precipState.today);});
document.querySelector('[data-precip-period]').parentElement.addEventListener('click',event=>{
  const button=event.target.closest('[data-precip-period]');if(button&&button.dataset.precipPeriod!==precipState.period)loadOctober(button.dataset.precipPeriod,precipState.method);
});
document.querySelector('[data-precip-method]').parentElement.addEventListener('click',event=>{
  const button=event.target.closest('[data-precip-method]');if(button&&button.dataset.precipMethod!==precipState.method)loadOctober(precipState.period,button.dataset.precipMethod);
});
$('#precipMatches').addEventListener('click',event=>{
  const button=event.target.closest('[data-precip-year]');if(!button)return;
  precipState.selectedYear=Number(button.dataset.precipYear);renderOctober(precipState.october);
});
$('#precipHourDay').addEventListener('change',event=>{precipState.hourDay=Number(event.target.value);hourlyDraw();});
new ResizeObserver(drawAll).observe($('#precipitationShell'));
setInterval(()=>{if(precipState.visible&&precipState.today){loadForecast(precipState.date);loadOctober(precipState.period,precipState.method);}},600000);
