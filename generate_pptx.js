/**
 * generate_pptx.js — FinAgent Slide Deck Generator
 * =================================================
 * Reads a JSON data file produced by report_pptx.py and outputs a
 * polished 16×9 investor presentation using PptxGenJS.
 *
 * Usage:
 *   node generate_pptx.js <data.json> <output.pptx>
 */

"use strict";

const pptxgen = require("pptxgenjs");
const fs      = require("fs");
const path    = require("path");

// ── CLI args ──────────────────────────────────────────────────────────────────
const [,, dataFile, outFile] = process.argv;
if (!dataFile || !outFile) {
  console.error("Usage: node generate_pptx.js <data.json> <output.pptx>");
  process.exit(1);
}

const data = JSON.parse(fs.readFileSync(dataFile, "utf8"));

// ── Palette — "Midnight Executive" finance theme ─────────────────────────────
const C = {
  navy:    "1E2761",   // dominant background / headings
  navyMid: "243070",   // card backgrounds
  blue:    "4472C4",   // accent 1
  ice:     "BDD7EE",   // accent 2 / text on dark
  white:   "FFFFFF",
  offWhite:"F4F7FC",
  grey:    "8496A9",
  darkGrey:"364153",
  green:   "22C55E",   // positive returns
  red:     "EF4444",   // negative / risk
  gold:    "F59E0B",   // highlight / key metric
  bodyBg:  "F4F7FC",   // light slide background
};

// ── Fonts ─────────────────────────────────────────────────────────────────────
const F = { head: "Calibri", body: "Calibri" };

// ── Helpers ───────────────────────────────────────────────────────────────────
function makeShadow() {
  return { type: "outer", color: "000000", blur: 8, offset: 3, angle: 135, opacity: 0.12 };
}

/**
 * Stat card: coloured rectangle with a big number and label underneath.
 */
function addStatCard(slide, x, y, w, h, value, label, accent) {
  // Card bg
  slide.addShape("rect", {
    x, y, w, h,
    fill: { color: C.white },
    shadow: makeShadow(),
    line: { color: "E2E8F0", width: 0.5 },
  });
  // Left accent bar
  slide.addShape("rect", {
    x, y, w: 0.06, h,
    fill: { color: accent || C.blue },
  });
  // Value
  slide.addText(value, {
    x: x + 0.15, y: y + 0.08, w: w - 0.2, h: h * 0.55,
    fontSize: 22, bold: true, color: C.navy,
    fontFace: F.head, valign: "bottom", align: "left", margin: 0,
  });
  // Label
  slide.addText(label, {
    x: x + 0.15, y: y + h * 0.58, w: w - 0.2, h: h * 0.38,
    fontSize: 9.5, color: C.grey, fontFace: F.body,
    valign: "top", align: "left", margin: 0,
  });
}

/**
 * Section heading — dark left panel with white text.
 */
function addSectionBanner(slide, sectionNum, title, subtitle) {
  // Dark left panel
  slide.addShape("rect", {
    x: 0, y: 0, w: 3.2, h: 5.625,
    fill: { color: C.navy },
  });
  // Section number accent line
  slide.addShape("rect", {
    x: 0.35, y: 1.8, w: 0.5, h: 0.06,
    fill: { color: C.gold },
  });
  slide.addText(`0${sectionNum}`, {
    x: 0.35, y: 1.9, w: 2.5, h: 0.7,
    fontSize: 42, bold: true, color: C.gold, fontFace: F.head,
    align: "left", valign: "middle", margin: 0,
  });
  slide.addText(title, {
    x: 0.35, y: 2.65, w: 2.5, h: 0.9,
    fontSize: 20, bold: true, color: C.white, fontFace: F.head,
    align: "left", valign: "top", margin: 0,
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.35, y: 3.6, w: 2.5, h: 0.7,
      fontSize: 11, color: C.ice, fontFace: F.body,
      align: "left", valign: "top", margin: 0,
    });
  }
}

/**
 * Standard content slide header (light bg slides).
 */
function addContentHeader(slide, title, tag) {
  slide.background = { color: C.bodyBg };
  slide.addText(title, {
    x: 0.45, y: 0.22, w: 8.6, h: 0.55,
    fontSize: 20, bold: true, color: C.navy, fontFace: F.head,
    align: "left", valign: "middle", margin: 0,
  });
  if (tag) {
    slide.addText(tag, {
      x: 7.8, y: 0.22, w: 1.8, h: 0.55,
      fontSize: 9, color: C.grey, fontFace: F.body,
      align: "right", valign: "middle", margin: 0,
    });
  }
  // Thin divider line
  slide.addShape("line", {
    x: 0.45, y: 0.82, w: 9.1, h: 0,
    line: { color: "D1DCF0", width: 1 },
  });
}

