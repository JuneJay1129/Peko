/**
 * 计划台三种运行模式的 jsdom 功能测试：
 *  - local : file:// 或任意非 127.0.0.1/localhost 的 http(s) URL -> localStorage 回退
 *  - bridge: 内嵌桌宠（window.qt + QWebChannel 桥接）-> 读写共享 plans.json/todos.json
 *  - http  : 系统浏览器经本地服务(http://127.0.0.1)打开 -> 同一份文件，双向同步
 *
 * 重点验证用户报告的 bug「两个地方的数据不会同步」：
 *  http 模式必须连到本地服务(127.0.0.1)，否则应安全回退 local，不得误入 http 调用未定义 fetch。
 */
const fs = require("fs");
const path = require("path");
const http = require("http");
const { JSDOM, VirtualConsole } = require("jsdom");

// 本地服务依赖 PyQt5（仅系统 Python 已装），与真实运行环境一致
const PY = "C:/Users/502380/AppData/Local/Programs/Python/Python313/python.exe";
const HTML_PATH = "D:/github/Peko/peko/ui/plans/plans_web.html";
const RUNNER = "D:/github/Peko/scripts/_wb_server_runner.py";
const PORT = 18340;
const ORIGIN = `http://127.0.0.1:${PORT}`;

let html = fs.readFileSync(HTML_PATH, "utf8");
// 去掉外部 qwebchannel 脚本（测试自行注入 mock / 由服务在真实场景提供）
html = html.replace(/<script src="qwebchannel\.js"><\/script>\s*/, "");

// ---- node 侧 HTTP 助手（直接打本地服务） ----
function nodeReq(method, p, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null;
    const r = http.request(
      {
        host: "127.0.0.1",
        port: PORT,
        path: p,
        method,
        headers: data
          ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) }
          : {},
      },
      (res) => {
        let buf = "";
        res.on("data", (c) => (buf += c));
        res.on("end", () => resolve({ status: res.statusCode, body: buf }));
      }
    );
    r.on("error", reject);
    if (data) r.write(data);
    r.end();
  });
}

// ---- 页面内 fetch 垫片（仅 http 模式需要，连真实本地服务） ----
function pageFetch() {
  return function (url, opts) {
    return new Promise((resolve, reject) => {
      const u = new URL(url);
      const body = opts && opts.body ? opts.body : null;
      const r = http.request(
        {
          host: u.hostname,
          port: u.port || 80,
          path: u.pathname + (u.search || ""),
          method: (opts && opts.method) || "GET",
          headers: body
            ? {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(body),
              }
            : {},
        },
        (res) => {
          let buf = "";
          res.on("data", (c) => (buf += c));
          res.on("end", () =>
            resolve({
              ok: res.statusCode >= 200 && res.statusCode < 300,
              status: res.statusCode,
              json: () => Promise.resolve(JSON.parse(buf)),
              text: () => Promise.resolve(buf),
            })
          );
        }
      );
      r.on("error", reject);
      if (body) r.write(body);
      r.end();
    });
  };
}

