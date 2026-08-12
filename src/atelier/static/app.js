(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    backends: [],
    media: [],
    graph: { nodes: {}, edges: [] },
    slots: [],
    selectedId: null,
    paramSchema: {},
  };

  function setStatus(msg) {
    $("status").textContent = msg;
  }

  function showError(err) {
    const el = $("error");
    if (!err) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    const detail = err.detail;
    el.textContent =
      typeof detail === "object" ? JSON.stringify(detail, null, 2) : String(detail || err.message || err);
    el.classList.remove("hidden");
  }

  async function api(path, opts = {}) {
    const res = await fetch(path, opts);
    let body = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) body = await res.json();
    if (!res.ok) {
      const err = new Error("api error");
      err.detail = body?.detail ?? body ?? res.statusText;
      throw err;
    }
    return body;
  }

  function fileUrl(id) {
    return `/api/media/${id}/file`;
  }

  function backendColor(name) {
    return name || "upload";
  }

  function currentBackend() {
    return state.backends.find((b) => b.name === $("backend").value);
  }

  function modeSupported(backend, mode) {
    const c = backend?.capabilities || {};
    return !!c[`supports_${mode}`];
  }

  function refreshModeOptions() {
    const b = currentBackend();
    const modeSel = $("mode");
    for (const opt of modeSel.options) {
      const ok = !b || modeSupported(b, opt.value);
      opt.disabled = !ok;
      opt.hidden = !ok;
    }
    if (modeSel.selectedOptions[0]?.disabled) {
      const first = [...modeSel.options].find((o) => !o.disabled);
      if (first) modeSel.value = first.value;
    }
    renderParams();
  }

  function renderParams() {
    const b = currentBackend();
    const mode = $("mode").value;
    const schema = b?.param_schema || {};
    const box = $("params");
    box.innerHTML = "";
    state.paramSchema = schema;
    for (const [key, def] of Object.entries(schema)) {
      const modes = def.modes || [];
      if (modes.length && !modes.includes(mode)) continue;
      const label = document.createElement("label");
      if (def.type === "string" && def.enum) {
        label.innerHTML = `<span>${key}</span>`;
        const sel = document.createElement("select");
        sel.dataset.param = key;
        for (const v of def.enum) {
          const o = document.createElement("option");
          o.value = v;
          o.textContent = v;
          if (v === def.default) o.selected = true;
          sel.appendChild(o);
        }
        label.appendChild(sel);
      } else if (def.type === "boolean") {
        label.innerHTML = `<span>${key}</span>`;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.dataset.param = key;
        input.checked = !!def.default;
        label.appendChild(input);
      } else if (def.type === "integer" || def.type === "number") {
        label.innerHTML = `<span>${key}</span>`;
        const input = document.createElement("input");
        input.type = "number";
        input.dataset.param = key;
        if (def.default != null) input.value = def.default;
        if (def.minimum != null) input.min = def.minimum;
        if (def.maximum != null) input.max = def.maximum;
        if (def.type === "number") input.step = "any";
        label.appendChild(input);
      } else {
        label.classList.add("span2");
        label.innerHTML = `<span>${key}</span>`;
        const input = document.createElement("input");
        input.type = "text";
        input.dataset.param = key;
        input.value = def.default ?? "";
        if (def.description) input.title = def.description;
        label.appendChild(input);
      }
      box.appendChild(label);
    }
  }

  function collectParams() {
    const params = {};
    for (const el of $("params").querySelectorAll("[data-param]")) {
      const key = el.dataset.param;
      const def = state.paramSchema[key] || {};
      let v = el.type === "checkbox" ? el.checked : el.value;
      if (def.type === "integer") v = v === "" ? def.default : parseInt(v, 10);
      else if (def.type === "number") v = v === "" ? def.default : parseFloat(v);
      else if (def.type === "boolean") v = !!v;
      if (v !== "" && v != null && !(typeof v === "number" && Number.isNaN(v))) params[key] = v;
    }
    return params;
  }

  function renderSlots() {
    const list = $("slotList");
    list.innerHTML = "";
    state.slots.forEach((id, i) => {
      const node = state.media.find((m) => m.id === id);
      const row = document.createElement("div");
      row.className = "slot";
      const kind = node?.kind === "video" ? "Video" : "Image";
      const media =
        node?.kind === "video"
          ? `<video src="${fileUrl(id)}" muted></video>`
          : `<img src="${fileUrl(id)}" alt="" />`;
      row.innerHTML = `
        ${media}
        <span class="idx">@${kind}${i + 1}</span>
        <span>${(node?.prompt || node?.original_name || id).slice(0, 40)}</span>
        <button type="button" class="rm ghost" data-i="${i}">×</button>`;
      row.querySelector(".rm").onclick = () => {
        state.slots.splice(i, 1);
        renderSlots();
      };
      list.appendChild(row);
    });
  }

  function selectMedia(id) {
    state.selectedId = id;
    const node = state.media.find((m) => m.id === id);
    const stage = $("preview");
    const meta = $("previewMeta");
    const dl = $("download");
    const use = $("useAsInput");
    if (!node) {
      stage.className = "preview-stage empty";
      stage.textContent = "Select or generate media";
      meta.textContent = "";
      dl.classList.add("hidden");
      use.classList.add("hidden");
      return;
    }
    stage.className = "preview-stage";
    stage.innerHTML =
      node.kind === "video"
        ? `<video src="${fileUrl(id)}" controls autoplay loop></video>`
        : `<img src="${fileUrl(id)}" alt="" />`;
    meta.textContent = [
      `id=${node.id}`,
      `backend=${node.backend || "-"}`,
      `kind=${node.kind}`,
      node.prompt ? `prompt=${node.prompt}` : null,
      node.params?.mode ? `mode=${node.params.mode}` : null,
      node.created_at || null,
    ]
      .filter(Boolean)
      .join("\n");
    dl.href = fileUrl(id);
    dl.download = node.original_name || node.filename || id;
    dl.classList.remove("hidden");
    use.classList.remove("hidden");
    use.onclick = () => {
      if (!state.slots.includes(id)) state.slots.push(id);
      renderSlots();
    };
    renderGallery();
    renderTree();
  }

  function renderGallery() {
    const g = $("gallery");
    g.innerHTML = "";
    for (const m of state.media) {
      const el = document.createElement("div");
      el.className = "thumb" + (m.id === state.selectedId ? " selected" : "");
      el.innerHTML =
        (m.kind === "video"
          ? `<video src="${fileUrl(m.id)}" muted></video>`
          : `<img src="${fileUrl(m.id)}" alt="" />`) +
        `<span class="badge ${backendColor(m.backend)}">${m.backend || m.kind}</span>`;
      el.onclick = () => selectMedia(m.id);
      el.ondblclick = () => {
        if (!state.slots.includes(m.id)) state.slots.push(m.id);
        renderSlots();
      };
      g.appendChild(el);
    }
  }

  function renderTree() {
    const root = $("tree");
    const nodes = state.graph.nodes || {};
    const edges = state.graph.edges || [];
    const list = Object.values(nodes);
    if (!list.length) {
      root.innerHTML = '<div class="tree-empty">No nodes yet</div>';
      return;
    }
    const children = {};
    const hasParent = new Set();
    for (const e of edges) {
      (children[e.source_id] ||= []).push(e.target_id);
      hasParent.add(e.target_id);
    }
    const roots = list.filter((n) => !hasParent.has(n.id));
    const shown = new Set();

    function renderNode(id, depth) {
      if (shown.has(id)) return "";
      shown.add(id);
      const n = nodes[id];
      if (!n) return "";
      const active = id === state.selectedId ? " active" : "";
      const title = `${n.backend || "?"} · ${n.kind} · ${id.slice(0, 8)}`;
      const prompt = (n.prompt || n.original_name || "").slice(0, 80);
      let html = `<div class="tree-node${active}" data-id="${id}" style="margin-left:${depth * 8}px">
        <div class="t-title badge ${backendColor(n.backend)}">${title}</div>
        <div class="t-prompt">${escapeHtml(prompt)}</div>
      </div>`;
      for (const cid of children[id] || []) html += renderNode(cid, depth + 1);
      return html;
    }

    let html = "";
    for (const r of roots.sort((a, b) => (a.created_at < b.created_at ? 1 : -1))) {
      html += renderNode(r.id, 0);
    }
    // orphans already shown via roots; any remaining
    for (const n of list) {
      if (!shown.has(n.id)) html += renderNode(n.id, 0);
    }
    root.innerHTML = html;
    root.querySelectorAll(".tree-node").forEach((el) => {
      el.onclick = () => selectMedia(el.dataset.id);
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function refresh() {
    const [media, graph, backends] = await Promise.all([
      api("/api/media"),
      api("/api/graph"),
      api("/api/backends"),
    ]);
    state.media = media;
    state.graph = graph;
    state.backends = backends;
    const sel = $("backend");
    const prev = sel.value;
    sel.innerHTML = "";
    for (const b of backends) {
      const o = document.createElement("option");
      o.value = b.name;
      o.textContent = `${b.name}${b.available ? "" : " (unavailable)"}`;
      sel.appendChild(o);
    }
    if (prev && backends.some((b) => b.name === prev)) sel.value = prev;
    else {
      const prefer = backends.find((b) => b.available) || backends[0];
      if (prefer) sel.value = prefer.name;
    }
    refreshModeOptions();
    renderGallery();
    renderTree();
    renderSlots();
    if (state.selectedId) selectMedia(state.selectedId);
  }

  $("backend").onchange = refreshModeOptions;
  $("mode").onchange = renderParams;
  $("clearSlots").onclick = () => {
    state.slots = [];
    renderSlots();
  };

  async function pollJob(jobId) {
    const started = Date.now();
    const maxMs = 15 * 60 * 1000;
    while (Date.now() - started < maxMs) {
      const job = await api(`/api/jobs/${jobId}`);
      setStatus(`job ${job.status}…`);
      if (job.status === "done") return job;
      if (job.status === "failed") {
        const err = new Error("job failed");
        err.detail = job.error || job;
        throw err;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
    throw Object.assign(new Error("job timeout"), { detail: "polling timed out" });
  }

  $("generate").onclick = async () => {
    showError(null);
    const btn = $("generate");
    btn.disabled = true;
    setStatus("generating…");
    try {
      const mode = $("mode").value;
      const body = {
        mode,
        backend: $("backend").value,
        prompt: $("prompt").value,
        media_ids: [...state.slots],
        input_slots: [...state.slots],
        params: collectParams(),
        resolve_at_refs: true,
        // video auto-async on server; force async for long image jobs if needed
        async_job: mode === "t2v" || mode === "i2v",
      };
      const res = await api("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      let nodes = res.nodes || [];
      if (res.job_id) {
        setStatus(`queued ${res.job_id.slice(0, 8)}…`);
        const job = await pollJob(res.job_id);
        nodes = job.nodes || [];
      }
      await refresh();
      if (nodes[0]) selectMedia(nodes[0].id);
      setStatus("done");
    } catch (e) {
      showError(e);
      setStatus("error");
    } finally {
      btn.disabled = false;
    }
  };

  $("file").onchange = async (ev) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    showError(null);
    setStatus("uploading…");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const node = await api("/api/media/upload", { method: "POST", body: fd });
      await refresh();
      selectMedia(node.id);
      if (!state.slots.includes(node.id)) {
        state.slots.push(node.id);
        renderSlots();
      }
      setStatus("uploaded");
    } catch (e) {
      showError(e);
      setStatus("error");
    } finally {
      ev.target.value = "";
    }
  };

  refresh().catch((e) => {
    showError(e);
    setStatus("error");
  });
})();
