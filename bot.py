"""
Telegram Video Downloader Bot
-----------------------------
- yt-dlp দিয়ে যেকোনো সাপোর্টেড লিংক থেকে ভিডিও নামায়
- Pyrogram (MTProto) দিয়ে পাঠায়, তাই ২ GB পর্যন্ত ফাইল পাঠাতে পারে
- পাঠানো শেষ হলেই ফাইল ডিলিট করে দেয় => ডিস্ক কখনো ভরে না (no crash)
- একসাথে সর্বোচ্চ ২টা ডাউনলোড (queue) => RAM/CPU সেফ

সব সিক্রেট environment variable থেকে আসে। কোডে টোকেন লিখবেন না।
"""

import asyncio
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path

import yt_dlp
from pyrogram import Client, filters
from pyrogram.errors import FloodWait
from pyrogram.types import Message

# ---------------------------------------------------------------- config
API_ID = int(os.environ.get("33019465", "0"))
API_HASH = os.environ.get("02fe1be68e1f501bb36dcfc55e8014ca", "")
BOT_TOKEN = os.environ.get("8656620646:AAERseX1q82Hn7BR4HZcEt4xi9PLjGstXQQ", "")

# টেলিগ্রাম বট আপলোড লিমিট (bytes). Pyrogram/MTProto => 2 GB
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", 2 * 1024 * 1024 * 1024))
# একসাথে কতগুলো ডাউনলোড চলবে
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "2"))
# ডাউনলোড ফোল্ডার (ephemeral disk)
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/tmp/downloads"))
# ডিস্কে অন্তত এত বাইট ফাঁকা না থাকলে ডাউনলোড শুরু হবে না (default 1.5 GB)
MIN_FREE_SPACE = int(os.environ.get("MIN_FREE_SPACE", 1536 * 1024 * 1024))

if not (API_ID and API_HASH and BOT_TOKEN):
    raise SystemExit("API_ID / API_HASH / BOT_TOKEN environment variable সেট করুন")

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("bot")

app = Client(
    "video-bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workdir="/tmp",
)

semaphore = asyncio.Semaphore(MAX_CONCURRENT)
URL_RE = re.compile(r"https?://\S+")


# ---------------------------------------------------------------- helpers
def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def free_space(path: Path) -> int:
    return shutil.disk_usage(path).free


def cleanup(path: Path) -> None:
    """ফাইল/ফোল্ডার নিরাপদে মুছে দেয় — কখনো exception তোলে না।"""
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)
    except Exception as exc:  # pragma: no cover
        log.warning("cleanup failed for %s: %s", path, exc)


def sweep_old_files(max_age_seconds: int = 3600) -> None:
    """পুরোনো/আটকে থাকা ফাইল মুছে ডিস্ক ফাঁকা রাখে।"""
    now = time.time()
    for item in DOWNLOAD_DIR.iterdir():
        try:
            if now - item.stat().st_mtime > max_age_seconds:
                cleanup(item)
        except Exception:
            pass


def blocking_download(url: str, folder: Path) -> Path:
    """yt-dlp দিয়ে ডাউনলোড (thread-এ চলে, event loop ব্লক করে না)।"""
    opts = {
        "outtmpl": str(folder / "%(title).80s.%(ext)s"),
        "format": "bv*[filesize<2G]+ba/b[filesize<2G]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "restrictfilenames": True,
        "max_filesize": MAX_FILE_SIZE,
    }
    cookies = os.environ.get("COOKIES_FILE")
    if cookies and Path(cookies).exists():
        opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info.get("entries"):
            info = info["entries"][0]
        return Path(ydl.prepare_filename(info)).with_suffix(".mp4") if Path(
            ydl.prepare_filename(info)
        ).with_suffix(".mp4").exists() else Path(ydl.prepare_filename(info))


async def safe_edit(msg: Message, text: str) -> None:
    try:
        await msg.edit_text(text)
    except Exception:
        pass


# ---------------------------------------------------------------- handlers
@app.on_message(filters.command(["start", "help"]) & filters.private)
async def start(_, message: Message):
    await message.reply_text(
        "👋 **Video Downloader Bot**\n\n"
        "যেকোনো ভিডিও লিংক পাঠান — আমি নামিয়ে আপনাকে পাঠিয়ে দেব।\n\n"
        f"• সর্বোচ্চ সাইজ: {human(MAX_FILE_SIZE)}\n"
        "• YouTube, Facebook, Instagram, TikTok, X সহ ১০০০+ সাইট\n"
        "• ফাইল পাঠানোর পরেই সার্ভার থেকে মুছে ফেলা হয়"
    )


@app.on_message(filters.text & filters.private & ~filters.command(["start", "help"]))
async def handle_link(client: Client, message: Message):
    match = URL_RE.search(message.text or "")
    if not match:
        await message.reply_text("❌ একটা সঠিক লিংক পাঠান।")
        return

    url = match.group(0)
    status = await message.reply_text("⏳ কিউতে আছে...")

    async with semaphore:
        sweep_old_files()

        if free_space(DOWNLOAD_DIR) < MIN_FREE_SPACE:
            await safe_edit(status, "⚠️ সার্ভারে জায়গা কম, একটু পরে আবার চেষ্টা করুন।")
            return

        job_dir = DOWNLOAD_DIR / uuid.uuid4().hex
        job_dir.mkdir(parents=True, exist_ok=True)
        file_path: Path | None = None

        try:
            await safe_edit(status, "⬇️ ডাউনলোড হচ্ছে...")
            file_path = await asyncio.to_thread(blocking_download, url, job_dir)

            if not file_path or not file_path.exists():
                found = list(job_dir.glob("*"))
                if not found:
                    raise FileNotFoundError("ফাইল পাওয়া যায়নি")
                file_path = found[0]

            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE:
                await safe_edit(
                    status,
                    f"❌ ফাইলটা অনেক বড় ({human(size)}). লিমিট {human(MAX_FILE_SIZE)}।",
                )
                return

            await safe_edit(status, f"⬆️ আপলোড হচ্ছে... ({human(size)})")
            await client.send_video(
                chat_id=message.chat.id,
                video=str(file_path),
                caption=file_path.stem,
                supports_streaming=True,
            )
            await safe_edit(status, "✅ হয়ে গেছে!")

        except FloodWait as exc:
            await asyncio.sleep(exc.value)
            await safe_edit(status, "⚠️ টেলিগ্রাম রেট লিমিট, আবার চেষ্টা করুন।")
        except Exception as exc:
            log.exception("job failed: %s", exc)
            await safe_edit(status, f"❌ ব্যর্থ: `{str(exc)[:300]}`")
        finally:
            # যা-ই হোক, ডিস্ক সবসময় ফাঁকা করে দেওয়া হয়
            cleanup(job_dir)


if __name__ == "__main__":
    log.info("bot starting...")
    app.run()