function wait(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function makeDom(opts) {
  const vc = new VirtualConsole();
  const errs = [];
  vc.on("jsdomError", (e) => errs.push(String(e && e.detail ? e.detail : e)));
  const dom = new JSDOM(html, {
    url: opts.url,
    runScripts: "dangerously",
    virtualConsole: vc,
    beforeParse(window) {
      if (opts.qt) {
        window.qt = { webChannelTransport: {} };
      }
      if (opts.qwebchannel) {
        window.QWebChannel = function (transport, cb) {
          const bridge = {
            _plans: JSON.stringify(opts.bridgePlans || []),
            _todos: JSON.stringify(opts.bridgeTodos || []),
            save(p) {
              this._plans = p;
            },
            saveTodos(t) {
              this._todos = t;
            },
            getAll(cb) {
              cb(this._plans);
            },
            getTodos(cb) {
              cb(this._todos);
            },
          };
          window.__bridgeMock = bridge;
          cb({ objects: { bridge } });
        };
      }
      if (opts.fetch) {
        window.fetch = opts.fetch();
      }
    },
  });
  dom._vcErrs = errs;
  return dom;
}

const results = {};

async function testLocal() {
  // 用原 bug 场景 URL(https://local.test) 验证：修复后必须落入 local，不得误入 http 调 fetch
  const dom = makeDom({ url: "https://local.test/plans_web.html" });
  await wait(120);
  const w = dom.window;
  const badge = w.document.getElementById("storeBadge").textContent;
  const embedded = w.document.body.classList.contains("embedded");
  // 本地模式应已注入示例（seed），并写入 localStorage
  const lsPlans = JSON.parse(w.localStorage.getItem("wb_planbench_plans") || "[]");
  const lsTodos = JSON.parse(w.localStorage.getItem("wb_planbench_todos") || "[]");
  const lsHabits = JSON.parse(w.localStorage.getItem("wb_wb_habits") || "[]");
  const lsLedger = JSON.parse(w.localStorage.getItem("wb_wb_ledger") || "[]");
  const lsFocus = JSON.parse(w.localStorage.getItem("wb_wb_focus") || "[]");
  // 模拟新增一条待办
  let addOk = false;
  try {
    w.document.getElementById("btnAddTodo").click();
    w.document.getElementById("tTitle").value = "本地测试待办";
    w.document.getElementById("tSave").click();
    const after = JSON.parse(w.localStorage.getItem("wb_planbench_todos") || "[]");
    addOk = after.some((t) => t.title === "本地测试待办");
  } catch (e) {
    dom._vcErrs.push("local add todo: " + e);
  }
  results.local = {
    badge,
    embedded,
    seeded:
      lsPlans.length > 0 &&
      lsTodos.length > 0 &&
      lsHabits.length > 0 &&
      lsLedger.length > 0 &&
      lsFocus.length > 0,
    addPersist: addOk,
    errs: dom._vcErrs.slice(),
    pass:
      badge === "本地模式" &&
      embedded === false &&
      lsPlans.length > 0 &&
      lsHabits.length > 0 &&
      lsLedger.length > 0 &&
      lsFocus.length > 0 &&
      addOk &&
      dom._vcErrs.length === 0,
  };
  dom.window.close();
}

async function testBridge() {
  const bridgePlans = [
    {
      id: "bp1",
      title: "内嵌计划A",
      cat: "work",
      cycle: "daily",
      period: "2026-08-13",
      pri: "P1",
      status: "pending",
      progress: 0,
      note: "",
      created_at: "2026-08-13",
      updated_at: "2026-08-13",
      done_at: null,
    },
  ];
  const dom = makeDom({
    url: "file:///x/plans_web.html",
    qt: true,
    qwebchannel: true,
    bridgePlans,
  });
  await wait(150);
  const w = dom.window;
  const badge = w.document.getElementById("storeBadge").textContent;
  const embedded = w.document.body.classList.contains("embedded");
  const planText = w.document.getElementById("planList").textContent;
  // 完成该计划 -> 应写回 bridge.save
  let writeBack = false;
  try {
    const chk = w.document.querySelector('.check[data-act="toggle"][data-type="plan"]');
    chk.click();
    const saved = JSON.parse(w.__bridgeMock._plans || "[]");
    writeBack = saved.some((p) => p.id === "bp1" && p.status === "done");
  } catch (e) {
    dom._vcErrs.push("bridge complete: " + e);
  }
  // 内嵌应隐藏新增/导入/导出/清空（embedded 类已加，按钮在该选择器内）
  const hiddenSel = ["btnAddPlan", "btnAddTodo", "btnExport", "btnImport", "btnClear"].every(
    (id) => {
      const el = w.document.getElementById(id);
      return el && el.closest && w.document.body.classList.contains("embedded");
    }
  );
  results.bridge = {
    badge,
    embedded,
    renderedPlan: planText.indexOf("内嵌计划A") >= 0,
    writeBack,
    embeddedGatingApplied: hiddenSel,
    errs: dom._vcErrs.slice(),
    pass:
      badge === "已连接桌宠" &&
      embedded === true &&
      planText.indexOf("内嵌计划A") >= 0 &&
      writeBack &&
      dom._vcErrs.length === 0,
  };
  dom.window.close();
}

async function testHttp() {
  // 1) 经 node 直接给本地服务写入初始数据
  const initPlan = {
    id: "hp1",
    title: "网页计划A",
    cat: "study",
    cycle: "daily",
    period: "2026-08-13",
    pri: "P0",
    status: "pending",
    progress: 0,
    note: "",
    created_at: "2026-08-13",
    updated_at: "2026-08-13",
    done_at: null,
  };
  const initTodo = {
    id: "ht1",
    title: "网页待办A",
    cat: "life",
    pri: "P1",
    due: "2026-08-13",
    status: "pending",
    note: "",
    created_at: "2026-08-13",
    done_at: null,
  };
  await nodeReq("POST", "/api/plans", [initPlan]);
  await nodeReq("POST", "/api/todos", [initTodo]);
  // 新模块：先写入初始数据
  const initHabit = { id: "hh1", title: "网页习惯A", cat: "diet", created_at: "2026-08-13", records: {} };
  const initLedger = { id: "hl1", title: "网页账目A", cat: "life", kind: "expense", amount: 12.5, date: "2026-08-13", note: "", created_at: "2026-08-13" };
  const initFocus = { id: "hf1", minutes: 25, label: "网页专注A", date: "2026-08-13", created_at: "2026-08-13" };
  const initReview = { id: "hr1", periodType: "month", period: "2026-08", text: "网页复盘A", created_at: "2026-08-13", updated_at: "2026-08-13" };
  await nodeReq("POST", "/api/habits", [initHabit]);
  await nodeReq("POST", "/api/ledger", [initLedger]);
  await nodeReq("POST", "/api/focus", [initFocus]);
  await nodeReq("POST", "/api/review", [initReview]);

  // 2) 以 http 模式（来自 127.0.0.1）加载页面
  const dom = makeDom({
    url: `${ORIGIN}/plans_web.html`,
    fetch: pageFetch,
  });
  await wait(450);
  const w = dom.window;
  const badge = w.document.getElementById("storeBadge").textContent;
  const planText = w.document.getElementById("planList").textContent;
  const readFromServer = planText.indexOf("网页计划A") >= 0;

  // 3) 完成计划 -> 写回服务
  let writeBackPlan = false;
  try {
    const chk = w.document.querySelector('.check[data-act="toggle"][data-type="plan"]');
    chk.click();
    await wait(250);
    const res = await nodeReq("GET", "/api/plans");
    const arr = JSON.parse(res.body);
    writeBackPlan = arr.some((p) => p.id === "hp1" && p.status === "done");
  } catch (e) {
    dom._vcErrs.push("http complete: " + e);
  }

  // 4) 新增待办 -> 写回服务
  let addTodoPersist = false;
  try {
    w.document.getElementById("btnAddTodo").click();
    w.document.getElementById("tTitle").value = "网页新增待办";
    w.document.getElementById("tSave").click();
    await wait(250);
    const res = await nodeReq("GET", "/api/todos");
    const arr = JSON.parse(res.body);
    addTodoPersist = arr.some((t) => t.title === "网页新增待办");
  } catch (e) {
    dom._vcErrs.push("http add todo: " + e);
  }

  // 5) 新增习惯 -> 写回服务
  let addHabitPersist = false;
  try {
    w.document.getElementById("btnAddHabit").click();
    w.document.getElementById("hTitle").value = "网页新增习惯";
    w.document.getElementById("hSave").click();
    await wait(250);
    const res = await nodeReq("GET", "/api/habits");
    const arr = JSON.parse(res.body);
    addHabitPersist = arr.some((h) => h.title === "网页新增习惯");
  } catch (e) {
    dom._vcErrs.push("http add habit: " + e);
  }

  // 6) 新增账目 -> 写回服务
  let addLedgerPersist = false;
  try {
    w.document.getElementById("btnAddLedger").click();
    w.document.getElementById("lTitle").value = "网页新增账目";
    w.document.getElementById("lAmount").value = "88.8";
    w.document.getElementById("lSave").click();
    await wait(250);
    const res = await nodeReq("GET", "/api/ledger");
    const arr = JSON.parse(res.body);
    addLedgerPersist = arr.some((e) => e.title === "网页新增账目");
  } catch (e) {
    dom._vcErrs.push("http add ledger: " + e);
  }

  // 7) 专注记一笔 -> 写回服务
  let focusPersist = false;
  try {
    w.document.getElementById("btnFocusLog").click();
    await wait(250);
    const res = await nodeReq("GET", "/api/focus");
    const arr = JSON.parse(res.body);
    focusPersist = arr.some((f) => f.label === "手动记录");
  } catch (e) {
    dom._vcErrs.push("http focus log: " + e);
  }

  // 8) 复盘保存 -> 写回服务
  let reviewPersist = false;
  try {
    w.document.getElementById("reviewText").value = "网页复盘新增";
    w.document.getElementById("btnReviewSave").click();
    await wait(250);
    const res = await nodeReq("GET", "/api/review");
    const arr = JSON.parse(res.body);
    reviewPersist = arr.some((r) => r.text === "网页复盘新增");
  } catch (e) {
    dom._vcErrs.push("http review: " + e);
  }

  results.http = {
    badge,
    readFromServer,
    writeBackPlan,
    addTodoPersist,
    addHabitPersist,
    addLedgerPersist,
    focusPersist,
    reviewPersist,
    errs: dom._vcErrs.slice(),
    pass:
      badge === "网页版 · 已同步" &&
      readFromServer &&
      writeBackPlan &&
      addTodoPersist &&
      addHabitPersist &&
      addLedgerPersist &&
      focusPersist &&
      reviewPersist &&
      dom._vcErrs.length === 0,
  };
  dom.window.close();
}

let serverProc = null;
async function startServer() {
  return new Promise((resolve, reject) => {
    serverProc = require("child_process").spawn(PY, [RUNNER], { stdio: ["ignore", "pipe", "pipe"] });
    let out = "";
    const onData = (d) => {
      out += d.toString();
      if (out.indexOf("http://") >= 0) resolve();
    };
    serverProc.stdout.on("data", onData);
    serverProc.stderr.on("data", (d) => process.stderr.write("[server] " + d));
    serverProc.on("error", reject);
    setTimeout(() => reject(new Error("server start timeout, out=" + out)), 8000);
  });
}

(async () => {
  try {
    await startServer();
    await testLocal();
    await testBridge();
    await testHttp();
  } catch (e) {
    results.fatal = String(e && e.stack ? e.stack : e);
  } finally {
    if (serverProc) serverProc.kill();
  }
  const allPass =
    results.local &&
    results.local.pass &&
    results.bridge &&
    results.bridge.pass &&
    results.http &&
    results.http.pass &&
    !results.fatal;
  console.log(JSON.stringify(results, null, 2));
  console.log(allPass ? "ALL PASS" : "SOME FAIL");
  process.exit(allPass ? 0 : 1);
})();
