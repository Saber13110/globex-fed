"""Resolve location strings to country flag emojis."""

from __future__ import annotations

import re

# ISO 3166-1 alpha-2 → common names / aliases (lowercase keys)
_COUNTRY_ALIASES: dict[str, str] = {
    "af": "AF", "afghanistan": "AF",
    "al": "AL", "albania": "AL", "albanie": "AL",
    "dz": "DZ", "algeria": "DZ", "algérie": "DZ", "algerie": "DZ",
    "ad": "AD", "andorra": "AD", "andorre": "AD",
    "ao": "AO", "angola": "AO",
    "ag": "AG", "antigua": "AG",
    "ar": "AR", "argentina": "AR", "argentine": "AR",
    "am": "AM", "armenia": "AM", "arménie": "AM",
    "au": "AU", "australia": "AU", "australie": "AU",
    "at": "AT", "austria": "AT", "autriche": "AT",
    "az": "AZ", "azerbaijan": "AZ",
    "bs": "BS", "bahamas": "BS",
    "bh": "BH", "bahrain": "BH", "bahreïn": "BH",
    "bd": "BD", "bangladesh": "BD",
    "bb": "BB", "barbados": "BB",
    "by": "BY", "belarus": "BY", "biélorussie": "BY",
    "be": "BE", "belgium": "BE", "belgique": "BE",
    "bz": "BZ", "belize": "BZ",
    "bj": "BJ", "benin": "BJ", "bénin": "BJ",
    "bt": "BT", "bhutan": "BT",
    "bo": "BO", "bolivia": "BO", "bolivie": "BO",
    "ba": "BA", "bosnia": "BA", "bosnie": "BA",
    "bw": "BW", "botswana": "BW",
    "br": "BR", "brazil": "BR", "brésil": "BR", "brasil": "BR", "são paulo": "BR", "sao paulo": "BR",
    "bn": "BN", "brunei": "BN",
    "bg": "BG", "bulgaria": "BG", "bulgarie": "BG",
    "bf": "BF", "burkina faso": "BF",
    "bi": "BI", "burundi": "BI",
    "kh": "KH", "cambodia": "KH", "cambodge": "KH",
    "cm": "CM", "cameroon": "CM", "cameroun": "CM",
    "ca": "CA", "canada": "CA",
    "cv": "CV", "cape verde": "CV", "cap-vert": "CV",
    "cf": "CF", "central african republic": "CF",
    "td": "TD", "chad": "TD", "tchad": "TD",
    "cl": "CL", "chile": "CL", "chili": "CL",
    "cn": "CN", "china": "CN", "chine": "CN", "shanghai": "CN", "beijing": "CN",
    "co": "CO", "colombia": "CO", "colombie": "CO",
    "km": "KM", "comoros": "KM", "comores": "KM",
    "cg": "CG", "congo": "CG",
    "cd": "CD", "drc": "CD", "democratic republic of the congo": "CD",
    "cr": "CR", "costa rica": "CR",
    "ci": "CI", "ivory coast": "CI", "côte d'ivoire": "CI", "cote d'ivoire": "CI",
    "hr": "HR", "croatia": "HR", "croatie": "HR",
    "cu": "CU", "cuba": "CU",
    "cy": "CY", "cyprus": "CY", "chypre": "CY",
    "cz": "CZ", "czech": "CZ", "czechia": "CZ", "tchéquie": "CZ",
    "dk": "DK", "denmark": "DK", "danemark": "DK",
    "dj": "DJ", "djibouti": "DJ",
    "dm": "DM", "dominica": "DM",
    "do": "DO", "dominican republic": "DO",
    "ec": "EC", "ecuador": "EC", "équateur": "EC",
    "eg": "EG", "egypt": "EG", "égypte": "EG", "egypte": "EG",
    "sv": "SV", "el salvador": "SV",
    "gq": "GQ", "equatorial guinea": "GQ",
    "er": "ER", "eritrea": "ER", "érythrée": "ER",
    "ee": "EE", "estonia": "EE", "estonie": "EE",
    "sz": "SZ", "eswatini": "SZ",
    "et": "ET", "ethiopia": "ET", "éthiopie": "ET",
    "fj": "FJ", "fiji": "FJ", "fidji": "FJ",
    "fi": "FI", "finland": "FI", "finlande": "FI",
    "fr": "FR", "france": "FR", "paris": "FR", "lyon": "FR", "marseille": "FR", "cdg": "FR",
    "ga": "GA", "gabon": "GA",
    "gm": "GM", "gambia": "GM", "gambie": "GM",
    "ge": "GE", "georgia": "GE", "géorgie": "GE",
    "de": "DE", "germany": "DE", "allemagne": "DE", "berlin": "DE", "frankfurt": "DE",
    "gh": "GH", "ghana": "GH",
    "gr": "GR", "greece": "GR", "grèce": "GR", "athens": "GR",
    "gd": "GD", "grenada": "GD",
    "gt": "GT", "guatemala": "GT",
    "gn": "GN", "guinea": "GN", "guinée": "GN",
    "gw": "GW", "guinea-bissau": "GW",
    "gy": "GY", "guyana": "GY",
    "ht": "HT", "haiti": "HT", "haïti": "HT",
    "hn": "HN", "honduras": "HN",
    "hu": "HU", "hungary": "HU", "hongrie": "HU",
    "is": "IS", "iceland": "IS", "islande": "IS",
    "in": "IN", "india": "IN", "inde": "IN", "mumbai": "IN", "delhi": "IN",
    "id": "ID", "indonesia": "ID", "indonésie": "ID", "jakarta": "ID",
    "ir": "IR", "iran": "IR",
    "iq": "IQ", "iraq": "IQ", "irak": "IQ",
    "ie": "IE", "ireland": "IE", "irlande": "IE", "dublin": "IE",
    "il": "IL", "israel": "IL", "israël": "IL",
    "it": "IT", "italy": "IT", "italie": "IT", "rome": "IT", "milan": "IT",
    "jm": "JM", "jamaica": "JM", "jamaïque": "JM",
    "jp": "JP", "japan": "JP", "japon": "JP", "tokyo": "JP", "osaka": "JP",
    "jo": "JO", "jordan": "JO", "jordanie": "JO",
    "kz": "KZ", "kazakhstan": "KZ",
    "ke": "KE", "kenya": "KE",
    "ki": "KI", "kiribati": "KI",
    "kw": "KW", "kuwait": "KW", "koweït": "KW",
    "kg": "KG", "kyrgyzstan": "KG",
    "la": "LA", "laos": "LA",
    "lv": "LV", "latvia": "LV", "lettonie": "LV",
    "lb": "LB", "lebanon": "LB", "liban": "LB",
    "ls": "LS", "lesotho": "LS",
    "lr": "LR", "liberia": "LR", "libéria": "LR",
    "ly": "LY", "libya": "LY", "libye": "LY",
    "li": "LI", "liechtenstein": "LI",
    "lt": "LT", "lithuania": "LT", "lituanie": "LT",
    "lu": "LU", "luxembourg": "LU",
    "mg": "MG", "madagascar": "MG",
    "mw": "MW", "malawi": "MW",
    "my": "MY", "malaysia": "MY", "malaisie": "MY", "kuala lumpur": "MY",
    "mv": "MV", "maldives": "MV",
    "ml": "ML", "mali": "ML",
    "mt": "MT", "malta": "MT", "malte": "MT",
    "mh": "MH", "marshall islands": "MH",
    "mr": "MR", "mauritania": "MR", "mauritanie": "MR",
    "mu": "MU", "mauritius": "MU", "maurice": "MU",
    "mx": "MX", "mexico": "MX", "mexique": "MX",
    "fm": "FM", "micronesia": "FM",
    "md": "MD", "moldova": "MD", "moldavie": "MD",
    "mc": "MC", "monaco": "MC",
    "mn": "MN", "mongolia": "MN", "mongolie": "MN",
    "me": "ME", "montenegro": "ME",
    "ma": "MA", "morocco": "MA", "maroc": "MA", "casablanca": "MA", "rabat": "MA", "cmn": "MA",
    "mz": "MZ", "mozambique": "MZ",
    "mm": "MM", "myanmar": "MM", "burma": "MM",
    "na": "NA", "namibia": "NA", "namibie": "NA",
    "nr": "NR", "nauru": "NR",
    "np": "NP", "nepal": "NP", "népal": "NP",
    "nl": "NL", "netherlands": "NL", "holland": "NL", "pays-bas": "NL", "amsterdam": "NL",
    "nz": "NZ", "new zealand": "NZ", "nouvelle-zélande": "NZ",
    "ni": "NI", "nicaragua": "NI",
    "ne": "NE", "niger": "NE",
    "ng": "NG", "nigeria": "NG",
    "kp": "KP", "north korea": "KP",
    "mk": "MK", "north macedonia": "MK",
    "no": "NO", "norway": "NO", "norvège": "NO", "oslo": "NO",
    "om": "OM", "oman": "OM",
    "pk": "PK", "pakistan": "PK",
    "pw": "PW", "palau": "PW",
    "pa": "PA", "panama": "PA",
    "pg": "PG", "papua new guinea": "PG",
    "py": "PY", "paraguay": "PY",
    "pe": "PE", "peru": "PE", "pérou": "PE",
    "ph": "PH", "philippines": "PH",
    "pl": "PL", "poland": "PL", "pologne": "PL", "warsaw": "PL",
    "pt": "PT", "portugal": "PT", "lisbon": "PT", "lisbonne": "PT",
    "qa": "QA", "qatar": "QA",
    "ro": "RO", "romania": "RO", "roumanie": "RO",
    "ru": "RU", "russia": "RU", "russie": "RU", "moscow": "RU", "moscou": "RU",
    "rw": "RW", "rwanda": "RW",
    "kn": "KN", "saint kitts": "KN",
    "lc": "LC", "saint lucia": "LC",
    "vc": "VC", "saint vincent": "VC",
    "ws": "WS", "samoa": "WS",
    "sm": "SM", "san marino": "SM",
    "st": "ST", "sao tome": "ST",
    "sa": "SA", "saudi arabia": "SA", "arabie saoudite": "SA", "riyadh": "SA",
    "sn": "SN", "senegal": "SN", "sénégal": "SN", "dakar": "SN",
    "rs": "RS", "serbia": "RS", "serbie": "RS",
    "sc": "SC", "seychelles": "SC",
    "sl": "SL", "sierra leone": "SL",
    "sg": "SG", "singapore": "SG", "singapour": "SG",
    "sk": "SK", "slovakia": "SK", "slovaquie": "SK",
    "si": "SI", "slovenia": "SI", "slovénie": "SI",
    "sb": "SB", "solomon islands": "SB",
    "so": "SO", "somalia": "SO", "somalie": "SO",
    "za": "ZA", "south africa": "ZA", "afrique du sud": "ZA", "johannesburg": "ZA",
    "kr": "KR", "south korea": "KR", "corée du sud": "KR", "seoul": "KR",
    "ss": "SS", "south sudan": "SS",
    "es": "ES", "spain": "ES", "espagne": "ES", "madrid": "ES", "barcelona": "ES",
    "lk": "LK", "sri lanka": "LK",
    "sd": "SD", "sudan": "SD", "soudan": "SD",
    "sr": "SR", "suriname": "SR",
    "se": "SE", "sweden": "SE", "suède": "SE", "stockholm": "SE",
    "ch": "CH", "switzerland": "CH", "suisse": "CH", "zurich": "CH", "geneva": "CH", "genève": "CH",
    "sy": "SY", "syria": "SY", "syrie": "SY",
    "tw": "TW", "taiwan": "TW", "taïwan": "TW",
    "tj": "TJ", "tajikistan": "TJ",
    "tz": "TZ", "tanzania": "TZ", "tanzanie": "TZ",
    "th": "TH", "thailand": "TH", "thaïlande": "TH", "bangkok": "TH",
    "tl": "TL", "timor-leste": "TL",
    "tg": "TG", "togo": "TG",
    "to": "TO", "tonga": "TO",
    "tt": "TT", "trinidad": "TT",
    "tn": "TN", "tunisia": "TN", "tunisie": "TN", "tunis": "TN",
    "tr": "TR", "turkey": "TR", "turquie": "TR", "istanbul": "TR",
    "tm": "TM", "turkmenistan": "TM",
    "tv": "TV", "tuvalu": "TV",
    "ug": "UG", "uganda": "UG", "ouganda": "UG",
    "ua": "UA", "ukraine": "UA", "kyiv": "UA", "kiev": "UA",
    "ae": "AE", "uae": "AE", "united arab emirates": "AE", "dubai": "AE", "abu dhabi": "AE", "émirats": "AE",
    "gb": "GB", "uk": "GB", "united kingdom": "GB", "royaume-uni": "GB", "england": "GB", "london": "GB", "lhr": "GB", "manchester": "GB",
    "us": "US", "usa": "US", "u.s.a.": "US", "u.s.": "US", "united states": "US", "états-unis": "US", "etats-unis": "US",
    "america": "US", "new york": "US", "nyc": "US", "jfk": "US", "los angeles": "US", "lax": "US", "chicago": "US",
    "miami": "US", "greenwood": "US", "houston": "US", "dallas": "US", "atlanta": "US", "boston": "US", "seattle": "US",
    "san francisco": "US", "washington": "US", "philadelphia": "US",
    "uy": "UY", "uruguay": "UY",
    "uz": "UZ", "uzbekistan": "UZ",
    "vu": "VU", "vanuatu": "VU",
    "va": "VA", "vatican": "VA",
    "ve": "VE", "venezuela": "VE",
    "vn": "VN", "vietnam": "VN", "viêt nam": "VN", "hanoi": "VN", "ho chi minh": "VN",
    "ye": "YE", "yemen": "YE", "yémen": "YE",
    "zm": "ZM", "zambia": "ZM", "zambie": "ZM",
    "zw": "ZW", "zimbabwe": "ZW",
}

