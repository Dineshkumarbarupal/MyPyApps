(() => {
  const call = (...args) => YTAApi.call(...args);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  function toast(text, type = "") {
    const node = document.createElement("div");
    node.className = "toast " + type;
    node.textContent = text;
    document.getElementById("toast-root").append(node);
    setTimeout(() => node.remove(), 5000);
  }
  async function refresh() {
    const result = await call("api_list_jobs");
    if (!result.ok) return;
    const box = document.getElementById("job-list");
    const jobs = result.jobs || [];
    if (!jobs.length) {
      box.innerHTML = '<div class="empty"><b>No videos processed yet</b><span>Your transcripts and downloads will appear here.</span></div>';
      return;
    }
    box.innerHTML = jobs.map(job => {
      const actions = (job.artifacts || []).map(item =>
        '<button data-open="' + esc(item.path) + '">Open ' + esc(item.kind) + '</button>'
      ).join("") + (["completed", "partial"].includes(job.status)
        ? '<button data-upload="' + esc(job.id) + '">Upload to GitHub</button>' : "");
      return '<article class="job-card"><div class="job-top"><span class="job-icon">▶</span><div class="job-info"><b>' +
        esc(job.title || job.url) + '</b><small>' + esc(job.url) + '</small></div><span class="job-status ' +
        esc(job.status) + '">' + esc(job.status) + '</span></div><div class="progress"><span style="width:' +
        Math.min(100, Math.max(0, Number(job.progress) || 0)) + '%"></span></div><div class="job-footer"><span>' +
        esc(job.message || "") + '</span><div class="job-actions">' + actions + '</div></div></article>';
    }).join("");
    box.querySelectorAll("[data-upload]").forEach(button =>
      button.addEventListener("click", () => upload(button.dataset.upload)));
    box.querySelectorAll("[data-open]").forEach(button =>
      button.addEventListener("click", async () => {
        const opened = await call("api_open_output", button.dataset.open);
        if (!opened.ok) toast(opened.error, "error");
      }));
  }
  async function upload(jobId) {
    const repo = document.getElementById("github-repo").value.trim();
    const token = document.getElementById("github-token").value.trim();
    const remember = document.getElementById("remember-token").checked;
    if (!repo) return toast("Enter your GitHub repository URL.", "error");
    const button = document.querySelector('[data-upload="' + CSS.escape(jobId) + '"]');
    if (button) { button.disabled = true; button.textContent = "Uploading…"; }
    const result = await call("api_upload_job", jobId, repo, token, remember);
    if (button) { button.disabled = false; button.textContent = "Upload to GitHub"; }
    if (!result.ok) return toast(result.error, "error");
    toast("Uploaded " + result.uploaded + " file(s). " + (result.warning || ""), "success");
  }
  async function init(user) {
    document.getElementById("sidebar-user-name").textContent = user.display_name;
    document.getElementById("sidebar-user-email").textContent = user.email;
    document.getElementById("sidebar-avatar").textContent = user.display_name.slice(0, 1).toUpperCase();
    document.getElementById("logout-button").addEventListener("click", async () => {
      await call("api_logout");
      YTA.renderAuth();
    });
    const input = document.getElementById("youtube-urls");
    input.addEventListener("input", () => {
      const count = input.value.split(/\r?\n/).filter(value => value.trim()).length;
      document.getElementById("url-count").textContent = count + " links";
      document.getElementById("queue-count").textContent = count;
    });
    document.getElementById("start-batch").addEventListener("click", async () => {
      const options = {
        transcript: document.getElementById("opt-transcript").checked,
        video: document.getElementById("opt-video").checked,
        audio: document.getElementById("opt-audio").checked,
        authorized: document.getElementById("authorized-content").checked,
        cookies_browser: document.getElementById("cookies-browser").value
      };
      if (!options.transcript && !options.video && !options.audio)
        return toast("Select at least one output.", "error");
      if (!options.authorized)
        return toast("Please confirm that you own these videos or have permission to download/process them.", "error");
      const button = document.getElementById("start-batch");
      button.disabled = true;
      const result = await call("api_start_batch", input.value, options);
      button.disabled = false;
      if (!result.ok) return toast(result.error, "error");
      input.value = "";
      document.getElementById("url-count").textContent = "0 links";
      document.getElementById("queue-count").textContent = "0";
      document.getElementById("queue-feedback").textContent = result.message;
      toast(result.message, "success");
      await refresh();
    });
    const refreshEvents = () => refresh();
    document.getElementById("refresh-jobs").addEventListener("click", refreshEvents);
    document.getElementById("refresh-jobs-link").addEventListener("click", refreshEvents);
    document.getElementById("choose-directory").addEventListener("click", async () => {
      const result = await call("api_choose_directory");
      if (result.ok && result.path) document.getElementById("output-directory").value = result.path;
      else if (result.error) toast(result.error, "error");
    });
    document.getElementById("save-settings").addEventListener("click", async () => {
      const result = await call("api_save_directory", document.getElementById("output-directory").value);
      toast(result.ok ? "Output folder saved." : result.error, result.ok ? "success" : "error");
    });
    const settings = await call("api_get_settings");
    if (settings.ok) document.getElementById("output-directory").value = settings.output_dir;
    const token = await call("api_token_status");
    document.getElementById("github-token-status").textContent =
      token.saved ? "A token is available in your OS keyring." : "Token requested only when uploading.";
    const environment = await call("api_environment");
    document.getElementById("dependency-status").textContent = environment.ok
      ? "FFmpeg: " + (environment.ffmpeg ? environment.ffmpeg_source : "not found — update requirements") +
        " · yt-dlp: " + (environment.ytdlp ? "ready" : "missing") +
        (environment.whisper ? " · Whisper installed" : "")
      : "Could not check local media dependencies.";
    await refresh();
    setInterval(refresh, 3500);
  }
  window.YTADashboard = { init, refresh };
})();
