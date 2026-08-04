(() => {
  document.querySelectorAll("[data-database-browser]").forEach((root) => {

  const rows = Array.from(root.querySelectorAll("[data-database-row]"));
  const sizeSelect = root.querySelector("[data-database-size]");
  const searchInput = root.querySelector("[data-database-search]");
  const info = root.querySelector("[data-database-info]");
  const pagination = root.querySelector("[data-database-pagination]");
  const sortButtons = Array.from(root.querySelectorAll("[data-database-sort]"));
  const exportStatus = root.querySelector("[data-database-export-status]");
  const exportButtons = Array.from(root.querySelectorAll("[data-database-export]"));
  if (!sizeSelect || !searchInput || !info || !pagination) return;
  const headers = Array.from(
    root.querySelectorAll("thead th:not([data-export-ignore])")
  ).map((heading) => heading.textContent.trim());


  let currentPage = 1;
  let sortColumn = null;
  let sortDirection = "asc";
  let statusTimer;

  const cellValue = (row, column) =>
    (row.cells[column]?.textContent || "").trim();

  const compareValues = (left, right) => {
    const numberPattern = /^-?(?:\d+\.?\d*|\.\d+)$/;
    if (numberPattern.test(left) && numberPattern.test(right)) {
      return Number(left) - Number(right);
    }
    return left.localeCompare(right, undefined, {
      numeric: true,
      sensitivity: "base",
    });
  };

  const filteredRows = () => {
    const query = searchInput.value.trim().toLocaleLowerCase();
    const matches = query
      ? rows.filter((row) => row.textContent.toLocaleLowerCase().includes(query))
      : [...rows];

    if (sortColumn !== null) {
      matches.sort((left, right) => {
        const result = compareValues(
          cellValue(left, sortColumn),
          cellValue(right, sortColumn)
        );
        return sortDirection === "asc" ? result : -result;
      });
    }
    return matches;
  };

  const exportMatrix = () => [
    headers,
    ...filteredRows().map((row) =>
      headers.map((_header, column) => cellValue(row, column))
    ),
  ];

  const showStatus = (message) => {
    clearTimeout(statusTimer);
    exportStatus.textContent = message;
    statusTimer = setTimeout(() => {
      exportStatus.textContent = "";
    }, 3500);
  };

  const copyFallback = (text) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("Copy command was rejected.");
  };

  const copyRows = async () => {
    const matrix = exportMatrix();
    const text = matrix
      .map((row) =>
        row.map((value) => value.replace(/[\t\r\n]+/g, " ")).join("\t")
      )
      .join("\n");

    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
      } catch (_error) {
        copyFallback(text);
      }
    } else {
      copyFallback(text);
    }
    showStatus("Copied " + Math.max(matrix.length - 1, 0) + " entries.");
  };

  const exportUrl = (format) => {
    const datasetKey = {
      csv: "databaseCsvUrl",
      xlsx: "databaseExcelUrl",
      pdf: "databasePdfUrl",
    }[format];
    const url = new URL(root.dataset[datasetKey], window.location.origin);
    const query = searchInput.value.trim();

    if (query) url.searchParams.set("q", query);
    if (sortColumn !== null) {
      url.searchParams.set("sort", String(sortColumn));
      url.searchParams.set("dir", sortDirection);
    }
    return url.toString();
  };

  const escapeHtml = (value) =>
    value.replace(
      /[&<>"']/g,
      (character) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[character]
    );

  const printRows = () => {
    const matrix = exportMatrix();
    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      showStatus("Allow pop-ups to print the table.");
      return;
    }
    printWindow.opener = null;

    const headerHtml = matrix[0]
      .map((value) => "<th>" + escapeHtml(value) + "</th>")
      .join("");
    const bodyHtml = matrix
      .slice(1)
      .map(
        (row) =>
          "<tr>" +
          row.map((value) => "<td>" + escapeHtml(value) + "</td>").join("") +
          "</tr>"
      )
      .join("");

    printWindow.document.write(
      "<!doctype html><html><head><title>Site Database</title>" +
        "<style>@page{size:A3 landscape;margin:10mm}" +
        "body{font:10px Arial,sans-serif;color:#17212b}" +
        "h1{font-size:18px}table{width:100%;border-collapse:collapse;table-layout:fixed}" +
        "th,td{border:1px solid #b8c4cf;padding:3px;vertical-align:top;overflow-wrap:anywhere}" +
        "th{background:#285a84;color:#fff}</style></head><body>" +
        "<h1>Site Database</h1><table><thead><tr>" +
        headerHtml +
        "</tr></thead><tbody>" +
        bodyHtml +
        "</tbody></table></body></html>"
    );
    printWindow.document.close();
    setTimeout(() => {
      printWindow.focus();
      printWindow.print();
    }, 150);
  };

  const pageTokens = (pageCount) => {
    if (pageCount <= 7) {
      return Array.from({ length: pageCount }, (_, index) => index + 1);
    }

    const visible = new Set([
      1,
      pageCount,
      currentPage - 1,
      currentPage,
      currentPage + 1,
    ]);
    const pages = [...visible]
      .filter((page) => page >= 1 && page <= pageCount)
      .sort((left, right) => left - right);
    const tokens = [];

    pages.forEach((page, index) => {
      if (index && page - pages[index - 1] > 1) tokens.push(null);
      tokens.push(page);
    });
    return tokens;
  };

  const pageButton = (label, page, options = {}) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reference-page-button";
    button.textContent = label;
    button.disabled = Boolean(options.disabled);
    if (options.current) button.setAttribute("aria-current", "page");
    button.addEventListener("click", () => {
      currentPage = page;
      render();
    });
    return button;
  };

  const renderPagination = (pageCount) => {
    pagination.replaceChildren();
    pagination.append(
      pageButton("Previous", Math.max(1, currentPage - 1), {
        disabled: currentPage === 1,
      })
    );

    pageTokens(pageCount).forEach((page) => {
      if (page === null) {
        const ellipsis = document.createElement("span");
        ellipsis.className = "reference-page-ellipsis";
        ellipsis.textContent = "\u2026";
        pagination.append(ellipsis);
        return;
      }
      pagination.append(
        pageButton(String(page), page, { current: page === currentPage })
      );
    });

    pagination.append(
      pageButton("Next", Math.min(pageCount, currentPage + 1), {
        disabled: currentPage === pageCount,
      })
    );
  };

  const render = () => {
    const matches = filteredRows();
    const requestedSize =
      sizeSelect.value === "all" ? Math.max(matches.length, 1) : Number(sizeSelect.value);
    const pageCount = Math.max(1, Math.ceil(matches.length / requestedSize));
    currentPage = Math.min(currentPage, pageCount);

    rows.forEach((row) => {
      row.hidden = true;
    });

    const start = (currentPage - 1) * requestedSize;
    const visibleRows = matches.slice(start, start + requestedSize);
    visibleRows.forEach((row) => {
      row.hidden = false;
    });

    const first = matches.length ? start + 1 : 0;
    const last = matches.length ? start + visibleRows.length : 0;
    info.textContent = `Showing ${first} to ${last} of ${matches.length} entries`;
    renderPagination(pageCount);
  };

  sizeSelect.addEventListener("change", () => {
    currentPage = 1;
    render();
  });

  searchInput.addEventListener("input", () => {
    currentPage = 1;
    render();
  });
  exportButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.databaseExport;
      if (action === "copy") {
        try {
          await copyRows();
        } catch (_error) {
          showStatus("The table could not be copied.");
        }
      } else if (action === "csv") {
        window.location.assign(exportUrl("csv"));
      } else if (action === "excel") {
        window.location.assign(exportUrl("xlsx"));
      } else if (action === "pdf") {
        window.location.assign(exportUrl("pdf"));
      } else if (action === "print") {
        printRows();
      }
    });
  });


  sortButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const column = Number(button.dataset.column);
      if (sortColumn === column) {
        sortDirection = sortDirection === "asc" ? "desc" : "asc";
      } else {
        sortColumn = column;
        sortDirection = "asc";
      }

      sortButtons.forEach((candidate) => {
        const selected = candidate === button;
        const heading = candidate.closest("th");
        const indicator = candidate.querySelector(".reference-sort-indicator");
        heading.setAttribute(
          "aria-sort",
          selected ? (sortDirection === "asc" ? "ascending" : "descending") : "none"
        );
        indicator.textContent = selected
          ? (sortDirection === "asc" ? "\u25B2" : "\u25BC")
          : "\u2195";
      });
      currentPage = 1;
      render();
    });
  });

  render();
  });
})();