_ISO3_TO_ISO2: dict[str, str] = {
    "usa": "US", "gbr": "GB", "fra": "FR", "deu": "DE", "esp": "ES", "ita": "IT", "mar": "MA",
    "are": "AE", "chn": "CN", "jpn": "JP", "bra": "BR", "ind": "IN", "can": "CA", "mex": "MX",
    "sau": "SA", "tur": "TR", "egy": "EG", "zaf": "ZA", "aus": "AU", "nld": "NL", "bel": "BE",
    "che": "CH", "aut": "AT", "prt": "PT", "pol": "PL", "swe": "SE", "nor": "NO", "dnk": "DK",
    "fin": "FI", "irl": "IE", "sgp": "SG", "hkg": "HK", "kor": "KR", "arg": "AR", "chl": "CL",
    "col": "CO", "per": "PE", "ven": "VE", "nzl": "NZ", "pak": "PK", "phl": "PH", "tha": "TH",
    "vnm": "VN", "mys": "MY", "idn": "ID", "rus": "RU", "ukr": "UA", "rou": "RO", "cze": "CZ",
    "hun": "HU", "grc": "GR", "isr": "IL", "qat": "QA", "kwt": "KW", "bhr": "BH", "omn": "OM",
    "lbn": "LB", "jor": "JO", "irq": "IQ", "irn": "IR", "ken": "KE", "nga": "NG", "gha": "GH",
    "sen": "SN", "tun": "TN", "dza": "DZ", "lby": "LY", "eth": "ET", "tza": "TZ", "uga": "UG",
}


