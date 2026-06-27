const COUNTRY_ALIASES: Record<string, string> = {
  usa: 'US', us: 'US', 'u.s.a.': 'US', 'u.s.': 'US', 'united states': 'US', 'états-unis': 'US', 'etats-unis': 'US',
  america: 'US', 'new york': 'US', nyc: 'US', jfk: 'US', 'los angeles': 'US', lax: 'US', miami: 'US', greenwood: 'US',
  bronx: 'US', chicago: 'US', houston: 'US', dallas: 'US', atlanta: 'US', boston: 'US', seattle: 'US', 'san francisco': 'US',
  france: 'FR', fr: 'FR', paris: 'FR', lyon: 'FR', marseille: 'FR', cdg: 'FR',
  'united kingdom': 'GB', uk: 'GB', gb: 'GB', england: 'GB', london: 'GB', lhr: 'GB',
  germany: 'DE', de: 'DE', allemagne: 'DE', berlin: 'DE', frankfurt: 'DE',
  spain: 'ES', es: 'ES', espagne: 'ES', madrid: 'ES', barcelona: 'ES',
  italy: 'IT', it: 'IT', italie: 'IT', rome: 'IT', milan: 'IT',
  morocco: 'MA', ma: 'MA', maroc: 'MA', casablanca: 'MA', cmn: 'MA', rabat: 'MA',
  uae: 'AE', ae: 'AE', 'united arab emirates': 'AE', dubai: 'AE', 'abu dhabi': 'AE', émirats: 'AE',
  china: 'CN', cn: 'CN', chine: 'CN', shanghai: 'CN', beijing: 'CN',
  japan: 'JP', jp: 'JP', japon: 'JP', tokyo: 'JP', osaka: 'JP',
  brazil: 'BR', br: 'BR', brésil: 'BR', brasil: 'BR', 'são paulo': 'BR', 'sao paulo': 'BR',
  canada: 'CA', ca: 'CA',
  mexico: 'MX', mx: 'MX', mexique: 'MX',
  india: 'IN', in: 'IN', inde: 'IN', mumbai: 'IN', delhi: 'IN',
  australia: 'AU', au: 'AU', australie: 'AU', sydney: 'AU', melbourne: 'AU',
  singapore: 'SG', sg: 'SG', singapour: 'SG',
  netherlands: 'NL', nl: 'NL', holland: 'NL', 'pays-bas': 'NL', amsterdam: 'NL',
  belgium: 'BE', be: 'BE', belgique: 'BE', brussels: 'BE', bruxelles: 'BE',
  switzerland: 'CH', ch: 'CH', suisse: 'CH', zurich: 'CH', geneva: 'CH', genève: 'CH',
  portugal: 'PT', pt: 'PT', lisbon: 'PT', lisbonne: 'PT',
  poland: 'PL', pl: 'PL', pologne: 'PL', warsaw: 'PL',
  sweden: 'SE', se: 'SE', suède: 'SE', stockholm: 'SE',
  norway: 'NO', no: 'NO', norvège: 'NO', oslo: 'NO',
  denmark: 'DK', dk: 'DK', danemark: 'DK', copenhagen: 'DK',
  finland: 'FI', fi: 'FI', finlande: 'FI', helsinki: 'FI',
  ireland: 'IE', ie: 'IE', irlande: 'IE', dublin: 'IE',
  russia: 'RU', ru: 'RU', russie: 'RU', moscow: 'RU', moscou: 'RU',
  'south korea': 'KR', kr: 'KR', 'corée du sud': 'KR', seoul: 'KR',
  'south africa': 'ZA', za: 'ZA', 'afrique du sud': 'ZA', johannesburg: 'ZA',
  turkey: 'TR', tr: 'TR', turquie: 'TR', istanbul: 'TR',
  egypt: 'EG', eg: 'EG', égypte: 'EG', egypte: 'EG', cairo: 'EG',
  'saudi arabia': 'SA', sa: 'SA', 'arabie saoudite': 'SA', riyadh: 'SA',
  qatar: 'QA', qa: 'QA', doha: 'QA',
  kuwait: 'KW', kw: 'KW',
  bahrain: 'BH', bh: 'BH',
  oman: 'OM', om: 'OM',
  israel: 'IL', il: 'IL', israël: 'IL', 'tel aviv': 'IL',
  lebanon: 'LB', lb: 'LB', liban: 'LB', beirut: 'LB',
  jordan: 'JO', jo: 'JO', jordanie: 'JO', amman: 'JO',
  tunisia: 'TN', tn: 'TN', tunisie: 'TN', tunis: 'TN',
  algeria: 'DZ', dz: 'DZ', algérie: 'DZ', algerie: 'DZ', algiers: 'DZ',
  senegal: 'SN', sn: 'SN', sénégal: 'SN', dakar: 'SN',
  nigeria: 'NG', ng: 'NG', lagos: 'NG',
  kenya: 'KE', ke: 'KE', nairobi: 'KE',
  ghana: 'GH', gh: 'GH', accra: 'GH',
  argentina: 'AR', ar: 'AR', argentine: 'AR', 'buenos aires': 'AR',
  chile: 'CL', cl: 'CL', chili: 'CL', santiago: 'CL',
  colombia: 'CO', co: 'CO', colombie: 'CO', bogota: 'CO',
  peru: 'PE', pe: 'PE', pérou: 'PE', lima: 'PE',
  venezuela: 'VE', ve: 'VE',
  vietnam: 'VN', vn: 'VN', 'viêt nam': 'VN', hanoi: 'VN', 'ho chi minh': 'VN',
  thailand: 'TH', th: 'TH', thaïlande: 'TH', bangkok: 'TH',
  malaysia: 'MY', my: 'MY', malaisie: 'MY', 'kuala lumpur': 'MY',
  indonesia: 'ID', id: 'ID', indonésie: 'ID', jakarta: 'ID',
  philippines: 'PH', ph: 'PH', manila: 'PH',
  'new zealand': 'NZ', nz: 'NZ', 'nouvelle-zélande': 'NZ', auckland: 'NZ',
  pakistan: 'PK', pk: 'PK', karachi: 'PK',
  ukraine: 'UA', ua: 'UA', kyiv: 'UA', kiev: 'UA',
  greece: 'GR', gr: 'GR', grèce: 'GR', athens: 'GR',
  austria: 'AT', at: 'AT', autriche: 'AT', vienna: 'AT',
  'czech republic': 'CZ', czechia: 'CZ', cz: 'CZ', tchéquie: 'CZ', prague: 'CZ',
  hungary: 'HU', hu: 'HU', hongrie: 'HU', budapest: 'HU',
  romania: 'RO', ro: 'RO', roumanie: 'RO', bucharest: 'RO',
  luxembourg: 'LU', lu: 'LU',
  monaco: 'MC', mc: 'MC',
};

