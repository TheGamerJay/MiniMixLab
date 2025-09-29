import numpy as np
import librosa as lr
from sklearn.cluster import SpectralClustering
from sklearn.preprocessing import StandardScaler

# === helpers ===

def _norm_rows(X, eps=1e-10):
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.maximum(n, eps)

def _checkerboard_kernel(size):
    # Foote-style Gaussian-tapered checkerboard
    n = np.arange(-size, size+1)
    g = np.exp(-0.5 * (n / (size/2))**2)
    K = np.outer(g, g)
    s = np.sign(np.add.outer(n, n))  # quadrant signs
    return K * s

def _novelty_from_ssm(SSM, sizes=(16, 32, 64)):
    N = SSM.shape[0]
    nov = np.zeros(N)
    for s in sizes:
        K = _checkerboard_kernel(s)
        # valid convolution along the diagonal neighborhood
        pad = s
        P = np.pad(SSM, ((pad,pad),(pad,pad)), mode='constant')
        score = np.array([
            np.sum(P[i:i+2*s+1, i:i+2*s+1] * K)
            for i in range(N)
        ])
        # relu + normalize each scale
        score = np.maximum(score, 0)
        if score.max() > 0:
            score /= score.max()
        nov += score
    # final normalize
    if nov.max() > 0:
        nov /= nov.max()
    return nov

def _peak_pick(nov, hop_s, min_gap_s=4.0, rel_thresh=0.25):
    # adaptive dynamic threshold
    med = lr.util.normalize(lr.decompose.nn_filter(nov[np.newaxis,:],
                                                   aggregate=np.median,
                                                   metric='cosine')[0])
    th = np.maximum(med, rel_thresh * nov.max())
    cand = (nov > th)
    # local maxima
    peaks = lr.util.peak_pick(nov, pre_max=3, post_max=3,
                              pre_avg=3, post_avg=3,
                              delta=0.0, wait=0)
    peaks = [p for p in peaks if cand[p]]
    # enforce minimum gap
    min_gap = int(np.round(min_gap_s / hop_s))
    pruned = []
    last = -10**9
    for p in peaks:
        if p - last >= min_gap:
            pruned.append(p)
            last = p
        elif nov[p] > nov[last]:
            pruned[-1] = p
            last = p
    return np.array(pruned, dtype=int)

def _letter_labels(k):
    # A,B,C,...,Z, AA, AB, ...
    letters = []
    i = 0
    while len(letters) < k:
        n = i
        s = ""
        while True:
            s = chr(ord('A') + (n % 26)) + s
            n = n // 26 - 1
            if n < 0: break
        letters.append(s)
        i += 1
    return letters

# === main API ===

