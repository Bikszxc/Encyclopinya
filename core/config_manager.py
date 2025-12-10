import logging
import discord
from discord import app_commands
from core.database import Database

logger = logging.getLogger("core.config")

class ConfigManager:
    _cache = {}

    @classmethod
    async def load_cache(cls):
        """Loads all config into memory on startup."""
        rows = await Database.fetch("SELECT key, value FROM config")
        cls._cache = {row['key']: row['value'] for row in rows}
        logger.info(f"Config loaded: {len(cls._cache)} keys.")

    @classmethod
    async def get(cls, key: str, default=None):
        return cls._cache.get(key, default)

    @classmethod
    async def set(cls, key: str, value: str):
        await Database.execute(
            "INSERT INTO config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
            key, str(value)
        )
        cls._cache[key] = str(value)
        logger.info(f"Config updated: {key} = {value}")

    @classmethod
    async def delete(cls, key: str):
        await Database.execute("DELETE FROM config WHERE key = $1", key)
        if key in cls._cache:
            del cls._cache[key]

# Decorator for Role-based access control
def is_configured_role(role_type: str):
    """
    Checks if the user has the role configured in the database for 'role_type'.
    Example usage: @is_configured_role('librarian')
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        role_id_str = await ConfigManager.get(f"role_{role_type}")
        
        if not role_id_str:
            await interaction.response.send_message(
                f"❌ The `{role_type}` role has not been configured yet. Ask an admin to run `/admin config role`.",
                ephemeral=True
            )
            return False

        try:
            role_id = int(role_id_str)
        except ValueError:
             await interaction.response.send_message(
                f"❌ Configuration error: `{role_type}` role ID is invalid.",
                ephemeral=True
            )
             return False

        user_roles = [r.id for r in interaction.user.roles]
        if role_id in user_roles:
            return True
        else:
            await interaction.response.send_message(
                f"⛔ You need the <@&{role_id}> role to use this command.",
                ephemeral=True
            )
            return False

    return app_commands.check(predicate)
