# Telegram Video Downloader Bot

কোনো ফাইল এডিট করতে হবে না — শুধু আপলোড + ৩টা environment variable বসান।

## ১. আগে টোকেন বদলান
BotFather → `/revoke` → নতুন BOT_TOKEN নিন (পুরোনোটা পাবলিক হয়ে গেছে)।

## ২. Railway-তে ডিপ্লয় (সবচেয়ে সহজ)
1. এই ফোল্ডারটা GitHub-এ একটা নতুন repo হিসেবে push করুন
2. railway.app → New Project → Deploy from GitHub repo
3. Variables ট্যাবে যোগ করুন:
   - `API_ID` (my.telegram.org থেকে)
   - `API_HASH`
   - `BOT_TOKEN`
4. Deploy — ব্যস। লগে `bot starting...` দেখলেই চালু।

Render / Fly.io / VPS-এও একই — Dockerfile আছে, সরাসরি বিল্ড হবে।

## ৩. ব্যবহার
বটে যেকোনো ভিডিও লিংক পাঠান → নামিয়ে ফেরত পাঠাবে।

## কেন ক্র্যাশ করবে না
- প্রতিটা জব আলাদা টেম্প ফোল্ডারে, শেষে `finally` ব্লকে **সবসময়** ডিলিট
- ডিস্কে ১.৫ GB ফাঁকা না থাকলে ডাউনলোড শুরুই হয় না
- ১ ঘণ্টার পুরোনো আটকে থাকা ফাইল অটো-ক্লিন
- একসাথে সর্বোচ্চ ২টা ডাউনলোড (RAM/CPU সেফ)
- ডাউনলোড থ্রেডে চলে, তাই বট হ্যাং করে না
- FloodWait সহ সব এরর ধরা, বট বন্ধ হয় না

## নোট
- সর্বোচ্চ ২ GB (Telegram লিমিট)
- YouTube-এ login লাগলে `cookies.txt` রেখে `COOKIES_FILE=/app/cookies.txt` সেট করুন
