

// Sidebar toggle (unchanged)
const sidebar  = document.getElementById('sidebar');
const openBtn  = document.getElementById('openSidebar');
const closeBtn = document.getElementById('closeSidebar');
const backdrop = document.getElementById('backdrop');

function openSidebar(){ sidebar?.classList.add('open'); backdrop?.classList.add('open'); }
function closeSidebar(){ sidebar?.classList.remove('open'); backdrop?.classList.remove('open'); }

openBtn?.addEventListener('click', openSidebar);
closeBtn?.addEventListener('click', closeSidebar);
backdrop?.addEventListener('click', closeSidebar);
sidebar?.querySelectorAll('a.nav-link').forEach(link => link.addEventListener('click', closeSidebar));

// Dropdowns: click/tap to toggle; close on ESC or outside click
// Theme toggle
const themeBtn = document.getElementById("themeToggle");
if (themeBtn) {
  themeBtn.addEventListener("click", () => {
    const root = document.documentElement;
    if (root.getAttribute("data-theme") === "dark") {
      root.removeAttribute("data-theme");   // back to light
      themeBtn.textContent = "ÃƒÂ°Ã…Â¸Ã…â€™Ã¢â€žÂ¢";
    } else {
      root.setAttribute("data-theme", "dark");
      themeBtn.textContent = "ÃƒÂ¢Ã‹Å“Ã¢â€šÂ¬ÃƒÂ¯Ã‚Â¸Ã‚Â";
    }
  });
}

const toggles = document.querySelectorAll('.dd-toggle');
function closeAllDropdowns(){
  document.querySelectorAll('.menu-item.dropdown-open').forEach(item => item.classList.remove('dropdown-open'));
  toggles.forEach(t => t.setAttribute('aria-expanded','false'));
}
toggles.forEach(btn => {
  btn.addEventListener('click', (e)=>{
    e.stopPropagation();
    const item = btn.closest('.menu-item');
    const open = item?.classList.contains('dropdown-open');
    closeAllDropdowns();
    if (item && !open){
      item.classList.add('dropdown-open');
      btn.setAttribute('aria-expanded','true');
    }
  });
});
document.addEventListener('click', (e)=>{ if(!e.target.closest('.menu-item')) closeAllDropdowns(); });
document.addEventListener('keydown', (e)=>{ if(e.key === 'Escape') closeAllDropdowns(); });


