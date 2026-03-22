"""
Prompt Parser — pure keyword matching, no ML model.
Converts a free-text prompt into structured fields for the pipeline.
Supports genre blending and BPM override from the UI.
"""
import re

GENRE_KEYWORDS = {
    # Hip-Hop / Urban
    "lo-fi":       ["lofi", "lo-fi", "lo fi", "chillhop"],
    "hip-hop":     ["hip hop", "hiphop", "rap", "beats"],
    "boom-bap":    ["boom bap", "boom-bap", "boomba", "90s hip hop", "ny rap", "old school rap"],
    "trap":        ["trap", "808", "hi-hat", "mumble"],
    "drill":       ["drill", "uk drill", "chicago drill"],
    # Latin
    "reggaeton":   ["reggaeton", "reggeaton", "perreo", "urbano", "latin urban", "dembow"],
    "salsa":       ["salsa", "cuban", "clave", "timba"],
    "bachata":     ["bachata", "bachata romantica", "dominican romance"],
    "merengue":    ["merengue", "perico ripiao"],
    "cumbia":      ["cumbia", "colombian", "cumbiamba"],
    "latin pop":   ["latin pop", "latin", "spanish pop", "pop en espanol"],
    # Pop / Rock
    "pop":         ["pop", "catchy", "radio"],
    "rock":        ["rock", "guitar", "band"],
    "indie":       ["indie", "indie rock", "alternative rock", "lo-fi rock"],
    "punk":        ["punk", "hardcore", "emo"],
    "metal":       ["metal", "heavy", "thrash", "death metal"],
    "alternative": ["alternative", "alt rock", "grunge"],
    # Electronic
    "electronic":  ["electronic", "edm", "synth"],
    "house":       ["house", "deep house", "chicago house", "garage"],
    "techno":      ["techno", "industrial", "berlin techno", "rave"],
    "dubstep":     ["dubstep", "wobble", "brostep"],
    "drum & bass": ["drum and bass", "dnb", "jungle", "liquid dnb"],
    "synthwave":   ["synthwave", "retrowave", "80s synth", "vaporwave", "outrun"],
    "ambient":     ["ambient", "atmospheric", "drone", "meditation", "sleep"],
    # Soul / R&B
    "r&b":         ["r&b", "rnb", "neo soul"],
    "soul":        ["soul", "soulful", "motown"],
    "funk":        ["funk", "funky", "groove"],
    "blues":       ["blues", "delta blues", "chicago blues"],
    "gospel":      ["gospel", "church", "worship", "spiritual"],
    # World / Other
    "jazz":        ["jazz", "swing", "bebop"],
    "classical":   ["classical", "orchestral", "symphony", "piano"],
    "reggae":      ["reggae", "rasta", "jamaican"],
    "dancehall":   ["dancehall", "dance hall", "patois"],
    "afrobeats":   ["afrobeats", "afro", "afropop", "amapiano"],
    "bossa nova":  ["bossa nova", "bossanova", "brazilian jazz", "samba"],
    "folk":        ["folk", "acoustic folk", "singer songwriter", "bluegrass"],
    "country":     ["country", "nashville", "honky tonk", "outlaw country"],
    "k-pop":       ["k-pop", "kpop", "korean pop"],
    "disco":       ["disco", "70s dance", "funk disco"],
}

MOOD_KEYWORDS = {
    "chill":        ["chill", "relaxed", "calm", "mellow", "peaceful", "soft"],
    "happy":        ["happy", "joyful", "upbeat", "cheerful", "fun", "bright"],
    "sad":          ["sad", "melancholy", "heartbreak", "lonely", "blue"],
    "energetic":    ["energetic", "hype", "intense", "powerful", "driving"],
    "romantic":     ["romantic", "love", "tender", "warm", "sweet"],
    "dark":         ["dark", "moody", "mysterious", "haunting", "eerie"],
    "motivational": ["motivational", "inspiring", "epic", "uplifting", "triumphant"],
}

VOICE_KEYWORDS = {
    "male":   ["male", "man", "boy", "deep voice", "baritone"],
    "female": ["female", "woman", "girl", "soprano", "alto"],
}

DEFAULT_BPM = {
    "lo-fi": 85, "hip-hop": 90, "boom-bap": 90, "trap": 140, "drill": 140,
    "reggaeton": 95, "salsa": 180, "bachata": 120, "merengue": 155, "cumbia": 100, "latin pop": 110,
    "pop": 120, "rock": 130, "indie": 120, "punk": 165, "metal": 150, "alternative": 125,
    "electronic": 128, "house": 128, "techno": 138, "dubstep": 140, "drum & bass": 174,
    "synthwave": 110, "ambient": 70,
    "r&b": 95, "soul": 85, "funk": 110, "blues": 75, "gospel": 90,
    "jazz": 100, "classical": 80, "reggae": 75, "dancehall": 90, "afrobeats": 102,
    "bossa nova": 130, "folk": 90, "country": 100, "k-pop": 120, "disco": 120,
}

# Exported for the UI dropdown
GENRES = list(GENRE_KEYWORDS.keys())
MOODS  = list(MOOD_KEYWORDS.keys())


def parse(
    prompt: str,
    genre1: str = None,
    genre2: str = None,
    blend: float = 0,
    bpm_override: int = 0,
) -> dict:
    """
    Convert free-text prompt + UI overrides into a structured dict.

    genre1      — primary genre from UI dropdown ("auto" = detect from prompt)
    genre2      — secondary genre for blending ("None" = no blend)
    blend       — 0–100, percentage of genre2 in the blend
    bpm_override — 0 = auto-detect from prompt, >0 = use this value
    """
    text = prompt.lower()

    # Genre: use UI selection unless "auto"
    genre = genre1 if (genre1 and genre1 != "auto") else _match(text, GENRE_KEYWORDS, "pop")
    mood  = _match(text, MOOD_KEYWORDS, "chill")
    voice = _match(text, VOICE_KEYWORDS, "neutral")

    # BPM: UI slider overrides, else parse from prompt, else genre default
    if bpm_override and int(bpm_override) > 0:
        bpm = int(bpm_override)
    else:
        bpm_match = re.search(r"(\d{2,3})\s*(?:bpm|beats)", text)
        bpm = int(bpm_match.group(1)) if bpm_match else DEFAULT_BPM.get(genre, 100)

    # Build music prompt — include blend genre if specified
    use_blend = genre2 and genre2 not in ("None", "auto", "") and blend > 0
    if use_blend:
        pct1 = int(100 - blend)
        pct2 = int(blend)
        music_prompt = (
            f"{pct1}% {genre} {pct2}% {genre2} fusion, {mood} mood, "
            f"{prompt.strip()}, {bpm} bpm, high quality audio"
        )
    else:
        music_prompt = f"{genre} {mood} music, {prompt.strip()}, {bpm} bpm, high quality audio"

    return {
        "genre":        genre,
        "genre2":       genre2 if use_blend else "",
        "blend":        blend if use_blend else 0,
        "mood":         mood,
        "theme":        prompt.strip(),
        "bpm":          bpm,
        "voice":        voice,
        "music_prompt": music_prompt,
    }


def _match(text: str, keyword_map: dict, default: str) -> str:
    for label, keywords in keyword_map.items():
        if any(kw in text for kw in keywords):
            return label
    return default
