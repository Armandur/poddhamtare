// poddhamtare webbgränssnitt. All text går via textContent, aldrig innerHTML med data.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const logEl = $("log");
  const STATUS = { klar: "Klar", saknas: "Saknas", tagga: "Taggas om" };
  const PLURAL = { klar: "klara", saknas: "saknas", tagga: "ska taggas om" };
  const SHOW_STEP = 10;
  const RUNS_STEP = 15;
  let runsShown = RUNS_STEP;
  let episodeData = null;
  let shown = SHOW_STEP;

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function lineClass(line) {
    if (/ (FEL|PROBLEM) /.test(" " + line + " ")) return "err";
    if (/ (Varning|NOTERA) |hoppar över/.test(" " + line + " ")) return "warn";
    return "";
  }

  function fillLog(pre, lines) {
    pre.textContent = "";
    for (const line of lines) pre.appendChild(el("div", lineClass(line), line));
  }

  function fmtTime(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" });
  }

  function fmtDuration(s) {
    if (!s) return "";
    const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    return h ? `${h} h ${m} min` : `${m} min`;
  }

  function describe(run) {
    const a = run.args || [];
    let what = a[0] === "retag" ? "Kontroll av gamla filer" : "Hämtning";
    if (a.includes("--dry-run") || a[0] === "retag") what += ", torrkörning";
    return `${what} (${run.trigger === "schema" ? "schema" : "manuell"})`;
  }

  // ---- Status och Kör nu ----
  function setRunning(running) {
    $("run-btn").disabled = running;
    $("run-btn").setAttribute("aria-busy", running ? "true" : "false");
    const st = $("state");
    st.textContent = running ? "Körning pågår" : "Väntar";
    st.className = "status" + (running ? " running" : "");
  }

  async function loadStatus() {
    try {
      const r = await fetch("/api/status");
      const s = await r.json();
      setRunning(s.running);
      $("schedule-info").textContent =
        `Schema: ${s.schedule}. Nästa körning: ${fmtTime(s.next_run) || "okänd"}.`;
    } catch (e) {
      $("schedule-info").textContent = "Kunde inte läsa status.";
    }
  }

  const form = $("run-form");
  form.kind.addEventListener("change", () => {
    const retag = form.kind.value === "retag";
    form.dry_run.checked = retag || form.dry_run.checked;
    form.dry_run.disabled = retag;
  });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const msg = $("run-status");
    $("run-btn").disabled = true;
    msg.className = "status";
    msg.textContent = "Startar...";
    try {
      const r = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: form.kind.value, dry_run: form.dry_run.checked }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.error || "Körningen kunde inte startas.");
      msg.textContent = "Körningen har startat. Följ loggen nedan.";
    } catch (e) {
      msg.className = "status error";
      msg.textContent = e.message;
      $("run-btn").disabled = false;
    }
  });

  // ---- Livelogg via SSE ----
  function append(text, cls) {
    logEl.appendChild(el("div", cls, text));
    if ($("autoscroll").checked) logEl.scrollTop = logEl.scrollHeight;
  }
  $("clear-btn").addEventListener("click", () => { logEl.textContent = ""; });

  const es = new EventSource("/api/events");
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.event === "start") {
      setRunning(true);
      append(`== ${describe(msg)} startade ${fmtTime(msg.started)} ==`, "start");
    } else if (msg.event === "log") {
      append(msg.line, lineClass(msg.line));
    } else if (msg.event === "end") {
      append(`== Klar, slutkod ${msg.exit_code} ==`, msg.exit_code === 0 ? "end" : "err");
      setRunning(false);
      $("run-status").textContent = "";
      loadRuns();
      loadEpisodes(false);
      loadStatus();
    }
  };

  // ---- Avsnitt ----
  function matches(ep) {
    const f = $("ep-filter").value;
    if (f && ep.status !== f) return false;
    const q = $("ep-search").value.trim().toLowerCase();
    if (!q) return true;
    return ep.title.toLowerCase().includes(q) || String(ep.num).padStart(4, "0").includes(q);
  }

  function renderEpisodes() {
    const box = $("episodes");
    box.textContent = "";
    box.setAttribute("aria-busy", "false");
    for (const show of episodeData.shows) {
      const sec = el("div", "show-section");
      sec.appendChild(el("h3", null, show.name));
      if (show.error) sec.appendChild(el("p", "alert", show.error));
      for (const p of show.problems) sec.appendChild(el("p", "alert", p));
      for (const n of show.notes) sec.appendChild(el("p", "muted", n));
      const eps = show.episodes.filter(matches);
      const counts = {};
      for (const e of show.episodes) counts[e.status] = (counts[e.status] || 0) + 1;
      if (show.episodes.length) {
        const parts = Object.keys(STATUS).filter((k) => counts[k]).map((k) => `${counts[k]} ${PLURAL[k]}`);
        sec.appendChild(el("p", "muted", `${show.episodes.length} avsnitt i flödet: ${parts.join(", ")}.`));
      }
      const ul = el("ul", "ep-list");
      for (const ep of eps.slice(0, shown)) {
        const li = el("li", "ep");
        li.appendChild(el("span", "ep-num", String(ep.num).padStart(4, "0")));
        li.appendChild(el("span", "ep-title", ep.title));
        li.appendChild(el("span", "badge " + ep.status, STATUS[ep.status] || ep.status));
        li.appendChild(el("span", "ep-meta", [ep.date, fmtDuration(ep.duration_s)].filter(Boolean).join(" · ")));
        li.appendChild(el("span", "ep-file", ep.filename));
        ul.appendChild(li);
      }
      sec.appendChild(ul);
      if (eps.length > shown) {
        const b = el("button", "secondary more", `Visa fler (${eps.length - shown} till)`);
        b.type = "button";
        b.addEventListener("click", () => { shown += 50; renderEpisodes(); });
        sec.appendChild(b);
      } else if (!eps.length && show.episodes.length) {
        sec.appendChild(el("p", "muted", "Inga avsnitt matchar."));
      }
      box.appendChild(sec);
    }
  }

  async function loadEpisodes(refresh) {
    const meta = $("ep-meta");
    meta.textContent = "Uppdaterar...";
    $("ep-refresh").disabled = true;
    try {
      const r = await fetch("/api/episodes" + (refresh ? "?refresh=1" : ""));
      if (!r.ok) throw new Error();
      episodeData = await r.json();
      renderEpisodes();
      meta.textContent = "Läst " + new Date(episodeData.fetched_at * 1000).toLocaleTimeString("sv-SE", { timeStyle: "short" });
    } catch (e) {
      meta.textContent = "Kunde inte läsa avsnitten.";
    } finally {
      $("ep-refresh").disabled = false;
    }
  }
  $("ep-refresh").addEventListener("click", () => loadEpisodes(true));
  $("ep-search").addEventListener("input", () => { shown = SHOW_STEP; if (episodeData) renderEpisodes(); });
  $("ep-filter").addEventListener("change", () => { shown = SHOW_STEP; if (episodeData) renderEpisodes(); });

  // ---- Körningshistorik ----
  function result(run) {
    if (run.exit_code === null || run.exit_code === undefined) return ["Avbruten", "err"];
    const parts = [];
    if (run.hamtade) parts.push(`${run.hamtade} hämtade`);
    if (run.taggade) parts.push(`${run.taggade} taggade`);
    if (run.problem) parts.push(`${run.problem} problem`);
    if (run.fel) parts.push(`${run.fel} fel`);
    const bad = run.exit_code !== 0 || run.fel || run.problem;
    return [parts.join(", ") || (bad ? "Misslyckades" : "Inget nytt"), bad ? "err" : "ok"];
  }

  async function loadRuns() {
    const box = $("runs");
    try {
      const r = await fetch("/api/runs");
      const data = await r.json();
      box.textContent = "";
      if (!data.runs.length) { box.appendChild(el("p", "muted", "Inga körningar ännu.")); return; }
      for (const run of data.runs.slice(0, runsShown)) {
        const [text, cls] = result(run);
        const d = el("details", "run" + (cls === "err" ? " failed" : ""));
        const s = el("summary");
        s.appendChild(el("span", "when", fmtTime(run.started)));
        s.appendChild(el("span", "what", describe(run)));
        s.appendChild(el("span", "result " + cls, text));
        d.appendChild(s);
        const pre = el("pre", "log", "Laddar...");
        d.appendChild(pre);
        d.addEventListener("toggle", async () => {
          if (!d.open || d.dataset.loaded) return;
          try {
            const full = await (await fetch("/api/runs/" + encodeURIComponent(run.id))).json();
            fillLog(pre, full.lines.length ? full.lines : ["(ingen utskrift)"]);
            d.dataset.loaded = "1";
          } catch (e) {
            pre.textContent = "Kunde inte läsa loggen.";
          }
        });
        box.appendChild(d);
      }
      if (data.runs.length > runsShown) {
        const b = el("button", "secondary more", `Visa äldre (${data.runs.length - runsShown} till)`);
        b.type = "button";
        b.addEventListener("click", () => { runsShown += 50; loadRuns(); });
        box.appendChild(b);
      }
    } catch (e) {
      box.textContent = "";
      box.appendChild(el("p", "muted", "Kunde inte läsa historiken."));
    }
  }

  loadStatus();
  loadEpisodes(false);
  loadRuns();
})();