/**
 * Slide footer — page indicator.
 */
function addFooter(slide, pageNum, total) {
  slide.addText(`FinAgent Investment Report  •  ${pageNum} / ${total}`, {
    x: 0.45, y: 5.25, w: 9.1, h: 0.28,
    fontSize: 8, color: C.grey, fontFace: F.body,
    align: "right", valign: "middle", margin: 0,
  });
}

/**
 * Wrap long text into lines of max `chars` characters.
 */
function wrapText(text, chars = 90) {
  const words = text.split(" ");
  const lines = [];
  let line = "";
  for (const w of words) {
    if ((line + " " + w).trim().length > chars) { lines.push(line.trim()); line = w; }
    else { line = (line + " " + w).trim(); }
  }
  if (line) lines.push(line.trim());
  return lines.join("\n");
}

/** Truncate text to `maxChars` with ellipsis. */
function truncate(text, maxChars) {
  if (!text || text.length <= maxChars) return text || "";
  return text.slice(0, maxChars - 1).trimEnd() + "…";
}

// ── Main generator ────────────────────────────────────────────────────────────

async function buildDeck() {
  const pres = new pptxgen();
  pres.layout  = "LAYOUT_16x9";
  pres.author  = "FinAgent";
  pres.title   = "FinAgent Investment Analysis";
  pres.subject = `Analysis: ${(data.tickers || []).join(", ")}`;

  const tickers   = data.tickers   || [];
  const stats     = data.stats     || {};
  const sections  = data.sections  || {};
  const chartPaths= data.charts    || {};
  const genDate   = data.generated || "";

  // Count total slides for footer
  // 1 cover + 1 agenda + 1 company overview + 1 price stats table +
  // charts (up to 5) + 7 analysis sections + 1 closing = variable
  // We'll use a placeholder and fill in after.
  const slides = [];

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 1 — Cover
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };

    // Left accent strip
    s.addShape("rect", {
      x: 0, y: 0, w: 0.18, h: 5.625,
      fill: { color: C.gold },
    });

    // Top label
    s.addText("EQUITY RESEARCH  •  AI-POWERED ANALYSIS", {
      x: 0.5, y: 0.55, w: 9, h: 0.35,
      fontSize: 9, color: C.ice, fontFace: F.body,
      align: "left", charSpacing: 3, margin: 0,
    });

    // Main title
    s.addText("FinAgent", {
      x: 0.5, y: 1.05, w: 9, h: 1.2,
      fontSize: 64, bold: true, color: C.white, fontFace: F.head,
      align: "left", margin: 0,
    });
    s.addText("Investment Analysis Report", {
      x: 0.5, y: 2.2, w: 9, h: 0.65,
      fontSize: 26, color: C.ice, fontFace: F.head,
      align: "left", margin: 0,
    });

    // Divider
    s.addShape("line", {
      x: 0.5, y: 3.0, w: 4.5, h: 0,
      line: { color: C.gold, width: 2 },
    });

    // Assets & date
    s.addText(tickers.join("   |   "), {
      x: 0.5, y: 3.2, w: 6, h: 0.4,
      fontSize: 15, bold: true, color: C.gold, fontFace: F.head,
      align: "left", margin: 0,
    });
    s.addText(`Generated: ${genDate}   •   Data: Yahoo Finance   •   AI: Groq llama-3.3-70b`, {
      x: 0.5, y: 3.7, w: 9, h: 0.3,
      fontSize: 9.5, color: C.grey, fontFace: F.body,
      align: "left", margin: 0,
    });

    // Bottom tagline
    s.addText("Powered by FinAgent — AI-Driven Financial Data Pipeline", {
      x: 0.5, y: 5.1, w: 9, h: 0.3,
      fontSize: 9, color: C.grey, fontFace: F.body,
      align: "left", margin: 0,
    });

    slides.push(s);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 2 — Agenda
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.bodyBg };

    addContentHeader(s, "Report Agenda", "CONTENTS");

    const items = [
      ["01", "Asset Overview",          "Company profiles, market cap, sector breakdown"],
      ["02", "Performance Snapshot",    "Key statistics — price, return, volatility at a glance"],
      ["03", "Price & Trend Analysis",  "52-week range, MA signals, momentum indicators"],
      ["04", "Risk & Volatility",       "Annualised vol, rolling vol, Bollinger, macro factors"],
      ["05", "Return Distribution",     "Daily return histogram, skew, kurtosis, Sharpe ratio"],
      ["06", "News Sentiment",          "Headline analysis, sentiment scoring, narrative vs data"],
      ["07", "Investment Perspective",  "Cross-asset ranking, valuation, final recommendation"],
    ];

    const colW = [0.6, 2.5, 5.8];
    const startY = 1.0;
    const rowH   = 0.58;

    items.forEach(([num, title, desc], i) => {
      const y = startY + i * rowH;
      // Row bg alternating
      if (i % 2 === 0) {
        s.addShape("rect", {
          x: 0.35, y: y - 0.04, w: 9.3, h: rowH - 0.04,
          fill: { color: "E8EFF8" },
        });
      }
      // Number badge
      s.addShape("rect", {
        x: 0.35, y: y, w: 0.52, h: rowH - 0.12,
        fill: { color: C.navy },
      });
      s.addText(num, {
        x: 0.35, y: y, w: 0.52, h: rowH - 0.12,
        fontSize: 11, bold: true, color: C.gold, fontFace: F.head,
        align: "center", valign: "middle", margin: 0,
      });
      // Title
      s.addText(title, {
        x: 1.05, y: y + 0.02, w: 2.6, h: 0.3,
        fontSize: 12, bold: true, color: C.navy, fontFace: F.head,
        align: "left", margin: 0,
      });
      // Description
      s.addText(desc, {
        x: 1.05, y: y + 0.3, w: 8.3, h: 0.22,
        fontSize: 9.5, color: C.grey, fontFace: F.body,
        align: "left", margin: 0,
      });
    });

    addFooter(s, 2, "—");
    slides.push(s);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 3 — Asset Overview (Company Profiles)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    addSectionBanner(s, 1, "Asset Overview", "Company Profiles");

    const cardW = 1.56, cardH = 4.0;
    const startX = 3.35;
    const accents = [C.blue, C.green, C.gold, "9333EA"];

    tickers.slice(0, 4).forEach((tk, i) => {
      const st  = stats[tk] || {};
      const inf = st.info   || {};
      const x   = startX + i * (cardW + 0.12);

      // Card bg
      s.addShape("rect", {
        x, y: 0.5, w: cardW, h: cardH,
        fill: { color: C.white }, shadow: makeShadow(),
        line: { color: "E2E8F0", width: 0.5 },
      });
      // Top accent
      s.addShape("rect", {
        x, y: 0.5, w: cardW, h: 0.06,
        fill: { color: accents[i] },
      });

      // Ticker
      s.addText(tk, {
        x: x + 0.1, y: 0.58, w: cardW - 0.2, h: 0.42,
        fontSize: 18, bold: true, color: C.navy, fontFace: F.head,
        align: "left", margin: 0,
      });
      // Company name
      s.addText(truncate(inf.longName || tk, 22), {
        x: x + 0.1, y: 1.02, w: cardW - 0.2, h: 0.32,
        fontSize: 8.5, color: C.grey, fontFace: F.body,
        align: "left", margin: 0,
      });

      // Divider
      s.addShape("line", {
        x: x + 0.1, y: 1.36, w: cardW - 0.2, h: 0,
        line: { color: "E2E8F0", width: 0.7 },
      });

      // Info rows
      const rows = [
        ["Sector",    truncate(inf.sector   || "N/A", 18)],
        ["Mkt Cap",   inf.marketCap ? `$${(inf.marketCap/1e9).toFixed(0)}B` : "N/A"],
        ["Fwd P/E",   inf.forwardPE  ? inf.forwardPE.toFixed(1)  : "N/A"],
        ["Beta",      inf.beta       ? inf.beta.toFixed(2)        : "N/A"],
        ["Rating",    (inf.recommendationKey || "N/A").toUpperCase()],
        ["Target",    inf.targetMeanPrice    ? `$${inf.targetMeanPrice.toFixed(0)}` : "N/A"],
      ];

      rows.forEach(([label, val], ri) => {
        const ry = 1.42 + ri * 0.38;
        s.addText(label, {
          x: x + 0.1, y: ry, w: cardW * 0.5, h: 0.32,
          fontSize: 8.5, color: C.grey, fontFace: F.body,
          align: "left", margin: 0,
        });
        s.addText(val, {
          x: x + cardW * 0.5, y: ry, w: cardW * 0.45, h: 0.32,
          fontSize: 8.5, bold: true, color: C.navy, fontFace: F.body,
          align: "right", margin: 0,
        });
      });
    });

    addFooter(s, 3, "—");
    slides.push(s);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE 4 — Performance Snapshot (Stats table)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.bodyBg };
    addContentHeader(s, "Performance Snapshot", "12-MONTH STATS");

    const headers = ["Ticker", "Price", "Period Ret.", "Ann. Vol.", "Sharpe", "Best Day", "Worst Day", "Outliers"];
    const colW    = [0.75, 0.9, 1.05, 0.95, 0.85, 0.95, 0.95, 0.85];
    const tableX  = 0.35;
    const tableY  = 0.95;
    const rowH    = 0.64;
    const accents = [C.blue, C.green, C.gold, "9333EA"];

    // Header row
    let cx = tableX;
    headers.forEach((h, i) => {
      s.addShape("rect", {
        x: cx, y: tableY, w: colW[i], h: 0.42,
        fill: { color: C.navy },
      });
      s.addText(h, {
        x: cx, y: tableY, w: colW[i], h: 0.42,
        fontSize: 9, bold: true, color: C.white, fontFace: F.head,
        align: "center", valign: "middle", margin: 0,
      });
      cx += colW[i] + 0.02;
    });

    // Data rows
    tickers.slice(0, 4).forEach((tk, ri) => {
      const st  = stats[tk] || {};
      const ret = (st.period_return || 0) * 100;
      const vol = (st.ann_vol || 0) * 100;
      const sharpe = st.sharpe || 0;
      const bestDay  = (st.best_day  || 0) * 100;
      const worstDay = (st.worst_day || 0) * 100;

      const rowY = tableY + 0.44 + ri * (rowH + 0.04);
      const bgColor = ri % 2 === 0 ? C.white : "EDF2FB";
      cx = tableX;

      const cells = [
        { v: tk,                        color: C.navy,  bold: true  },
        { v: `$${(st.price||0).toFixed(2)}`, color: C.darkGrey },
        { v: `${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%`,  color: ret  >= 0 ? C.green : C.red  },
        { v: `${vol.toFixed(2)}%`,      color: C.darkGrey },
        { v: sharpe.toFixed(2),         color: sharpe >= 1 ? C.green : sharpe >= 0 ? C.darkGrey : C.red },
        { v: `+${bestDay.toFixed(2)}%`,  color: C.green },
        { v: `${worstDay.toFixed(2)}%`, color: C.red   },
        { v: String(st.outliers || 0),  color: C.darkGrey },
      ];

      cells.forEach((c, ci) => {
        // Bg
        s.addShape("rect", {
          x: cx, y: rowY, w: colW[ci], h: rowH,
          fill: { color: bgColor }, line: { color: "E8EFF8", width: 0.5 },
        });
        // Left accent on ticker column
        if (ci === 0) {
          s.addShape("rect", {
            x: cx, y: rowY, w: 0.06, h: rowH,
            fill: { color: accents[ri] },
          });
        }
        s.addText(c.v, {
          x: cx, y: rowY, w: colW[ci], h: rowH,
          fontSize: 11, bold: c.bold || false, color: c.color,
          fontFace: F.body, align: "center", valign: "middle", margin: 0,
        });
        cx += colW[ci] + 0.02;
      });
    });

    addFooter(s, 4, "—");
    slides.push(s);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDES 5-9 — Chart slides (one per chart image)
  // ═══════════════════════════════════════════════════════════════════════════
  const chartMeta = [
    { key: "price_volume",   title: "Price Trend & Volume",              tag: "CHART 1" },
    { key: "correlation",    title: "Daily Return Correlation Heatmap",  tag: "CHART 2" },
    { key: "distribution",   title: "Return Distribution (Histogram + KDE)", tag: "CHART 3" },
    { key: "rolling",        title: "Rolling Statistics & Bollinger Bands",  tag: "CHART 4" },
    { key: "cumulative",     title: "Cumulative Returns — Buy & Hold",   tag: "BONUS CHART 5" },
  ];

  chartMeta.forEach(({ key, title, tag }, ci) => {
    const imgPath = chartPaths[key];
    if (!imgPath || !fs.existsSync(imgPath)) return;

    const s = pres.addSlide();
    s.background = { color: C.bodyBg };
    addContentHeader(s, title, tag);

    s.addImage({
      path: imgPath,
      x: 0.35, y: 0.9, w: 9.3, h: 4.5,
      sizing: { type: "contain", w: 9.3, h: 4.5 },
    });

    addFooter(s, `5–${5 + ci}`, "—");
    slides.push(s);
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDES — AI Analysis sections (one slide per section)
  // ═══════════════════════════════════════════════════════════════════════════
  const sectionMeta = [
    { key: "company_overview",   num: 2, title: "Company Overview",            sub: "Business Model & Strategy" },
    { key: "trend_analysis",     num: 3, title: "Price & Trend Analysis",      sub: "Momentum & MA Signals" },
    { key: "risk_adjusted",      num: 4, title: "Return Distribution & Risk",  sub: "Sharpe, Skew & Kurtosis" },
    { key: "risk_commentary",    num: 4, title: "Risk Commentary",             sub: "Volatility & Macro Factors" },
    { key: "news_sentiment",     num: 5, title: "News Sentiment",              sub: "Narrative Analysis" },
    { key: "cross_asset",        num: 6, title: "Cross-Asset Comparison",      sub: "Valuation & Diversification" },
    { key: "investment_view",    num: 7, title: "Investment Perspective",      sub: "Recommendation & Key Metrics" },
  ];

  sectionMeta.forEach(({ key, num, title, sub }) => {
    const text = sections[key];
    if (!text) return;

    // Split into paragraphs; pick best 2-3 for the slide
    const paras = text
      .split(/\n\n+/)
      .map(p => p.replace(/\n/g, " ").trim())
      .filter(p => p.length > 40)
      .slice(0, 3);

    const s = pres.addSlide();
    addSectionBanner(s, num, title, sub);

    // Right content panel
    s.background = { color: C.bodyBg };
    // Re-draw the left banner (addSectionBanner already drew on the slide)

    paras.forEach((para, pi) => {
      const yBase = 0.75 + pi * 1.55;
      // Para container
      s.addShape("rect", {
        x: 3.4, y: yBase, w: 6.25, h: 1.42,
        fill: { color: C.white }, shadow: makeShadow(),
        line: { color: "E2E8F0", width: 0.5 },
      });
      s.addText(truncate(para, 340), {
        x: 3.55, y: yBase + 0.06, w: 6.0, h: 1.3,
        fontSize: 9.5, color: C.darkGrey, fontFace: F.body,
        align: "left", valign: "top", wrap: true, margin: 0,
      });
    });

    addFooter(s, "—", "—");
    slides.push(s);
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // SLIDE — Closing / Key Takeaways
  // ═══════════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };

    s.addShape("rect", {
      x: 0, y: 0, w: 0.18, h: 5.625,
      fill: { color: C.gold },
    });

    s.addText("KEY TAKEAWAYS", {
      x: 0.5, y: 0.5, w: 9, h: 0.4,
      fontSize: 11, color: C.ice, fontFace: F.body,
      align: "left", charSpacing: 3, margin: 0,
    });
    s.addText("Investment Summary", {
      x: 0.5, y: 0.95, w: 9, h: 0.75,
      fontSize: 34, bold: true, color: C.white, fontFace: F.head,
      align: "left", margin: 0,
    });

    // Takeaway cards from investment_view section
    const investText = sections["investment_view"] || "";
    const paras = investText
      .split(/\n\n+/)
      .map(p => p.replace(/\n/g, " ").trim())
      .filter(p => p.length > 40)
      .slice(0, 3);

    const cardLabels = ["Most Attractive Asset", "Highest Risk Asset", "Final Recommendation"];
    const cardAccents = [C.green, C.red, C.gold];

    paras.forEach((para, i) => {
      const x = 0.45 + i * 3.2;
      s.addShape("rect", {
        x, y: 1.9, w: 3.0, h: 3.3,
        fill: { color: C.navyMid }, line: { color: "304080", width: 0.5 },
      });
      s.addShape("rect", {
        x, y: 1.9, w: 3.0, h: 0.06,
        fill: { color: cardAccents[i] },
      });
      s.addText(cardLabels[i], {
        x: x + 0.12, y: 1.98, w: 2.76, h: 0.38,
        fontSize: 10, bold: true, color: cardAccents[i], fontFace: F.head,
        align: "left", margin: 0,
      });
      s.addText(truncate(para, 260), {
        x: x + 0.12, y: 2.4, w: 2.76, h: 2.65,
        fontSize: 9, color: C.ice, fontFace: F.body,
        align: "left", valign: "top", wrap: true, margin: 0,
      });
    });

    // Footer
    s.addText(`FinAgent  •  ${genDate}  •  Groq AI  •  Data: Yahoo Finance`, {
      x: 0.5, y: 5.2, w: 9, h: 0.3,
      fontSize: 8, color: C.grey, fontFace: F.body,
      align: "center", margin: 0,
    });

    slides.push(s);
  }

  // ─── Write file ────────────────────────────────────────────────────────────
  await pres.writeFile({ fileName: outFile });
  console.log(`✓ Saved: ${outFile}  (${slides.length} slides)`);
}

buildDeck().catch(err => { console.error(err); process.exit(1); });
