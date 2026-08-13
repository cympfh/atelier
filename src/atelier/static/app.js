(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    backends: [],
    media: [],
    graph: { nodes: {}, edges: [] },
    slots: [],
    selectedId: null,
    paramSchema: {},
    lineages: [],
    currentLineage: null,
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

  const MAX_IMAGE_EDGE = 2048;

  function modeSupported(backend, mode) {
    const c = backend?.capabilities || {};
    return !!c[`supports_${mode}`];
  }

  function outputKind() {
    const el = document.querySelector('input[name="outputKind"]:checked');
    return el ? el.value : "image";
  }

  /** Videos are only valid sources for → Video (mode v2v). */
  function canUseAsInput(node) {
    if (!node) return false;
    if (node.kind === "image") return true;
    if (node.kind === "video") return outputKind() === "video";
    return false;
  }

  function slotsHaveVideo() {
    return state.slots.some((id) => {
      const n = state.media.find((m) => m.id === id);
      return n && n.kind === "video";
    });
  }

  function addToSlots(id) {
    const node = state.media.find((m) => m.id === id);
    if (!canUseAsInput(node)) {
      showError({
        detail:
          node?.kind === "video"
            ? "Video can only be used as input when Output is → Video (video edit)"
            : "Cannot use this media as input",
      });
      return false;
    }
    if (!state.slots.includes(id)) state.slots.push(id);
    // Drop videos if user later switches to → Image
    pruneSlotsForOutput();
    return true;
  }

  function pruneSlotsForOutput() {
    if (outputKind() === "image") {
      state.slots = state.slots.filter((id) => {
        const n = state.media.find((m) => m.id === id);
        return n && n.kind === "image";
      });
    }
  }

  /** Resolve t2i/i2i/t2v/i2v/v2v from output kind + input slots. */
  function resolvedMode() {
    const out = outputKind(); // image | video
    const hasInput = state.slots.length > 0;
    if (out === "video") {
      if (!hasInput) return "t2v";
      return slotsHaveVideo() ? "v2v" : "i2v";
    }
    return hasInput ? "i2i" : "t2i";
  }

  function refreshModeOptions() {
    const b = currentBackend();
    const radios = [...document.querySelectorAll('input[name="outputKind"]')];
    for (const radio of radios) {
      const kind = radio.value;
      let ok = true;
      if (b) {
        if (kind === "image") {
          ok = modeSupported(b, "t2i") || modeSupported(b, "i2i");
        } else {
          ok =
            modeSupported(b, "t2v") ||
            modeSupported(b, "i2v") ||
            modeSupported(b, "v2v");
        }
      }
      radio.disabled = !ok;
      radio.closest(".radio")?.classList.toggle("disabled", !ok);
    }
    const checked = radios.find((r) => r.checked);
    if (checked?.disabled) {
      const first = radios.find((r) => !r.disabled);
      if (first) first.checked = true;
    }
    updateModeHint();
    renderParams();
  }

  function updateModeHint() {
    const mode = resolvedMode();
    const b = currentBackend();
    const ok = !b || modeSupported(b, mode);
    const src = state.slots.length ? "Image" : "Text";
    const dst = outputKind() === "video" ? "Video" : "Image";
    $("modeHint").textContent = ok
      ? `mode: ${mode} · ${src} → ${dst} (auto)`
      : `mode: ${mode} · unsupported on ${b?.name || "?"}`;
    $("modeHint").style.color = ok ? "" : "var(--danger)";
  }

  function renderParams(preset) {
    const b = currentBackend();
    const mode = resolvedMode();
    const schema = b?.param_schema || {};
    const box = $("params");
    box.innerHTML = "";
    state.paramSchema = schema;
    const values = preset && typeof preset === "object" ? preset : {};
    for (const [key, def] of Object.entries(schema)) {
      const modes = def.modes || [];
      if (modes.length && !modes.includes(mode)) continue;
      const label = document.createElement("label");
      const hasPreset = Object.prototype.hasOwnProperty.call(values, key);
      if (def.type === "string" && def.enum) {
        label.innerHTML = `<span>${key}</span>`;
        const sel = document.createElement("select");
        sel.dataset.param = key;
        for (const v of def.enum) {
          const o = document.createElement("option");
          o.value = v;
          o.textContent = v;
          if (hasPreset ? v === values[key] : v === def.default) o.selected = true;
          sel.appendChild(o);
        }
        label.appendChild(sel);
      } else if (def.type === "boolean") {
        label.innerHTML = `<span>${key}</span>`;
        const input = document.createElement("input");
        input.type = "checkbox";
        input.dataset.param = key;
        input.checked = hasPreset ? !!values[key] : !!def.default;
        label.appendChild(input);
      } else if (def.type === "integer" || def.type === "number") {
        label.innerHTML = `<span>${key}</span>`;
        const input = document.createElement("input");
        input.type = "number";
        input.dataset.param = key;
        if (hasPreset) input.value = values[key];
        else if (def.default != null) input.value = def.default;
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
        input.value = hasPreset ? values[key] ?? "" : (def.default ?? "");
        if (def.description) input.title = def.description;
        label.appendChild(input);
      }
      box.appendChild(label);
    }
  }

  function setOutputKind(kind) {
    const radio = document.querySelector(`input[name="outputKind"][value="${kind}"]`);
    if (radio && !radio.disabled) radio.checked = true;
    pruneSlotsForOutput();
  }

  /** Restore compose panel from a generated node's prompt / parents / params. */
  function restoreSetup(node) {
    if (!node) return;
    // Backend
    if (node.backend && node.backend !== "upload") {
      const sel = $("backend");
      if ([...sel.options].some((o) => o.value === node.backend)) {
        sel.value = node.backend;
      }
    }
    // Output kind from media kind or stored mode
    const mode = node.params?.mode;
    if (mode === "t2v" || mode === "i2v" || mode === "v2v" || node.kind === "video") {
      setOutputKind("video");
    } else {
      setOutputKind("image");
    }
    // Inputs used for generation
    const parents = (node.parent_ids || []).filter((pid) => state.media.some((m) => m.id === pid));
    state.slots = [...parents];
    // Prompt (already stripped of @refs at generate time — fine to restore as-is)
    $("prompt").value = node.prompt || "";
    refreshModeOptions();
    renderSlots();
    // Re-apply after mode/backend settle
    const { mode: _m, ...rest } = node.params || {};
    renderParams(rest);
    updateModeHint();
    setStatus("setup restored");
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
        updateModeHint();
        renderParams();
      };
      list.appendChild(row);
    });
    updateModeHint();
  }

  function resizeImageFile(file, maxEdge = MAX_IMAGE_EDGE) {
    return new Promise((resolve, reject) => {
      if (!file.type.startsWith("image/") || file.type === "image/gif") {
        resolve(file);
        return;
      }
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        const w = img.naturalWidth || img.width;
        const h = img.naturalHeight || img.height;
        if (w <= maxEdge && h <= maxEdge) {
          resolve(file);
          return;
        }
        const scale = maxEdge / Math.max(w, h);
        const cw = Math.max(1, Math.round(w * scale));
        const ch = Math.max(1, Math.round(h * scale));
        const canvas = document.createElement("canvas");
        canvas.width = cw;
        canvas.height = ch;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, cw, ch);
        const outType = file.type === "image/png" ? "image/png" : "image/jpeg";
        canvas.toBlob(
          (blob) => {
            if (!blob) {
              reject(new Error("resize failed"));
              return;
            }
            const base = file.name.replace(/\.[^.]+$/, "") || "image";
            const ext = outType === "image/png" ? ".png" : ".jpg";
            resolve(new File([blob], base + ext, { type: outType }));
          },
          outType,
          0.92
        );
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        resolve(file);
      };
      img.src = url;
    });
  }

  async function uploadFiles(fileList) {
    const files = [...fileList].filter(Boolean);
    if (!files.length) return;
    showError(null);
    setStatus("uploading…");
    try {
      let lastId = null;
      for (const raw of files) {
        const file = await resizeImageFile(raw);
        const fd = new FormData();
        fd.append("file", file);
        const node = await api("/api/media/upload", { method: "POST", body: fd });
        lastId = node.id;
        // Auto-slot only if valid for current output (videos need → Video)
        if (canUseAsInput(node) && !state.slots.includes(node.id)) {
          state.slots.push(node.id);
        }
      }
      await refresh();
      if (lastId) selectMedia(lastId);
      renderSlots();
      updateModeHint();
      renderParams();
      setStatus(files.length > 1 ? `uploaded ${files.length}` : "uploaded");
    } catch (e) {
      showError(e);
      setStatus("error");
    }
  }

  function isLeafNode(id) {
    const edges = state.graph.edges || [];
    return !edges.some((e) => e.source_id === id);
  }

  function closeLightbox() {
    const lb = $("lightbox");
    if (!lb || lb.classList.contains("hidden")) return;
    const stage = $("lightboxStage");
    // Pause any video before tearing down
    stage.querySelectorAll("video").forEach((v) => {
      try {
        v.pause();
      } catch (_) {}
    });
    stage.innerHTML = "";
    lb.classList.add("hidden");
    lb.hidden = true;
    document.body.classList.remove("lightbox-open");
  }

  function openLightbox(id) {
    const node = state.media.find((m) => m.id === id);
    if (!node) return;
    const lb = $("lightbox");
    const stage = $("lightboxStage");
    stage.innerHTML =
      node.kind === "video"
        ? `<video src="${fileUrl(id)}" controls autoplay loop playsinline></video>`
        : `<img src="${fileUrl(id)}" alt="" />`;
    lb.classList.remove("hidden");
    lb.hidden = false;
    document.body.classList.add("lightbox-open");
    // Focus close for keyboard users
    $("lightboxClose")?.focus();
  }

  function selectMedia(id) {
    state.selectedId = id;
    const node = state.media.find((m) => m.id === id);
    const stage = $("preview");
    const meta = $("previewMeta");
    const dl = $("download");
    const expand = $("expandPreview");
    const use = $("useAsInput");
    const restore = $("restoreSetup");
    const del = $("deleteMedia");
    if (!node) {
      stage.className = "preview-stage empty";
      stage.textContent = "Select or generate media";
      meta.textContent = "";
      dl.classList.add("hidden");
      expand.classList.add("hidden");
      expand.onclick = null;
      use.classList.add("hidden");
      restore.classList.add("hidden");
      del.classList.add("hidden");
      closeLightbox();
      return;
    }
    stage.className = "preview-stage";
    stage.innerHTML =
      node.kind === "video"
        ? `<video src="${fileUrl(id)}" controls autoplay loop></video>`
        : `<img src="${fileUrl(id)}" alt="" />`;
    // Click media to expand (video: only if not interacting with controls — use Expand btn too)
    const mediaEl = stage.querySelector("img, video");
    if (mediaEl) {
      if (mediaEl.tagName === "IMG") {
        mediaEl.onclick = () => openLightbox(id);
        mediaEl.title = "Click to expand";
      } else {
        // Double-click video body opens fullscreen (single click is for controls)
        mediaEl.ondblclick = () => openLightbox(id);
        mediaEl.title = "Double-click to expand";
      }
    }
    meta.textContent = [
      `id=${node.id}`,
      `backend=${node.backend || "-"}`,
      `kind=${node.kind}`,
      node.prompt ? `prompt=${node.prompt}` : null,
      node.params?.mode ? `mode=${node.params.mode}` : null,
      node.parent_ids?.length ? `parents=${node.parent_ids.length}` : null,
      node.created_at || null,
    ]
      .filter(Boolean)
      .join("\n");
    dl.href = fileUrl(id);
    dl.download = node.original_name || node.filename || id;
    dl.classList.remove("hidden");
    expand.classList.remove("hidden");
    expand.onclick = () => openLightbox(id);
    if (canUseAsInput(node)) {
      use.classList.remove("hidden");
      use.onclick = () => {
        showError(null);
        if (addToSlots(id)) {
          renderSlots();
          updateModeHint();
          renderParams();
        }
      };
    } else {
      use.classList.add("hidden");
      use.onclick = null;
    }
    // Show restore when there is something to restore (generated nodes)
    const canRestore =
      node.backend &&
      node.backend !== "upload" &&
      (node.prompt || (node.parent_ids && node.parent_ids.length) || node.params?.mode);
    if (canRestore) {
      restore.classList.remove("hidden");
      restore.onclick = () => restoreSetup(node);
    } else {
      restore.classList.add("hidden");
      restore.onclick = null;
    }
    // Delete: only leaves in the lineage tree
    del.classList.remove("hidden");
    const leaf = isLeafNode(id);
    del.disabled = !leaf;
    del.title = leaf
      ? "Delete this media (leaf)"
      : "Cannot delete: has child generations in the tree";
    del.onclick = leaf
      ? async () => {
          showError(null);
          try {
            const res = await fetch(`/api/media/${id}`, { method: "DELETE" });
            if (!res.ok) {
              let body = null;
              try {
                body = await res.json();
              } catch (_) {}
              const err = new Error("delete failed");
              err.detail = body?.detail ?? res.statusText;
              throw err;
            }
            state.slots = state.slots.filter((s) => s !== id);
            state.selectedId = null;
            await refresh();
            setStatus("deleted");
          } catch (e) {
            showError(e);
            setStatus("error");
          }
        }
      : null;
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
        showError(null);
        if (addToSlots(m.id)) {
          renderSlots();
          updateModeHint();
          renderParams();
        }
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

  function renderLineages() {
    const sel = $("lineageSelect");
    const prev = state.currentLineage?.id;
    sel.innerHTML = "";
    for (const L of state.lineages) {
      const o = document.createElement("option");
      o.value = L.id;
      o.textContent = L.name;
      sel.appendChild(o);
    }
    if (prev && state.lineages.some((L) => L.id === prev)) sel.value = prev;
    else if (state.currentLineage) sel.value = state.currentLineage.id;
    $("lineageName").value = state.currentLineage?.name || "";
  }

  async function refresh() {
    const [media, graph, backends, lineages, current] = await Promise.all([
      api("/api/media"),
      api("/api/graph"),
      api("/api/backends"),
      api("/api/lineages"),
      api("/api/lineages/current"),
    ]);
    state.media = media;
    state.graph = graph;
    state.backends = backends;
    state.lineages = lineages;
    state.currentLineage = current;
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
    renderLineages();
    renderGallery();
    renderTree();
    renderSlots();
    if (state.selectedId && state.media.some((m) => m.id === state.selectedId)) {
      selectMedia(state.selectedId);
    } else {
      state.selectedId = null;
      selectMedia(null);
    }
  }

  $("backend").onchange = refreshModeOptions;
  document.querySelectorAll('input[name="outputKind"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      pruneSlotsForOutput();
      renderSlots();
      updateModeHint();
      renderParams();
      if (state.selectedId) selectMedia(state.selectedId);
    });
  });
  $("clearSlots").onclick = () => {
    state.slots = [];
    renderSlots();
    updateModeHint();
    renderParams();
  };

  // Fullscreen preview: close via button, Esc, or backdrop click
  $("lightboxClose").onclick = (ev) => {
    ev.stopPropagation();
    closeLightbox();
  };
  $("lightbox").onclick = (ev) => {
    if (ev.target === $("lightbox") || ev.target === $("lightboxStage")) {
      closeLightbox();
    }
  };
  $("lightboxStage").onclick = (ev) => {
    // Click image to close; leave video controls alone
    if (ev.target.tagName === "IMG") closeLightbox();
  };
  window.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") closeLightbox();
  });

  $("prompt").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
      ev.preventDefault();
      $("generate").click();
    }
  });

  $("lineageSelect").onchange = async () => {
    showError(null);
    try {
      await api("/api/lineages/current", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: $("lineageSelect").value }),
      });
      state.slots = [];
      state.selectedId = null;
      await refresh();
      setStatus("lineage switched");
    } catch (e) {
      showError(e);
    }
  };

  $("lineageRename").onclick = async () => {
    const name = $("lineageName").value.trim();
    if (!name || !state.currentLineage) return;
    try {
      await api(`/api/lineages/${state.currentLineage.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      await refresh();
      setStatus("renamed");
    } catch (e) {
      showError(e);
    }
  };

  $("lineageNew").onclick = async () => {
    try {
      await api("/api/lineages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      state.slots = [];
      state.selectedId = null;
      await refresh();
      setStatus("new lineage");
    } catch (e) {
      showError(e);
    }
  };

  $("lineageSave").onclick = async () => {
    try {
      const name = $("lineageName").value.trim();
      if (name && state.currentLineage && name !== state.currentLineage.name) {
        await api(`/api/lineages/${state.currentLineage.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name }),
        });
      }
      await api("/api/lineages/current/save", { method: "POST" });
      await refresh();
      setStatus("saved");
    } catch (e) {
      showError(e);
    }
  };

  // Autosave every 10s (graph already persists on mutation; flush meta + graph)
  setInterval(() => {
    api("/api/lineages/current/save", { method: "POST" }).catch(() => {});
  }, 10000);

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
    const mode = resolvedMode();
    const b = currentBackend();
    if (b && !modeSupported(b, mode)) {
      showError({ detail: `backend ${b.name} does not support ${mode}` });
      return;
    }
    btn.disabled = true;
    setStatus("generating…");
    try {
      const body = {
        mode,
        backend: $("backend").value,
        prompt: $("prompt").value,
        media_ids: [...state.slots],
        input_slots: [...state.slots],
        params: collectParams(),
        resolve_at_refs: true,
        async_job: mode === "t2v" || mode === "i2v" || mode === "v2v",
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

  const dz = $("dropzone");
  const fileInput = $("file");
  dz.addEventListener("click", () => fileInput.click());
  dz.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" || ev.key === " ") {
      ev.preventDefault();
      fileInput.click();
    }
  });
  fileInput.onchange = async (ev) => {
    const files = ev.target.files;
    if (files?.length) await uploadFiles(files);
    ev.target.value = "";
  };
  ["dragenter", "dragover"].forEach((evName) => {
    dz.addEventListener(evName, (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      dz.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((evName) => {
    dz.addEventListener(evName, (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (evName === "dragleave") dz.classList.remove("dragover");
    });
  });
  dz.addEventListener("drop", async (ev) => {
    dz.classList.remove("dragover");
    const files = ev.dataTransfer?.files;
    if (files?.length) await uploadFiles(files);
  });

  // Also accept D&D onto the whole compose panel window for convenience
  window.addEventListener("dragover", (ev) => {
    if (ev.dataTransfer?.types?.includes("Files")) ev.preventDefault();
  });

  refresh().catch((e) => {
    showError(e);
    setStatus("error");
  });
})();
