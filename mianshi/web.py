"""Web 入口:http.server 零依赖,单页两个页签。"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import agent, tools
from .db import Database

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>面试 · 这一轮多了什么证据</title>
<style>
:root{--bg:#0e1116;--card:#171c24;--line:#26303c;--text:#e6edf3;--dim:#8b98a5;--accent:#f2b544;--ok:#57c98b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--dim);font-size:13px;margin-bottom:20px}
.tabs{display:flex;gap:8px;margin-bottom:18px}
.tab{padding:7px 14px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--dim);cursor:pointer}
.tab.on{color:var(--bg);background:var(--accent);border-color:var(--accent)}
.panel{display:none}.panel.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
label{display:block;font-size:13px;color:var(--dim);margin:10px 0 6px}
textarea,input,select{width:100%;background:#0b0f14;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px;font:14px/1.6 inherit}
textarea{min-height:120px;resize:vertical}
.row{display:flex;gap:10px}.row>*{flex:1}
button.go{margin-top:12px;background:var(--accent);color:#161b22;border:0;border-radius:8px;padding:10px 18px;font-weight:600;cursor:pointer}
button.go:disabled{opacity:.55;cursor:wait}
pre{white-space:pre-wrap;word-break:break-word;background:#0b0f14;border:1px solid var(--line);border-radius:8px;padding:14px;min-height:80px;font:13px/1.65 "Cascadia Mono",monospace}
.badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--dim);margin-left:8px}
.badge.off{color:var(--accent);border-color:var(--accent)}

h1{font-size:clamp(31px,5vw,39px);line-height:1.26}
.prod{display:block;font-size:11px;line-height:1.4;letter-spacing:.18em;font-weight:650;margin-bottom:8px;opacity:.72}
.lede,.sub{max-width:62ch;line-height:1.75}
.route{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1px;margin:0 0 20px;border:1px solid var(--line);background:var(--line)}
.route span{padding:11px 13px;background:var(--card);font-size:12px;line-height:1.5}
.route b{display:block;font-size:10px;letter-spacing:.1em;margin-bottom:3px;opacity:.66}
button{min-height:46px}
input,select{min-height:44px}
@media(max-width:680px){
  .wrap{padding:20px 16px 56px}
  .route{grid-template-columns:1fr}
  h1{font-size:30px!important}
  .row>div{min-width:100%!important}
  button{width:100%}
}

body{background:#f4efe8;color:#2b2927;font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:900px}
header{background:#262a2f;color:#fbf8f3;padding:24px 24px 22px;margin-bottom:20px;border-bottom:4px solid #b45d2a}
header h1{font-size:37px;line-height:1.26;letter-spacing:-.02em}
header p{color:#d1c9bf;font-size:14px}
.card{background:#fffaf4;border:1px solid #ded2c2;border-radius:2px;box-shadow:0 1px 0 #e9dfd3}
button{background:#b45d2a;border-radius:2px;letter-spacing:.05em}
button:hover{background:#9c4d20}
textarea,input,select{background:#fffdf9;border-color:#d9ccbb;border-radius:2px}
textarea:focus,input:focus,select:focus{border-color:#b45d2a;box-shadow:0 0 0 2px #eed9cd}
.cost .cell b,.cell b{font-family:"Cascadia Mono",Consolas,monospace;font-variant-numeric:tabular-nums}
.item{border-left:3px solid #b45d2a}
h3{color:#8d4a25;letter-spacing:.08em}


/* palette-normalized */
:root{--bg:#f4efe8;--card:#fffaf4;--ink:#2b2927;--text:#2b2927;--dim:#746b60;--line:#ded2c2;--accent:#b45d2a}
pre{background:#fffdf8;color:#2b2927;border-color:#ded2c2;border-radius:2px}

/* polish-batch1 */
button.ghost,button.secondary{background:transparent!important;color:#b45d2a!important;border:1px solid #ded2c2!important}

/* mobile-32 */

@media(max-width:760px){
  main{grid-template-columns:1fr!important}
  aside{border-right:0!important;border-bottom:1px solid #ded2c2;width:auto!important}
  section{padding:16px!important}
  .row{flex-wrap:wrap!important}
  .row>div{min-width:100%!important}
  h1{font-size:30px!important}
  .route{grid-template-columns:1fr!important}
  button{min-height:48px}
  pre{overflow-x:auto}
}

/* mobile-height */
@media(max-width:760px){main{min-height:auto!important}aside{min-height:0!important}}

/* mobile-sticky-cta */
.mobile-cta{display:none}
@media(max-width:760px){
  body{padding-bottom:88px}
  .route{grid-template-columns:repeat(3,minmax(0,1fr))!important}
  .route span{padding:8px 8px!important;font-size:11px!important;line-height:1.35!important}
  .route b{font-size:9px!important;margin-bottom:1px!important}
  .mobile-cta{position:fixed;left:12px;right:12px;bottom:12px;z-index:80;display:flex;
    padding:8px;border:1px solid rgba(0,0,0,.08);border-radius:12px;
    background:rgba(255,255,255,.94);backdrop-filter:blur(10px);
    box-shadow:0 10px 28px rgba(16,24,40,.18)}
  .mobile-cta button{width:100%;min-height:52px;margin:0!important;font-size:15px}
}
</style></head><body><div class="wrap">
<h1><span class="prod">面试</span>同一个追问，这次答得更好吗 <span id="status" class="badge">…</span></h1>
  <p class="sub">给已有目标岗位的求职者：按 JD 和真实经历出题，用同一套维度复练，比较遗漏证据、结构和时长，收成口袋卡。</p>
<div class="sub">简历与 JD 匹配、出题、回答点评、措辞建议。只读你粘进来的文本。</div>
<div class="tabs">
  <button class="tab on" data-tab="match">匹配与出题</button>
  <button class="tab" data-tab="drill">模拟面试</button>
</div>

<div class="panel on" id="match">
  
  <div class="route" aria-label="任务步骤"><span><b>01</b>贴 JD 和经历</span><span><b>02</b>计时答一轮</span><span><b>03</b>同维度复练</span></div>
<div class="card">
    <div class="row"><div><label>岗位标题</label><input id="title" value="AI 产品经理"></div>
    <div><label>公司</label><input id="company" placeholder="可留空"></div></div>
    <label>JD(不少于 60 字)</label><textarea id="jd" placeholder="把岗位描述粘进来……"></textarea>
    <label>简历(不少于 100 字)</label><textarea id="resume" placeholder="把简历正文粘进来……"></textarea>
    <button class="go" id="btnAnalyze">算匹配度</button>
    <button class="go" id="btnGen" style="background:#2b3441;color:#e6edf3">按 JD 出题</button>
  </div>
  <div class="card"><pre id="outMatch">结果会出现在这里。</pre></div>
</div>

<div class="panel" id="drill">
  <div class="card">
    <label>岗位</label><select id="jobSel"></select>
    <label>题目</label><select id="qSel"></select>
    <label>你的回答(不少于 30 字)</label><textarea id="answer" placeholder="按 STAR 说:当时什么情况、你负责什么、做了什么、结果如何"></textarea>
    <button class="go" id="btnReview">点评这一轮</button>
  </div>
  <div class="card"><pre id="outDrill">还没有记录。</pre></div>
</div>
</div>
<script>
const $=s=>document.querySelector(s);
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id===t.dataset.tab));
});
function loading(btn,on){
  if(on){btn.dataset.label=btn.dataset.label||btn.textContent;btn.disabled=true;btn.textContent='处理中…';}
  else{btn.disabled=false;btn.textContent=btn.dataset.label||btn.textContent;}
}
async function api(path,opt){
  const r=await fetch(path,opt);const j=await r.json();
  if(!r.ok||j.error)throw new Error(j.error||('HTTP '+r.status));
  return j;
}
async function boot(){
  try{
    const s=await api('/api/status');
    const b=$('#status');b.textContent=s.offline?'离线模式':'模型 '+s.model;b.classList.toggle('off',s.offline);
    const jobs=await api('/api/jobs');
    $('#jobSel').innerHTML=jobs.map(j=>`<option value="${j.id}">${j.company?j.company+' · ':''}${j.title}</option>`).join('')||'<option value="">还没有岗位</option>';
    await loadQuestions();
  }catch(e){$('#status').textContent='读取失败';}
}
async function loadQuestions(){
  const job=$('#jobSel').value;if(!job)return;
  const qs=await api('/api/questions?job='+job);
  $('#qSel').innerHTML=qs.map(q=>`<option value="${q.id}">${q.question}</option>`).join('')||'<option value="">还没有题,先去左边出题</option>';
}
$('#jobSel').onchange=loadQuestions;
$('#btnAnalyze').onclick=async()=>{
  const btn=$('#btnAnalyze');loading(btn,true);
  try{
    const r=await api('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title:$('#title').value,company:$('#company').value,jd:$('#jd').value,resume:$('#resume').value})});
    $('#outMatch').textContent=r.text;
    $('#jobSel').innerHTML=`<option value="${r.job_id}">${r.job_id} · ${$('#title').value}</option>`;
    await loadQuestions();
  }catch(e){$('#outMatch').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
$('#btnGen').onclick=async()=>{
  const btn=$('#btnGen');loading(btn,true);
  try{
    const r=await api('/api/gen',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({job_id:Number($('#jobSel').value)||0})});
    $('#outMatch').textContent=r.text;
    await loadQuestions();
  }catch(e){$('#outMatch').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
$('#btnReview').onclick=async()=>{
  const btn=$('#btnReview');loading(btn,true);
  try{
    const r=await api('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({job_id:Number($('#jobSel').value)||0,question_id:Number($('#qSel').value)||0,answer:$('#answer').value})});
    $('#outDrill').textContent=r.text;
  }catch(e){$('#outDrill').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
boot();
</script>
<script>
(function(){
  var want = "匹配与出题";
  function norm(t){ return String(t||'').replace(/\s+/g,''); }
  var all=[].slice.call(document.querySelectorAll('button'));
  var src=null, fallback=null;
  for(var i=0;i<all.length;i++){
    var b=all[i];
    if(b.offsetParent===null||b.disabled) continue;
    if(!fallback) fallback=b;
    if(norm(b.textContent).indexOf(norm(want))>=0){ src=b; break; }
  }
  if(!src) src=fallback;
  if(!src) return;
  var bar=document.createElement('div'); bar.className='mobile-cta';
  var btn=src.cloneNode(true); btn.removeAttribute('id'); btn.type='button';
  btn.addEventListener('click',function(e){e.preventDefault(); src.click();});
  bar.appendChild(btn); document.body.appendChild(bar);
})();
</script>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    db: Database
    cfg: dict
    force_mock: bool

    def log_message(self, *args):  # 静默,不往 stderr 刷访问日志
        pass

    def _json(self, data, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # Windows 下 curl 直接发中文是 GBK
            text = raw.decode("gbk", errors="replace")
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            self._html(PAGE)
            return
        if path == "/api/status":
            self._json({"mode": "offline" if self.force_mock else "model",
                        "model": self.cfg.get("model", ""), "offline": self.force_mock})
            return
        if path == "/api/jobs":
            self._json(self.db.list_jobs())
            return
        if path == "/api/questions":
            qs = parse_qs(urlparse(self.path).query)
            job = (qs.get("job") or [""])[0]
            rows = self.db.list_questions(int(job) if job.isdigit() else None)
            self._json(rows)
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        data = self._read_json()
        try:
            if path == "/api/analyze":
                self._analyze(data)
            elif path == "/api/gen":
                self._gen(data)
            elif path == "/api/review":
                self._review(data)
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # 不让单个请求把服务打挂
            self._json({"error": str(e)}, 502)

    # 业务 -----------------------------------------------------------------
    def _analyze(self, data: dict):
        from .cli import render_analysis
        resume = tools.normalize(str(data.get("resume", "")))
        jd = tools.normalize(str(data.get("jd", "")))
        if len(jd) < 60:
            self._json({"error": "JD 太短,少于 60 字"}, 400)
            return
        if len(resume) < 100:
            self._json({"error": "简历太短,少于 100 字"}, 400)
            return
        title = str(data.get("title") or "未命名岗位")
        rid = self.db.add_resume(title + " · 简历", resume)
        jid = self.db.add_job(title, jd, str(data.get("company", "")), rid)
        job = self.db.get_job(jid)
        result = agent.analyze(resume, job, self.cfg, self.force_mock)
        result["job_id"] = jid
        result["text"] = render_analysis(result)
        result["coverage_text"] = tools.match_line(result["coverage"])
        self._json(result)

    def _gen(self, data: dict):
        from .cli import render_questions
        jid = int(data.get("job_id") or 0)
        job = self.db.get_job(jid)
        if not job:
            self._json({"error": "先做一次匹配,岗位才会入库"}, 400)
            return
        resume = ""
        if job.get("resume_id"):
            r = self.db.get_resume(int(job["resume_id"]))
            resume = r["text"] if r else ""
        if not resume:
            self._json({"error": "这个岗位没有绑定简历"}, 400)
            return
        result = agent.gen_questions(job, resume, int(data.get("n") or 5), self.cfg, self.force_mock)
        self.db.clear_questions(jid)
        for q in result["questions"]:
            dbid = self.db.add_question(jid, q["question"], q.get("why", ""))
            q["id"] = dbid
        result["text"] = render_questions(result)
        self._json(result)

    def _review(self, data: dict):
        from .cli import render_review
        jid = int(data.get("job_id") or 0)
        qid = int(data.get("question_id") or 0)
        job = self.db.get_job(jid)
        qrow = self.db.get_question(qid)
        if not job or not qrow:
            self._json({"error": "岗位或题目不存在"}, 400)
            return
        answer = tools.normalize(str(data.get("answer", "")))
        if len(answer) < 30:
            self._json({"error": "回答太短,少于 30 字"}, 400)
            return
        resume = ""
        if job.get("resume_id"):
            r = self.db.get_resume(int(job["resume_id"]))
            resume = r["text"] if r else ""
        result = agent.review(job, resume, qrow["question"], answer, self.cfg, self.force_mock)
        text = render_review(result)
        result["text"] = text
        result["round_id"] = self.db.add_round(jid, qid, qrow["question"], answer, text,
                                              int(result.get("score") or 0))
        self._json(result)


def _make_handler(db: Database, cfg: dict, force_mock: bool):
    return type("Handler", (_Handler,), {"db": db, "cfg": cfg, "force_mock": force_mock})


def serve(host: str = "127.0.0.1", port: int = 8771, db_path: str = "data/mianshi.db",
          force_mock: bool = False, cfg: dict | None = None):
    from . import llm
    db = Database(db_path)
    cfg = dict(llm.default_config() if cfg is None else cfg)
    if not cfg.get("api_key"):
        force_mock = True
    handler = _make_handler(db, cfg, force_mock)
    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"🎯 面试已启动  http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n· 已停止")
    finally:
        httpd.server_close()
        db.close()
