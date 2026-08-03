import streamlit as st
import os
import re
import zipfile
import shutil
import asyncio
import edge_tts
from pydub import AudioSegment

# Cấu hình trang web
st.set_page_config(page_title="AI Audio Studio - File 5 Phút", page_icon="🎧", layout="wide")

# Thư mục tạm
TEMP_DIR = "temp_audio_chunks"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ==========================================
# 1. CẤU HÌNH SIDEBAR
# ==========================================
VOICE_OPTIONS = {
    "Nữ - Hoài My (vi-VN-HoaiMyNeural)": "vi-VN-HoaiMyNeural",
    "Nam - Nam Minh (vi-VN-NamMinhNeural)": "vi-VN-NamMinhNeural"
}

with st.sidebar:
    st.header("⚙️ Cấu Hình Đọc")
    selected_voice_name = st.selectbox("Chọn Giọng Đọc AI:", list(VOICE_OPTIONS.keys()))
    selected_voice = VOICE_OPTIONS[selected_voice_name]
    
    words_per_chunk = st.slider(
        "Số từ mục tiêu mỗi file (~5 phút):", 
        min_value=500, 
        max_value=1000, 
        value=750, 
        step=50,
        help="700 - 800 từ tương đương khoảng 5 phút đọc thoại."
    )
    
    st.markdown("---")
    st.header("🎚️ Hậu Kỳ (Audio Mixing)")
    bgm_file = st.file_uploader("Tải Nhạc Nền (BGM) - MP3/WAV", type=["mp3", "wav"])
    bgm_volume = st.slider("Âm lượng Nhạc nền (dB)", -40, 0, -20)

# ==========================================
# 2. HÀM TÁCH VĂN BẢN VÀ XỬ LÝ TTS
# ==========================================
def split_text_by_sentences_and_words(text, target_words=750):
    """
    Tách văn bản dựa trên dấu kết thúc câu (. ! ? hoặc xuống dòng).
    Gom các câu lại sao cho tổng số từ đạt khoảng target_words (700-800 từ)
    mà không bao giờ bị ngắt ngang câu.
    """
    # Tách văn bản thành các câu dựa trên dấu . ! ? hoặc ký tự xuống dòng
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    chunks = []
    current_chunk = []
    current_word_count = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        words_in_sentence = len(sentence.split())
        
        # Nếu cộng câu này vào mà vượt quá lượng từ target và đã có câu trước đó
        if current_word_count + words_in_sentence > target_words and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_word_count = words_in_sentence
        else:
            current_chunk.append(sentence)
            current_word_count += words_in_sentence

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

async def generate_audio_async(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def generate_audio(text, voice, output_path):
    asyncio.run(generate_audio_async(text, voice, output_path))

# ==========================================
# 3. GIAO DIỆN CHÍNH & TẠO AUDIO
# ==========================================
st.title("🎧 Studio Tạo Audio Truyện/Kịch (Xuất File 5 Phút)")
st.markdown("Hệ thống sẽ tự động phân chia văn bản thành các phần dài **~5 phút (700-800 từ)**, chỉ ngắt ở **dấu chấm/kết thúc câu** và đóng gói thành 1 file ZIP.")

script_input = st.text_area("Dán toàn bộ văn bản truyện/kịch vào đây:", height=300)

if st.button("🚀 Render & Chia File 5 Phút (.ZIP)"):
    if not script_input.strip():
        st.warning("Vui lòng nhập nội dung văn bản!")
    else:
        try:
            # Bước 1: Tách văn bản thành từng khối 5 phút
            chunks = split_text_by_sentences_and_words(script_input, target_words=words_per_chunk)
            total_chunks = len(chunks)
            st.info(f"Đã phân chia văn bản thành **{total_chunks} phần** (mỗi phần ~5 phút, ngắt đúng dấu chấm).")
            
            progress_bar = st.progress(0)
            generated_files = []
            
            # Đọc file BGM 1 lần nếu có
            bgm_audio = None
            if bgm_file:
                bgm_audio = AudioSegment.from_file(bgm_file) + bgm_volume

            # Bước 2: Tạo Audio cho từng phần 5 phút
            for i, chunk_text in enumerate(chunks):
                part_num = i + 1
                word_count = len(chunk_text.split())
                st.write(f"🎙️ **Đang tạo Phần {part_num}/{total_chunks}** ({word_count} từ)...")
                
                raw_path = os.path.join(TEMP_DIR, f"temp_part_{part_num}.mp3")
                final_part_name = f"Phan_{part_num:03d}_5Min.mp3"
                final_part_path = os.path.join(TEMP_DIR, final_part_name)
                
                # Gọi TTS sinh giọng
                generate_audio(chunk_text, selected_voice, raw_path)
                
                # Trộn nhạc nền nếu có
                part_audio = AudioSegment.from_file(raw_path)
                if bgm_audio:
                    # Lặp BGM cho bằng độ dài giọng đọc
                    bgm_matched = bgm_audio
                    if len(bgm_matched) < len(part_audio):
                        bgm_matched = bgm_matched.loop_for(len(part_audio))
                    bgm_matched = bgm_matched[:len(part_audio)]
                    
                    final_audio = part_audio.overlay(bgm_matched)
                else:
                    final_audio = part_audio
                
                # Xuất file MP3 của phần này
                final_audio.export(final_part_path, format="mp3")
                generated_files.append(final_part_path)
                
                # Cập nhật thanh tiến trình
                progress_bar.progress(part_num / total_chunks)

            # Bước 3: Nén tất cả các file 5 phút vào 1 file ZIP
            zip_filename = "Thu_Muc_Audio_5Phut_Full.zip"
            with zipfile.ZipFile(zip_filename, 'w') as zipf:
                for file_path in generated_files:
                    zipf.write(file_path, os.path.basename(file_path))

            st.success("🎉 Đã xuất thành công toàn bộ các file 5 phút!")

            # Hiển thị trình nghe thử cho từng phần
            st.markdown("### 🎧 Nghe thử từng phần:")
            for file_path in generated_files:
                st.caption(os.path.basename(file_path))
                st.audio(file_path)

            # Nút tải file ZIP
            with open(zip_filename, "rb") as fp:
                st.download_button(
                    label="📦 Tải Toàn Bộ File 5 Phút (.ZIP)",
                    data=fp,
                    file_name=zip_filename,
                    mime="application/zip"
                )

        except Exception as e:
            st.error(f"Đã xảy ra lỗi: {str(e)}")

        finally:
            # Dọn dẹp thư mục tạm
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
                os.makedirs(TEMP_DIR)
