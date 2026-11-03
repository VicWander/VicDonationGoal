/* Admin appearance. Palette values are vendored from Tailwind's official theme.css;
   no network request or external library is needed in the browser. */
(function () {
  'use strict';
  const PALETTES = {"red":{"50":"oklch(97.1% 0.013 17.38)","100":"oklch(93.6% 0.032 17.717)","200":"oklch(88.5% 0.062 18.334)","300":"oklch(80.8% 0.114 19.571)","400":"oklch(70.4% 0.191 22.216)","500":"oklch(63.7% 0.237 25.331)","600":"oklch(57.7% 0.245 27.325)","700":"oklch(50.5% 0.213 27.518)","800":"oklch(44.4% 0.177 26.899)","900":"oklch(39.6% 0.141 25.723)","950":"oklch(25.8% 0.092 26.042)"},"orange":{"50":"oklch(98% 0.016 73.684)","100":"oklch(95.4% 0.038 75.164)","200":"oklch(90.1% 0.076 70.697)","300":"oklch(83.7% 0.128 66.29)","400":"oklch(75% 0.183 55.934)","500":"oklch(70.5% 0.213 47.604)","600":"oklch(64.6% 0.222 41.116)","700":"oklch(55.3% 0.195 38.402)","800":"oklch(47% 0.157 37.304)","900":"oklch(40.8% 0.123 38.172)","950":"oklch(26.6% 0.079 36.259)"},"amber":{"50":"oklch(98.7% 0.022 95.277)","100":"oklch(96.2% 0.059 95.617)","200":"oklch(92.4% 0.12 95.746)","300":"oklch(87.9% 0.169 91.605)","400":"oklch(82.8% 0.189 84.429)","500":"oklch(76.9% 0.188 70.08)","600":"oklch(66.6% 0.179 58.318)","700":"oklch(55.5% 0.163 48.998)","800":"oklch(47.3% 0.137 46.201)","900":"oklch(41.4% 0.112 45.904)","950":"oklch(27.9% 0.077 45.635)"},"yellow":{"50":"oklch(98.7% 0.026 102.212)","100":"oklch(97.3% 0.071 103.193)","200":"oklch(94.5% 0.129 101.54)","300":"oklch(90.5% 0.182 98.111)","400":"oklch(85.2% 0.199 91.936)","500":"oklch(79.5% 0.184 86.047)","600":"oklch(68.1% 0.162 75.834)","700":"oklch(55.4% 0.135 66.442)","800":"oklch(47.6% 0.114 61.907)","900":"oklch(42.1% 0.095 57.708)","950":"oklch(28.6% 0.066 53.813)"},"lime":{"50":"oklch(98.6% 0.031 120.757)","100":"oklch(96.7% 0.067 122.328)","200":"oklch(93.8% 0.127 124.321)","300":"oklch(89.7% 0.196 126.665)","400":"oklch(84.1% 0.238 128.85)","500":"oklch(76.8% 0.233 130.85)","600":"oklch(64.8% 0.2 131.684)","700":"oklch(53.2% 0.157 131.589)","800":"oklch(45.3% 0.124 130.933)","900":"oklch(40.5% 0.101 131.063)","950":"oklch(27.4% 0.072 132.109)"},"green":{"50":"oklch(98.2% 0.018 155.826)","100":"oklch(96.2% 0.044 156.743)","200":"oklch(92.5% 0.084 155.995)","300":"oklch(87.1% 0.15 154.449)","400":"oklch(79.2% 0.209 151.711)","500":"oklch(72.3% 0.219 149.579)","600":"oklch(62.7% 0.194 149.214)","700":"oklch(52.7% 0.154 150.069)","800":"oklch(44.8% 0.119 151.328)","900":"oklch(39.3% 0.095 152.535)","950":"oklch(26.6% 0.065 152.934)"},"emerald":{"50":"oklch(97.9% 0.021 166.113)","100":"oklch(95% 0.052 163.051)","200":"oklch(90.5% 0.093 164.15)","300":"oklch(84.5% 0.143 164.978)","400":"oklch(76.5% 0.177 163.223)","500":"oklch(69.6% 0.17 162.48)","600":"oklch(59.6% 0.145 163.225)","700":"oklch(50.8% 0.118 165.612)","800":"oklch(43.2% 0.095 166.913)","900":"oklch(37.8% 0.077 168.94)","950":"oklch(26.2% 0.051 172.552)"},"teal":{"50":"oklch(98.4% 0.014 180.72)","100":"oklch(95.3% 0.051 180.801)","200":"oklch(91% 0.096 180.426)","300":"oklch(85.5% 0.138 181.071)","400":"oklch(77.7% 0.152 181.912)","500":"oklch(70.4% 0.14 182.503)","600":"oklch(60% 0.118 184.704)","700":"oklch(51.1% 0.096 186.391)","800":"oklch(43.7% 0.078 188.216)","900":"oklch(38.6% 0.063 188.416)","950":"oklch(27.7% 0.046 192.524)"},"cyan":{"50":"oklch(98.4% 0.019 200.873)","100":"oklch(95.6% 0.045 203.388)","200":"oklch(91.7% 0.08 205.041)","300":"oklch(86.5% 0.127 207.078)","400":"oklch(78.9% 0.154 211.53)","500":"oklch(71.5% 0.143 215.221)","600":"oklch(60.9% 0.126 221.723)","700":"oklch(52% 0.105 223.128)","800":"oklch(45% 0.085 224.283)","900":"oklch(39.8% 0.07 227.392)","950":"oklch(30.2% 0.056 229.695)"},"sky":{"50":"oklch(97.7% 0.013 236.62)","100":"oklch(95.1% 0.026 236.824)","200":"oklch(90.1% 0.058 230.902)","300":"oklch(82.8% 0.111 230.318)","400":"oklch(74.6% 0.16 232.661)","500":"oklch(68.5% 0.169 237.323)","600":"oklch(58.8% 0.158 241.966)","700":"oklch(50% 0.134 242.749)","800":"oklch(44.3% 0.11 240.79)","900":"oklch(39.1% 0.09 240.876)","950":"oklch(29.3% 0.066 243.157)"},"blue":{"50":"oklch(97% 0.014 254.604)","100":"oklch(93.2% 0.032 255.585)","200":"oklch(88.2% 0.059 254.128)","300":"oklch(80.9% 0.105 251.813)","400":"oklch(70.7% 0.165 254.624)","500":"oklch(62.3% 0.214 259.815)","600":"oklch(54.6% 0.245 262.881)","700":"oklch(48.8% 0.243 264.376)","800":"oklch(42.4% 0.199 265.638)","900":"oklch(37.9% 0.146 265.522)","950":"oklch(28.2% 0.091 267.935)"},"indigo":{"50":"oklch(96.2% 0.018 272.314)","100":"oklch(93% 0.034 272.788)","200":"oklch(87% 0.065 274.039)","300":"oklch(78.5% 0.115 274.713)","400":"oklch(67.3% 0.182 276.935)","500":"oklch(58.5% 0.233 277.117)","600":"oklch(51.1% 0.262 276.966)","700":"oklch(45.7% 0.24 277.023)","800":"oklch(39.8% 0.195 277.366)","900":"oklch(35.9% 0.144 278.697)","950":"oklch(25.7% 0.09 281.288)"},"violet":{"50":"oklch(96.9% 0.016 293.756)","100":"oklch(94.3% 0.029 294.588)","200":"oklch(89.4% 0.057 293.283)","300":"oklch(81.1% 0.111 293.571)","400":"oklch(70.2% 0.183 293.541)","500":"oklch(60.6% 0.25 292.717)","600":"oklch(54.1% 0.281 293.009)","700":"oklch(49.1% 0.27 292.581)","800":"oklch(43.2% 0.232 292.759)","900":"oklch(38% 0.189 293.745)","950":"oklch(28.3% 0.141 291.089)"},"purple":{"50":"oklch(97.7% 0.014 308.299)","100":"oklch(94.6% 0.033 307.174)","200":"oklch(90.2% 0.063 306.703)","300":"oklch(82.7% 0.119 306.383)","400":"oklch(71.4% 0.203 305.504)","500":"oklch(62.7% 0.265 303.9)","600":"oklch(55.8% 0.288 302.321)","700":"oklch(49.6% 0.265 301.924)","800":"oklch(43.8% 0.218 303.724)","900":"oklch(38.1% 0.176 304.987)","950":"oklch(29.1% 0.149 302.717)"},"fuchsia":{"50":"oklch(97.7% 0.017 320.058)","100":"oklch(95.2% 0.037 318.852)","200":"oklch(90.3% 0.076 319.62)","300":"oklch(83.3% 0.145 321.434)","400":"oklch(74% 0.238 322.16)","500":"oklch(66.7% 0.295 322.15)","600":"oklch(59.1% 0.293 322.896)","700":"oklch(51.8% 0.253 323.949)","800":"oklch(45.2% 0.211 324.591)","900":"oklch(40.1% 0.17 325.612)","950":"oklch(29.3% 0.136 325.661)"},"pink":{"50":"oklch(97.1% 0.014 343.198)","100":"oklch(94.8% 0.028 342.258)","200":"oklch(89.9% 0.061 343.231)","300":"oklch(82.3% 0.12 346.018)","400":"oklch(71.8% 0.202 349.761)","500":"oklch(65.6% 0.241 354.308)","600":"oklch(59.2% 0.249 0.584)","700":"oklch(52.5% 0.223 3.958)","800":"oklch(45.9% 0.187 3.815)","900":"oklch(40.8% 0.153 2.432)","950":"oklch(28.4% 0.109 3.907)"},"rose":{"50":"oklch(96.9% 0.015 12.422)","100":"oklch(94.1% 0.03 12.58)","200":"oklch(89.2% 0.058 10.001)","300":"oklch(81% 0.117 11.638)","400":"oklch(71.2% 0.194 13.428)","500":"oklch(64.5% 0.246 16.439)","600":"oklch(58.6% 0.253 17.585)","700":"oklch(51.4% 0.222 16.935)","800":"oklch(45.5% 0.188 13.697)","900":"oklch(41% 0.159 10.272)","950":"oklch(27.1% 0.105 12.094)"},"slate":{"50":"oklch(98.4% 0.003 247.858)","100":"oklch(96.8% 0.007 247.896)","200":"oklch(92.9% 0.013 255.508)","300":"oklch(86.9% 0.022 252.894)","400":"oklch(70.4% 0.04 256.788)","500":"oklch(55.4% 0.046 257.417)","600":"oklch(44.6% 0.043 257.281)","700":"oklch(37.2% 0.044 257.287)","800":"oklch(27.9% 0.041 260.031)","900":"oklch(20.8% 0.042 265.755)","950":"oklch(12.9% 0.042 264.695)"},"gray":{"50":"oklch(98.5% 0.002 247.839)","100":"oklch(96.7% 0.003 264.542)","200":"oklch(92.8% 0.006 264.531)","300":"oklch(87.2% 0.01 258.338)","400":"oklch(70.7% 0.022 261.325)","500":"oklch(55.1% 0.027 264.364)","600":"oklch(44.6% 0.03 256.802)","700":"oklch(37.3% 0.034 259.733)","800":"oklch(27.8% 0.033 256.848)","900":"oklch(21% 0.034 264.665)","950":"oklch(13% 0.028 261.692)"},"zinc":{"50":"oklch(98.5% 0 none)","100":"oklch(96.7% 0.001 286.375)","200":"oklch(92% 0.004 286.32)","300":"oklch(87.1% 0.006 286.286)","400":"oklch(70.5% 0.015 286.067)","500":"oklch(55.2% 0.016 285.938)","600":"oklch(44.2% 0.017 285.786)","700":"oklch(37% 0.013 285.805)","800":"oklch(27.4% 0.006 286.033)","900":"oklch(21% 0.006 285.885)","950":"oklch(14.1% 0.005 285.823)"},"neutral":{"50":"oklch(98.5% 0 none)","100":"oklch(97% 0 none)","200":"oklch(92.2% 0 none)","300":"oklch(87% 0 none)","400":"oklch(70.8% 0 none)","500":"oklch(55.6% 0 none)","600":"oklch(43.9% 0 none)","700":"oklch(37.1% 0 none)","800":"oklch(26.9% 0 none)","900":"oklch(20.5% 0 none)","950":"oklch(14.5% 0 none)"},"stone":{"50":"oklch(98.5% 0.001 106.423)","100":"oklch(97% 0.001 106.424)","200":"oklch(92.3% 0.003 48.717)","300":"oklch(86.9% 0.005 56.366)","400":"oklch(70.9% 0.01 56.259)","500":"oklch(55.3% 0.013 58.071)","600":"oklch(44.4% 0.011 73.639)","700":"oklch(37.4% 0.01 67.558)","800":"oklch(26.8% 0.007 34.298)","900":"oklch(21.6% 0.006 56.043)","950":"oklch(14.7% 0.004 49.25)"},"mauve":{"50":"oklch(98.5% 0 none)","100":"oklch(96% 0.003 325.6)","200":"oklch(92.2% 0.005 325.62)","300":"oklch(86.5% 0.012 325.68)","400":"oklch(71.1% 0.019 323.02)","500":"oklch(54.2% 0.034 322.5)","600":"oklch(43.5% 0.029 321.78)","700":"oklch(36.4% 0.029 323.89)","800":"oklch(26.3% 0.024 320.12)","900":"oklch(21.2% 0.019 322.12)","950":"oklch(14.5% 0.008 326)"},"olive":{"50":"oklch(98.8% 0.003 106.5)","100":"oklch(96.6% 0.005 106.5)","200":"oklch(93% 0.007 106.5)","300":"oklch(88% 0.011 106.6)","400":"oklch(73.7% 0.021 106.9)","500":"oklch(58% 0.031 107.3)","600":"oklch(46.6% 0.025 107.3)","700":"oklch(39.4% 0.023 107.4)","800":"oklch(28.6% 0.016 107.4)","900":"oklch(22.8% 0.013 107.4)","950":"oklch(15.3% 0.006 107.1)"},"mist":{"50":"oklch(98.7% 0.002 197.1)","100":"oklch(96.3% 0.002 197.1)","200":"oklch(92.5% 0.005 214.3)","300":"oklch(87.2% 0.007 219.6)","400":"oklch(72.3% 0.014 214.4)","500":"oklch(56% 0.021 213.5)","600":"oklch(45% 0.017 213.2)","700":"oklch(37.8% 0.015 216)","800":"oklch(27.5% 0.011 216.9)","900":"oklch(21.8% 0.008 223.9)","950":"oklch(14.8% 0.004 228.8)"},"taupe":{"50":"oklch(98.6% 0.002 67.8)","100":"oklch(96% 0.002 17.2)","200":"oklch(92.2% 0.005 34.3)","300":"oklch(86.8% 0.007 39.5)","400":"oklch(71.4% 0.014 41.2)","500":"oklch(54.7% 0.021 43.1)","600":"oklch(43.8% 0.017 39.3)","700":"oklch(36.7% 0.016 35.7)","800":"oklch(26.8% 0.011 36.5)","900":"oklch(21.4% 0.009 43.1)","950":"oklch(14.7% 0.004 49.3)"}};
  const BASES = ['neutral', 'stone', 'zinc', 'slate', 'gray', ...Object.keys(PALETTES).filter(name=>!['neutral','stone','zinc','slate','gray'].includes(name))];
  const DEFAULT = { mode: 'dark', family: 'monocrome', base: 'neutral', accent: 'neutral', baseSaturation: 35 };
  const LEGACY_KEY = 'donationGoalAdminTheme';
  let current = { ...DEFAULT }, persisted = { ...DEFAULT }, busy = false, loading = true, notice = '', failed = false;
  const forms = [];
  const copy = value => ({ ...value });
  const same = (a, b) => Object.keys(DEFAULT).every(key => a[key] === b[key]);
  function normalize(value) {
    value = value && typeof value === 'object' ? value : {};
    return {
      mode: ['dark', 'light'].includes(value.mode) ? value.mode : DEFAULT.mode,
      family: ['monocrome', 'palette', 'vicwander'].includes(value.family) ? value.family : DEFAULT.family,
      base: BASES.includes(value.base) ? value.base : DEFAULT.base,
      accent: Object.hasOwn(PALETTES, value.accent) ? value.accent : DEFAULT.accent,
      baseSaturation: typeof value.baseSaturation==='number'&&Number.isFinite(value.baseSaturation)?Math.max(0,Math.min(100,value.baseSaturation)):DEFAULT.baseSaturation
    };
  }
  function localRead() { try { return localStorage.getItem(LEGACY_KEY); } catch (_) { return null; } }
  function localWrite(mode) { try { localStorage.setItem(LEGACY_KEY, mode); } catch (_) { /* Storage may be disabled. */ } }
  function setTokens(theme) {
    const dark = theme.mode === 'dark', mono = theme.family === 'monocrome', vic = theme.family === 'vicwander';
    let base = PALETTES[mono ? 'neutral' : vic ? 'slate' : theme.base];
    if(!mono&&!vic){
      const sample=base[500].match(/oklch\([^ ]+ ([^ ]+) ([^)]+)\)/),chroma=Number(sample[1]),hue=sample[2]==='none'?'0':sample[2];
      const amount=theme.baseSaturation/100;
      base=Object.fromEntries(Object.entries(PALETTES.neutral).map(([step,color])=>{
        const lightness=color.match(/oklch\(([^ ]+)/)[1];
        const cap=Number(step)<=50?.02:Number(step)<=100?.04:.075;
        return [step,`oklch(${lightness} ${Math.min(chroma,cap)*amount} ${hue})`];
      }));
    }
    const accent = PALETTES[vic ? 'cyan' : theme.accent];
    const tokens = dark ? {
      bg: mono ? '#0a0a0a' : base[950], 'bg-soft': mono ? '#111111' : base[950],
      card: mono ? '#171717' : base[900], 'card-2': mono ? '#111111' : base[950], 'card-3': base[800],
      text: '#f5f5f5', 'text-strong': '#ffffff', strong: '#ffffff', muted: '#c2c2c2', 'muted-2': '#a3a3a3',
      border: base[800], 'border-strong': base[600], 'input-bg': base[950], 'input-text': '#f5f5f5'
    } : {
      bg: base[100], 'bg-soft': base[50], card: mono ? '#ffffff' : `color-mix(in oklch, ${base[50]} 75%, white)`, 'card-2': base[50], 'card-3': base[200],
      text: '#262626', 'text-strong': '#171717', strong: '#171717', muted: '#525252', 'muted-2': '#525252',
      border: base[300], 'border-strong': base[400], 'input-bg': mono ? '#ffffff' : base[50], 'input-text': '#171717'
    };
    if (vic) Object.assign(tokens, dark ? {
      bg: '#0b0f17', 'bg-soft': '#0f1624', card: '#111827', 'card-2': '#0b1020', 'card-3': '#151f31',
      'input-bg': '#0b1020'
    } : {
      bg: '#edf3f8', 'bg-soft': '#e6eef6', card: '#ffffff', 'card-2': '#f7fbff', 'card-3': '#eef6fb',
      'input-bg': '#f8fbff'
    });
    Object.assign(tokens, {
      accent: mono ? (dark ? '#e5e5e5' : '#262626') : accent[dark ? 300 : 700],
      'accent-2': mono ? (dark ? '#ffffff' : '#171717') : accent[dark ? 400 : 800],
      'accent-dark': mono ? '#525252' : accent[800],
      'primary-bg': mono ? (dark ? '#ffffff' : '#171717') : accent[800],
      'primary-hover': mono ? (dark ? '#e5e5e5' : '#404040') : accent[700],
      'primary-text': mono && dark ? '#171717' : '#ffffff',
      'progress-bg': base[dark ? 800 : 200], 'table-head': base[dark ? 900 : 100],
      'table-row': dark ? base[950] : '#ffffff', 'table-row-alt': base[dark ? 900 : 50],
      'table-hover': base[dark ? 800 : 100], shadow: 'none', 'shadow-soft': 'none',
      'surface-1': tokens.card, 'surface-2': tokens['card-2'], 'surface-3': tokens['card-3']
    });
    // VicWander keeps the original admin palette and depth in both modes.
    // Apply these last so the configurable palette cannot flatten its gradients.
    if (vic) Object.assign(tokens, {
      text: dark ? '#e5e7eb' : '#172033', 'text-strong': dark ? '#f9fafb' : '#0b1220',
      strong: dark ? '#f9fafb' : '#0b1220', muted: dark ? '#8b95a7' : '#526174',
      'muted-2': dark ? '#64748b' : '#7a8797',
      border: dark ? 'rgba(255,255,255,.08)' : 'rgba(15,23,42,.10)',
      'border-strong': dark ? 'rgba(255,255,255,.14)' : 'rgba(15,23,42,.17)',
      'input-text': dark ? '#f9fafb' : '#0b1220',
      accent: '#35a9d4', 'accent-2': '#3bc7da', 'accent-dark': '#23489e',
      'primary-bg': 'linear-gradient(135deg,#23489e,#35a9d4,#3bc7da)',
      'primary-hover': 'linear-gradient(135deg,#23489e,#35a9d4,#3bc7da)',
      'primary-text': '#ffffff',
      'progress-bg': dark ? 'color-mix(in srgb,#8b95a7 24%,transparent)' : '#d7e3ed',
      'table-head': dark ? '#151f31' : '#e8f1f8',
      'table-row': dark ? '#0b1020' : '#ffffff', 'table-row-alt': dark ? '#111827' : '#f7fbff',
      'table-hover': dark ? 'color-mix(in srgb,#3bc7da 7%,#0b1020)' : '#edf8fc',
      shadow: dark ? '0 18px 44px rgba(0,0,0,.24)' : '0 18px 44px rgba(35,72,158,.10)',
      'shadow-soft': dark ? '0 10px 26px rgba(0,0,0,.18)' : '0 10px 28px rgba(35,72,158,.08)'
    });
    for (const [key, value] of Object.entries(tokens)) document.body.style.setProperty('--' + key, value);
    document.body.style.colorScheme = theme.mode;
  }
  function sync() {
    const dirty = !same(current, persisted);
    const entry = document.querySelector('.studio-theme-open');
    if (entry) {
      entry.textContent = failed ? 'Оформление · ошибка' : dirty ? 'Оформление · предпросмотр' : 'Оформление';
      entry.title = notice || (dirty ? 'Тема ещё не сохранена' : 'Настроить оформление');
    }
    for (const form of forms) {
      for (const key of Object.keys(DEFAULT)) {
        form.elements[key].value = current[key];
        form.elements[key].disabled = loading;
      }
      form.elements.base.disabled = loading || current.family !== 'palette';
      form.elements.accent.disabled = loading || current.family !== 'palette';
      form.elements.baseSaturation.disabled = loading || current.family !== 'palette';
      form.querySelector('[data-theme-save]').disabled = loading || busy || !dirty;
      form.querySelector('[data-theme-reset]').disabled = loading || busy || !dirty;
      const status = form.querySelector('[data-theme-status]');
      status.textContent = notice || (loading ? 'Загружаю тему…' : dirty ? 'Предпросмотр — изменения ещё не сохранены.' : 'Тема сохранена.');
      status.dataset.error = String(failed);
      form.setAttribute('aria-busy', String(busy || loading));
    }
  }
  function apply(value) {
    current = normalize(value);
    document.body.dataset.theme = current.mode;
    document.body.dataset.themeFamily = current.family;
    document.body.dataset.themeBase = current.base;
    document.body.dataset.themeAccent = current.accent;
    setTokens(current);
    sync();
    window.dispatchEvent(new CustomEvent('vdg:themechange', { detail: copy(current) }));
    return copy(current);
  }
  async function request(options) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch('/api/ui/settings', { ...options, signal: controller.signal });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const result = await response.json();
      if (result.ok !== true) throw new Error('Invalid settings response');
      return result;
    } finally { clearTimeout(timeout); }
  }
  // Serialize writes so a late response can never overwrite a newer save.
  let saveQueue = Promise.resolve();
  function save(patch) {
    const candidate = normalize({ ...current, ...patch });
    const operation = async () => {
      busy = true; failed = false; notice = 'Сохраняю тему…'; sync();
      try {
        const result = await request({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ theme: candidate }) });
        persisted = normalize(result.settings && result.settings.theme || candidate);
        notice = ''; localWrite(persisted.mode);
        if (same(current, candidate)) apply(persisted);
        return copy(persisted);
      } catch (error) {
        failed = true; notice = 'Не удалось сохранить тему. Предпросмотр остаётся несохранённым. Повтори сохранение.';
        throw error;
      } finally { busy = false; sync(); }
    };
    const pending = saveQueue.then(operation, operation);
    saveQueue = pending.catch(() => {});
    return pending;
  }
  function option(value, label) { const el = document.createElement('option'); el.value = value; el.textContent = label; return el; }
  function buildForm(host) {
    const form = document.createElement('form'); form.className = 'studio-theme-form';
    const controls = [
      ['mode', 'Режим', [['dark', 'Тёмный'], ['light', 'Светлый']]],
      ['family', 'Тема', [['monocrome', 'Monocrome'], ['palette', 'Monocrome — палитры'], ['vicwander', 'VicWander']]],
      ['base', 'Основа', BASES.map(name => [name, 'Monocrome — ' + name[0].toUpperCase() + name.slice(1)])],
      ['accent', 'Акцент', Object.keys(PALETTES).map(name => [name, name[0].toUpperCase() + name.slice(1)])]
    ];
    const grid = document.createElement('div'); grid.className = 'studio-theme-controls';
    for (const [key, title, values] of controls) {
      const label = document.createElement('label'); label.textContent = title;
      const select = document.createElement('select'); select.name = key;
      for (const [value, text] of values) select.appendChild(option(value, text));
      label.appendChild(select); grid.appendChild(label);
      select.addEventListener('change', () => {
        failed = false; notice = '';
        apply({ ...current, [key]: select.value });
      });
    }
    const saturationLabel=document.createElement('label');saturationLabel.className='studio-base-saturation';saturationLabel.textContent='Насыщенность основы';
    const saturation=document.createElement('input');saturation.type='range';saturation.name='baseSaturation';saturation.min='0';saturation.max='100';saturation.step='1';
    saturation.addEventListener('input',()=>{failed=false;notice='';apply({...current,baseSaturation:Number(saturation.value)});});
    saturationLabel.append(saturation);grid.append(saturationLabel);
    const help = document.createElement('p'); help.className = 'hint';
    help.textContent = 'Monocrome — чёрно-белая тема с белыми кнопками в тёмном режиме. В палитрах можно выбрать основу и любой акцент Tailwind. Тема меняет только панель управления.';
    const actions = document.createElement('div'); actions.className = 'studio-theme-actions';
    const submit = document.createElement('button'); submit.type = 'submit'; submit.textContent = 'Сохранить тему'; submit.dataset.themeSave = '';
    const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'secondary'; reset.textContent = 'Отменить изменения'; reset.dataset.themeReset = '';
    reset.addEventListener('click', () => { notice = ''; failed = false; apply(persisted); });
    const status = document.createElement('p'); status.className = 'studio-theme-status'; status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); status.dataset.themeStatus = '';
    actions.append(submit, reset); form.append(grid, help, actions, status);
    form.addEventListener('submit', event => { event.preventDefault(); if (!busy) save(current).catch(() => {}); });
    host.appendChild(form); forms.push(form); sync();
  }
  function buildUI() {
    const panel = document.getElementById('studioAppearanceSettings');
    if (panel) buildForm(panel);
    const slot = document.getElementById('sidebarThemeSlot');
    if (!slot) return;
    const dialog = document.createElement('dialog'); dialog.className = 'studio-theme-dialog'; dialog.setAttribute('aria-labelledby', 'studioThemeDialogTitle');
    const heading = document.createElement('h2'); heading.id = 'studioThemeDialogTitle'; heading.textContent = 'Оформление';
    const close = document.createElement('button'); close.type = 'button'; close.className = 'secondary studio-theme-close'; close.textContent = 'Закрыть'; close.addEventListener('click', () => dialog.close());
    dialog.appendChild(heading); buildForm(dialog); dialog.appendChild(close); document.body.appendChild(dialog);
    const open = document.createElement('button'); open.type = 'button'; open.className = 'secondary studio-theme-open'; open.textContent = 'Оформление'; open.setAttribute('aria-haspopup', 'dialog');
    open.addEventListener('click', () => dialog.showModal()); slot.replaceChildren(open);
  }
  let resolveReady;
  const ready = new Promise(resolve => { resolveReady = resolve; });
  window.VDGThemes = { ready, apply, get: () => copy(current), save };
  async function init() {
    apply(DEFAULT); buildUI();
    try {
      const result = await request();
      const serverTheme = result.settings && result.settings.theme;
      persisted = normalize(serverTheme);
      const absent = result.configured === false || result.hasCustomSettings === false || !serverTheme;
      const legacy = absent && !document.body.hasAttribute('data-theme-no-migrate') && localRead();
      if (legacy === 'dark' || legacy === 'light') {
        apply({ ...DEFAULT, mode: legacy });
        await save(current).catch(() => {});
      } else { notice = ''; apply(persisted); }
    } catch (_) {
      failed = true; notice = 'Не удалось загрузить сохранённую тему. Показан локальный предпросмотр. Перезагрузи страницу, чтобы повторить загрузку.'; sync();
    } finally { loading = false; sync(); resolveReady(copy(current)); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();