document.addEventListener("DOMContentLoaded", () => {
  const contactForm = document.getElementById("contactForm");
  if (!contactForm) return;

  contactForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msgBox = document.getElementById("contactMessage");
    const submitButton = contactForm.querySelector('button[type="submit"]');
    const name = document.getElementById("contactName").value.trim();
    const email = document.getElementById("contactEmail").value.trim();
    const message = document.getElementById("contactMsg").value.trim();
    const csrfToken = document.getElementById("contactCsrf").value;

    if (!name || !email || !message) {
      msgBox.className = "contact-message error";
      msgBox.textContent = "Enter your name, email, and message.";
      return;
    }

    submitButton.disabled = true;
    msgBox.className = "contact-message";
    msgBox.textContent = "Sending...";

    try {
      const res = await fetch("/contact", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ name, email, message }),
      });
      const data = await res.json();

      if (!res.ok || !data.success) {
        throw new Error(data.message || "Message could not be sent.");
      }

      msgBox.className = "contact-message success";
      msgBox.textContent = data.message;
      contactForm.reset();
    } catch (error) {
      msgBox.className = "contact-message error";
      msgBox.textContent = error.message || "Message could not be sent. Try again later.";
    }

    submitButton.disabled = false;
  });
});
// log in page
document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const username = document.getElementById("username").value;
            const password = document.getElementById("password").value;
            const csrfToken = loginForm.elements["_csrf_token"].value;
            const msgBox = document.getElementById("loginMessage");
            msgBox.textContent = "Checking credentials...";

            try {
                const res = await fetch("/login", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": csrfToken,
                    },
                    body: JSON.stringify({ username, password }),
                });

                const data = await res.json();

                if (data.success) {
                    window.location.href = data.redirect;
                } else {
                    msgBox.style.color = "red";
                    msgBox.textContent = data.message;
                }
            } catch (err) {
                msgBox.style.color = "red";
                msgBox.textContent = "Server error. Try again later.";
            }
        });
    }
});
document.addEventListener("DOMContentLoaded", () => {
    const regForm = document.getElementById("registerForm");
    if (regForm) {
        regForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const username = document.getElementById("reg_username").value;
            const email = document.getElementById("reg_email").value;
            const password = document.getElementById("reg_password").value;
            const confirmPassword = document.getElementById("reg_confirm").value;
            const csrfToken = regForm.elements["_csrf_token"].value;
            const msgBox = document.getElementById("registerMessage");
            const submitButton = regForm.querySelector('button[type="submit"]');

            if (submitButton.disabled) return;
            submitButton.disabled = true;

            msgBox.textContent = "Creating account...";

            try {
                const res = await fetch("/register", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": csrfToken,
                    },
                    body: JSON.stringify({ username, email, password, confirmPassword }),
                });

                const data = await res.json();

                if (data.success) {
                    window.location.href = data.redirect;
                } else {
                    msgBox.className = "error";
                    msgBox.textContent = data.message;
                    submitButton.disabled = false;
                }
            } catch (error) {
                msgBox.className = "error";
                msgBox.textContent = "Server error. Please try again.";
                submitButton.disabled = false;
            }
        });
    }
});
document.addEventListener("DOMContentLoaded", () => {
  // highlight active top menu item
  const path = window.location.pathname;
  document.querySelectorAll(".headbar .menu-link").forEach(a => {
    if (a.getAttribute("href") === path) {
      a.classList.add("nav-active");
    }
  });
});
document.addEventListener("DOMContentLoaded", () => {
  const csvInput = document.getElementById("csvFileInput");
  const csvLabel = document.getElementById("csvFileLabel");

  if (csvInput && csvLabel) {
    csvInput.addEventListener("change", () => {
      if (csvInput.files && csvInput.files.length > 0) {
        csvLabel.textContent = csvInput.files[0].name;
      } else {
        csvLabel.textContent = "Choose CSV fileÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦";
      }
    });
  }
});
document.addEventListener("DOMContentLoaded", () => {
  const thicknessInput = document.querySelector('input[name="Thickness"]');
  const dispersivityInput = document.querySelector('input[name="Dispersivity"]');

  if (thicknessInput) {
    thicknessInput.addEventListener("input", () => {
      thicknessInput.title = `Thickness: ${thicknessInput.value} m`;
    });
  }

  if (dispersivityInput) {
    dispersivityInput.addEventListener("input", () => {
      dispersivityInput.title = `ÃƒÅ½Ã‚Â±_Tv: ${dispersivityInput.value} m`;
    });
  }
});
document.addEventListener("DOMContentLoaded", () => {
  const thicknessSlider = document.getElementById("sliderThickness");
  const thicknessVal = document.getElementById("thicknessVal");
  const dispSlider = document.getElementById("sliderDispersivity");
  const dispVal = document.getElementById("dispersivityVal");

  if (thicknessSlider && thicknessVal) {
    thicknessSlider.addEventListener("input", () => {
      thicknessVal.textContent = thicknessSlider.value;
    });
  }

  if (dispSlider && dispVal) {
    dispSlider.addEventListener("input", () => {
      dispVal.textContent = dispSlider.value;
    });
  }

  // ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œView full screen graphÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ simple expand effect
  const fullBtn = document.getElementById("fullScreen");
  const wrapper = document.getElementById("liedlPlotWrapper");
  if (fullBtn && wrapper) {
    fullBtn.addEventListener("click", () => {
      wrapper.classList.toggle("plot-fullscreen");
    });
  }
});
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;

  document.querySelectorAll(".headbar .dd-link").forEach((link) => {
    if (link.getAttribute("href") === path) {
      link.classList.add("nav-active");
    }
  });
});
document.addEventListener("DOMContentLoaded", () => {
  const path = window.location.pathname;
  document.querySelectorAll(".headbar .dd-link").forEach((link) => {
    if (link.getAttribute("href") === path) {
      link.classList.add("nav-active");
    }
  });
});
document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("site_ids");
  if (!select) return;

  select.addEventListener("change", () => {
    const count = Array.from(select.options).filter(o => o.selected).length;
    select.title = count > 0 ? `${count} scenario(s) selected` : "No scenarios selected";
  });
});
document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("site_ids");
  if (!select) return;

  const updateTitle = () => {
    const count = Array.from(select.options).filter(o => o.selected).length;
    select.title = count > 0
      ? `${count} scenario(s) selected`
      : "No scenarios selected";
  };

  select.addEventListener("change", updateTitle);
  updateTitle();
});

