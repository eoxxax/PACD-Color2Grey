import streamlit as st
import struct
import zlib
import base64

#  PNG DECODER - pure Python
def read_png(file_bytes: bytes):
    """
    Decode file PNG 8-bit RGB/RGBA menjadi list 2D pixels[row][col] = (R, G, B).
    """
    if file_bytes[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError("Bukan file PNG yang valid.")

    pos = 8
    ihdr = None
    idat_chunks = []

    while pos < len(file_bytes):
        length = struct.unpack('>I', file_bytes[pos:pos+4])[0]
        chunk_type = file_bytes[pos+4:pos+8]
        data = file_bytes[pos+8:pos+8+length]
        pos += 12 + length

        if chunk_type == b'IHDR':
            width, height = struct.unpack('>II', data[:8])
            bit_depth  = data[8]
            color_type = data[9]
            ihdr = (width, height, bit_depth, color_type)
        elif chunk_type == b'IDAT':
            idat_chunks.append(data)
        elif chunk_type == b'IEND':
            break

    if ihdr is None:
        raise ValueError("Chunk IHDR tidak ditemukan.")

    width, height, bit_depth, color_type = ihdr

    if bit_depth != 8:
        raise ValueError(f"Hanya mendukung PNG 8-bit (file ini {bit_depth}-bit).")
    if color_type not in (2, 6):
        raise ValueError("Hanya mendukung PNG dengan mode RGB atau RGBA.")

    channels = 3 if color_type == 2 else 4
    raw      = zlib.decompress(b''.join(idat_chunks))
    stride   = width * channels

    pixels   = []
    idx      = 0
    prev_row = [0] * stride

    for _ in range(height):
        filter_byte = raw[idx]; idx += 1
        row_raw     = list(raw[idx:idx+stride]); idx += stride

        if filter_byte == 0:        # None
            row = row_raw

        elif filter_byte == 1:      # Sub
            row = list(row_raw)
            for i in range(channels, stride):
                row[i] = (row[i] + row[i - channels]) & 0xFF

        elif filter_byte == 2:      # Up
            row = [(row_raw[i] + prev_row[i]) & 0xFF for i in range(stride)]

        elif filter_byte == 3:      # Average
            row = list(row_raw)
            for i in range(stride):
                a = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + (a + prev_row[i]) // 2) & 0xFF

        elif filter_byte == 4:      # Paeth
            row = list(row_raw)
            for i in range(stride):
                a  = row[i - channels]      if i >= channels else 0
                b  = prev_row[i]
                c  = prev_row[i - channels] if i >= channels else 0
                p  = a + b - c
                pa = abs(p - a); pb = abs(p - b); pc = abs(p - c)
                pr = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF

        else:
            raise ValueError(f"Tipe filter PNG tidak dikenal: {filter_byte}")

        pixels.append([
            (row[x*channels], row[x*channels+1], row[x*channels+2])
            for x in range(width)
        ])
        prev_row = row

    return pixels, width, height


#  PNG ENCODER (pure Python)
def write_png_gray(gray2d, width, height) -> bytes:
    """
    Encode list 2D integer (0-255) sebagai file PNG grayscale 8-bit
    """
    def make_chunk(chunk_type, data):
        body = chunk_type + data
        crc  = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + body + struct.pack('>I', crc)

    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    ihdr = make_chunk(b'IHDR', ihdr_data)

    # Filter byte 0 (None) untuk setiap baris
    raw_rows = b''.join(bytes([0] + list(row)) for row in gray2d)
    idat = make_chunk(b'IDAT', zlib.compress(raw_rows, 9))
    iend = make_chunk(b'IEND', b'')

    return b'\x89PNG\r\n\x1a\n' + ihdr + idat + iend


#  5 ALGORITMA KONVERSI (pure Python)
def algo_averaging(pixels, w, h):
    """1. Averaging: g(i,j) = (R + G + B) / 3"""
    return [[(r + g + b) // 3 for r, g, b in row] for row in pixels]


def algo_weighting(pixels, w, h, pr, pg, pb):
    """2. Weighting: g(i,j) = pr*R + pg*G + pb*B"""
    return [[max(0, min(255, int(pr*r + pg*g + pb*b))) for r, g, b in row] for row in pixels]


def algo_desaturation(pixels, w, h):
    """3. Desaturation: Gray = (Max(R,G,B) + Min(R,G,B)) / 2"""
    return [[(max(r, g, b) + min(r, g, b)) // 2 for r, g, b in row] for row in pixels]


def algo_decomp_max(pixels, w, h):
    """4a. Decomposition Max: Gray = Max(R,G,B)"""
    return [[max(r, g, b) for r, g, b in row] for row in pixels]


def algo_decomp_min(pixels, w, h):
    """4b. Decomposition Min: Gray = Min(R,G,B)"""
    return [[min(r, g, b) for r, g, b in row] for row in pixels]


def algo_channel(pixels, w, h, ch):
    """5. Single Color Channel: Gray = R / G / B"""
    idx = {'R': 0, 'G': 1, 'B': 2}[ch]
    return [[px[idx] for px in row] for row in pixels]


#  STREAMLIT UI
st.set_page_config(page_title="RGB to Grayscale Converter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Sora:wght@300;400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Sora', sans-serif; }

.title-box {
    background: linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);
    border: 1px solid #e94560; border-radius: 12px;
    padding: 28px 36px; margin-bottom: 28px;
}
.title-box h1 {
    color: #e94560; font-family: 'Space Mono', monospace;
    font-size: 1.8rem; margin: 0 0 6px; letter-spacing: -1px;
}
.title-box p { color: #a0a8c0; margin: 0; font-size: 0.88rem; line-height: 1.6; }

.algo-card {
    background: #1a1a2e; border: 1px solid #2a2a4e;
    border-left: 4px solid #e94560; border-radius: 10px;
    padding: 12px 16px; margin-bottom: 10px;
}
.algo-title {
    color: #e94560; font-family: 'Space Mono', monospace;
    font-size: 0.75rem; font-weight: 700; margin-bottom: 4px;
}
.algo-formula {
    color: #f5a623; font-family: 'Space Mono', monospace;
    font-size: 0.7rem; background: #0f0f1a;
    padding: 5px 8px; border-radius: 4px;
}

.result-card {
    background: #1a1a2e; border: 1px solid #2a2a4e;
    border-radius: 10px; padding: 10px; text-align: center;
}
.result-card img { width: 100%; border-radius: 6px; display: block; }
.result-label {
    font-family: 'Space Mono', monospace; font-size: 0.68rem;
    color: #e94560; font-weight: 700; margin: 8px 0 10px; line-height: 1.4;
}

.stDownloadButton { width: 100%; }
.stDownloadButton > button {
    background: #e94560 !important; color: white !important;
    border: none !important; font-family: 'Space Mono', monospace !important;
    font-size: 0.7rem !important; border-radius: 6px !important;
    width: 100% !important; padding: 6px 0 !important;
}
.stDownloadButton > button:hover { background: #c73652 !important; }

section[data-testid="stFileUploadDropzone"] {
    background: #1a1a2e !important;
    border: 2px dashed #e94560 !important;
    border-radius: 10px !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="title-box">
    <h1>RGB to Grayscale Converter</h1>
    <p>Konversi citra warna ke greylevel menggunakan <strong>5 algoritma</strong> berbeda.<br>
    Implementasi 100% pure Python — tidak menggunakan library image processing eksternal.</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Algoritma")
    for title, formula in [
        ("1. Averaging",               "g(i,j) = (R + G + B) / 3"),
        ("2a. Weighting - Human Eye",  "0.3R + 0.59G + 0.11B"),
        ("2b. Weighting - Luma BT.709","0.2126R + 0.7152G + 0.0722B"),
        ("2c. Weighting - BT.601",     "0.299R + 0.587G + 0.114B"),
        ("3. Desaturation",            "(Max(R,G,B) + Min(R,G,B)) / 2"),
        ("4a. Decomposition Max",      "Gray = Max(R, G, B)"),
        ("4b. Decomposition Min",      "Gray = Min(R, G, B)"),
        ("5a. Single Channel R",       "Gray = R"),
        ("5b. Single Channel G",       "Gray = G"),
        ("5c. Single Channel B",       "Gray = B"),
    ]:
        st.markdown(
            f'<div class="algo-card">'
            f'<div class="algo-title">{title}</div>'
            f'<div class="algo-formula">{formula}</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    st.markdown("---")
    st.markdown(
        '<p style="color:#5a5a8a;font-size:0.7rem;font-family:Space Mono,monospace;">'
        'Pengolahan Citra · Unpad</p>',
        unsafe_allow_html=True
    )

uploaded = st.file_uploader("Upload gambar PNG (8-bit RGB)", type=["png"])

if uploaded is None:
    st.markdown("""
    <div style="background:#1a1a2e;border:2px dashed #2a2a4e;border-radius:10px;
                padding:32px;text-align:center;color:#5a5a8a;font-size:0.85rem;">
        Upload file PNG di atas untuk memulai konversi.
    </div>""", unsafe_allow_html=True)
else:
    file_bytes = uploaded.read()

    ALGORITHMS = [
        ("1. Averaging",              "averaging",          lambda p,w,h: algo_averaging(p,w,h)),
        ("2a. Weighting\nHuman Eye",  "weighting_humaneye", lambda p,w,h: algo_weighting(p,w,h,0.3,0.59,0.11)),
        ("2b. Weighting\nBT.709",     "weighting_bt709",    lambda p,w,h: algo_weighting(p,w,h,0.2126,0.7152,0.0722)),
        ("2c. Weighting\nBT.601",     "weighting_bt601",    lambda p,w,h: algo_weighting(p,w,h,0.299,0.587,0.114)),
        ("3. Desaturation",           "desaturation",       lambda p,w,h: algo_desaturation(p,w,h)),
        ("4a. Decomposition\nMax",    "decomp_max",         lambda p,w,h: algo_decomp_max(p,w,h)),
        ("4b. Decomposition\nMin",    "decomp_min",         lambda p,w,h: algo_decomp_min(p,w,h)),
        ("5a. Single Channel\nR",     "channel_r",          lambda p,w,h: algo_channel(p,w,h,'R')),
        ("5b. Single Channel\nG",     "channel_g",          lambda p,w,h: algo_channel(p,w,h,'G')),
        ("5c. Single Channel\nB",     "channel_b",          lambda p,w,h: algo_channel(p,w,h,'B')),
    ]

    # Gunakan hash file sebagai cache key
    file_hash = hash(file_bytes)

    if st.session_state.get("file_hash") != file_hash:
        with st.spinner("Membaca gambar..."):
            try:
                pixels, w, h = read_png(file_bytes)
            except Exception as e:
                st.error(f"Gagal membaca gambar: {e}")
                st.stop()

        with st.spinner("Memproses semua algoritma..."):
            computed = [(label, stem, fn(pixels, w, h)) for label, stem, fn in ALGORITHMS]
            png_map  = {stem: write_png_gray(gray, w, h) for _, stem, gray in computed}

        st.session_state.file_hash = file_hash
        st.session_state.pixels    = pixels
        st.session_state.w         = w
        st.session_state.h         = h
        st.session_state.computed  = computed
        st.session_state.png_map   = png_map
    else:
        pixels   = st.session_state.pixels
        w        = st.session_state.w
        h        = st.session_state.h
        computed = st.session_state.computed
        png_map  = st.session_state.png_map

    col_orig, col_info = st.columns([1, 1])
    with col_orig:
        st.markdown("#### Gambar Asli (RGB)")
        b64_orig = base64.b64encode(file_bytes).decode()
        st.markdown(
            f'<img src="data:image/png;base64,{b64_orig}" style="width:100%;border-radius:8px;"/>',
            unsafe_allow_html=True
        )
    with col_info:
        st.markdown("#### Info Gambar")
        st.markdown(f"""
| Property | Value |
|---|---|
| Lebar | {w} px |
| Tinggi | {h} px |
| Total Piksel | {w*h:,} |
| Format | PNG |
| Bit Depth | 8-bit/channel |
""")

    st.divider()
    st.markdown("## Hasil Konversi")

    for row_start in range(0, len(computed), 5):
        row_algos = computed[row_start:row_start+5]
        cols = st.columns(5)
        for col, (label, stem, gray) in zip(cols, row_algos):
            b64           = base64.b64encode(png_map[stem]).decode()
            display_label = label.replace('\n', '<br>')
            with col:
                st.markdown(
                    f'<div class="result-card">'
                    f'<img src="data:image/png;base64,{b64}"/>'
                    f'<div class="result-label">{display_label}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                st.download_button(
                    "Download",
                    data=png_map[stem],
                    file_name=f"{stem}.png",
                    mime="image/png",
                    key=f"dl_{stem}"
                )

    st.divider()
    st.markdown("## Perbandingan Rata-rata Kecerahan")

    rows_html = ""
    for label, stem, gray in computed:
        flat = [v for row in gray for v in row]
        avg  = sum(flat) / len(flat)
        mn   = min(flat); mx = max(flat)
        pct  = int(avg / 255 * 100)
        bar  = (
            f'<div style="background:#2a2a4e;border-radius:3px;height:8px;">'
            f'<div style="background:#e94560;width:{pct}%;height:8px;border-radius:3px;"></div>'
            f'</div>'
        )
        name = label.replace('\n', ' ')
        rows_html += (
            f"<tr>"
            f"<td style='color:#ccc;font-size:0.78rem;padding:6px 10px;white-space:nowrap;'>{name}</td>"
            f"<td style='color:#f5a623;font-family:Space Mono,monospace;font-size:0.78rem;padding:6px 10px;'>{avg:.1f}</td>"
            f"<td style='color:#7a7a9a;font-family:Space Mono,monospace;font-size:0.78rem;padding:6px 10px;'>{mn} - {mx}</td>"
            f"<td style='padding:6px 10px;min-width:140px;'>{bar}</td>"
            f"</tr>"
        )

    st.markdown(f"""
    <table style="width:100%;border-collapse:collapse;background:#1a1a2e;border-radius:10px;overflow:hidden;">
        <thead><tr style="background:#0f0f1a;">
            <th style="color:#e94560;font-family:Space Mono,monospace;font-size:0.75rem;padding:10px;text-align:left;">Algoritma</th>
            <th style="color:#e94560;font-family:Space Mono,monospace;font-size:0.75rem;padding:10px;text-align:left;">Rata-rata</th>
            <th style="color:#e94560;font-family:Space Mono,monospace;font-size:0.75rem;padding:10px;text-align:left;">Rentang</th>
            <th style="color:#e94560;font-family:Space Mono,monospace;font-size:0.75rem;padding:10px;text-align:left;">Bar</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table>""", unsafe_allow_html=True)

    st.markdown(
        '<p style="text-align:center;color:#3a3a5a;font-family:Space Mono,monospace;'
        'font-size:0.7rem;padding-top:20px;">Pengolahan Citra · Unpad 2024</p>',
        unsafe_allow_html=True
    )