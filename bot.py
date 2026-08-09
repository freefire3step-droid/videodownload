import os
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
from pyrogram.errors import MessageNotModified, FloodWait
import yt_dlp

# ==================== CONFIGURATION ====================
API_ID = 33019465
API_HASH = "02fe1be68e1f501bb36dcfc55e8014ca"
BOT_TOKEN = "8656620646:AAERseX1q82Hn7BR4HZcEt4xi9PLjGstXQQ"

AUTO_DELETE_SECONDS = 120  # ২ মিনিট পর প্রাইভেট চ্যাট থেকে ফাইল ডিলিট হবে
# =======================================================

app = Client("2gb_video_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# প্রাইভেট চ্যাটের জন্য ব্যাকগ্রাউন্ড অটো-ডিলিট
async def auto_delete_msg(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id=chat_id, message_ids=message_id)
        print(f"[SUCCESS] Auto-deleted video message from chat {chat_id}")
    except Exception as e:
        print(f"[ERROR] Could not delete message: {e}")

# প্রোগ্রেস আপডেট করার ব্যাকগ্রাউন্ড টাস্ক (সার্ভার ক্র্যাশ রোধ করতে)
async def update_progress_message(status_msg, progress_data):
    last_text = ""
    while progress_data["is_active"]:
        current_text = progress_data.get("text", "")
        if current_text and current_text != last_text:
            try:
                await status_msg.edit_text(current_text)
                last_text = current_text
            except MessageNotModified:
                pass
            except FloodWait as e:
                await asyncio.sleep(e.value) # টেলিগ্রাম ব্লক করলে অপেক্ষা করবে
            except Exception:
                pass
        await asyncio.sleep(5)  # প্রতি ৫ সেকেন্ড পর পর আপডেট (সার্ভার প্রেশার কমাবে)

@app.on_message(filters.command("start"))
async def start_command(client, message: Message):
    await message.reply_text("👋 Welcome! যেকোনো Video link (Wispybite বা অন্যান্য) পাঠান। আমি ২ GB পর্যন্ত দ্রুত ভিডিও ডাউনলোড করে দেব।")

@app.on_message(filters.text & ~filters.forwarded)
async def handle_video_download(client, message: Message):
    url = message.text.strip()

    if not url.startswith("http"):
        await message.reply_text("❌ অনুগ্রহ করে একটি সঠিক Video URL পাঠান।")
        return

    status_msg = await message.reply_text("⏳ Processing request... Please wait.")
    
    timestamp = int(time.time())
    file_name = f"video_{message.chat.id}_{timestamp}.mp4"
    local_path = f"./{file_name}"

    loop = asyncio.get_running_loop()
    
    # ডিকশনারি দিয়ে ডেটা শেয়ার করা হচ্ছে থ্রেড এবং অ্যাসিন্ক টাস্কের মাঝে
    progress_data = {"is_active": True, "text": "⏳ Starting download..."}
    updater_task = asyncio.create_task(update_progress_message(status_msg, progress_data))

    def yt_dlp_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed') or 0

            if total > 0:
                percentage = (downloaded / total) * 100
                speed_mb = speed / (1024 * 1024)
                downloaded_mb = downloaded / (1024 * 1024)
                total_mb = total / (1024 * 1024)

                progress_data["text"] = (
                    f"📥 **Downloading Video...**\n\n"
                    f"📊 **Progress:** `{percentage:.1f}%` ({downloaded_mb:.1f}/{total_mb:.1f} MB)\n"
                    f"🚀 **Speed:** `{speed_mb:.2f} MB/s`"
                )

    # Multi-threaded Super Fast Speed Config (Optimized for Server)
    ydl_opts = {
        'outtmpl': local_path,
        'format': 'best[ext=mp4]/best', # Wispybite বা যেকোনো সাইটের জন্য সেরা mp4 ফরমেট
        'quiet': True,
        'no_warnings': True,
        'concurrent_fragment_downloads': 3, # সার্ভারে প্রেশার কমাতে ১০ থেকে কমিয়ে ৩ করা হয়েছে
        'progress_hooks': [yt_dlp_hook],
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
        }
    }

    try:
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)

        # Thread এ ডাউনলোড রান করা হচ্ছে যেন বট ফ্রিজ না হয়
        info_dict = await loop.run_in_executor(None, download)
        
        # ডাউনলোড শেষ, প্রোগ্রেস টাস্ক বন্ধ করা
        progress_data["is_active"] = False
        await updater_task 
        
        if not os.path.exists(local_path):
            await status_msg.edit_text("❌ ভিডিও ডাউনলোড সম্ভব হয়নি। লিংক সঠিক আছে কিনা চেক করুন বা সাইটটি সাপোর্ট করে না।")
            return

        file_size_mb = os.path.getsize(local_path) / (1024 * 1024)

        if file_size_mb > 2000:
            await status_msg.edit_text(f"⚠️ ভিডিওটির সাইজ {file_size_mb:.2f} MB, যা টেলিগ্রামের ২ GB সীমার চেয়ে বেশি।")
            return

        duration = 0
        if info_dict and isinstance(info_dict, dict):
            duration = int(info_dict.get('duration') or 0)

        if message.chat.type == ChatType.PRIVATE:
            caption_text = f"✅ **Here is your video!** ({file_size_mb:.1f} MB)\n\n⚠️ *Note: এই মেসেজটি ২ মিনিট পর অটোমেটিক ডিলিট হয়ে যাবে।*"
        else:
            caption_text = f"✅ **Here is your video!** ({file_size_mb:.1f} MB)\n\n📌 *Note: এই ভিডিওটি গ্রুপে পারমানেন্ট থাকবে।*"

        # Upload Progress Callback
        last_up_update = [0]
        async def upload_progress(current, total):
            now = time.time()
            if now - last_up_update[0] >= 5: # আপলোডের সময় ৫ সেকেন্ড পর পর আপডেট
                last_up_update[0] = now
                percentage = (current / total) * 100
                current_mb = current / (1024 * 1024)
                total_mb = total / (1024 * 1024)
                try:
                    await status_msg.edit_text(
                        f"📤 **Uploading to Telegram...**\n\n"
                        f"📊 **Progress:** `{percentage:.1f}%` ({current_mb:.1f}/{total_mb:.1f} MB)"
                    )
                except Exception:
                    pass

        # Telegram Upload
        sent_video = await app.send_video(
            chat_id=message.chat.id,
            video=local_path,
            duration=duration,
            supports_streaming=True,
            caption=caption_text,
            progress=upload_progress
        )

        await status_msg.delete()

        # Auto-delete for private chats
        if message.chat.type == ChatType.PRIVATE:
            asyncio.create_task(auto_delete_msg(message.chat.id, sent_video.id, AUTO_DELETE_SECONDS))

    except Exception as e:
        progress_data["is_active"] = False
        try:
            await status_msg.edit_text(f"❌ Error occurred: {str(e)}")
        except Exception:
            pass
    finally:
        progress_data["is_active"] = False
        # Server Crash Solve: যেকোনো পরিস্থিতিতেই লোকাল ফাইল মুছে ফেলা সুনিশ্চিত করা
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                print(f"[CLEANUP] Deleted local file {local_path} from server.")
            except Exception as cleanup_err:
                print(f"[CLEANUP ERROR] {cleanup_err}")

print("Bot running with Speed Optimization & Anti-Crash System...")
app.run()
