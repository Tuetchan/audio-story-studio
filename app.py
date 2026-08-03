import streamlit as st
import pandas as pd
import re
import os
import zipfile
import shutil
import asyncio
import edge_tts
from pydub import AudioSegment

# Cấu hình trang web
st.set_page_config(page_title="AI Audio Studio", page_icon="🎧", layout="wide")

# Thư mục tạm thời
TEMP_DIR = "temp_audio"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ==========================================
# 1. DANH BẠ GIỌNG ĐỌC (SIDEBAR)
# ==========================================
DEFAULT_VOICES = [
    {"Nhân vật": "NguoiDanTruyen", "Voice ID": "vi-VN-HoaiMyNeural"},
    {"Nhân vật": "NamChinh", "Voice ID": "vi-VN-NamMinhNeural"},
    {"Nhân vật": "NuChinh", "Voice ID": "vi-VN-HoaiMyNeural"}
]

if 'voice_dir' not in st.session_state:
    st.session_state.voice_dir = pd.DataFrame(DEFAULT_VOICES)

with st.sidebar:
    st.header("📇 Danh Bạ Voice (Edge-TTS)")
    st.markdown("Nhập tên nhân vật và Mã giọng đọc tương ứng. Dùng phím Delete để xóa dòng.")
    
    edited_df = st.data_editor(st.session_state.voice_dir, num_rows="dynamic", use_container_width=True)
    voice_dict = dict(zip(edited_df["Nhân vật"], edited_df["Voice ID"]))
    
    st.markdown("---")
    st.header("🎚️ Hậu Kỳ (Audio Mixing)")
    bgm_file = st.file_uploader("Tải Nhạc Nền (BGM) - MP3/WAV", type=["mp3", "wav"])
    bgm_volume = st.slider("Âm lượng Nhạc nền (dB)", -40, 0, -20)

# ==========================================
# 2. HÀM XỬ LÝ LÕI
# ==========================================
def parse_script(script_text):
    """Bóc tách kịch bản thành từng câu thoại"""
    lines = script_text.split('\n')
    segments = []
    for line in lines:
        if not line.strip(): 
            continue
        
        match = re.match(r'\[(.*?)\]:\s*(.*)', line)
        if match:
            char, text = match.group(1).strip(), match.group(2).strip()
        else:
            char, text = "NguoiDanTruyen", line.strip()
            
        vid = voice_dict.get(char, "vi-VN-HoaiMyNeural")
        segments.append({"character": char, "voice_id": vid, "text": text})
    return segments

async def generate_audio_edge_tts_async(text, voice, output_path):
    """Chạy Edge-TTS trực tiếp qua Python (Không qua Terminal)"""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_audio_edge_tts(text, voice, output_path):
    """Hàm bọc để Streamlit gọi bất đồng bộ"""
    asyncio.run(generate_audio_edge_tts_async(text, voice, output_path))

# ==========================================
# 3. GIAO DIỆN CHÍNH
# ==========================================
st.title("🎧 Studio Tạo Kịch Truyền Thanh AI")
st.markdown("Cú pháp chuẩn: `[Tên Nhân Vật]: Lời thoại`. Ví dụ: `[NamChinh]: Ta đến đây!`")

script_input = st.text_area("Nhập kịch bản truyện/kịch của bạn:", height=250)

if st.button("🚀 Render Toàn Bộ Audio & Ghép Nhạc"):
    if not script_input:
        st.warning("Vui lòng nhập kịch bản!")
    else:
        try:
            # Bước 1: Bóc tách
            segments = parse_script(script_input)
            st.info(f"Đã bóc tách được {len(segments)} phân đoạn thoại. Đang tiến hành thu âm AI...")
            
            progress_bar = st.progress(0)
            generated_files = []
            combined_audio = AudioSegment.empty()
            
            # Bước 2: Sinh Audio cho từng câu
            for i, seg in enumerate(segments):
                file_name = f"{i+1:03d}_{seg['character']}.mp3"
                file_path = os.path.join(TEMP_DIR, file_name)
                
                with st.spinner(f"Đang thu âm: {seg['character']}..."):
                    generate_audio_edge_tts(seg['text'], seg['voice_id'], file_path)
                    generated_files.append(file_path)
                    
                    # Nối audio vào file tổng (thêm 500ms tĩnh lặng giữa các câu)
                    audio_clip = AudioSegment.from_file(file_path)
                    combined_audio += audio_clip + AudioSegment.silent(duration=500)
                    
                progress_bar.progress((i + 1) / len(segments))
                
            st.success("Hoàn tất thu âm các nhân vật!")

            # Bước 3: Ghép nhạc nền (BGM)
            final_export_path = "Thanh_Pham_Kich_Audio.mp3"
            with st.spinner("Đang lồng ghép nhạc nền (Mixing)..."):
                if bgm_file:
                    bgm = AudioSegment.from_file(bgm_file)
                    bgm = bgm + bgm_volume # Điều chỉnh âm lượng
                    
                    # Lặp nhạc nền cho bằng độ dài giọng đọc
                    if len(bgm) < len(combined_audio):
                        bgm = bgm.loop_for(len(combined_audio))
                    bgm = bgm[:len(combined_audio)]
                    
                    # Trộn 2 track
                    final_audio = combined_audio.overlay(bgm)
                else:
                    final_audio = combined_audio
                    
                final_audio.export(final_export_path, format="mp3")

            # Bước 4: Đóng gói ZIP
            zip_filename = "Du_An_Kich_Truyen_Thanh.zip"
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                zipf.write(final_export_path)
                for f in generated_files:
                    zipf.write(f, os.path.basename(f))

            # Hiển thị nút tải
            st.success("🎉 Mọi thứ đã sẵn sàng!")
            st.audio(final_export_path)
            
            with open(zip_filename, "rb") as fp:
                st.download_button(
                    label="📦 Tải Toàn Bộ Dự Án Về Máy (.ZIP)",
                    data=fp,
                    file_name=zip_filename,
                    mime="application/zip"
                )
                
        except Exception as e:
            st.error(f"Đã xảy ra lỗi trong quá trình xử lý: {str(e)}")

        finally:
            # Dọn dẹp máy chủ ảo an toàn dù thành công hay sập lỗi
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
                os.makedirs(TEMP_DIR)
