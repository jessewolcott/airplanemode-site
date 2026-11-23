// Shared by every language's page (index.html, es/, fr/, it/, zh/, ja/, vi/).
// The page's own UI strings come from its <script type="application/json" id="ui-strings">,
// which tools/build_i18n.py translates for each language, so the strings always match
// document.documentElement.lang.
(() => {
  // This file lives in assets/, so the site root is one level up from it. That keeps the
  // command right on the translated pages (/es/ etc.) as well as on /.
  const SITE_ROOT = new URL("..", document.currentScript.src);
  // Served over https (its own server): the command points back at this site's install.sh.
  // Anywhere else (local preview over http): the file in the GitHub repo.
  const FALLBACK_URL = "https://raw.githubusercontent.com/jessewolcott/airplanemode-site/main/install.sh";
  const installUrl = SITE_ROOT.protocol === "https:" ? new URL("install.sh", SITE_ROOT).href : FALLBACK_URL;
  const T = JSON.parse(document.getElementById("ui-strings").textContent);
  const LANG = document.documentElement.lang;
  const DEVICES = {
    "nanopi-r6s": { label: T["device.nanopi-r6s"], profile: T["profile.nanopi-r6s"], ip: "192.168.2.1" },
    "glinet": { label: T["device.glinet"], profile: T["profile.glinet"], ip: "192.168.8.1" },
  };
  // localStorage keys (am.device, am.opts, am.done, am.lang, am.langHint) are shared by all
  // languages: step ids and option names are the same on every page, so progress carries over.
  const store = {
    get(k, d) { try { const v = localStorage.getItem("am." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem("am." + k, JSON.stringify(v)); } catch {} },
  };
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // Fill {name} placeholders. Values are HTML (already escaped by the caller); the string isn't.
  const fmt = (s, vars = {}) => esc(s).replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));

  // ---- the config tool ----
  const tool = $("#tool-tpl").content.firstElementChild.cloneNode(true);
  const f = { lan: $("#t-lan", tool), vpn: $("#t-vpn", tool), rebind: $("#t-rebind", tool), wan: $("#t-wan", tool), dir: $("#t-dir", tool) };
  const saved = store.get("opts", {});
  for (const [k, el] of Object.entries(f)) {
    if (saved[k] === undefined) continue;
    if (el.type === "checkbox") el.checked = saved[k]; else el.value = saved[k];
  }
  let device = store.get("device", "nanopi-r6s");
  if (!DEVICES[device]) device = "nanopi-r6s";

  const ipOk = v => /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/.test(v);
  const nameOk = v => /^[A-Za-z0-9_.-]+$/.test(v);
  const dirOk = v => /^\/[A-Za-z0-9_./-]*$/.test(v);

  function render() {
    const lan = f.lan.value.trim(), wan = f.wan.value.trim(), dir = f.dir.value.trim();
    f.lan.setAttribute("aria-invalid", lan && !ipOk(lan));
    f.wan.setAttribute("aria-invalid", wan && !nameOk(wan));
    f.dir.setAttribute("aria-invalid", dir && !dirOk(dir));
    const opts = [];
    // detection is reliable on both, but say it out loud so the command documents itself
    opts.push(["--device", device]);
    if (lan && ipOk(lan)) opts.push(["--lan-ip", lan]);
    if (!f.vpn.checked) opts.push(["--no-wireguard"]);
    if (!f.rebind.checked) opts.push(["--keep-rebind"]);
    if (wan && nameOk(wan) && wan !== "wan") opts.push(["--wan", wan]);
    if (dir && dirOk(dir) && dir !== "/opt/airplanemode") opts.push(["--dir", dir]);

    // OpenWrt's built-in wget can't talk TLS to GitHub; curl can, so make sure it's there first.
    const url = installUrl;
    const prep = "command -v curl >/dev/null || { opkg update && opkg install curl || apk add -U curl; } >/dev/null 2>&1";
    const plain = `${prep}\ncurl -fsSL ${url} | sh -s -- ${opts.map(o => o.join(" ")).join(" ")}`;
    $(".t-cmd", tool).innerHTML = `<span class="p"># </span><span class="d">${esc(prep)}</span>\n<span class="p"># </span>curl -fsSL ${esc(url)} | sh -s -- ` +
      opts.map(o => `<span class="o">${esc(o[0])}</span>${o[1] ? " " + esc(o[1]) : ""}`).join(" ");
    $(".t-cmd", tool).dataset.copy = plain;
    $(".tool-dev", tool).textContent = DEVICES[device].label;

    const ip = (lan && ipOk(lan)) ? lan : DEVICES[device].ip;
    const code = s => `<code>${esc(s)}</code>`;
    const does = [
      fmt(T["does.check"]),
      fmt(T["does.download"], { dir: code(dir && dirOk(dir) ? dir : "/opt/airplanemode"), profile: esc(DEVICES[device].profile) }),
      fmt(T["does.login"], { user: code("airplanemode") }),
      fmt(T["does.name"], { name: code("airplane.mode"), ip: esc(ip) }),
      fmt(T[f.rebind.checked ? "does.rebind-off" : "does.rebind-on"]),
      fmt(T[f.vpn.checked ? "does.wireguard" : "does.no-wireguard"]),
      fmt(T[device === "nanopi-r6s" ? "does.apps-model" : "does.apps"]),
      fmt(T["does.password"]),
    ];
    $(".t-does", tool).innerHTML = does.map(d => `<li>${d}</li>`).join("");
    $$(".ssh").forEach(el => { if (el.closest(`.guide[data-device="${device}"]`)) el.textContent = `ssh root@${ip}`; });

    store.set("opts", Object.fromEntries(Object.entries(f).map(([k, el]) => [k, el.type === "checkbox" ? el.checked : el.value])));
  }
  Object.values(f).forEach(el => el.addEventListener("input", render));

  // ---- device tabs ----
  function selectDevice(d) {
    device = d; store.set("device", d);
    $$(".device").forEach(b => b.setAttribute("aria-selected", b.dataset.device === d));
    $$(".guide").forEach(g => g.hidden = g.dataset.device !== d);
    $(`.guide[data-device="${d}"] .tool-slot`).append(tool);
    render(); progress();
  }
  $$(".device").forEach(b => b.addEventListener("click", () => selectDevice(b.dataset.device)));
  $(".devices").addEventListener("keydown", e => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const tabs = $$(".device"), i = tabs.findIndex(t => t.dataset.device === device);
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    selectDevice(next.dataset.device); next.focus();
  });

  // ---- step checklist ----
  const done = new Set(store.get("done", []));
  function progress() {
    const steps = $$(`.guide[data-device="${device}"] li[data-step]`);
    const n = steps.filter(s => done.has(s.dataset.step)).length;
    $("#progText").textContent = T.progress.replace("{n}", n).replace("{total}", steps.length);
    $("#progBar").style.width = (100 * n / steps.length) + "%";
  }
  $$("li[data-step]").forEach(li => {
    const box = $(".step-head input", li);
    box.checked = done.has(li.dataset.step);
    li.classList.toggle("done", box.checked);
    box.addEventListener("change", () => {
      box.checked ? done.add(li.dataset.step) : done.delete(li.dataset.step);
      li.classList.toggle("done", box.checked);
      store.set("done", [...done]); progress();
    });
  });
  $("#reset").addEventListener("click", () => {
    done.clear(); store.set("done", []);
    $$("li[data-step]").forEach(li => { $(".step-head input", li).checked = false; li.classList.remove("done"); });
    progress();
  });

  // ---- copy buttons ----
  document.addEventListener("click", async e => {
    const btn = e.target.closest(".copy");
    if (!btn) return;
    const pre = btn.parentElement.querySelector("pre");
    const text = pre.dataset.copy || pre.textContent.replace(/^#\s*/gm, "");
    try { await navigator.clipboard.writeText(text); }
    catch {
      const r = document.createRange(); r.selectNodeContents(pre);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r); document.execCommand("copy"); s.removeAllRanges();
    }
    btn.textContent = T.copied; btn.classList.add("ok");
    setTimeout(() => { btn.textContent = T.copy; btn.classList.remove("ok"); }, 1600);
  });

  // ---- languages ----
  const langs = $(".langs");
  const langLinks = $$(".langs a[hreflang]");
  langLinks.forEach(a => {
    if (a.hreflang === LANG) a.setAttribute("aria-current", "true");
    // Keep the section: #setup on one language opens #setup on the other.
    a.addEventListener("click", () => {
      store.set("lang", a.hreflang);
      if (/^#[\w-]+$/.test(location.hash)) a.href = a.href.replace(/#.*$/, "") + location.hash;
    });
  });
  document.addEventListener("click", e => { if (langs.open && !langs.contains(e.target)) langs.open = false; });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && langs.open) { langs.open = false; $("summary", langs).focus(); } });

  // A hint (never a redirect) when the browser prefers another language we have, until the
  // visitor picks a language or closes it.
  function preferred() {
    for (const tag of navigator.languages || [navigator.language || ""]) {
      const t = tag.toLowerCase();
      if (t.startsWith("zh")) {
        if (/^zh-(hant|tw|hk|mo)/.test(t)) continue;      // Traditional: we only have Simplified
        return "zh-Hans";
      }
      const hit = langLinks.find(a => a.hreflang === t.split("-")[0]);
      if (hit) return hit.hreflang;
    }
    return null;
  }
  const want = preferred();
  const hint = $("#lang-hint");
  if (want && want !== LANG && !store.get("lang", null) && !store.get("langHint", false)) {
    const a = langLinks.find(l => l.hreflang === want);
    const link = $("a", hint);
    link.href = a.href; link.lang = want; link.textContent = a.dataset.hint;
    link.addEventListener("click", () => { store.set("lang", want); if (/^#[\w-]+$/.test(location.hash)) link.href += location.hash; });
    $("button", hint).addEventListener("click", () => { hint.hidden = true; store.set("langHint", true); });
    hint.hidden = false;
  }

  selectDevice(device);
})();