document.addEventListener("DOMContentLoaded", () => {
  const frames = document.querySelectorAll("iframe.panel-frame");
  if (!frames.length) return;

  // Bokeh figures here have fixed pixel heights, but the Panel document around
  // them does not, so the frame still has to track its content.
  // Record why a frame is not tracking its content. Every failure below used to
  // be swallowed, which left the embedded plot silently cut off at the CSS floor.
  // Warn once per state change, not once per observer tick.
  const noteSync = (frame, state, detail) => {
    if (frame.dataset.frameSync === state) return;
    frame.dataset.frameSync = state;
    if (state !== "ok") console.warn(`[cast] panel frame ${state}: ${detail}`, frame);
  };
  const measure = (frame) => {
    let doc = null;
    try {
      doc = frame.contentDocument || frame.contentWindow?.document;
    } catch (_err) {
      // Cross-origin: the parent cannot read the iframe, so this sync can never
      // run and the frame stays at its floor. Almost always PANEL_PUBLIC_BASE
      // set to an absolute URL - a different port is a different origin.
      noteSync(frame, "cross-origin",
        `cannot measure ${new URL(frame.src, location.href).origin} from ` +
        `${location.origin}; set PANEL_PUBLIC_BASE to a same-origin path like /panel`);
      return null;
    }
    if (!doc || !doc.body || !doc.documentElement) {
      noteSync(frame, "pending", "iframe document not ready yet");
      return null;
    }
    return Math.ceil(Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight));
  };
  const floorOf = (frame) => Number(frame.dataset.minHeight || 680);

  // Grow-only, exact target (no fudge). Safe to call from a ResizeObserver: once
  // the frame equals its content the responsive body reports that same height,
  // target == current, and it stops ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â no runaway.
  const growFrame = (frame) => {
    try {
      const content = measure(frame);
      if (content == null) return;
      const target = Math.max(content, floorOf(frame));
      const current = Math.round(parseFloat(frame.style.height) || 0);
      if (target > current + 1) frame.style.height = `${target}px`;
      noteSync(frame, "ok", "");
    } catch (_err) { /* measure() already reported the reason */ }
  };

  // Reset then fit ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â allows shrinking too. Only from discrete events (load,
  // window resize), never an observer, so it can't loop.
  const refitFrame = (frame) => {
    try {
      frame.style.height = "";               // collapse so short content can re-measure smaller
      const content = measure(frame);
      if (content == null) return;
      frame.style.height = `${Math.max(content, floorOf(frame))}px`;
      noteSync(frame, "ok", "");
    } catch (_err) { /* measure() already reported the reason */ }
  };

  frames.forEach((frame) => {
    frame.addEventListener("load", () => {
      refitFrame(frame);
      try {
        const doc = frame.contentDocument || frame.contentWindow?.document;
        if (doc && doc.body && "ResizeObserver" in window) {
          new ResizeObserver(() => growFrame(frame)).observe(doc.body);
        }
      } catch (_err) { /* timers below still cover it */ }
      // Catch the async Bokeh render even if the observer misses it.
      [150, 600, 1500, 3000, 5000, 8000].forEach((ms) => setTimeout(() => growFrame(frame), ms));
      // Past the last retry: if the frame never fitted, the plot is almost
      // certainly clipped. Say so rather than leaving a silently cut graph.
      setTimeout(() => {
        if (frame.dataset.frameSync === "ok") return;
        noteSync(frame, "failed",
          `never fitted its content (last state: ${frame.dataset.frameSync || "unknown"}); ` +
          "the embedded plot is probably cut off");
      }, 9000);
    });
  });

  window.addEventListener("resize", () => {
    frames.forEach((frame) => refitFrame(frame));
  });
});

