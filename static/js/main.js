/* ============================================================
   ROMAX DIGITAL, Wallet Pass Creator
   main.js: Frontend Logic
   ============================================================ */

'use strict';

// State
let passData = {};
let barcodeType = 'QR'; // always show QR in preview
let currentWallet = 'apple';
let qrInstanceApple = null;
let qrInstanceGoogle = null;

// DOM refs
const $  = (id) => document.getElementById(id);
const $$ = (sel) => document.querySelector(sel);

// Init
document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  renderQR('ROMAX-DEMO-2026', 'qrCanvas');
  renderQR('ROMAX-DEMO-2026', 'qrCanvasGoogle');
  syncColourInputs();
  loadSavedPassFromQuery();

  // Stage 1 -> Stage 2: reuse Company / Contact / Email on the signup link
  const signupLink = $('modalSignupLink');
  if (signupLink) {
    signupLink.addEventListener('click', () => {
      const base = signupLink.getAttribute('href').split('?')[0];
      const params = new URLSearchParams({
        organisation: ($('fBrandName') && $('fBrandName').value) || '',
        email: ($('fEmail') && $('fEmail').value) || '',
      });
      signupLink.setAttribute('href', `${base}?${params.toString()}`);
    });
  }
});

// Event Binding
function bindEvents() {
  $('btnCreate').addEventListener('click', handleCreate);
  $('websiteUrl').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleCreate(); });
  $('btnUpdate').addEventListener('click', updatePreview);
  $('btnExportApple').addEventListener('click', handleExportApple);
  $('btnExportGoogle').addEventListener('click', handleExportGoogle);
  $('btnSaveDesign').addEventListener('click', handleSaveDesign);
  $('btnShare').addEventListener('click', () => $('emailModal').classList.remove('hidden'));
  $('btnVerify').addEventListener('click', handleVerify);
  $('verifyCode').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleVerify(); });
  $('btnLoadMembers').addEventListener('click', loadMembers);
  $('btnAddMember').addEventListener('click', handleAddMember);
  $('newMemberName').addEventListener('keydown', (e) => { if (e.key === 'Enter') handleAddMember(); });
  $('memberSearch').addEventListener('input', filterMembers);
  $('memberFilter').addEventListener('change', filterMembers);
  $('btnSendEmail').addEventListener('click', handleEmailCapture);
  $('burgerBtn').addEventListener('click', toggleMobileMenu);

  // Manual logo / banner image upload
  $('fLogoUpload').addEventListener('change', (e) => handleImageUpload(e, 'logo'));
  $('fBannerUpload').addEventListener('change', (e) => handleImageUpload(e, 'banner'));
  $('btnClearLogo').addEventListener('click', () => clearUploadedImage('logo'));
  $('btnClearBanner').addEventListener('click', () => clearUploadedImage('banner'));

  // Sync colour pickers ↔ hex inputs
  // Colour swatch live sync
  ['fPrimaryColor','fSecondaryColor','fTextColor'].forEach(id => {
    const el = $(id);
    if (el) el.addEventListener('input', () => updatePreview());
  });

  // Live field sync on typing
  ['fBrandName','fMemberName','fTier','fQrValue'].forEach(id => {
    $(id).addEventListener('input', () => {
      debounce(updatePreview, 400)();
    });
  });
}

// Dynamic field delegation (card fields added at runtime)
document.addEventListener('input', (e) => {
  if (e.target.classList.contains('field-label-input') ||
      e.target.classList.contains('field-value-input')) {
    debounce(updatePreview, 300)();
  }
});

// fExpiry change also updates preview
document.addEventListener('change', (e) => {
  if (e.target && e.target.id === 'fExpiry') updatePreview();
});

// Quick fill demo URLs
window.quickFill = function(url) {
  $('websiteUrl').value = url;
  handleCreate();
};

