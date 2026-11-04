/* Search and theme toggle, on every page. */
(function(){
  const ROOT = document.body.dataset.root || "";

  /* ---- theme ---- */
  const themeBtn = document.getElementById("theme");
  if(themeBtn){
    themeBtn.addEventListener("click", ()=>{
      const cur = document.documentElement.dataset.theme ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try{ localStorage.setItem("ootd-theme", next); }catch(e){}
    });
  }

  /* ---- search ---- */
  const q = document.getElementById("q"), box = document.getElementById("results");
  if(!q || !box) return;
  let index = null, loading = null, sel = -1, hits = [];

  function load(){
    if(index) return Promise.resolve(index);
    if(!loading){
      loading = fetch(ROOT + "search.json").then(r=>r.json()).then(d=>{
        index = d.map(it=>Object.assign(it, {
          _t: norm(it.t), _a: (it.a||[]).map(norm), _b: norm(it.b||"")
        }));
        return index;
      }).catch(()=>{ index = []; return index; });
    }
    return loading;
  }
  function norm(s){ return (s||"").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g,""); }
  function escHtml(s){ return (s||"").replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }

  function score(it, terms, whole){
    let s = 0;
    if(it._t === whole) s += 100;
    else if(it._t.startsWith(whole)) s += 40;
    if(it._a.some(a=>a === whole)) s += 60;
    for(const t of terms){
      let hit = false;
      if(it._t.includes(t)){ s += it._t.split(/\W+/).some(w=>w.startsWith(t)) ? 12 : 6; hit = true; }
      if(it._a.some(a=>a.includes(t))){ s += 8; hit = true; }
      const c = it._b.split(t).length - 1;
      if(c){ s += Math.min(c, 5); hit = true; }
      if(!hit) return 0;
    }
    if(it.s === "Session" || it.s === "Day") s *= 0.85;
    return s;
  }
  function snippet(it, terms){
    const i = terms.length ? it._b.indexOf(terms[0]) : -1;
    if(i < 0 || it._t.includes(terms[0])) return escHtml(it.x || "");
    const start = Math.max(0, i - 50);
    let s = (start ? "…" : "") + it.b.slice(start, i + 90) + "…";
    s = escHtml(s);
    terms.forEach(t=>{
      if(t.length < 2) return;
      s = s.replace(new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g,"\\$&") + ")", "ig"), "<mark>$1</mark>");
    });
    return s;
  }
  function render(){
    const whole = norm(q.value.trim());
    if(!whole){ box.hidden = true; return; }
    const terms = whole.split(/\s+/).filter(Boolean);
    hits = index.map(it=>[score(it, terms, whole), it]).filter(x=>x[0] > 0)
      .sort((a,b)=>b[0]-a[0]).slice(0, 14).map(x=>x[1]);
    sel = hits.length ? 0 : -1;
    box.innerHTML = hits.length ? hits.map((it,i)=>
      '<a href="'+ROOT+it.u+'" role="option"'+(i===sel?' class="sel"':'')+'>'+
      '<span class="rs">'+escHtml(it.s)+'</span><span class="rt">'+escHtml(it.t)+'</span>'+
      '<span class="rx">'+snippet(it, terms)+'</span></a>').join("")
      : '<div class="none">Nothing in the chronicle about that (yet).</div>';
    box.hidden = false;
  }
  function move(d){
    if(!hits.length) return;
    sel = (sel + d + hits.length) % hits.length;
    box.querySelectorAll("a").forEach((a,i)=>a.classList.toggle("sel", i===sel));
    const a = box.querySelectorAll("a")[sel]; if(a) a.scrollIntoView({block:"nearest"});
  }
  q.addEventListener("focus", load);
  q.addEventListener("input", ()=>load().then(render));
  q.addEventListener("keydown", e=>{
    if(e.key==="ArrowDown"){ e.preventDefault(); move(1); }
    else if(e.key==="ArrowUp"){ e.preventDefault(); move(-1); }
    else if(e.key==="Enter" && hits[sel]){ location.href = ROOT + hits[sel].u; }
    else if(e.key==="Escape"){ box.hidden = true; q.blur(); }
  });
  document.addEventListener("click", e=>{ if(!e.target.closest(".search")) box.hidden = true; });
  document.addEventListener("keydown", e=>{
    if(e.key==="/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)){ e.preventDefault(); q.focus(); }
  });
})();