window.onLandingTitleAnimationComplete = window.onLandingTitleAnimationComplete || (() => {
  console.log("Landing title animation completed.");
});

document.addEventListener("DOMContentLoaded", () => {
  const blurNodes = document.querySelectorAll("[data-blur-text]");
  if (!blurNodes.length) return;

  const parseNum = (val, fallback) => {
    const n = Number(val);
    return Number.isFinite(n) ? n : fallback;
  };

  const buildSegments = (text, animateBy) => {
    if (animateBy === "characters") return text.split("");
    return text.split(" ");
  };

  blurNodes.forEach((el) => {
    const text = el.dataset.blurText || el.textContent || "";
    const delay = parseNum(el.dataset.blurDelay, 200);
    const animateBy = el.dataset.blurAnimateBy === "characters" ? "characters" : "words";
    const direction = el.dataset.blurDirection === "bottom" ? "bottom" : "top";
    const threshold = parseNum(el.dataset.blurThreshold, 0.1);
    const rootMargin = el.dataset.blurRootMargin || "0px";
    const stepDuration = parseNum(el.dataset.blurStepDuration, 0.35);
    const onCompleteName = el.dataset.blurOnComplete || "";
    const fromY = direction === "top" ? -50 : 50;
    const midY = direction === "top" ? 5 : -5;
    const totalDuration = Math.max(120, stepDuration * 1000 * 2);

    el.textContent = "";
    const segments = buildSegments(text, animateBy);
    const spans = segments.map((segment, i) => {
      const span = document.createElement("span");
      span.className = "blur-text-segment";
      span.textContent = segment;
      span.style.opacity = "0";
      span.style.filter = "blur(10px)";
      span.style.transform = `translateY(${fromY}px)`;
      el.appendChild(span);
      if (animateBy === "words" && i < segments.length - 1) {
        el.appendChild(document.createTextNode("\u00a0"));
      }
      return span;
    });

    let doneCount = 0;
    const run = () => {
      spans.forEach((span, i) => {
        const anim = span.animate(
          [
            { filter: "blur(10px)", opacity: 0, transform: `translateY(${fromY}px)`, color: "rgba(255,255,255,0.20)" },
            { filter: "blur(5px)", opacity: 0.58, transform: `translateY(${midY}px)`, color: "rgba(255,255,255,0.65)" },
            { filter: "blur(0px)", opacity: 1, transform: "translateY(0px)", color: "#ffffff" }
          ],
          {
            duration: totalDuration,
            delay: i * delay,
            easing: "cubic-bezier(0.22, 1, 0.36, 1)",
            fill: "forwards"
          }
        );
        anim.onfinish = () => {
          doneCount += 1;
          if (doneCount === spans.length && onCompleteName && typeof window[onCompleteName] === "function") {
            window[onCompleteName]();
          }
        };
      });
    };

    if (!("IntersectionObserver" in window)) {
      run();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            run();
            observer.unobserve(el);
          }
        });
      },
      { threshold, rootMargin }
    );
    observer.observe(el);
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.querySelector(".home-bg-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  const state = {
    w: 0,
    h: 0,
    mouseX: 0.5,
    mouseY: 0.5,
    targetMouseX: 0.5,
    targetMouseY: 0.5,
    t0: performance.now()
  };

  const hexToRgb = (hex) => {
    const clean = (hex || "").replace("#", "");
    if (clean.length !== 6) return [0, 0, 0];
    return [
      parseInt(clean.slice(0, 2), 16),
      parseInt(clean.slice(2, 4), 16),
      parseInt(clean.slice(4, 6), 16)
    ];
  };

  const colors = {
    c1: hexToRgb("#0D3F78"),
    c2: hexToRgb("#006BB4"),
    c3: hexToRgb("#162325")
  };

  const lerp = (a, b, t) => a + (b - a) * t;
  const rgba = (c, a) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${a})`;

  const resize = () => {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    state.w = Math.max(1, Math.floor(rect.width));
    state.h = Math.max(1, Math.floor(rect.height));
    canvas.width = Math.floor(state.w * dpr);
    canvas.height = Math.floor(state.h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  const onMouse = (e) => {
    state.targetMouseX = Math.min(1, Math.max(0, e.clientX / Math.max(1, window.innerWidth)));
    state.targetMouseY = Math.min(1, Math.max(0, e.clientY / Math.max(1, window.innerHeight)));
  };

  const onTouch = (e) => {
    if (!e.touches || !e.touches.length) return;
    const t = e.touches[0];
    state.targetMouseX = Math.min(1, Math.max(0, t.clientX / Math.max(1, window.innerWidth)));
    state.targetMouseY = Math.min(1, Math.max(0, t.clientY / Math.max(1, window.innerHeight)));
  };

  window.addEventListener("resize", resize);
  window.addEventListener("mousemove", onMouse);
  window.addEventListener("touchmove", onTouch, { passive: true });
  resize();

  let raf = 0;
  const render = (now) => {
    const t = (now - state.t0) * 0.00055;
    const { w, h } = state;

    ctx.clearRect(0, 0, w, h);

    const g0 = ctx.createLinearGradient(0, 0, 0, h);
    g0.addColorStop(0, "rgba(244,250,255,1)");
    g0.addColorStop(1, "rgba(229,240,252,1)");
    ctx.fillStyle = g0;
    ctx.fillRect(0, 0, w, h);

    state.mouseX += (state.targetMouseX - state.mouseX) * 0.12;
    state.mouseY += (state.targetMouseY - state.mouseY) * 0.12;
    const mx = (state.mouseX - 0.5) * 0.22;
    const my = (state.mouseY - 0.5) * 0.18;

    const blobs = [
      { x: 0.18, y: 0.22, r: 0.58, a: 0.48, c: colors.c1, s: 0.72 },
      { x: 0.74, y: 0.26, r: 0.50, a: 0.50, c: colors.c2, s: 0.55 },
      { x: 0.52, y: 0.63, r: 0.64, a: 0.34, c: colors.c3, s: 0.38 },
      { x: 0.90, y: 0.72, r: 0.38, a: 0.40, c: colors.c2, s: 0.62 }
    ];

    blobs.forEach((b, i) => {
      const ox = Math.sin(t * (0.8 + b.s) + i * 2.0) * 0.11 + mx * (i + 1.5);
      const oy = Math.cos(t * (0.7 + b.s) + i * 1.6) * 0.10 + my * (i + 1.5);
      const cx = (b.x + ox) * w;
      const cy = (b.y + oy) * h;
      const rr = b.r * Math.min(w, h);
      const grad = ctx.createRadialGradient(cx, cy, rr * 0.1, cx, cy, rr);
      grad.addColorStop(0, rgba(b.c, b.a));
      grad.addColorStop(1, rgba(b.c, 0));
      ctx.fillStyle = grad;
      ctx.fillRect(0, 0, w, h);
    });

    ctx.globalCompositeOperation = "overlay";
    const stripCount = 24;
    for (let i = 0; i < stripCount; i += 1) {
      const p = i / (stripCount - 1);
      const y = lerp(0, h, p) + Math.sin(t * 2.4 + i * 0.9) * 10;
      const col = i % 3 === 0 ? colors.c2 : (i % 3 === 1 ? colors.c1 : colors.c3);
      ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${0.06 + p * 0.05})`;
      ctx.fillRect(0, y, w, 4);
    }
    ctx.globalCompositeOperation = "source-over";

    const center = ctx.createRadialGradient(
      w * (0.5 + (state.mouseX - 0.5) * 0.12),
      h * (0.45 + (state.mouseY - 0.5) * 0.10),
      Math.min(w, h) * 0.12,
      w * 0.5,
      h * 0.5,
      Math.max(w, h) * 0.65
    );
    center.addColorStop(0, "rgba(255,255,255,0.20)");
    center.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = center;
    ctx.fillRect(0, 0, w, h);

    raf = requestAnimationFrame(render);
  };

  raf = requestAnimationFrame(render);

  window.addEventListener("beforeunload", () => {
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", resize);
    window.removeEventListener("mousemove", onMouse);
    window.removeEventListener("touchmove", onTouch);
  });
});