function normalize(text: string): string {
  return text.trim().toLowerCase().replace(/\s+/g, ' ');
}

function isoFlag(code: string): string {
  const c = code.trim().toUpperCase();
  if (c.length !== 2 || !/^[A-Z]{2}$/.test(c)) return '🌍';
  return String.fromCodePoint(...[...c].map((ch) => 127397 + ch.charCodeAt(0)));
}

function emojiToIso(emoji: string): string | null {
  const chars = [...emoji];
  if (chars.length !== 2) return null;
  const a = chars[0].codePointAt(0)!;
  const b = chars[1].codePointAt(0)!;
  if (a < 0x1f1e6 || a > 0x1f1ff || b < 0x1f1e6 || b > 0x1f1ff) return null;
  return String.fromCharCode(a - 0x1f1e6 + 65, b - 0x1f1e6 + 65);
}

function resolveIsoCode(text: string | null | undefined): string | null {
  if (!text?.trim()) return null;
  const raw = text.trim();
  const norm = normalize(raw);

  if (raw.includes(',')) {
    const suffix = normalize(raw.split(',').pop() ?? '');
    if (COUNTRY_ALIASES[suffix]) return COUNTRY_ALIASES[suffix];
    if (/^[a-z]{2}$/i.test(suffix)) return suffix.toUpperCase();
  }

  const tokens = norm.match(/[a-zà-ÿ]{2,}/gi) ?? [];
  for (let i = tokens.length - 1; i >= 0; i--) {
    const token = tokens[i].toLowerCase();
    if (COUNTRY_ALIASES[token]) return COUNTRY_ALIASES[token];
    if (/^[a-z]{2}$/i.test(token)) return token.toUpperCase();
  }

  const aliases = Object.keys(COUNTRY_ALIASES).sort((a, b) => b.length - a.length);
  for (const alias of aliases) {
    if (norm.includes(alias)) return COUNTRY_ALIASES[alias];
  }

  return null;
}

export function isoCodeForLocation(text: string | null | undefined): string | null {
  return resolveIsoCode(text);
}

export function isoCodeForShipment(flag: string | null | undefined, location: string): string | null {
  if (flag?.trim()) {
    const f = flag.trim();
    if (/^[A-Za-z]{2}$/.test(f)) return f.toUpperCase();
    const fromEmoji = emojiToIso(f);
    if (fromEmoji) return fromEmoji;
    if (f !== '🌍') {
      const fromFlagText = resolveIsoCode(f);
      if (fromFlagText) return fromFlagText;
    }
  }
  return resolveIsoCode(location);
}

export function flagImageUrl(flag: string | null | undefined, location: string, width = 20): string | null {
  const code = isoCodeForShipment(flag, location);
  if (!code) return null;
  return `https://flagcdn.com/w${width}/${code.toLowerCase()}.png`;
}

export function flagForLocation(text: string | null | undefined): string {
  const code = resolveIsoCode(text);
  return code ? isoFlag(code) : '🌍';
}

export function resolveShipmentFlag(flag: string | null | undefined, location: string): string {
  const code = isoCodeForShipment(flag, location);
  return code ? isoFlag(code) : '🌍';
}
