import os
import discord
import logging
import asyncio
from discord.ext import commands
from dotenv import load_dotenv
from core.database import Database
from core.config_manager import ConfigManager

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")

load_dotenv()

class PinyaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True # Required for mention listener
        self.current_avatar_state = None
        
        super().__init__(
            command_prefix="!", # Not used for slash commands really
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # Connect to Database
        await Database.connect()
        
        # Load Config Cache
        await ConfigManager.load_cache()

        # Load Extensions
        initial_extensions = [
            'cogs.admin',
            'cogs.knowledge',
            'cogs.query'
        ]

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"Loaded extension: {ext}")
            except Exception as e:
                logger.error(f"Failed to load extension {ext}: {e}")

        # Sync Slash Commands
        # In production, you might want to sync only to a guild for faster updates
        # await self.tree.sync(guild=discord.Object(id=YOUR_GUILD_ID)) 
        # For global sync:
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands.")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user} (ID: {self.user.id})')
        await self.update_status()
        logger.info('------')

    async def update_avatar(self, state: str, retry_delay: int = 0):
        """Updates the bot avatar if a matching file exists in assets/."""
        # Avoid redundant API calls (Discord has strict rate limits for avatar changes)
        if self.current_avatar_state == state:
            return
            
        if retry_delay > 600: # Give up after 10 minutes of backoff
            logger.error(f"❌ Gave up updating avatar to {state} after repeated failures.")
            return

        if retry_delay > 0:
             await asyncio.sleep(retry_delay)

        file_path = f"assets/{state}.png"
        if not os.path.exists(file_path):
            return

        try:
            with open(file_path, "rb") as f:
                avatar_bytes = f.read()
            await self.user.edit(avatar=avatar_bytes)
            self.current_avatar_state = state
            logger.info(f"✅ Avatar updated to state: {state}")
            
        except discord.HTTPException as e:
            if e.code == 50035 or e.status == 429: # Invalid Form Body (too fast) or Rate Limit
                new_delay = max(300, retry_delay * 2) if retry_delay else 300 # Start with 5 mins
                logger.warning(f"⚠️ Rate limited on avatar change. Retrying in {new_delay}s...")
                self.loop.create_task(self.update_avatar(state, new_delay))
            else:
                logger.error(f"❌ Failed to update avatar: {e}")
        except Exception as e:
            logger.error(f"❌ Error updating avatar: {e}")

    async def update_status(self):
        """Updates the bot's status based on current configuration."""
        global_enabled = await ConfigManager.get("global_reply_enabled", "true")
        allowed_roles = await ConfigManager.get("allowed_roles", "")
        
        if global_enabled == "false":
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.Game(name="Sleeping 💤 (Replies Off)")
            )
            await self.update_avatar("sleeping")
        elif allowed_roles:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name="Helping specific roles 🔒")
            )
            await self.update_avatar("locked")
        else:
            await self.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name="Ask me via @Encyclopinya")
            )
            await self.update_avatar("online")

    async def close(self):
        await Database.close()
        await super().close()

async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token or token == "your_discord_token_here":
        logger.error("DISCORD_TOKEN is not set in .env")
        return

    bot = PinyaBot()
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Handle graceful shutdown on Ctrl+C
        pass