// ---------------------------------------------------------------------------
// CAST report bridge: Panel iframes post their latest run results here so the
// page-level "Report Export" card (outside the iframe) can build the PDF via
// POST /report/export.
// ---------------------------------------------------------------------------
(function () {
  let reportPayload = null;

  const fromEmbeddedFrame = (source) =>
    Array.from(document.querySelectorAll("iframe")).some((f) => f.contentWindow === source);

  window.addEventListener("message", (event) => {
    const data = event.data;
    if (!data || data.type !== "cast-report") return;
    // Only trust messages sent by an iframe we embedded (blocks a page that
    // opened us via window.open from spoofing report payloads).
    if (!fromEmbeddedFrame(event.source)) return;
    const card = document.getElementById("reportExportCard");
    if (!card) return;
    if (data.clear || !data.state) {
      reportPayload = null;
      card.hidden = true;
      return;
    }
    reportPayload = data;
    card.hidden = false;
  });

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest && e.target.closest("#reportExportBtn");
    if (!btn || !reportPayload) return;
    e.preventDefault();
    const card = document.getElementById("reportExportCard");
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Preparing PDF...";
    try {
      const res = await fetch("/report/export", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": card ? card.dataset.csrf : "",
        },
        body: JSON.stringify({
          title: reportPayload.title,
          subtitle: reportPayload.subtitle,
          filename: reportPayload.filename,
          parameters: (reportPayload.state && reportPayload.state.parameters) || [],
          outputs: (reportPayload.state && reportPayload.state.outputs) || [],
          plot_data: (reportPayload.state && reportPayload.state.plot_data) || null,
          plot_images: (reportPayload.state && reportPayload.state.plot_images) || [],
        }),
      });
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = reportPayload.filename || "cast_report.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      btn.textContent = original;
    } catch (err) {
      btn.textContent = "Export failed - try again";
      setTimeout(() => { btn.textContent = original; }, 2500);
    }
    btn.disabled = false;
  });
})();

