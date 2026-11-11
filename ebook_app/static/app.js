// ---------- helpers ----------
const $ = s => document.querySelector(s);
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const ct = r.headers.get("content-type") || "";
  if (!ct.includes("json")) return await r.json().catch(()=>({}));
  return r.json();
};
function show(view){
  document.querySelectorAll(".view").forEach(v=>v.classList.toggle("active", v.id==="view-"+view));
  $("#navUpload").classList.toggle("active", view==="upload");
  $("#navStorage").classList.toggle("active", view==="storage");
}

// ---------- state ----------
let currentBook = null;          // {book_id, pages:[...]}
const animateSet = new Set();
let pollTimer = null;

// ---------- boot: prefill API key ----------
(async function boot(){
  try{
    const c = await api("/api/config");
    if (c.hasKey){ $("#apiKey").value = c.defaultKey; $("#keyHint").textContent = "Loaded your saved key."; }
    else { $("#apiKey").placeholder = "Enter your Qwen API key (sk-...)"; $("#keyHint").textContent = "New here? Paste your Qwen / DashScope API key."; }
  }catch(e){}
})();

// ---------- navigation ----------
$("#navUpload").onclick = ()=>show("upload");
$("#navStorage").onclick = ()=>{ show("storage"); loadLibrary(); };
$("#homeUpload").onclick = ()=>show("upload");
$("#homeStorage").onclick = ()=>{ show("storage"); loadLibrary(); };

// ---------- upload ----------
$("#btnUpload").onclick = async ()=>{
  const file = $("#pdfFile").files[0];
  const key = $("#apiKey").value.trim();
  if(!file){ alert("Choose a PDF first."); return; }
  if(!key){ alert("Enter your Qwen API key."); return; }
  $("#btnUpload").disabled = true; $("#btnUpload").textContent = "Uploading…";
  const fd = new FormData(); fd.append("pdf", file); fd.append("api_key", key);
  try{
    const res = await api("/api/upload", {method:"POST", body:fd});
    if(res.error){ alert(res.error); return; }
    currentBook = res;
    animateSet.clear(); res.pages.forEach(p=>animateSet.add(p.index)); // default: animate all
    renderPages();
    $("#pagePick").classList.remove("hidden");
  } finally { $("#btnUpload").disabled=false; $("#btnUpload").textContent="Upload & preview pages"; }
};

function renderPages(){
  const g = $("#pageGrid"); g.innerHTML="";
  currentBook.pages.forEach(p=>{
    const d=document.createElement("div");
    d.className="pg"+(animateSet.has(p.index)?"":" off");
    const on=animateSet.has(p.index);
    d.innerHTML=`<img src="/${p.thumb}" alt="page ${p.index+1}">
      <span class="badge">Page ${p.index+1}</span>
      <span class="state">${on?"Animate":"Skip"}</span>`;
    d.onclick=()=>{ if(animateSet.has(p.index)) animateSet.delete(p.index); else animateSet.add(p.index); renderPages(); };
    g.appendChild(d);
  });
}

$("#btnGenerate").onclick = async ()=>{
  if(!currentBook) return;
  const animate=[...animateSet].sort((a,b)=>a-b);
  if(!animate.length){ alert("Select at least one page to animate."); return; }
  $("#btnGenerate").disabled=true; $("#progress").classList.remove("hidden");
  await api("/api/generate", {method:"POST", headers:{"content-type":"application/json"},
    body: JSON.stringify({book_id:currentBook.book_id, animate, api_key:$("#apiKey").value.trim()})});
  pollStatus(currentBook.book_id);
};

function pollStatus(bid){
  clearInterval(pollTimer);
  pollTimer=setInterval(async ()=>{
    const s = await api("/api/status/"+bid);
    const pct = Math.round((s.progress||0)*100);
    $("#barFill").style.width = pct+"%";
    $("#progText").textContent = `${s.status} — ${s.done||0}/${s.total||0} pages (${pct}%)`;
    if(s.status==="done"){ clearInterval(pollTimer); $("#progText").innerHTML =
      `Done! <button class="big" onclick="openReader('${bid}')">Read the e-book ➤</button>`; }
    if(s.status==="error"){ clearInterval(pollTimer); $("#progText").textContent="Error: "+(s.error||""); }
  }, 3000);
}

// ---------- storage ----------
async function loadLibrary(){
  const books = await api("/api/books");
  const c=$("#libList"); c.innerHTML="";
  if(!books.length){ c.innerHTML='<p class="muted">No books yet. Upload one to get started.</p>'; return; }
  books.forEach(b=>{
    const row=document.createElement("div"); row.className="item";
    const st=b.status;
    row.innerHTML=`<div><div class="t">${b.title||b.id}</div>
      <div class="s">${b.total||0} pages</div></div>
      <div class="item-actions"><span class="pill ${st}">${st}</span>
      ${st==="done"?`<button class="big sm" onclick="openReader('${b.id}')">Read</button>`:""}
      <button class="del" onclick="deleteBook('${b.id}','${(b.title||b.id).replace(/'/g,"\\'")}')">Delete</button></div>`;
    c.appendChild(row);
  });
}

window.deleteBook = async function(bid, title){
  if(!confirm(`Delete "${title}"?\nIt will be moved to the app's trash folder (recoverable), not permanently erased.`)) return;
  const r = await api("/api/books/"+bid, {method:"DELETE"});
  if(r.error){ alert(r.error); return; }
  loadLibrary();
};

// ---------- reader ----------
let EB=null, bookEl=null, idx=0; const audio=new Audio(); let raf=null, sched=null;

window.openReader = async function(bid){
  show("reader");
  const data = await api("/api/book/"+bid);
  if(data.error){ alert("This book isn't ready yet."); return; }
  EB = { bid, title:data.title, pages:data.pages };
  $("#readerTitle").textContent = EB.title || "E-book";
  buildReader();
};

