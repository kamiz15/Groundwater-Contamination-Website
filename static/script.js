

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
