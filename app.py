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

    # Đã sửa lại Selectbox -> SelectboxColumn
    column_config = {
        "Nguồn Giọng": st.column_config.SelectboxColumn(
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
        role_map[str(row["Mã @"]).strip().lower()] = {
            "provider": row["Nguồn Giọng"],
            "voice_id": str(row["Voice ID"]).strip()
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
    """Bóc tách kịch bản dựa vào ký hiệu @ ở đầu đoạn văn"""
    lines = script_text.split('\n')
    segments = []
    current_char = "nguoidantruyen"

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

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

st.markdown(
    "**Hướng dẫn cú pháp:** Đặt `@Mã_Nhân_Vật` trước mỗi lời thoại.\n\n"
    "**Ví dụ mẫu:**\n"
    "- `@NguoiDanTruyen Ngày xửa ngày xưa, tại một ngôi làng nọ...`\n"
    "- `@NamChinh Ta nhất định phải ra đi tìm sự thật!`\n"
    "- `@NuChinh Chàng hãy cẩn thận nhé!`\n"
    "- `@NamChinh2 Ta sẽ đi cùng huynh!`"
)

script_input = st.text_area("Nhập kịch bản phân vai của bạn vào đây:", height=250)

# Khai báo 2 Tab
tab1, tab2 = st.tabs(["🔊 TAB 1: Full Audio (1 File Duy Nhất)", "🎭 TAB 2: Kịch Truyền Thanh (Chia File 5 Phút .ZIP)"])

# ------------------------------------------
# TAB 1: FULL AUDIO
# ------------------------------------------
with tab1:
    st.subheader("Xuất toàn bộ kịch bản ra 1 file Audio duy nhất")
    if st.button("🚀 Render Full Audio (1 File)"):
        if not script_input.strip():
            st.warning("Vui lòng nhập kịch bản!")
        else:
            try:
                segments = parse_script_by_at_tag(script_input, role_map)
                st.info(f"Đã bóc tách được {len(segments)} phân đoạn. Đang tiến hành tạo audio...")
                
                progress_bar = st.progress(0)
                combined_audio = AudioSegment.empty()

                for i, seg in enumerate(segments):
                    temp_path = os.path.join(TEMP_DIR, f"tab1_seg_{i}.mp3")
                    generate_tts_audio(seg["text"], seg["provider"], seg["voice_id"], temp_path)
                    
                    audio_clip = AudioSegment.from_file(temp_path)
                    combined_audio += audio_clip + AudioSegment.silent(duration=400)
                    
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    
                    progress_bar.progress((i + 1) / len(segments))

                # Ghép Nhạc Nền
                if bgm_file:
                    bgm = AudioSegment.from_file(bgm_file) + bgm_volume
                    if len(bgm) < len(combined_audio):
                        bgm = bgm.loop_for(len(combined_audio))
                    bgm = bgm[:len(combined_audio)]
                    final_audio = combined_audio.overlay(bgm)
                else:
                    final_audio = combined_audio

                export_path = "Full_Audio_Kich_Truyen_Thanh.mp3"
                final_audio.export(export_path, format="mp3")

                st.success("🎉 Đã hoàn tất render Full Audio!")
                st.audio(export_path)
                
                with open(export_path, "rb") as fp:
                    st.download_button("📦 Tải File MP3 Hoàn Chỉnh", data=fp, file_name=export_path, mime="audio/mpeg")

            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {str(e)}")
            finally:
                if os.path.exists(TEMP_DIR):
                    shutil.rmtree(TEMP_DIR)
                    os.makedirs(TEMP_DIR)

# ------------------------------------------
# TAB 2: KỊCH TRUYỀN THANH CHIA FILE 5 PHÚT
# ------------------------------------------
with tab2:
    st.subheader("Phân chia kịch bản thành từng file ~5 phút (Ngắt đúng câu thoại)")
    if st.button("🚀 Render & Chia File 5 Phút (.ZIP)"):
        if not script_input.strip():
            st.warning("Vui lòng nhập kịch bản!")
        else:
            try:
                segments = parse_script_by_at_tag(script_input, role_map)
                
                # Gom nhóm câu thoại thành các file ~5 phút (700-800 từ)
                chunks = []
                current_chunk = []
                current_words = 0

                for seg in segments:
                    seg_words = len(seg["text"].split())
                    if current_words + seg_words > words_per_chunk and current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = [seg]
                        current_words = seg_words
                    else:
                        current_chunk.append(seg)
                        current_words += seg_words

                if current_chunk:
                    chunks.append(current_chunk)

                total_chunks = len(chunks)
                st.info(f"Kịch bản được chia thành **{total_chunks} file kịch** (~5 phút/file).")

                progress_bar = st.progress(0)
                generated_files = []

                bgm_audio = None
                if bgm_file:
                    bgm_audio = AudioSegment.from_file(bgm_file) + bgm_volume

                for i, chunk_segs in enumerate(chunks):
                    part_num = i + 1
                    chunk_audio = AudioSegment.empty()

                    for j, seg in enumerate(chunk_segs):
                        temp_line_path = os.path.join(TEMP_DIR, f"p{part_num}_line_{j}.mp3")
                        generate_tts_audio(seg["text"], seg["provider"], seg["voice_id"], temp_line_path)
                        
                        line_segment = AudioSegment.from_file(temp_line_path)
                        chunk_audio += line_segment + AudioSegment.silent(duration=400)
                        
                        if os.path.exists(temp_line_path):
                            os.remove(temp_line_path)

                    # Mix BGM cho từng part
                    if bgm_audio:
                        matched_bgm = bgm_audio
                        if len(matched_bgm) < len(chunk_audio):
                            matched_bgm = matched_bgm.loop_for(len(chunk_audio))
                        matched_bgm = matched_bgm[:len(chunk_audio)]
                        final_chunk_audio = chunk_audio.overlay(matched_bgm)
                    else:
                        final_chunk_audio = chunk_audio

                    final_part_name = f"Phan_{part_num:03d}_Kich_5Min.mp3"
                    final_part_path = os.path.join(TEMP_DIR, final_part_name)
                    final_chunk_audio.export(final_part_path, format="mp3")
                    generated_files.append(final_part_path)

                    progress_bar.progress(part_num / total_chunks)

                # Nén ZIP
                zip_filename = "Kich_Truyen_Thanh_5Phut_Full.zip"
                with zipfile.ZipFile(zip_filename, 'w') as zipf:
                    for file_path in generated_files:
                        zipf.write(file_path, os.path.basename(file_path))

                st.success("🎉 Đã hoàn tất render toàn bộ các file 5 phút!")

                for file_path in generated_files:
                    st.caption(os.path.basename(file_path))
                    st.audio(file_path)

                with open(zip_filename, "rb") as fp:
                    st.download_button("📦 Tải Toàn Bộ File 5 Phút (.ZIP)", data=fp, file_name=zip_filename, mime="application/zip")

            except Exception as e:
                st.error(f"Đã xảy ra lỗi: {str(e)}")
            finally:
                if os.path.exists(TEMP_DIR):
                    shutil.rmtree(TEMP_DIR)
                    os.makedirs(TEMP_DIR)