// Create Pass from URL
async function handleCreate() {
  const url = $('websiteUrl').value.trim();
  if (!url) { showAlert('Please enter a website URL first.', 'error'); return; }

  setBusy(true);
  hideAlert();

  try {
    const res = await fetch('/api/scrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (data.error) { showAlert(data.error, 'error'); setBusy(false); return; }

    passData = { ...data, serial: generateSerial() };
    populateEditor(data);
    renderVariantGrid(data.design_variants || [], 'corner-classic');
    updatePreview();
    showEditor();
    showAlert(`✓ Brand data extracted from ${data.brand_name || url}`, 'success');
    updateCompleteness();

    // Smooth scroll to preview
    setTimeout(() => {
      $('creator').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 300);

  } catch (err) {
    showAlert('Connection error. Is the backend running? (python app.py)', 'error');
  } finally {
    setBusy(false);
  }
}

// Populate Editor Fields
function populateEditor(d) {
  $('fBrandName').value   = d.brand_name || '';
  $('fPassType').value    = d.pass_type  || 'Membership Card';
  $('fPassTitle').value   = d.pass_title || '';
  $('fMemberName').value  = d.member_name || 'Digital Member';
  $('fTier').value        = d.tier || 'Standard';
  $('fExpiry').value      = d.expiry || '31/12/2026';
  $('fQrValue').value     = d.qr_value || generateSerial();
  $('fEmail').value       = d.email || '';
  $('fPhone').value       = d.phone || '';

  const primary   = d.primary_color   || '#1A6B8A';
  const secondary = d.secondary_color || '#0F4A61';

  $('fPrimaryColor').value    = primary;
  $('fPrimaryColorHex').value = primary;
  $('fSecondaryColor').value  = secondary;
  $('fSecondaryColorHex').value = secondary;
  $('fTextColor').value       = d.foreground_color || bestForeground(primary);
}

// Update Live Preview
function updatePreview() {
  const brand  = $('fBrandName').value  || 'Your Organisation';
  const ptype  = $('fPassType').value   || 'Membership Card';
  const passTitle = $('fPassTitle') ? $('fPassTitle').value.trim() : '';
  const displayType = passTitle || ptype; // custom title overrides the pass type label on the card
  const member = $('fMemberName').value || 'Digital Member';
  const tier   = $('fTier').value       || 'Gold';
  const expiry = $('fExpiry').value     || '31/12/2026';
  const qrVal  = $('fQrValue').value    || 'ROMAX-DEMO';
  const primary   = $('fPrimaryColor').value || '#1A6B8A';
  const secondary = $('fSecondaryColor').value || '#0F4A61';
  const fg = $('fTextColor').value || bestForeground(primary);

  // ---- Read dynamic card fields
  const cardFieldRows = document.querySelectorAll('#cardFieldsList .card-field-row');
  const customFields = [];
  cardFieldRows.forEach(row => {
    const label = row.querySelector('.field-label-input');
    const value = row.querySelector('.field-value-input');
    if (label && value && label.value.trim()) {
      customFields.push({ label: label.value.trim(), value: value.value.trim() });
    }
  });

  // ---- Apple pass fields
  setText('prevOrgName',    brand);
  setText('prevPassType',   displayType);
  setText('prevLogo',       logoInitials(brand));
  // Member name = first field value (if exists)
  const firstField = customFields[0];
  setText('prevMemberName', firstField ? firstField.value || firstField.label : member);

  // Render dynamic fields into apple pass
  const appleFieldsEl = document.querySelector('#appleCard .apple-pass-fields');
  if (appleFieldsEl) {
    appleFieldsEl.innerHTML = customFields.map(f => `
      <div class="apple-field">
        <span class="apple-field-label">${escHtml(f.label.toUpperCase())}</span>
        <span class="apple-field-value">${escHtml(f.value || 'N/A')}</span>
      </div>`).join('');
    // Always add expiry at the end
    const expiryVal = $('fExpiry') ? $('fExpiry').value : expiry;
    if (expiryVal && expiryVal !== 'No expiry') {
      appleFieldsEl.innerHTML += `
        <div class="apple-field">
          <span class="apple-field-label">VALID UNTIL</span>
          <span class="apple-field-value">${escHtml(expiryVal)}</span>
        </div>`;
    }
  }

  // ---- Google pass fields
  setText('gPrevOrgName',    brand);
  setText('gPrevPassType',   displayType);
  setText('gPrevLogo',       logoInitials(brand));
  setText('gPrevMemberName', firstField ? firstField.value || firstField.label : member);

  const googleFieldsEl = document.querySelector('#googleCard .google-fields');
  if (googleFieldsEl) {
    googleFieldsEl.innerHTML = customFields.map(f => `
      <div class="google-field">
        <span>${escHtml(f.label.toUpperCase())}</span>
        <strong>${escHtml(f.value || 'N/A')}</strong>
      </div>`).join('');
    const expiryVal = $('fExpiry') ? $('fExpiry').value : expiry;
    if (expiryVal && expiryVal !== 'No expiry') {
      googleFieldsEl.innerHTML += `
        <div class="google-field">
          <span>VALID UNTIL</span>
          <strong>${escHtml(expiryVal)}</strong>
        </div>`;
    }
  }

  // ---- Hero phone card
  setText('heroOrg',  brand);
  setText('heroLogo', logoInitials(brand));

  // ---- Card background colours
  const gradient = `linear-gradient(135deg, ${primary}, ${secondary})`;
  setStyle('appleCard',  'background', gradient);
  setStyle('googleCard', 'background', gradient);
  setStyle('phoneCard',  'background', gradient);
  setStyle('appleCard',  'color', fg);
  setStyle('googleCard', 'color', fg);
  setStyle('phoneCard',  'color', fg);

  // ---- Logo images
  if (passData.logo_base64) {
    setLogoImage('prevLogo', passData.logo_base64);
    setLogoImage('gPrevLogo', passData.logo_base64);
    setLogoImage('heroLogo', passData.logo_base64);
  }

  // ---- QR code
  renderQR(qrVal, 'qrCanvas');
  renderQR(qrVal, 'qrCanvasGoogle');

  // ---- Pass Info table
  updatePassInfoTable({
    'Organisation': brand, 'Pass Type': displayType,
    'Member': member, 'Tier': tier,
    'Valid Until': expiry, 'QR/Barcode': qrVal,
    'Primary Colour': primary, 'Email': $('fEmail').value,
    'Phone': $('fPhone').value,
  });

  // ---- Completeness
  updateCompleteness();

  // ---- Merge into passData
  Object.assign(passData, {
    brand_name: brand, pass_type: ptype, pass_title: passTitle, member_name: member,
    tier, expiry, qr_value: qrVal,
    primary_color: primary, secondary_color: secondary,
    foreground_color: fg,
    email: $('fEmail').value, phone: $('fPhone').value,
    custom_fields: customFields,
    barcode_type: barcodeType,
  });

  applyCardLayout(passData.layout || 'corner-classic');
}

// Completeness Score
function updateCompleteness() {
  const checks = [
    { label: 'Organisation name', ok: !!($('fBrandName').value) },
    { label: 'Pass type set',     ok: !!($('fPassType').value) },
    { label: 'Member name',       ok: !!($('fMemberName').value) },
    { label: 'Expiry date',       ok: !!($('fExpiry').value) },
    { label: 'Logo detected',     ok: !!(passData.logo_url || passData.logo_base64) },
    { label: 'Primary colour',    ok: !!($('fPrimaryColor').value) },
    { label: 'Contact info',      ok: !!($('fEmail').value || $('fPhone').value) },
    { label: 'QR value set',      ok: !!($('fQrValue').value) },
  ];

  const score = Math.round((checks.filter(c => c.ok).length / checks.length) * 100);
  $('completenessScore').textContent = score + '%';
  $('progressFill').style.width = score + '%';

  const hint_el = $('completenessHints');
  hint_el.innerHTML = checks.map(c =>
    `<li><span class="${c.ok ? 'hint-ok' : 'hint-warn'}">${c.ok ? '✓' : '○'}</span> ${c.label}</li>`
  ).join('');

  $('completenessWidget').classList.remove('hidden');
}

// Show Editor / Export after scrape
function showEditor() {
  $('editorPanel').classList.remove('hidden');
  $('designVariantsSection').classList.remove('hidden');
  $('walletTabs').classList.remove('hidden');
  $('applePreview').classList.remove('hidden');
  $('passInfoPanel').classList.remove('hidden');
  $('exportActions').classList.remove('hidden');
  $('ctaPlatform').classList.remove('hidden');
}

// Wallet Tab Switching
window.switchWallet = function(wallet, evt) {
  currentWallet = wallet;
  const clickEvent = evt || window.event;
  document.querySelectorAll('.wallet-tab').forEach(t => t.classList.remove('active'));
  if (clickEvent && clickEvent.currentTarget) clickEvent.currentTarget.classList.add('active');
  if (wallet === 'apple') {
    $('applePreview').classList.remove('hidden');
    $('googlePreview').classList.add('hidden');
  } else {
    $('applePreview').classList.add('hidden');
    $('googlePreview').classList.remove('hidden');
  }
};

// Barcode Type Toggle
// setBarcodeType defined below (overridden by the extended version at end of file)
window.setBarcodeType = function(type) {
  barcodeType = type;
  const area = $('barcodeArea');
  if (area) area.style.display = ''; // always show for demo
  renderQR($('fQrValue').value || 'ROMAX-DEMO', 'qrCanvas');
  renderQR($('fQrValue').value || 'ROMAX-DEMO', 'qrCanvasGoogle');
};

// QR Rendering
function renderQR(value, containerId) {
  const el = $(containerId);
  if (!el) return;
  el.innerHTML = ''; // clear previous

  if (barcodeType === 'BARCODE') {
    // Draw barcode via SVG
    el.innerHTML = drawBarcodeSVG(value);
    return;
  }

  // QR mode: use QRCode.js, it renders an image into the div
  if (typeof QRCode !== 'undefined') {
    const size = containerId === 'qrCanvas' ? 120 : 100;
    new QRCode(el, {
      text: value || 'ROMAX-DEMO',
      width: size,
      height: size,
      colorDark: '#000000',
      colorLight: '#ffffff',
      correctLevel: QRCode.CorrectLevel.M,
    });
  } else {
    // Fallback: SVG-based QR-like pattern
    el.innerHTML = drawFallbackQRSVG(value);
  }
}

function drawFallbackQRSVG(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) | 0;
  const cells = 21;
  const size = 5;
  let rects = '';
  for (let r = 0; r < cells; r++) {
    for (let c = 0; c < cells; c++) {
      const isFinder = (r < 7 && c < 7) || (r < 7 && c >= cells-7) || (r >= cells-7 && c < 7);
      const bit = isFinder || (((hash >> ((r * cells + c) % 32)) & 1) === 1);
      if (bit) rects += `<rect x="${c*size}" y="${r*size}" width="${size-1}" height="${size-1}" fill="#000"/>`;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${cells*size}" height="${cells*size}" style="background:#fff;display:block">${rects}</svg>`;
}

function drawBarcodeSVG(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) | 0;
  const bars = 60; const w = 120; const h = 60;
  const barW = w / bars;
  let rects = '';
  for (let i = 0; i < bars; i++) {
    if ((hash >> (i % 32)) & 1) {
      rects += `<rect x="${(i*barW).toFixed(1)}" y="4" width="${Math.max(1,barW-1).toFixed(1)}" height="${h-8}" fill="#000"/>`;
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" style="background:#fff;display:block">${rects}</svg>`;
}

// Design Variant Picker (2-3 looks from the SAME scrape)
function renderVariantGrid(variants, defaultId) {
  const grid = $('variantGrid');
  if (!grid) return;
  if (!variants.length) { $('designVariantsSection').classList.add('hidden'); return; }

  passData.all_variants = variants;
  grid.innerHTML = variants.map(v => `
    <div class="variant-card ${v.id === defaultId ? 'active' : ''}" data-variant-id="${v.id}">
      <div class="variant-swatch" style="background:linear-gradient(135deg, ${v.primary_color}, ${v.secondary_color})"></div>
      <div class="variant-card-name">${escHtml(v.name)}</div>
      <div class="variant-card-desc">${escHtml(v.description)}</div>
    </div>
  `).join('');

  grid.querySelectorAll('.variant-card').forEach(card => {
    card.addEventListener('click', () => selectVariant(card.getAttribute('data-variant-id')));
  });

  selectVariant(defaultId);
}

function selectVariant(variantId) {
  const variants = passData.all_variants || [];
  const variant = variants.find(v => v.id === variantId) || variants[0];
  if (!variant) return;

  document.querySelectorAll('.variant-card').forEach(c =>
    c.classList.toggle('active', c.getAttribute('data-variant-id') === variant.id));

  $('fPrimaryColor').value      = variant.primary_color;
  $('fPrimaryColorHex').value   = variant.primary_color;
  $('fSecondaryColor').value    = variant.secondary_color;
  $('fSecondaryColorHex').value = variant.secondary_color;
  $('fTextColor').value         = variant.foreground_color;

  if (variant.banner_base64) passData.banner_base64 = variant.banner_base64;
  applyCardLayout(variant.layout);

  passData.design_variant = variant.id;
  updatePreview();
}

// Manual logo / banner image upload
// Both are resized on a canvas to a standard size before being stored,
// so every card renders the logo/image at a consistent, non-distorted size.
const LOGO_STANDARD_PX = 320;      // square
const BANNER_STANDARD_W = 680;     // 3.4 : 1, matches .apple-pass-banner ratio
const BANNER_STANDARD_H = 200;

function resizeImageFile(file, targetW, targetH, fit /* 'contain' | 'cover' */) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = targetW;
        canvas.height = targetH;
        const ctx = canvas.getContext('2d');
        const srcRatio = img.width / img.height;
        const dstRatio = targetW / targetH;
        let sx = 0, sy = 0, sw = img.width, sh = img.height;
        let dx = 0, dy = 0, dw = targetW, dh = targetH;

        if (fit === 'cover') {
          // crop source to match target ratio, then fill target exactly
          if (srcRatio > dstRatio) {
            sw = img.height * dstRatio;
            sx = (img.width - sw) / 2;
          } else {
            sh = img.width / dstRatio;
            sy = (img.height - sh) / 2;
          }
        } else {
          // contain: fit whole image inside target, transparent letterbox
          ctx.clearRect(0, 0, targetW, targetH);
          if (srcRatio > dstRatio) {
            dw = targetW; dh = targetW / srcRatio; dy = (targetH - dh) / 2;
          } else {
            dh = targetH; dw = targetH * srcRatio; dx = (targetW - dw) / 2;
          }
          sx = 0; sy = 0; sw = img.width; sh = img.height;
        }

        ctx.drawImage(img, sx, sy, sw, sh, dx, dy, dw, dh);
        resolve(canvas.toDataURL('image/png'));
      };
      img.onerror = reject;
      img.src = reader.result;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function handleImageUpload(e, kind) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  try {
    if (kind === 'logo') {
      const dataUrl = await resizeImageFile(file, LOGO_STANDARD_PX, LOGO_STANDARD_PX, 'contain');
      passData.logo_base64 = dataUrl;
      passData.logo_url = '';
      setLogoImage('prevLogo', dataUrl);
      setLogoImage('gPrevLogo', dataUrl);
      setLogoImage('heroLogo', dataUrl);
    } else {
      const dataUrl = await resizeImageFile(file, BANNER_STANDARD_W, BANNER_STANDARD_H, 'cover');
      passData.banner_base64 = dataUrl;
      passData.banner_url = '';
    }
    updatePreview();
    showAlert(kind === 'logo' ? '✓ Custom logo added' : '✓ Custom card image added', 'success');
  } catch (err) {
    showAlert('Could not process that image, try a different file.', 'error');
  }
}

function clearUploadedImage(kind) {
  if (kind === 'logo') {
    passData.logo_base64 = null;
    $('fLogoUpload').value = '';
    const brand = $('fBrandName').value || 'Romax Digital';
    ['prevLogo', 'gPrevLogo', 'heroLogo'].forEach(id => {
      const el = $(id);
      if (el) { el.style.backgroundImage = ''; el.textContent = logoInitials(brand); }
    });
  } else {
    passData.banner_base64 = null;
    $('fBannerUpload').value = '';
  }
  updatePreview();
}

// Apply card layout (3 distinct designs, not just colour)
function applyCardLayout(layout) {
  const l = layout || 'corner-classic';
  ['appleCard', 'googleCard'].forEach(id => {
    const el = $(id);
    if (el) el.setAttribute('data-layout', l);
  });

  const captions = {
    'corner-classic': 'Classic Corner: logo badge top-left, details stacked below',
    'image-strip': 'Image Strip: brand image band beneath the barcode',
    'side-band': 'Side Band: bold colour band with centred logo',
  };
  const captionEl = $('layoutCaption');
  if (captionEl) captionEl.textContent = captions[l] || '';

  const bannerSrc = passData.banner_base64 || null;
  ['appleBanner', 'googleBanner'].forEach(id => {
    const el = $(id);
    if (!el) return;
    if (l === 'image-strip') {
      el.style.display = 'block';
      el.style.backgroundImage = bannerSrc ? `url(${bannerSrc})` : `linear-gradient(135deg, ${passData.primary_color || '#1A6B8A'}, ${passData.secondary_color || '#0F4A61'})`;
    } else {
      el.style.display = 'none';
    }
  });

  passData.layout = l;
}


function updatePassInfoTable(obj) {
  const table = $('passInfoTable');
  table.innerHTML = Object.entries(obj)
    .filter(([, v]) => v)
    .map(([k, v]) => {
      const display = k === 'Primary Colour'
        ? `<span style="display:inline-block;width:12px;height:12px;border-radius:3px;background:${v};margin-right:.4rem;vertical-align:middle;"></span>${v}`
        : escHtml(v);
      return `<tr><td>${escHtml(k)}</td><td>${display}</td></tr>`;
    }).join('');
}

// Wallet result banner helper
function showWalletBanner(html, kind) {
  const el = $('walletResultBanner');
  el.className = `wallet-result-banner ${kind}`;
  el.innerHTML = html;
  el.classList.remove('hidden');
}

// Export: REAL Apple Wallet .pkpass
async function handleExportApple() {
  if (!passData.brand_name) { showAlert('Create a pass first!', 'error'); return; }
  const btn = $('btnExportApple');
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = 'Building pass…';
  try {
    const res = await fetch('/api/generate-pass/apple', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(passData),
    });
    const data = await res.json();
    if (data.download_url) {
      const a = document.createElement('a');
      a.href = data.download_url;
      a.download = '';
      a.click();
    }
    if (data.signed) {
      showWalletBanner(
        `&#10003; Signed &amp; installable <strong>.pkpass</strong> downloaded. Open it on iPhone (or double-click on Mac) to add it to Apple Wallet. Serial: ${escHtml(data.serial)}`,
        'signed'
      );
      showAlert('✓ Real Apple Wallet pass downloaded!', 'success');
    } else if (data.logged_in) {
      showWalletBanner(
        `This is an <strong>unsigned preview</strong> .pkpass (same structure, images and fields, just not cryptographically signed yet). ` +
        `<a href="/settings/wallet">Connect your Apple certificates in Wallet Setup</a> to generate a real, installable pass.`,
        'unsigned'
      );
      showAlert('✓ Preview pass downloaded (unsigned)', 'success');
    } else {
      showWalletBanner(
        `This is an <strong>unsigned preview</strong> .pkpass. <a href="/signup">Sign up</a> and connect your Apple certificates to generate a real, installable pass.`,
        'unsigned'
      );
      showAlert('✓ Preview pass downloaded (unsigned)', 'success');
    }
  } catch (err) {
    showAlert('Export failed. Is the backend running?', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

// Export: REAL Google Wallet save link
async function handleExportGoogle() {
  if (!passData.brand_name) { showAlert('Create a pass first!', 'error'); return; }
  const btn = $('btnExportGoogle');
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = 'Building pass…';
  try {
    const res = await fetch('/api/generate-pass/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(passData),
    });
    const data = await res.json();

    if (data.configured && data.save_url) {
      window.open(data.save_url, '_blank');
      showWalletBanner(
        `&#10003; Real <strong>Add to Google Wallet</strong> link generated and opened in a new tab. ` +
        `<a href="${data.save_url}" target="_blank">Open it again</a> if the tab didn't appear.`,
        'signed'
      );
      showAlert('✓ Google Wallet save link opened!', 'success');
    } else if (data.logged_in) {
      showWalletBanner(
        `This is a <strong>preview only</strong>. ${escHtml(data.reason || 'Google Wallet is not connected yet.')} ` +
        `<a href="/settings/wallet">Connect Google Wallet in Wallet Setup</a> to generate a real "Add to Google Wallet" link.`,
        'unsigned'
      );
      showAlert('Preview generated (not a real pass yet)', 'success');
    } else {
      showWalletBanner(
        `This is a <strong>preview only</strong>. <a href="/signup">Sign up</a> and connect Google Wallet to generate a real "Add to Google Wallet" link.`,
        'unsigned'
      );
      showAlert('Preview generated (not a real pass yet)', 'success');
    }
  } catch (err) {
    showAlert('Export failed. Is the backend running?', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

// Save design to dashboard (requires login)
async function handleSaveDesign() {
  if (!passData.brand_name) { showAlert('Create a pass first!', 'error'); return; }
  if (!window.IS_LOGGED_IN) {
    $('loginPromptModal').classList.remove('hidden');
    return;
  }
  try {
    const res = await fetch('/api/save-pass', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(passData),
    });
    const data = await res.json();
    if (data.saved) {
      showAlert('✓ Saved to your dashboard.', 'success');
    } else {
      showAlert(data.error || 'Could not save design.', 'error');
    }
  } catch (err) {
    showAlert('Save failed. Is the backend running?', 'error');
  }
}

// Load a previously-saved pass from the Dashboard
async function loadSavedPassFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const loadId = params.get('load_pass');
  if (!loadId || !window.IS_LOGGED_IN) return;
  try {
    const res = await fetch('/api/my-passes');
    const list = await res.json();
    const found = list.find(p => String(p.id) === String(loadId));
    if (!found) return;
    const cfg = found.config || {};
    passData = { ...cfg };
    populateEditor(cfg);
    renderVariantGrid(cfg.all_variants || [], cfg.design_variant || 'corner-classic');
    updatePreview();
    showEditor();
    updateCompleteness();
    showAlert(`✓ Loaded "${found.brand_name}" from your dashboard`, 'success');
    setTimeout(() => $('creator').scrollIntoView({ behavior: 'smooth' }), 300);
  } catch (err) { /* silent */ }
}

// Email Capture
function handleEmailCapture() {
  const email = $('captureEmail').value.trim();
  if (!email || !email.includes('@')) { return; }
  // In production this would POST to a CRM endpoint
  $('emailFeedback').classList.remove('hidden');
  $('btnSendEmail').disabled = true;
  setTimeout(() => {
    $('emailModal').classList.add('hidden');
    $('emailFeedback').classList.add('hidden');
    $('btnSendEmail').disabled = false;
  }, 2500);
}

// Member CRM
let allMembers = [];

async function loadMembers() {
  $('btnLoadMembers').textContent = 'Loading…';
  try {
    const res = await fetch('/api/members');
    allMembers = await res.json();
    renderMembers(allMembers);
  } catch (err) {
    $('membersBody').innerHTML = '<tr><td colspan="7" class="table-empty">Could not load members.</td></tr>';
  } finally {
    $('btnLoadMembers').textContent = 'Refresh';
  }
}

function renderMembers(list) {
  if (!list.length) {
    $('membersBody').innerHTML = '<tr><td colspan="7" class="table-empty">No members found. Add one above.</td></tr>';
    return;
  }
  $('membersBody').innerHTML = list.map(m => `
    <tr>
      <td><code>${escHtml(m.id)}</code></td>
      <td>${escHtml(m.name)}</td>
      <td><span class="tier-${m.tier}">${m.tier}</span></td>
      <td>${m.joined}</td>
      <td><span class="status-badge status-${m.status}">${m.status}</span></td>
      <td>${m.checkins}</td>
      <td style="display:flex;gap:.4rem">
        <button class="btn-issue-pass" onclick="issuePassForMember('${escHtml(m.id)}','${escHtml(m.name)}','${m.tier}')">Issue Pass</button>
        <button class="btn-remove-field" title="Delete" onclick="handleDeleteMember('${escHtml(m.id)}')">&#x2715;</button>
      </td>
    </tr>
  `).join('');
}

function showCrmFeedback(msg, type = 'success') {
  const el = $('crmFeedback');
  if (!el) { showAlert(msg, type); return; }
  el.textContent = msg;
  el.className = `alert ${type === 'error' ? 'error' : 'success'}`;
  el.classList.remove('hidden');
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  clearTimeout(showCrmFeedback._t);
  showCrmFeedback._t = setTimeout(() => el.classList.add('hidden'), 4000);
}

async function handleAddMember() {
  const nameInput = $('newMemberName');
  const name = nameInput.value.trim();
  const tier = $('newMemberTier').value;
  if (!name) {
    showCrmFeedback('Enter a member name first.', 'error');
    nameInput.focus();
    return;
  }

  const btn = $('btnAddMember');
  const originalLabel = btn.textContent;
  btn.disabled = true;
  btn.textContent = 'Adding…';

  try {
    const res = await fetch('/api/members', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, tier }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Could not add member.');

    nameInput.value = '';
    showCrmFeedback(`✓ ${name} added to members.`, 'success');
    await loadMembers();
  } catch (err) {
    showCrmFeedback(err.message || 'Could not add member.', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = originalLabel;
  }
}

window.handleDeleteMember = async function(id) {
  if (!confirm('Remove this member?')) return;
  try {
    const res = await fetch(`/api/members/${encodeURIComponent(id)}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Could not delete member.');
    showCrmFeedback('✓ Member removed.', 'success');
    await loadMembers();
  } catch (err) {
    showCrmFeedback(err.message || 'Could not delete member.', 'error');
  }
};

function filterMembers() {
  const q      = $('memberSearch').value.toLowerCase();
  const status = $('memberFilter').value;
  const filtered = allMembers.filter(m =>
    (!q || m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q)) &&
    (!status || m.status === status)
  );
  renderMembers(filtered);
}

window.issuePassForMember = function(id, name, tier) {
  $('fMemberName').value = name;
  $('fTier').value       = tier;
  $('fQrValue').value    = id;
  updatePreview();
  $('creator').scrollIntoView({ behavior: 'smooth' });
  showAlert(`✓ Editing pass for ${name}. Scroll up to preview.`, 'success');
};

// QR Verify
async function handleVerify() {
  const code = $('verifyCode').value.trim();
  if (!code) return;
  $('btnVerify').textContent = '…';
  try {
    const res = await fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    const el = $('verifyResult');
    el.classList.remove('hidden', 'verify-valid', 'verify-invalid');

    if (data.valid) {
      el.classList.add('verify-valid');
      el.innerHTML = `
        <div style="color:#4caf50;font-weight:700;margin-bottom:.5rem">✓ Valid Membership</div>
        ${makeVerifyRow('Member', data.member)}
        ${makeVerifyRow('Tier', data.tier)}
        ${makeVerifyRow('Status', data.status)}
        ${makeVerifyRow('Valid Until', data.expires)}
        ${makeVerifyRow('Checked in', data.checkin_time)}
      `;
    } else {
      el.classList.add('verify-invalid');
      el.innerHTML = `<div>✗ Invalid or expired. ${data.message}</div>`;
    }
  } catch (err) {
    showAlert('Verify endpoint unavailable.', 'error');
  } finally {
    $('btnVerify').textContent = 'Verify';
  }
}

function makeVerifyRow(label, value) {
  return `<div class="verify-result-row"><span style="color:rgba(255,255,255,.5)">${label}</span><strong>${escHtml(value)}</strong></div>`;
}

// Helpers
function showAlert(msg, type = 'success') {
  const el = $('alertBanner');
  el.textContent = msg;
  el.className = `alert ${type}`;
  el.classList.remove('hidden');
  if (type === 'success') setTimeout(hideAlert, 4000);
}
function hideAlert() { $('alertBanner').classList.add('hidden'); }

function setBusy(state) {
  const btn = $('btnCreate');
  $('btnCreateText').textContent = state ? 'Analysing…' : 'Create Pass';
  $('spinner').classList.toggle('hidden', !state);
  btn.disabled = state;
}

function setText(id, text) {
  const el = $(id); if (el) el.textContent = text;
}
function setStyle(id, prop, val) {
  const el = $(id); if (el) el.style[prop] = val;
}

function setLogoImage(containerId, src) {
  const el = $(containerId);
  if (!el) return;
  el.innerHTML = `<img src="${src}" alt="logo" style="width:100%;height:100%;object-fit:contain;border-radius:6px;">`;
}

function logoInitials(name) {
  if (!name) return 'RD';
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function bestForeground(hex) {
  try {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const lin = c => { const s = c / 255; return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
    const L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
    return L < 0.35 ? '#FFFFFF' : '#000000';
  } catch { return '#FFFFFF'; }
}

function generateSerial() {
  return Math.random().toString(36).substring(2, 14).toUpperCase();
}

function syncColourInputs() {
  const hex1 = $('fPrimaryColorHex');
  const hex2 = $('fSecondaryColorHex');
  if (hex1) hex1.value = $('fPrimaryColor').value;
  if (hex2) hex2.value = $('fSecondaryColor').value;
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

let debounceTimer;
function debounce(fn, delay) {
  return (...args) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => fn(...args), delay);
  };
}

function toggleMobileMenu() {
  const links = document.querySelector('.nav-links');
  if (links) {
    const open = links.style.display === 'flex';
    links.style.display = open ? 'none' : 'flex';
    links.style.flexDirection = 'column';
    links.style.position = 'absolute';
    links.style.top = '64px';
    links.style.right = '1rem';
    links.style.background = 'var(--surface-2)';
    links.style.border = '1px solid var(--border)';
    links.style.padding = '1rem';
    links.style.borderRadius = 'var(--radius-sm)';
    links.style.gap = '.8rem';
    links.style.zIndex = '200';
    if (open) links.style.display = 'none';
  }
}

// Scroll animations
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.style.opacity = '1';
      e.target.style.transform = 'translateY(0)';
    }
  });
}, { threshold: 0.15 });

document.querySelectorAll('.step, .creator-left, .creator-right, .crm-inner, .verify-card').forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(24px)';
  el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
  observer.observe(el);
});

// NEW: Pass Type Button Selection
window.selectPassType = function(btn) {
  document.querySelectorAll('.pass-type-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const type = btn.getAttribute('data-type');
  const sel = $('fPassType');
  if (sel) {
    for (let i = 0; i < sel.options.length; i++) {
      if (sel.options[i].value === type) { sel.selectedIndex = i; break; }
    }
  }
  updatePreview();
};

// NEW: Add / Remove dynamic card fields
window.addCardField = function() {
  const list = $('cardFieldsList');
  if (!list) return;
  const row = document.createElement('div');
  row.className = 'card-field-row';
  row.innerHTML = `
    <input type="text" placeholder="Label" class="field-label-input" />
    <input type="text" placeholder="Value" class="field-value-input" />
    <button class="btn-remove-field" onclick="removeCardField(this)" title="Remove">&#x2715;</button>`;
  list.appendChild(row);
  row.querySelector('.field-label-input').focus();
};

window.removeCardField = function(btn) {
  const row = btn.closest('.card-field-row');
  if (row) row.remove();
};

// NEW: Sync colour swatch to hidden hex
window.syncColorHex = function(colorId, hexId) {
  const hexEl = $(hexId);
  if (hexEl) hexEl.value = $(colorId).value;
  updatePreview();
};

// NEW: Toggle custom expiry input
window.toggleCustomExpiry = function(val) {
  const custom = $('fExpiryCustom');
  if (custom) custom.style.display = val === 'custom' ? 'block' : 'none';
};

// Override setBarcodeType to also handle radio + NONE
window.setBarcodeType = function(type) {
  barcodeType = type;
  // Sync radio buttons
  ['radioQR','radioBarcode','radioNone'].forEach(id => {
    const el = $(id);
    if (el) el.checked = (el.value === type);
  });
  // Legacy toggle buttons (may not exist in new layout)
  const bQR = $('btnQR'), bBar = $('btnBarcode');
  if (bQR) bQR.classList.toggle('active', type === 'QR');
  if (bBar) bBar.classList.toggle('active', type === 'BARCODE');
  // Show/hide barcode area
  const area = $('barcodeArea');
  if (area) area.style.display = ''; // always visible in preview
  renderQR($('fQrValue').value || 'ROMAX-DEMO', 'qrCanvas');
  renderQR($('fQrValue').value || 'ROMAX-DEMO', 'qrCanvasGoogle');
};