// ---------------------------------------------------------------------------
// Async numerical report export: the export endpoint queues a background
// simulation (202 + job_id). Poll the job status, then download the PDF
// from report_url once the run is done.
// ---------------------------------------------------------------------------
(function () {
  const POLL_MS = 2000;
  const MAX_POLLS = 600; // ~20 minutes

  document.addEventListener("click", async (e) => {
    const link = e.target.closest && e.target.closest("a[data-async-export]");
    if (!link) return;
    e.preventDefault();
    if (link.dataset.exportRunning === "1") return;
    link.dataset.exportRunning = "1";

    const original = link.textContent;
    const statusBox = link.parentElement.querySelector(".report-export-status");
    const show = (msg) => {
      if (statusBox) {
        statusBox.hidden = false;
        statusBox.textContent = msg;
      }
    };
    const fail = (msg) => {
      link.textContent = original;
      link.dataset.exportRunning = "";
      show(msg);
    };

    link.textContent = "Submitting simulation...";
    try {
      const res = await fetch(link.getAttribute("href"), {
        headers: { "Accept": "application/json" },
      });
      if (res.status !== 202) throw new Error("submit failed");
      const job = await res.json();

      for (let i = 0; i < MAX_POLLS; i++) {
        const statusRes = await fetch(job.status_url);
        if (!statusRes.ok) throw new Error("status failed");
        const status = await statusRes.json();
        if (status.status === "done") {
          show("Simulation finished - downloading report.");
          link.textContent = original;
          link.dataset.exportRunning = "";
          window.location.href = status.report_url || job.report_url;
          return;
        }
        if (status.status === "failed" || status.status === "cancelled") {
          fail(status.error || "Simulation " + status.status + ".");
          return;
        }
        link.textContent = status.queue_position
          ? "Queued (position " + status.queue_position + ")..."
          : "Running simulation...";
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      }
      fail("Simulation timed out. Please try again.");
    } catch (err) {
      fail("Could not generate the report. Please try again later.");
    }
  });
})();