function assetURL(p){ return "/books/"+EB.bid+"/"+p; }

function buildReader(){
  bookEl=$("#book"); bookEl.innerHTML=""; idx=0;
  EB.pages.forEach((p,i)=>{
    const el=document.createElement("div"); el.className="page";
    if(p.type==="content"){
      const ov=document.createElement("div"); ov.className="overlay";
      (p.layout?.lines||[]).forEach(ln=>{
        const ld=document.createElement("div"); ld.className="line";
        ld.innerHTML=ln.text.split(" ").map(w=>`<span class="word">${w}</span>`).join(" ");
        ov.appendChild(ld);
      });
      (p.layout?.pageNumbers||[]).forEach(pn=>{
        const pd=document.createElement("div"); pd.className="pnum"; pd.textContent=pn.text; ov.appendChild(pd);
      });
      el.innerHTML=`<div class="media"><video src="${assetURL(p.video)}" poster="${assetURL(p.poster)}" muted loop playsinline preload="auto"></video></div>`;
      el.appendChild(ov);
    } else { // image (static scanned page)
      el.innerHTML=`<div class="imgpage"><img src="${assetURL(p.image)}"></div>`;
    }
    bookEl.appendChild(el);
  });
  const dots=$("#dots"); dots.innerHTML="";
  EB.pages.forEach((_,i)=>{ const d=document.createElement("span"); d.className="dot"; d.onclick=()=>go(i); dots.appendChild(d); });
  $("#prev").onclick=()=>go(idx-1);
  $("#next").onclick=()=>{ if(idx===EB.pages.length-1) go(0); else go(idx+1); };
  $("#replay").onclick=()=>{ const p=EB.pages[idx]; if(p.type!=="content")return;
    const v=bookEl.querySelector(".page.active video"); if(v)v.currentTime=0;
    resetTyped(); audio.currentTime=0; audio.play().then(startTyping).catch(()=>{}); };
  $("#backToLib").onclick=()=>{ show("storage"); loadLibrary(); };
  render();
}

function current(){ return EB.pages[idx]; }
function layoutActive(){
  const p=current(); if(p.type!=="content"||!p.layout) return;
  const media=bookEl.querySelector(".page.active .media"); if(!media) return;
  const r=media.getBoundingClientRect();
  bookEl.querySelectorAll(".page.active .line").forEach((ld,k)=>{
    const [x1,y1,x2,y2]=p.layout.lines[k].box;
    ld.style.left=(x1/1000*r.width)+"px"; ld.style.top=(y1/1000*r.height)+"px";
    ld.style.fontSize=((y2-y1)/1000*r.height*0.86)+"px";
  });
  const pn=bookEl.querySelectorAll(".page.active .pnum");
  (p.layout.pageNumbers||[]).forEach((n,k)=>{ const el=pn[k]; if(!el)return; const [x1,y1,x2,y2]=n.box;
    el.style.left=(x1/1000*r.width)+"px"; el.style.top=(y1/1000*r.height)+"px";
    el.style.fontSize=((y2-y1)/1000*r.height*0.9)+"px"; });
}
function buildSchedule(){
  const words=[...bookEl.querySelectorAll(".page.active .word")];
  const total=words.reduce((s,w)=>s+w.textContent.length+1,0); let acc=0; const sc=[];
  words.forEach(w=>{ sc.push({el:w,start:acc/total}); acc+=w.textContent.length+1; });
  return {words,sc};
}
function startTyping(){
  stopTyping(); sched=buildSchedule();
  const dur=()=>(audio.duration&&isFinite(audio.duration))?audio.duration:3;
  (function tick(){
    if(!audio.paused){ const frac=Math.min(1,audio.currentTime/dur()); let last=-1;
      sched.sc.forEach((s,i)=>{ if(frac>=s.start){s.el.classList.add("show"); last=i;} });
      sched.words.forEach(w=>w.classList.remove("caret"));
      if(last>=0&&last<sched.words.length-1) sched.words[last].classList.add("caret");
      if(frac>=1) sched.words.forEach(w=>w.classList.add("show")); }
    raf=requestAnimationFrame(tick);
  })();
}
function stopTyping(){ if(raf)cancelAnimationFrame(raf); raf=null; }
function resetTyped(){ bookEl.querySelectorAll(".page.active .word").forEach(w=>w.classList.remove("show","caret")); }
function go(n){ n=Math.max(0,Math.min(EB.pages.length-1,n)); if(n===idx){render();return;}
  bookEl.classList.add("flipping"); setTimeout(()=>{ idx=n; render(); bookEl.classList.remove("flipping"); layoutActive(); },250); }
function render(){
  document.querySelectorAll("#book .page").forEach((el,i)=>el.classList.toggle("active",i===idx));
  document.querySelectorAll("#dots .dot").forEach((el,i)=>el.classList.toggle("on",i===idx));
  const p=current();
  $("#pageno").textContent=(idx+1)+" / "+EB.pages.length;
  $("#prev").disabled=idx===0;
  $("#next").innerHTML=idx===EB.pages.length-1?"Restart ↻":(idx===0&&p.type!=="content"?"Start ➤":"Next ➤");
  stopTyping(); resetTyped(); audio.pause();
  if(p.type==="content"){ layoutActive();
    const v=bookEl.querySelector(".page.active video"); if(v){v.currentTime=0;v.play().catch(()=>{});}
    if(p.audio){ audio.src=assetURL(p.audio); audio.currentTime=0; audio.play().then(startTyping).catch(()=>{}); } }
}
window.addEventListener("resize", ()=>{ if(EB && document.getElementById("view-reader").classList.contains("active")) layoutActive(); });
