

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

// Dropdowns: click/tap to toggle; close on ESC or outside click
// Theme toggle
const themeBtn = document.getElementById("themeToggle");
if (themeBtn) {
  themeBtn.addEventListener("click", () => {
    const root = document.documentElement;
    if (root.getAttribute("data-theme") === "dark") {
      root.removeAttribute("data-theme");   // back to light
      themeBtn.textContent = "🌙";
    } else {
      root.setAttribute("data-theme", "dark");
      themeBtn.textContent = "☀️";
    }
  });
}

const toggles = document.querySelectorAll('.dd-toggle');
function closeAllDropdowns(){
  document.querySelectorAll('.dropdown').forEach(d => d.style.display = 'none');
  toggles.forEach(t => t.setAttribute('aria-expanded','false'));
}
toggles.forEach(btn => {
  btn.addEventListener('click', (e)=>{
    e.stopPropagation();
    const dd = btn.parentElement.querySelector('.dropdown');
    const open = dd && dd.style.display === 'block';
    closeAllDropdowns();
    if (dd && !open){ dd.style.display = 'block'; btn.setAttribute('aria-expanded','true'); }
  });
});
document.addEventListener('click', (e)=>{ if(!e.target.closest('.menu-item')) closeAllDropdowns(); });
document.addEventListener('keydown', (e)=>{ if(e.key === 'Escape') closeAllDropdowns(); });


// log in page
document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
        loginForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const username = document.getElementById("username").value;
            const password = document.getElementById("password").value;
            const msgBox = document.getElementById("loginMessage");
            msgBox.innerHTML = "⏳ Checking credentials...";

            try {
                const res = await fetch("/login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, password }),
                });

                const data = await res.json();

                if (data.success) {
                    msgBox.style.color = "green";
                    msgBox.innerHTML = "✅ Login successful! Redirecting...";
                    setTimeout(() => {
                        window.location.href = data.redirect;
                    }, 1200);
                } else {
                    msgBox.style.color = "red";
                    msgBox.innerHTML = "❌ " + data.message;
                }
            } catch (err) {
                msgBox.style.color = "red";
                msgBox.innerHTML = "⚠️ Server error. Try again later.";
            }
        });
    }
});
document.addEventListener("DOMContentLoaded", () => {
    const regForm = document.getElementById("registerForm");
    if (regForm) {
        regForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            const email = document.getElementById("reg_email").value;
            const password = document.getElementById("reg_password").value;
            const confirm = document.getElementById("reg_confirm").value;
            const msgBox = document.getElementById("registerMessage");
            msgBox.innerHTML = "⏳ Creating account...";

            try {
                const res = await fetch("/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email, password, confirm })
                });

                const data = await res.json();
                if (data.success) {
                    msgBox.className = "success";
                    msgBox.innerHTML = "✅ Account created! Redirecting...";
                    setTimeout(() => window.location.href = data.redirect, 1000);
                } else {
                    msgBox.className = "error";
                    msgBox.innerHTML = "❌ " + data.message;
                }
            } catch (error) {
                msgBox.className = "error";
                msgBox.innerHTML = "⚠️ Server error, please try again.";
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
            const confirm = document.getElementById("reg_confirm").value;
            const country = document.getElementById("reg_country").value;
            const organisation = document.getElementById("reg_org").value;
            const msgBox = document.getElementById("registerMessage");

            msgBox.textContent = "⏳ Creating account...";

            try {
                const res = await fetch("/register", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ username, email, password, confirm, country, organisation }),
                });

                const data = await res.json();

                if (data.success) {
                    msgBox.className = "success";
                    msgBox.textContent = "✅ Account created! Redirecting...";
                    setTimeout(() => window.location.href = data.redirect, 1000);
                } else {
                    msgBox.className = "error";
                    msgBox.textContent = "❌ " + data.message;
                }
            } catch (error) {
                msgBox.className = "error";
                msgBox.textContent = "⚠️ Server error, please try again.";
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
        csvLabel.textContent = "Choose CSV file…";
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
      dispersivityInput.title = `α_Tv: ${dispersivityInput.value} m`;
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

  // “View full screen graph” – simple expand effect
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

  const fitFrame = (frame) => {
    try {
      const doc = frame.contentDocument || frame.contentWindow?.document;
      if (!doc || !doc.body || !doc.documentElement) return;
      const bodyH = doc.body.scrollHeight || 0;
      const docH = doc.documentElement.scrollHeight || 0;
      const target = Math.max(bodyH, docH, 680);
      frame.style.height = `${target + 8}px`;
    } catch (_err) {
      // Keep default min-height if frame is not ready yet.
    }
  };

  frames.forEach((frame) => {
    frame.addEventListener("load", () => {
      fitFrame(frame);
      const i1 = setTimeout(() => fitFrame(frame), 150);
      const i2 = setTimeout(() => fitFrame(frame), 600);
      frame.dataset.fitTimers = `${i1},${i2}`;
    });
  });

  window.addEventListener("resize", () => {
    frames.forEach((frame) => fitFrame(frame));
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
            { filter: "blur(10px)", opacity: 0, transform: `translateY(${fromY}px)`, color: "rgba(26,79,136,0.20)" },
            { filter: "blur(5px)", opacity: 0.58, transform: `translateY(${midY}px)`, color: "rgba(26,79,136,0.65)" },
            { filter: "blur(0px)", opacity: 1, transform: "translateY(0px)", color: "#1a4f88" }
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