def iso_flag(code: str) -> str:
    c = (code or "").strip().upper()
    if len(c) != 2 or not c.isalpha():
        return "🌍"
    return "".join(chr(127397 + ord(ch)) for ch in c)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def flag_for_location(text: str | None) -> str:
    if not text or not str(text).strip():
        return "🌍"

    raw = str(text).strip()
    norm = _normalize(raw)

    # Trailing ISO2 / ISO3 / alias after comma: "Miami, USA"
    if "," in raw:
        suffix = _normalize(raw.rsplit(",", 1)[-1])
        if suffix in _COUNTRY_ALIASES:
            return iso_flag(_COUNTRY_ALIASES[suffix])
        if len(suffix) == 2 and suffix.isalpha():
            return iso_flag(suffix)
        if suffix in _ISO3_TO_ISO2:
            return iso_flag(_ISO3_TO_ISO2[suffix])

    # Airport / port codes embedded
    tokens = re.findall(r"[a-zA-ZÀ-ÿ]{2,}", norm)
    for token in reversed(tokens):
        if token in _COUNTRY_ALIASES:
            return iso_flag(_COUNTRY_ALIASES[token])
        if len(token) == 2 and token.isalpha():
            return iso_flag(token)
        if token in _ISO3_TO_ISO2:
            return iso_flag(_ISO3_TO_ISO2[token])

    # Longest alias substring match
    for alias in sorted(_COUNTRY_ALIASES, key=len, reverse=True):
        if alias in norm:
            return iso_flag(_COUNTRY_ALIASES[alias])

    return "🌍"
