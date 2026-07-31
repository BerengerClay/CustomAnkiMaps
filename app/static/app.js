document.addEventListener('DOMContentLoaded', () => {
  // Preset palettes mapping for 6 distinct categories
  const PRESETS = {
    anki: {
      water: '#FFFFFF',
      other_countries: '#CCCCCC',
      target_country: '#59A353',
      country_borders: '#FFFFFF',
      silhouette: '#CCCCCC',
      capital_map: '#000000',
      capital_silhouette: '#000000',
      grid_lines: '#D8D8D8'
    },
    modern_light: {
      water: '#E3F2FD',           // Bleu très doux
      other_countries: '#F5F5F5', // Gris très clair (fond neutre)
      target_country: '#3B82F6',  // Bleu franc (attire l'œil)
      country_borders: '#FFFFFF', // Frontières blanches
      silhouette: '#94A3B8',      // Gris bleuté pour la silhouette seule
      capital_map: '#EF4444',     // Rouge vif pour trancher avec le bleu
      capital_silhouette: '#EF4444', 
      grid_lines: '#DCE7F0'       // Quadrillage à peine visible
    },
    dark_pro: {
      water: '#0F172A',           // Bleu ardoise très sombre
      other_countries: '#1E293B', // Gris-bleu foncé
      target_country: '#38BDF8',  // Bleu clair lumineux (mais pas néon)
      country_borders: '#0F172A', // Frontières sombres
      silhouette: '#475569',      // Gris moyen
      capital_map: '#FBBF24',     // Jaune ambre (très lisible sur fond sombre)
      capital_silhouette: '#FBBF24',
      grid_lines: '#334155'       // Quadrillage discret
    },
    vintage_atlas: {
      water: '#D4E3D5',           // Bleu-vert d'eau rétro
      other_countries: '#F4E8D1', // Beige parchemin
      target_country: '#CD5C5C',  // Rouge brique sourd
      country_borders: '#8B7E6B', // Frontières vintage
      silhouette: '#A89F91',      // Gris chaud
      capital_map: '#1E293B',     // Encre bleu marine profond
      capital_silhouette: '#1E293B',
      grid_lines: '#E3D7C1'       // Lignes beiges
    },
    high_contrast: {
      water: '#FFFFFF',           // Blanc pur
      other_countries: '#E0E0E0', // Gris standard
      target_country: '#005AB5',  // Bleu "Safe" (très fort contraste)
      country_borders: '#000000', // Frontières noires nettes
      silhouette: '#757575',      // Gris foncé
      capital_map: '#DC3220',     // Rouge "Safe" (contraste parfait avec le bleu)
      capital_silhouette: '#DC3220',
      grid_lines: '#EEEEEE'
    },
    minimalist: {
      water: '#FAFAFA',           // Presque blanc
      other_countries: '#E5E5E5', // Gris neutre
      target_country: '#10B981',  // Vert émeraude moderne
      country_borders: '#FAFAFA', // Frontières très douces
      silhouette: '#A3A3A3',      // Gris moyen
      capital_map: '#F43F5E',     // Rose/Rouge (contraste parfait avec le vert émeraude)
      capital_silhouette: '#F43F5E',
      grid_lines: '#F0F0F0'
    }
  };
  
  // State
  let state = {
    colors: { ...PRESETS.anki },
    originalColors: {
      water: ["#FFFFFF", "#FFF", "#ffffff", "#fff"],
      other_countries: ["#CCCCCC", "#CCC", "#cccccc", "#ccc"],
      target_country: ["#59a353", "#59A353"],
      country_borders: ["#FFFFFF", "#FFF", "#ffffff", "#fff"],
      silhouette: ["#9CA3AF", "#9ca3af"],
      capital_map: ["#D95F5F", "#d95f5f"],
      capital_silhouette: ["#D95F5F", "#d95f5f"],
      grid_lines: ["#D8D8D8", "#d8d8d8"]
    },
    countries: [],
    selectedCountry: 'FXX',
    samples: [],
    activeTab: 'globe'
  };

  // DOM Elements for 8 color pickers
  const pickers = {
    water: { picker: document.getElementById('picker-water'), hex: document.getElementById('hex-water') },
    other_countries: { picker: document.getElementById('picker-other_countries'), hex: document.getElementById('hex-other_countries') },
    target_country: { picker: document.getElementById('picker-target_country'), hex: document.getElementById('hex-target_country') },
    country_borders: { picker: document.getElementById('picker-country_borders'), hex: document.getElementById('hex-country_borders') },
    silhouette: { picker: document.getElementById('picker-silhouette'), hex: document.getElementById('hex-silhouette') },
    capital_map: { picker: document.getElementById('picker-capital_map'), hex: document.getElementById('hex-capital_map') },
    capital_silhouette: { picker: document.getElementById('picker-capital_silhouette'), hex: document.getElementById('hex-capital_silhouette') },
    grid_lines: { picker: document.getElementById('picker-grid_lines'), hex: document.getElementById('hex-grid_lines') }
  };

  const countrySelect = document.getElementById('country-select');
  const randomCountryBtn = document.getElementById('random-country-btn');
  const sampleTabs = document.getElementById('sample-tabs');
  const loadingSpinner = document.getElementById('loading-spinner');
  const previewStage = document.getElementById('preview-stage');
  const svgCustomContainer = document.getElementById('svg-custom-container');
  const sampleName = document.getElementById('sample-name');
  const sampleDesc = document.getElementById('sample-desc');
  const downloadBtn = document.getElementById('download-btn');
  const genModal = document.getElementById('gen-modal');

  const REGION_LABELS = {
    'Africa': 'Afrique',
    'Americas': 'Amériques',
    'North America': 'Amérique du Nord',
    'South America': 'Amérique du Sud',
    'Asia': 'Asie',
    'Europe': 'Europe',
    'Oceania': 'Océanie',
    'Autre': 'Autre'
  };

  // Initialize
  async function init() {
    if (window.lucide) {
      lucide.createIcons();
    }
    setupColorPickers();
    setupPresets();
    setupTabs();
    setupActions();
    setupCountrySelector();
    await fetchDefaults();
    applyAnkiPreset();
    await fetchCountries();
    await fetchSamples(state.selectedCountry);
  }

  // Fetch defaults & original colors mapping from backend
  async function fetchDefaults() {
    try {
      const res = await fetch('/api/defaults');
      const data = await res.json();
      if (data.original_colors) {
        state.originalColors = data.original_colors;
      }
      if (data.palette) {
        PRESETS.anki = { ...data.palette };
      }
    } catch (err) {
      console.warn('Utilisation des couleurs par défaut en local.');
    }
  }

  // Apply default Classique Anki preset and update UI pickers
  function applyAnkiPreset() {
    state.colors = { ...PRESETS.anki };
    syncPickersUI();
    const presetBtns = document.querySelectorAll('.preset-btn');
    presetBtns.forEach(b => b.classList.toggle('active', b.dataset.preset === 'anki'));
  }

  // Bind color pickers for INSTANT live rendering on input & change
  function setupColorPickers() {
    Object.keys(pickers).forEach(key => {
      const item = pickers[key];
      if (!item || !item.picker) return;

      const { picker, hex } = item;

      const handleUpdate = (val) => {
        if (!val) return;
        val = val.trim().toUpperCase();
        if (!val.startsWith('#')) val = '#' + val;
        if (/^#[0-9A-FA-F]{3,6}$/.test(val)) {
          picker.value = val;
          hex.value = val;
          state.colors[key] = val;
          updatePreview(); // Instant real-time live preview update
        }
      };

      picker.addEventListener('input', (e) => handleUpdate(e.target.value));
      picker.addEventListener('change', (e) => handleUpdate(e.target.value));

      hex.addEventListener('input', (e) => handleUpdate(e.target.value));
      hex.addEventListener('change', (e) => handleUpdate(e.target.value));
    });
  }

  // Bind preset buttons and dynamically render swatches from PRESETS
  function setupPresets() {
    const presetBtns = document.querySelectorAll('.preset-btn');
    presetBtns.forEach(btn => {
      const presetKey = btn.dataset.preset;
      const preset = PRESETS[presetKey];
      if (preset) {
        const swatchesWrap = btn.querySelector('.preset-swatches');
        if (swatchesWrap) {
          swatchesWrap.innerHTML = `
            <span class="swatch" style="background: ${preset.target_country};"></span>
            <span class="swatch" style="background: ${preset.other_countries};"></span>
            <span class="swatch" style="background: ${preset.water};"></span>
          `;
        }
      }

      btn.addEventListener('click', () => {
        const pKey = btn.dataset.preset;
        if (PRESETS[pKey]) {
          presetBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');

          state.colors = { ...PRESETS[pKey] };
          syncPickersUI();
          updatePreview();
        }
      });
    });
  }

  // Update UI color pickers from state
  function syncPickersUI() {
    Object.keys(pickers).forEach(key => {
      const val = state.colors[key];
      if (val && pickers[key] && pickers[key].picker) {
        pickers[key].picker.value = val;
        pickers[key].hex.value = val;
      }
    });
  }

  // Country selector binding
  function setupCountrySelector() {
    countrySelect.addEventListener('change', async (e) => {
      const code = e.target.value;
      if (code) {
        state.selectedCountry = code;
        await fetchSamples(code);
      }
    });

    randomCountryBtn.addEventListener('click', async () => {
      if (state.countries.length > 0) {
        const randomItem = state.countries[Math.floor(Math.random() * state.countries.length)];
        countrySelect.value = randomItem.code;
        state.selectedCountry = randomItem.code;
        await fetchSamples(randomItem.code);
      }
    });
  }

  // Tab switching
  function setupTabs() {
    const tabBtns = sampleTabs.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.activeTab = btn.dataset.tab;
        updatePreview();
      });
    });
  }

  // Action buttons
  function setupActions() {
    downloadBtn.addEventListener('click', handleDownload);
  }

  // Fetch full country database from backend
  async function fetchCountries() {
    try {
      const res = await fetch('/api/countries');
      const data = await res.json();
      if (data.countries && data.countries.length > 0) {
        state.countries = data.countries;

        const grouped = {};
        data.countries.forEach(c => {
          const region = c.region || 'Autre';
          if (!grouped[region]) grouped[region] = [];
          grouped[region].push(c);
        });

        let html = '';
        Object.keys(grouped).sort().forEach(region => {
          const regionName = REGION_LABELS[region] || region;
          html += `<optgroup label="${regionName}">`;
          grouped[region].forEach(c => {
            const isSelected = c.code === state.selectedCountry ? 'selected' : '';
            html += `<option value="${c.code}" ${isSelected}>${c.name} (${c.code})</option>`;
          });
          html += `</optgroup>`;
        });

        countrySelect.innerHTML = html;
      }
    } catch (err) {
      console.error('Erreur lors du chargement des pays:', err);
    }
  }

  // Fetch sample maps for selected country
  async function fetchSamples(countryCode) {
    loadingSpinner.classList.remove('hidden');
    previewStage.classList.add('hidden');

    try {
      const url = countryCode ? `/api/samples?country=${encodeURIComponent(countryCode)}` : '/api/samples';
      const res = await fetch(url);
      const data = await res.json();
      if (data.samples && data.samples.length > 0) {
        state.samples = data.samples;
        loadingSpinner.classList.add('hidden');
        previewStage.classList.remove('hidden');
        updatePreview();
      }
    } catch (err) {
      console.error('Erreur de chargement des cartes d\'échantillon:', err);
      loadingSpinner.innerHTML = '<p style="color: #ef4444;">Erreur de connexion au serveur backend.</p>';
    }
  }

  // Format SVG for responsive scaling
  function formatResponsiveSvg(svgStr) {
    if (!svgStr.includes('viewBox')) {
      svgStr = svgStr.replace(/<svg\b([^>]*)>/i, '<svg $1 viewBox="0 0 800 800" preserveAspectRatio="xMidYMid meet">');
    }
    return svgStr;
  }

  // Real-time live SVG rendering matching Python apply_color_transform 100%
  function updatePreview() {
    if (!state.samples.length) return;

    const currentSample = state.samples.find(s => s.id === state.activeTab) || state.samples[0];
    sampleName.textContent = `${currentSample.filename} (${currentSample.country_name})`;
    sampleDesc.textContent = currentSample.description;

    const rawSvg = formatResponsiveSvg(currentSample.svg);

    // Generate Customized SVG
    let customSvg = rawSvg;

    const isSilhouetteTab = state.activeTab === 'silhouette' || state.activeTab === 'capitale';

    const water = state.colors.water || PRESETS.anki.water;
    const otherCountries = state.colors.other_countries || PRESETS.anki.other_countries;
    const targetCountry = state.colors.target_country || PRESETS.anki.target_country;
    const countryBorders = state.colors.country_borders || PRESETS.anki.country_borders;
    const silhouette = state.colors.silhouette || PRESETS.anki.silhouette;
    const capitalMap = state.colors.capital_map || PRESETS.anki.capital_map;
    const capitalSilhouette = state.colors.capital_silhouette || PRESETS.anki.capital_silhouette;

    const gridLines = state.colors.grid_lines || PRESETS.anki.grid_lines;

    // 1. Capital pin marker replacement (<path transform="translate..." ...>)
    const capVal = isSilhouetteTab ? capitalSilhouette : capitalMap;
    customSvg = customSvg.replace(/<path\b[^>]*transform=[\"\']translate[^>]*>/gi, (tag) => {
      tag = tag.replace(/stroke=[\"\'][^\"\']+[\"\']/gi, `stroke="${capVal}"`);
      tag = tag.replace(/fill=[\"\'](?!none)[^\"\']+[\"\']/gi, `fill="${capVal}"`);
      return tag;
    });

    // Helper regex escape function
    const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // 2. Water / Ocean background replacement
    const origWaterList = state.originalColors.water || ["#FFFFFF", "#FFF"];
    origWaterList.forEach(wCode => {
      const re = new RegExp(`fill=["']${escapeRegex(wCode)}["']`, 'gi');
      customSvg = customSvg.replace(re, `fill="${water}"`);
    });

    // 3. Silhouette vs Map Land & Target handling
    if (isSilhouetteTab) {
      // Silhouette country shape fill -> silhouette color
      const origSilList = state.originalColors.silhouette || ["#9CA3AF"];
      origSilList.forEach(sCode => {
        const re = new RegExp(`fill=["']${escapeRegex(sCode)}["']`, 'gi');
        customSvg = customSvg.replace(re, `fill="${silhouette}"`);
      });

      const origTargetList = state.originalColors.target_country || ["#59a353"];
      origTargetList.forEach(tCode => {
        const re = new RegExp(escapeRegex(tCode), 'gi');
        customSvg = customSvg.replace(re, silhouette);
      });
    } else {
      // Globe/Zoomed other countries -> other_countries color
      const origOtherList = state.originalColors.other_countries || ["#CCCCCC", "#CCC"];
      origOtherList.forEach(oCode => {
        const re = new RegExp(`fill=["']${escapeRegex(oCode)}["']`, 'gi');
        customSvg = customSvg.replace(re, `fill="${otherCountries}"`);
      });

      // Target country -> target_country color
      const origTargetList = state.originalColors.target_country || ["#59a353"];
      origTargetList.forEach(tCode => {
        const re = new RegExp(escapeRegex(tCode), 'gi');
        customSvg = customSvg.replace(re, targetCountry);
      });

      // Target country glow gradient stop-color update
      const origCapList = state.originalColors.capital_map || ["#D95F5F"];
      origCapList.forEach(gCode => {
        const re = new RegExp(`stop-color=["']${escapeRegex(gCode)}["']`, 'gi');
        customSvg = customSvg.replace(re, `stop-color="${targetCountry}"`);
      });

      // Grid lines stroke replacement (#D8D8D8 -> gridLines)
      const origGridList = state.originalColors.grid_lines || ["#D8D8D8", "#d8d8d8"];
      origGridList.forEach(gCode => {
        const re = new RegExp(`stroke=["']${escapeRegex(gCode)}["']`, 'gi');
        customSvg = customSvg.replace(re, `stroke="${gridLines}"`);
      });

      // Country borders stroke replacement (#FFFFFF -> countryBorders)
      const origBorderList = state.originalColors.country_borders || ["#FFFFFF", "#FFF"];
      origBorderList.forEach(bCode => {
        const re = new RegExp(`stroke=["']${escapeRegex(bCode)}["']`, 'gi');
        customSvg = customSvg.replace(re, `stroke="${countryBorders}"`);
      });
    }

    svgCustomContainer.innerHTML = customSvg;
  }

  // Handle .apkg download with real-time SSE progress bar
  async function handleDownload() {
    const progressBar = document.getElementById('progress-bar');
    const modalStatus = document.getElementById('modal-status');

    if (progressBar) progressBar.style.width = '0%';
    if (modalStatus) modalStatus.textContent = 'Initialisation de la génération...';

    genModal.classList.remove('hidden');

    try {
      const response = await fetch('/api/generate-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ colors: state.colors })
      });

      if (!response.ok) {
        throw new Error('Erreur lors de la génération du fichier APKG.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let jobId = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('data: ')) {
            try {
              const data = JSON.parse(trimmed.slice(6));
              if (data.type === 'progress') {
                if (progressBar) progressBar.style.width = `${data.percent}%`;
                if (modalStatus) modalStatus.textContent = `Traitement : ${data.percent}% (${data.current}/${data.total} cartes)`;
              } else if (data.type === 'complete') {
                jobId = data.job_id;
                if (progressBar) progressBar.style.width = '100%';
                if (modalStatus) modalStatus.textContent = 'Préparation du téléchargement...';
              } else if (data.type === 'error') {
                throw new Error(data.message);
              }
            } catch (e) {
              console.warn('JSON error in SSE:', e);
            }
          }
        }
      }

      if (jobId) {
        const downloadRes = await fetch(`/api/download/${jobId}`);
        if (!downloadRes.ok) throw new Error('Téléchargement échoué.');

        const blob = await downloadRes.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'GeoQuiz_Personnalise.apkg';
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
    } catch (err) {
      alert('Erreur lors de la génération : ' + err.message);
    } finally {
      setTimeout(() => {
        genModal.classList.add('hidden');
        if (progressBar) progressBar.style.width = '0%';
      }, 500);
    }
  }

  init();
});