def segment_and_label(
    y, sr,
    hop_len=512,
    min_seg_s=7.0,
    target_clusters=(3,6),  # search range for best #labels
    tempo=None
):
    # 1) features
    y = lr.to_mono(y)
    y = lr.effects.preemphasis(y)
    y_h, y_p = lr.effects.hpss(y)

    # harmony
    C = lr.feature.chroma_cens(y=y_h, sr=sr, hop_length=hop_len, win_len_smooth=41)
    # timbre
    MF = lr.feature.mfcc(y=y, sr=sr, hop_length=hop_len, n_mfcc=20)
    D1 = lr.feature.delta(MF); D2 = lr.feature.delta(MF, order=2)
    # rhythm
    oenv = lr.onset.onset_strength(y=y_p, sr=sr, hop_length=hop_len, aggregate=np.median)
    T = lr.feature.tempogram(onset_envelope=oenv, sr=sr, hop_length=hop_len)
    T = lr.util.sync(T, np.arange(T.shape[1]), aggregate=np.mean)  # keep as-is

    # stack + normalize per feature block
    F = np.vstack([
        _norm_rows(C.T),
        _norm_rows(MF.T),
        _norm_rows(D1.T),
        _norm_rows(D2.T),
        _norm_rows(T.T)
    ])  # (time, feat)
    F = StandardScaler(with_mean=True, with_std=True).fit_transform(F)

    # 2) self-similarity (cosine)
    Fn = _norm_rows(F)
    SSM = Fn @ Fn.T  # (T x T), in [0,1] approx

    # 3) novelty + boundaries
    nov = _novelty_from_ssm(SSM, sizes=(16, 32, 64))
    hop_s = hop_len / sr
    peaks = _peak_pick(nov, hop_s, min_gap_s=min_seg_s, rel_thresh=0.25)

    # add first/last frames as boundaries
    bounds = np.unique(np.concatenate([[0], peaks, [F.shape[0]-1]])).astype(int)

    # 4) build segments (start/end in seconds)
    segs_idx = np.vstack([bounds[:-1], bounds[1:]]).T
    segs = []
    for a, b in segs_idx:
        if b <= a: continue
        segs.append((a*hop_s, b*hop_s))
    if not segs:
        return []

    # Merge too-short segments into neighbor with higher similarity
    min_len = min_seg_s
    i = 0
    while i < len(segs):
        s, e = segs[i]
        if (e - s) < min_len and len(segs) > 1:
            # decide merge direction by SSM energy across boundary
            if i == 0:
                segs[i+1] = (s, segs[i+1][1]); segs.pop(i)
            elif i == len(segs)-1:
                segs[i-1] = (segs[i-1][0], e); segs.pop(i)
            else:
                a0, a1 = int(segs_idx[i][1]), int(segs_idx[i+1][0])
                left_energy = SSM[a0-1, a0-10:a0].mean() if a0 > 10 else 0
                right_energy = SSM[a1+1:a1+10, a1].mean() if a1+10 < SSM.shape[0] else 0
                if right_energy > left_energy:
                    segs[i+1] = (s, segs[i+1][1]); segs.pop(i)
                else:
                    segs[i-1] = (segs[i-1][0], e); segs.pop(i)
            continue
        i += 1

    # 5) label segments by clustering pooled embeddings
    # mean-pool the same F used for SSM
    embeds = []
    idx_pairs = []
    for (s, e) in segs:
        a, b = int(round(s / hop_s)), int(round(e / hop_s))
        idx_pairs.append((a,b))
        embeds.append(F[a:b].mean(axis=0))
    E = np.vstack(embeds)
    E = StandardScaler().fit_transform(E)

    best_k, best_aff = None, -1
    k_min, k_max = target_clusters
    # simple model selection: average intra-cluster affinity
    for k in range(k_min, min(k_max, len(segs))+1):
        cl = SpectralClustering(
            n_clusters=k, affinity='nearest_neighbors', n_neighbors=min(10, len(segs)-1),
            assign_labels='kmeans', random_state=0
        )
        labs = cl.fit_predict(E)
        # compute mean similarity within clusters (using cosine on E)
        En = _norm_rows(E)
        sim = En @ En.T
        score = np.mean([sim[i, labs==labs[i]].mean() for i in range(len(segs))])
        if score > best_aff:
            best_aff, best_k = score, k

    if best_k is None:
        best_k = min(3, len(segs))

    cl = SpectralClustering(
        n_clusters=best_k, affinity='nearest_neighbors', n_neighbors=min(10, len(segs)-1),
        assign_labels='kmeans', random_state=0
    )
    labs = cl.fit_predict(E)
    letters = _letter_labels(best_k)
    labels = [letters[i] for i in labs]

    # 6) pack results
    out = []
    for (s,e), lab in zip(segs, labels):
        out.append({"start": float(s), "end": float(e), "label": lab})

    # de-flicker: if pattern like A,B,A with tiny middle B, merge it into A
    cleaned = []
    for seg in out:
        if cleaned and seg["label"] == cleaned[-1]["label"]:
            cleaned[-1]["end"] = seg["end"]
        else:
            cleaned.append(seg)

    return cleaned

def map_letters_to_music_labels(segments, detected_tempo=120):
    """
    Map abstract A/B/C labels to musical section names based on patterns
    """
    if not segments:
        return segments

    # Count occurrences of each label
    label_counts = {}
    for seg in segments:
        label = seg["label"]
        label_counts[label] = label_counts.get(label, 0) + 1

    # Most repeated = Chorus candidate
    most_repeated = max(label_counts.items(), key=lambda x: x[1])[0] if label_counts else None

    # Map labels to musical meanings
    result = []
    used_labels = set()
    verse_counter = 1

    for i, seg in enumerate(segments):
        duration = seg["end"] - seg["start"]
        label = seg["label"]

        # Intro: first segment that's reasonably short
        if i == 0 and duration < 30:
            musical_label = "Intro"
        # Outro: last segment
        elif i == len(segments) - 1 and duration > 10:
            musical_label = "Outro"
        # Chorus: most repeated pattern
        elif label == most_repeated and label_counts[label] >= 2:
            musical_label = "Chorus"
        # Bridge: unique label (appears only once) in middle sections
        elif label_counts[label] == 1 and i not in [0, len(segments)-1]:
            musical_label = "Bridge"
        # Verse: everything else, numbered sequentially
        else:
            musical_label = f"Verse {verse_counter}"
            verse_counter += 1

        result.append({
            "start": seg["start"],
            "end": seg["end"],
            "label": musical_label,
            "confidence": 0.8,
            "original_label": label  # keep the clustering label for reference
        })

    return result