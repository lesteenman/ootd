/* The voyage map: arcs and days on the map of Thylea, linked into the wiki. Data: map.json. */
(function(){
  const ROOT = document.body.dataset.root || "";
  const SVGNS = "http://www.w3.org/2000/svg";
  const LS_KEY = "ootd-pins-v1";
  const $ = id => document.getElementById(id);
  const frame=$("mapFrame"), img=$("mapImg"), svg=$("routeSvg"), tip=$("tip"), panel=$("panel"),
        slider=$("slider"), readout=$("posReadout"), playBtn=$("play"), revealChk=$("reveal"),
        routeChk=$("showRoute"), editBtn=$("editBtn"), copyBtn=$("copyBtn"), resetBtn=$("resetBtn"),
        editHint=$("editHint"), placecard=$("placecard"), pinOut=$("pinOut"),
        segBtns=Array.from(document.querySelectorAll(".seg button"));
  const reduceMotion = matchMedia("(prefers-reduced-motion:reduce)").matches;
  const esc = s => String(s==null?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

  let D, PINS, ARCS, DAYIDX;
  let mode="session", si=0, di=0, editing=false, playing=false, timer=null, focusPlace=null;
  let moved = {};
  try{ moved = JSON.parse(localStorage.getItem(LS_KEY)) || {}; }catch(e){ moved = {}; }
  const markerEls = {};
  const px = id => moved[id] || PINS[id];
  const curMax = () => mode==="session" ? ARCS.length-1 : DAYIDX.length-1;
  const curIdx = () => mode==="session" ? si : di;

  fetch(ROOT + "map.json").then(r=>r.json()).then(init).catch(err=>{
    frame.innerHTML = '<p class="editHint">Could not load the map data ('+esc(err)+').</p>';
  });

  function init(data){
    D = data; PINS = data.pins; ARCS = data.arcs.filter(a=>a.pin);
    DAYIDX = buildDays(data.days);
    img.src = ROOT + data.image;
    Object.keys(PINS).forEach(addMarker);
    buildPanel();
    slider.max = curMax();
    const m = location.hash.match(/place=([\w-]+)/);
    if(m && PINS[m[1]]){
      focusPlace = m[1];
      const i = ARCS.findIndex(a=>a.pin===m[1]);
      if(i >= 0) si = i;
    }
    img.addEventListener("load", ()=>setPos(curIdx(), !!focusPlace));
    if(img.complete && img.naturalWidth) setPos(curIdx(), !!focusPlace);
    new ResizeObserver(drawRoute).observe(frame);
  }

  /* Thylea's calendar: loop I counts days 1–41; loop II is counted relative to day 0 (−5 … ),
     so the first days exist twice: we are in two places at once. */
  function buildDays(days){
    const by = {}, last = {1:null, 2:null};
    days.forEach(d=>{
      const wd = d.loop===2 ? d.rel : d.day;
      const pins = d.pins.length ? d.pins : (last[d.loop] ? [last[d.loop]] : []);
      if(pins.length) last[d.loop] = pins[pins.length-1];
      if(!pins.length) return;
      const e = by[wd] = by[wd] || {wd};
      e["l"+d.loop] = {pins, pin: pins[pins.length-1], d, moving: !d.pins.length};
    });
    return Object.values(by).sort((a,b)=>a.wd-b.wd);
  }

  /* ---------- markers ---------- */
  function addMarker(id){
    const p = PINS[id];
    const el = document.createElement("button");
    el.className = "marker " + (p.layer==="sea" ? "sea" : p.layer==="special" ? "special" : "");
    el.setAttribute("aria-label", p.name);
    place(el, id);
    el.addEventListener("mouseenter", ()=>showTip(id));
    el.addEventListener("mouseleave", hideTip);
    el.addEventListener("focus", ()=>showTip(id));
    el.addEventListener("blur", hideTip);
    el.addEventListener("click", ()=>{ if(!editing) markerClick(id); });
    enableDrag(el, id);
    frame.appendChild(el);
    markerEls[id] = el;
  }
  function place(el, id){ const p = px(id); el.style.left = p.x+"%"; el.style.top = p.y+"%"; }
  function showTip(id){
    const p = px(id);
    tip.textContent = PINS[id].name;
    tip.style.left = p.x+"%"; tip.style.top = p.y+"%";
    tip.classList.add("show");
  }
  function hideTip(){ tip.classList.remove("show"); }

  /* ---------- panel ---------- */
  function buildPanel(){ mode==="session" ? panelArcs() : panelDays(); }
  function loopHead(txt){
    return '<div class="loopHead"><span class="dot"></span><span class="txt label">'+txt+'</span><span class="rule"></span></div>';
  }
  function dayLabel(a){
    if(a.loop===2){
      const r = x=>x-47, f = x=>(x<0?"−"+(-x):x);
      return (a.dayStart===a.dayEnd ? "Day "+f(r(a.dayStart)) : "Days "+f(r(a.dayStart))+" to "+f(r(a.dayEnd))) +
        " · lived "+a.dayStart+(a.dayEnd!==a.dayStart?"–"+a.dayEnd:"");
    }
    return a.dayStart===a.dayEnd ? "Day "+a.dayStart : "Days "+a.dayStart+"–"+a.dayEnd;
  }
  function panelArcs(){
    let h = "", last = null;
    ARCS.forEach((a,i)=>{
      if(a.loop!==last){
        if(a.loop===2) h += '<div class="jump"><b>Khronos turns back the hourglass.</b> We are thrown back to day −5, five days before we first gathered at the Sour Vintage, to sail a second, secret voyage alongside the first.</div>';
        h += loopHead(a.loop===1 ? "Loop I · The first voyage" : "Loop II · Before the beginning");
        last = a.loop;
      }
      const ses = a.ses.map(s=>'<li><a class="sn" href="'+ROOT+s.url+'">S'+esc(s.n)+'</a><span>'+esc(s.t)+'</span></li>').join("");
      h += '<div class="leg" data-i="'+i+'" role="button" tabindex="0">'+
        '<div class="badge">'+(i+1)+'</div><div>'+
        '<div class="ttl display"><a href="'+ROOT+a.url+'">'+esc(a.title)+'</a></div>'+
        '<div class="meta"><span class="reg">'+esc(a.region)+'</span><span>'+dayLabel(a)+'</span></div>'+
        '<div class="body"><p class="blurb">'+esc(a.blurb)+'</p><ul class="ses">'+ses+'</ul></div></div></div>';
    });
    panel.innerHTML = h;
    wireRows(".leg", "i");
  }
  function locLine(cls, label, ref){
    const names = ref.d.places.length ? ref.d.places.join(" → ") : PINS[ref.pin].name + " (travelling)";
    return '<div class="loclabel"><span class="lbadge '+cls+'">'+label+'</span><span>'+
      '<span class="place">'+esc(names)+(ref.d.unsure?" ?":"")+'</span> '+
      '<span class="legttl">— <a href="'+ROOT+ref.d.url+'">'+esc(ref.d.summary)+'</a></span></span></div>';
  }
  function panelDays(){
    let h = '<div class="jump"><b>Thylea\'s calendar.</b> Days count from our first day (Session 1 = day 1). After Khronos we are thrown back to <b>day −5</b>, and our second voyage runs on into the days we had already lived, so on the first days we stand in two places at once; those rows show both loops.</div>';
    DAYIDX.forEach((d,i)=>{
      const lab = d.wd<0 ? "−"+(-d.wd) : d.wd;
      const sub = d.l2 ? '<small>lived '+d.l2.d.day+'</small>' : '<small>&nbsp;</small>';
      h += '<div class="dayrow'+(d.l1&&d.l2?" dual":"")+'" data-d="'+i+'" role="button" tabindex="0">'+
        '<div class="dnum">'+lab+sub+'</div><div class="locs">'+
        (d.l1 ? locLine("l1","Loop I",d.l1) : "") + (d.l2 ? locLine("l2","Loop II",d.l2) : "") + '</div></div>';
    });
    panel.innerHTML = h;
    wireRows(".dayrow", "d");
  }
  function wireRows(sel, key){
    panel.querySelectorAll(sel).forEach(el=>{
      const go = ()=>{ stopPlay(); focusPlace=null; setPos(+el.dataset[key], true); };
      el.addEventListener("click", e=>{ if(!e.target.closest("a")) go(); });
      el.addEventListener("keydown", e=>{ if((e.key==="Enter"||e.key===" ") && e.target===el){ e.preventDefault(); go(); } });
    });
  }

  /* ---------- selection ---------- */
  function setPos(v, scroll){
    v = Math.max(0, Math.min(curMax(), v));
    if(mode==="session") si = v; else di = v;
    slider.value = v;
    readoutUpdate(); highlight(scroll); updateMarkers(); drawRoute(); updatePlacecard();
  }
  function readoutUpdate(){
    if(mode==="session"){ readout.textContent = "Arc "+(si+1)+" / "+ARCS.length; return; }
    const d = DAYIDX[di];
    let t = "Day "+(d.wd<0?"−"+(-d.wd):d.wd);
    if(d.l1 && d.l2) t += " · both loops";
    else if(d.l2) t += " · lived day "+d.l2.d.day;
    readout.textContent = t;
  }
  function highlight(scroll){
    const sel = mode==="session" ? ".leg" : ".dayrow", key = mode==="session" ? "i" : "d", cur = curIdx();
    panel.querySelectorAll(sel).forEach(el=>el.classList.toggle("active", +el.dataset[key]===cur));
    if(scroll){
      const a = panel.querySelector(sel+'[data-'+key+'="'+cur+'"]');
      if(a) a.scrollIntoView({block:"nearest", behavior: reduceMotion?"auto":"smooth"});
    }
  }
  function markerClick(id){
    focusPlace = id;
    if(mode==="session"){
      let i = ARCS.findIndex((a,k)=>k>si && a.pin===id);
      if(i<0) i = ARCS.findIndex(a=>a.pin===id);
      if(i>=0){ setPos(i, true); return; }
    } else {
      const hit = d=>(d.l1&&d.l1.pins.includes(id))||(d.l2&&d.l2.pins.includes(id));
      let i = DAYIDX.findIndex((d,k)=>k>di && hit(d));
      if(i<0) i = DAYIDX.findIndex(hit);
      if(i>=0){ setPos(i, true); return; }
    }
    updatePlacecard();
  }
  function updatePlacecard(){
    const link = id => '<a href="'+ROOT+PINS[id].url+'">'+esc(PINS[id].name)+'</a> <span class="pk">'+esc(PINS[id].kind)+'</span>';
    let h = "";
    if(focusPlace) h += '<span>'+link(focusPlace)+'</span>';
    if(mode==="session"){
      const a = ARCS[si];
      if(a.pin && a.pin!==focusPlace) h += '<span>'+link(a.pin)+'</span>';
      h += '<span class="pk">Arc</span><a href="'+ROOT+a.url+'">'+esc(a.title)+'</a>';
    } else {
      const d = DAYIDX[di];
      [d.l1, d.l2].forEach(r=>{ if(r){
        r.pins.forEach(p=>{ if(p!==focusPlace) h += '<span>'+link(p)+'</span>'; });
        h += '<a href="'+ROOT+r.d.url+'">Day '+r.d.day+'</a>';
      }});
    }
    placecard.innerHTML = h;
  }

  /* ---------- markers + route ---------- */
  function updateMarkers(){
    const reveal = revealChk.checked;
    Object.values(markerEls).forEach(el=>el.classList.remove("active","active2","dim","hiddenPin"));
    let a1 = new Set(), a2 = new Set(), seen = new Set();
    if(mode==="session"){
      a1.add(ARCS[si].pin);
      ARCS.slice(0, si+1).forEach(a=>seen.add(a.pin));
    } else {
      const d = DAYIDX[di];
      if(d.l1) a1.add(d.l1.pin);
      if(d.l2) a2.add(d.l2.pin);
      DAYIDX.slice(0, di+1).forEach(x=>[x.l1,x.l2].forEach(r=>r&&r.pins.forEach(p=>seen.add(p))));
    }
    Object.keys(markerEls).forEach(id=>{
      const el = markerEls[id];
      if(editing) return;
      if(reveal && !seen.has(id)){ el.classList.add("hiddenPin"); return; }
      if(a1.has(id)) el.classList.add("active");
      else if(a2.has(id)) el.classList.add("active2");
      else if(!seen.has(id) || mode==="day") el.classList.add("dim");
    });
  }
  function routeLine(ids, color){
    const w = frame.clientWidth, h = frame.clientHeight, path = [];
    ids.forEach(id=>{
      const p = px(id); if(!p) return;
      const pt = [p.x/100*w, p.y/100*h], l = path[path.length-1];
      if(!l || l[0]!==pt[0] || l[1]!==pt[1]) path.push(pt);
    });
    if(path.length>1){
      const line = document.createElementNS(SVGNS, "path");
      line.setAttribute("d", "M"+path.map(p=>p[0].toFixed(1)+","+p[1].toFixed(1)).join(" L"));
      [["fill","none"],["stroke",color],["stroke-width","2.4"],["stroke-linejoin","round"],
       ["stroke-linecap","round"],["stroke-dasharray","2 7"],["opacity","0.9"]].forEach(([k,v])=>line.setAttribute(k,v));
      svg.appendChild(line);
    }
    path.forEach(p=>{
      const c = document.createElementNS(SVGNS, "circle");
      c.setAttribute("cx",p[0]); c.setAttribute("cy",p[1]); c.setAttribute("r","2.6");
      c.setAttribute("fill",color); c.setAttribute("opacity","0.5");
      svg.appendChild(c);
    });
  }
  function drawRoute(){
    svg.innerHTML = "";
    if(!D || !routeChk.checked || !frame.clientWidth) return;
    if(mode==="session"){
      routeLine(ARCS.slice(0, si+1).map(a=>a.pin), "var(--gold)");
    } else {
      const upto = DAYIDX.slice(0, di+1), flat = k => upto.filter(x=>x[k]).flatMap(x=>x[k].pins);
      routeLine(flat("l1"), "var(--gold)");
      routeLine(flat("l2"), "var(--violet)");
    }
  }

  /* ---------- pin editor ---------- */
  function enableDrag(el, id){
    let dragging = false;
    el.addEventListener("pointerdown", e=>{ if(!editing) return; dragging = true; el.setPointerCapture(e.pointerId); e.preventDefault(); });
    el.addEventListener("pointermove", e=>{
      if(!dragging) return;
      const r = frame.getBoundingClientRect();
      const x = Math.max(0, Math.min(100, (e.clientX-r.left)/r.width*100));
      const y = Math.max(0, Math.min(100, (e.clientY-r.top)/r.height*100));
      moved[id] = {x:+x.toFixed(1), y:+y.toFixed(1)};
      place(el, id); showTip(id); drawRoute();
    });
    el.addEventListener("pointerup", ()=>{
      if(!dragging) return; dragging = false; hideTip();
      try{ localStorage.setItem(LS_KEY, JSON.stringify(moved)); }catch(e){}
      writePinOut();
    });
  }
  function writePinOut(){
    const ids = Object.keys(moved).filter(id=>PINS[id]);
    pinOut.value = ids.length
      ? "# Paste each line into the frontmatter of the named note, replacing its map: line.\n" +
        ids.map(id=>"# "+PINS[id].name+".md\nmap: {x: "+moved[id].x+", y: "+moved[id].y+", layer: "+PINS[id].layer+"}").join("\n")
      : "";
    pinOut.hidden = !editing || !ids.length;
  }
  editBtn.addEventListener("click", ()=>{
    editing = !editing;
    editBtn.setAttribute("aria-pressed", editing);
    copyBtn.hidden = resetBtn.hidden = !editing;
    editHint.textContent = editing ? "Edit mode: drag pins onto their true spot. This only changes your view; copy the result into the notes to keep it." : "";
    Object.values(markerEls).forEach(el=>el.classList.toggle("editing", editing));
    writePinOut(); updateMarkers();
  });
  copyBtn.addEventListener("click", ()=>{
    writePinOut();
    if(!pinOut.value){ editHint.textContent = "No pins moved yet."; return; }
    navigator.clipboard.writeText(pinOut.value).then(
      ()=>{ editHint.textContent = "Copied. Paste the map: lines into the notes (or hand them to Claude)."; },
      ()=>{ pinOut.hidden = false; pinOut.select(); editHint.textContent = "Copy the text below."; });
  });
  resetBtn.addEventListener("click", ()=>{
    moved = {}; try{ localStorage.removeItem(LS_KEY); }catch(e){}
    Object.keys(markerEls).forEach(id=>place(markerEls[id], id));
    drawRoute(); writePinOut(); editHint.textContent = "Pins reset to the positions in the notes.";
  });

  /* ---------- controls ---------- */
  function stopPlay(){ playing = false; clearInterval(timer); timer = null; playBtn.textContent = "▶ Play"; playBtn.setAttribute("aria-pressed","false"); }
  function startPlay(){
    if(curIdx() >= curMax()) setPos(0, false);
    playing = true; playBtn.textContent = "❚❚ Pause"; playBtn.setAttribute("aria-pressed","true");
    timer = setInterval(()=>{ if(curIdx() >= curMax()){ stopPlay(); return; } focusPlace = null; setPos(curIdx()+1, true); }, reduceMotion ? 900 : 1500);
  }
  function switchMode(m){
    if(mode===m) return;
    stopPlay(); mode = m; focusPlace = null;
    segBtns.forEach(b=>b.setAttribute("aria-pressed", b.dataset.mode===m ? "true" : "false"));
    slider.max = curMax(); buildPanel(); setPos(curIdx(), true);
  }
  segBtns.forEach(b=>b.addEventListener("click", ()=>switchMode(b.dataset.mode)));
  playBtn.addEventListener("click", ()=> playing ? stopPlay() : startPlay());
  $("next").addEventListener("click", ()=>{ stopPlay(); focusPlace=null; setPos(curIdx()+1, true); });
  $("prev").addEventListener("click", ()=>{ stopPlay(); focusPlace=null; setPos(curIdx()-1, true); });
  slider.addEventListener("input", e=>{ stopPlay(); focusPlace=null; setPos(+e.target.value, true); });
  revealChk.addEventListener("change", ()=>{ updateMarkers(); drawRoute(); });
  routeChk.addEventListener("change", drawRoute);
  document.addEventListener("keydown", e=>{
    if(/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    if(e.key==="ArrowRight"){ stopPlay(); focusPlace=null; setPos(curIdx()+1, true); }
    if(e.key==="ArrowLeft"){ stopPlay(); focusPlace=null; setPos(curIdx()-1, true); }
  });
})();
