import discord
from discord import app_commands
from discord.ext import commands
from core.config_manager import ConfigManager

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    admin_group = app_commands.Group(name="admin", description="Administration commands")
    config_group = app_commands.Group(parent=admin_group, name="config", description="Configure bot settings")

    @config_group.command(name="role", description="Set a role for a specific permission level")
    @app_commands.choices(role_type=[
        app_commands.Choice(name="Librarian (Can teach)", value="librarian"),
        app_commands.Choice(name="Manager (Can config)", value="manager")
    ])
    @app_commands.default_permissions(administrator=True)
    async def config_role(self, interaction: discord.Interaction, role_type: app_commands.Choice[str], role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        await ConfigManager.set(f"role_{role_type.value}", str(role.id))
        await interaction.followup.send(
            f"✅ Configured `{role_type.name}` role to {role.mention}"
        )

    @config_group.command(name="channel", description="Set a channel for logs or gaps")
    @app_commands.choices(channel_type=[
        app_commands.Choice(name="Audit Log", value="audit_log"),
        app_commands.Choice(name="Knowledge Gaps", value="knowledge_gaps")
    ])
    @app_commands.default_permissions(administrator=True)
    async def config_channel(self, interaction: discord.Interaction, channel_type: app_commands.Choice[str], channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        await ConfigManager.set(f"channel_{channel_type.value}", str(channel.id))
        await interaction.followup.send(
            f"✅ Configured `{channel_type.name}` channel to {channel.mention}"
        )

    @config_group.command(name="threshold", description="Set the AI confidence threshold")
    @app_commands.describe(value="Value between 0.1 and 1.0")
    @app_commands.default_permissions(administrator=True)
    async def config_threshold(self, interaction: discord.Interaction, value: float):
        await interaction.response.defer(ephemeral=True)
        if not 0.1 <= value <= 1.0:
            await interaction.followup.send("❌ Value must be between 0.1 and 1.0", ephemeral=True)
            return
        
        await ConfigManager.set("ai_threshold", str(value))
        await interaction.followup.send(
            f"✅ AI Confidence Threshold set to `{value}`"
        )

    @config_group.command(name="reply_global", description="Toggle whether the bot replies to anyone")
    @app_commands.default_permissions(administrator=True)
    async def config_reply_global(self, interaction: discord.Interaction, enabled: bool):
        await interaction.response.defer(ephemeral=True)
        await ConfigManager.set("global_reply_enabled", str(enabled).lower())
        status = "enabled" if enabled else "disabled"
        await self.bot.update_status()
        await interaction.followup.send(f"✅ Bot replies have been **{status}**.")

    @config_group.command(name="reply_role", description="Manage roles allowed to interact with the bot (Optional whitelist)")
    @app_commands.choices(action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
        app_commands.Choice(name="Clear All", value="clear")
    ])
    @app_commands.default_permissions(administrator=True)
    async def config_reply_role(self, interaction: discord.Interaction, action: app_commands.Choice[str], role: discord.Role = None):
        await interaction.response.defer(ephemeral=True)
        if action.value in ["add", "remove"] and not role:
            await interaction.followup.send("❌ You must specify a role for Add/Remove.", ephemeral=True)
            return

        current_raw = await ConfigManager.get("allowed_roles", "")
        current_list = current_raw.split(",") if current_raw else []
        current_list = [x for x in current_list if x] # Clean empty strings

        if action.value == "add":
            if str(role.id) not in current_list:
                current_list.append(str(role.id))
                await ConfigManager.set("allowed_roles", ",".join(current_list))
                await self.bot.update_status()
                await interaction.followup.send(f"✅ Added {role.mention} to allowed roles.")
            else:
                await interaction.followup.send(f"⚠️ {role.mention} is already in the list.", ephemeral=True)

        elif action.value == "remove":
            if str(role.id) in current_list:
                current_list.remove(str(role.id))
                await ConfigManager.set("allowed_roles", ",".join(current_list))
                await self.bot.update_status()
                await interaction.followup.send(f"✅ Removed {role.mention} from allowed roles.")
            else:
                await interaction.followup.send(f"⚠️ {role.mention} was not in the list.", ephemeral=True)

        elif action.value == "clear":
            await ConfigManager.set("allowed_roles", "")
            await self.bot.update_status()
            await interaction.followup.send("✅ Cleared all allowed roles. Bot is now open to everyone (unless global toggled off).")

    @admin_group.command(name="sync", description="Sync application commands")
    @app_commands.default_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"✅ Synced {len(synced)} commands.")
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}")

    # Maintenance Group
    maintenance_group = app_commands.Group(parent=admin_group, name="maintenance", description="Database maintenance tasks")

    @maintenance_group.command(name="reindex", description="Regenerate all embeddings (Use after changing AI models)")
    @app_commands.default_permissions(administrator=True)
    async def reindex(self, interaction: discord.Interaction):
        from utils.ai import AI
        from core.database import Database
        import asyncio

        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("🔄 Starting Re-indexing... This may take a while.", ephemeral=True)

        try:
            # Fetch all docs
            docs = await Database.fetch("SELECT id, topic, content FROM pinya_docs")
            total = len(docs)
            updated = 0
            
            if total == 0:
                await interaction.followup.send("⚠️ Database is empty. Nothing to re-index.", ephemeral=True)
                return

            # Process in chunks or one by one
            for i, doc in enumerate(docs):
                text_to_embed = f"Topic: {doc['topic']}\nContent: {doc['content']}"
                new_embedding = await AI.get_embedding(text_to_embed)
                vec_str = str(new_embedding)
                
                await Database.execute(
                    "UPDATE pinya_docs SET embedding = $1 WHERE id = $2",
                    vec_str, doc['id']
                )
                updated += 1
                
                # Log progress every 10 items
                if updated % 10 == 0:
                   await interaction.edit_original_response(content=f"🔄 Re-indexing... ({updated}/{total})")

            await interaction.followup.send(f"✅ Re-indexing complete! Updated {updated}/{total} documents.", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Re-indexing failed: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
