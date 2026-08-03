import streamlit as st
import pandas as pd
import re
import os
import zipfile
import shutil
import asyncio
import requests
import edge_tts
from pydub import AudioSegment

# Cấu hình trang web
st.set_page_config(page_title="Studio Kịch Truyền Thanh AI Pro", page_icon="🎧", layout="wide")

# Thư mục tạm
TEMP_DIR = "temp_kicks_audio_pro"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ==========================================
# 1. CẤU HÌNH API & PHÂN VAI (SIDEBAR)
# ==========================================
with st.sidebar:
    st.header("🔑 Cấu Hình API Key Trả Phí")
    elevenlabs_key = st.text_input("ElevenLabs API Key:", type="password", help="Nhập API Key ElevenLabs nếu muốn dùng giọng trả phí")
    openai_key = st.text_input("OpenAI API Key:", type="password", help="Nhập OpenAI API Key nếu muốn dùng OpenAI TTS")
    
    st.markdown("---")
    st.header("🎭 Phân Vai Giọng Đọc Nhân Vật")
    st.caption("Gõ cú pháp `@Mã_Nhân_Vật` ở đầu mỗi đoạn kịch bản.")

    # Cấu hình danh sách nhân vật mặc định
    default_roles = [
        {"Mã @": "NguoiDanTruyen", "Tên Vai": "Người dẫn truyện", "Nguồn Giọng": "Edge-TTS (Miễn phí)", "Voice ID": "vi-VN-HoaiMyNeural"},
        {"Mã @": "NamChinh", "Tên Vai": "Nam chính", "Nguồn Giọng": "Edge-TTS (Miễn phí)", "Voice ID": "vi-VN-NamMinhNeural"},
        {"Mã @": "NuChinh", "Tên Vai": "Nữ chính", "Nguồn Giọng": "Edge-TTS (Miễn phí)", "Voice ID": "vi-VN-HoaiMyNeural"},
        {"Mã @": "NamChinh2", "Tên Vai": "Nam chính thứ 2", "Nguồn Giọng": "Edge-TTS (Miễn phí)", "Voice ID": "vi-VN-NamMinhNeural"},
        {"Mã @": "NhanVatKhac", "Tên Vai": "Các nhân vật khác", "Nguồn Giọng": "Edge-TTS (Miễn phí)", "Voice ID": "vi-VN-HoaiMyNeural"},
    ]

    if 'roles_df' not in st.session_state:
        st.session_state.roles_df = pd.DataFrame(default_roles)

    column_config = {
        "Nguồn Giọng": st.column_config.Selectbox(
            "Nguồn Giọng",
            options=["Edge-TTS (Miễn phí)", "ElevenLabs (Trả phí)", "OpenAI (Trả phí)"],
            required=True
        )
    }

    edited_roles = st.data_editor(
        st.session_state.roles_df,
        column_config=column_config,
        num_rows="dynamic",
        use_container_width=True
    )

    # Chuyển đổi bảng phân vai thành Dictionary
    role_map = {}
    for _, row in edited_roles.iterrows():
        role_map[row["Mã @"].strip().lower()] = {
            "provider": row["Nguồn Giọng"],
            "voice_id": row["Voice ID"].strip()
        }

    st.markdown("---")
    st.header("⏱️ Cấu Hình File & Nhạc Nền")
    words_per_chunk = st.slider("Số từ/file ở Tab 2 (~5 phút):", 500, 1000, 750, 50)
    bgm_file = st.file_uploader("Tải Nhạc Nền (BGM) - MP3/WAV", type=["mp3", "wav"])
    bgm_volume = st.slider("Âm lượng Nhạc nền (dB)", -40, 0, -20)

# ==========================================
# 2. HÀM XỬ LÝ TTS & BÓC TÁCH KỊCH BẢN
# ==========================================
async def generate_edge_tts_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_tts_audio(text, provider, voice_id, output_path):
    """Hàm điều hướng tạo âm thanh theo nguồn giọng (Free / ElevenLabs / OpenAI)"""
    # 1. ElevenLabs Trả phí
    if provider == "ElevenLabs (Trả phí)" and elevenlabs_key:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": elevenlabs_key}
        data = {"text": text, "model_id": "eleven_multilingual_v2"}
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return
        else:
            st.warning(f"Lỗi ElevenLabs API ({response.status_code}), chuyển về giọng mặc định Edge-TTS.")

    # 2. OpenAI Trả phí
    elif provider == "OpenAI (Trả phí)" and openai_key:
        url = "https://api.openai.com/v1/audio/speech"
        headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
        data = {"model": "tts-1", "input": text, "voice": voice_id if voice_id in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"] else "alloy"}
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return
        else:
            st.warning(f"Lỗi OpenAI API ({response.status_code}), chuyển về giọng mặc định Edge-TTS.")

    # 3. Mặc định / Free Edge-TTS
    default_voice = voice_id if "Neural" in voice_id else "vi-VN-HoaiMyNeural"
    asyncio.run(generate_edge_tts_async(text, default_voice, output_path))


def parse_script_by_at_tag(script_text, role_map):
    """Bóc tách kịch bản dựa vào ký hiệu @ở đầu đoạn văn"""
    lines = script_text.split('\n')
    segments = []
    current_char = "nguoidantruyen" # Mặc định nếu chưa gõ @

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Regex tìm ký hiệu @Tên_Nhân_Vật ở đầu dòng
        match = re.match(r'^@([^\s:]+)\b[:\s]*(.*)', line_str)
        if match:
            char_tag = match.group(1).strip().lower()
            text = match.group(2).strip()
            current_char = char_tag
        else:
            text = line_str

        if text:
            role_info = role_map.get(current_char, {
                "provider": "Edge-TTS (Miễn phí)", 
                "voice_id": "vi-VN-HoaiMyNeural"
            })
            segments.append({
                "character": current_char,
                "provider": role_info["provider"],
                "voice_id": role_info["voice_id"],
                "text": text
            })

    return segments

# ==========================================
# 3. GIAO DIỆN CHÍNH & XỬ LÝ TABS
# ==========================================
st.title("🎧 Studio Tạo Kịch Truyền Thanh AI Pro")
st.markdown("""
**Hướng dẫn cú pháp:** Đặt `@Mã_Nhân_Vật` trước mỗi lời thoại. 
Ví dụ:
```text
@NguoiDanTruyen Ngày xửa ngày xưa, tại một ngôi làng nọ...
@NamChinh Ta nhất định phải ra đi tìm sự thật!
@NuChinh Chàng hãy cẩn thận nhé!
@NamChinh2 Ta sẽ đi cùng huynh!
