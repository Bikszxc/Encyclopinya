import discord
import logging
from discord import app_commands
from discord.ext import commands
from core.database import Database
from core.config_manager import is_configured_role, ConfigManager
from utils.ui import TeachModal, Colors
from utils.ai import AI

logger = logging.getLogger("cogs.knowledge")

class Knowledge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_audit(self, title: str, description: str, user: discord.User):
        """Sends an embed to the configured audit log channel."""
        channel_id = await ConfigManager.get("channel_audit_log")
        if not channel_id:
            return

        channel = self.bot.get_channel(int(channel_id))
        if not channel:
            return

        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.set_footer(text=f"User ID: {user.id}")
        await channel.send(embed=embed)

    async def topic_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """
        Real-time autocomplete for topics.
        """
        if not current:
            query = "SELECT topic FROM pinya_docs ORDER BY created_at DESC LIMIT 25"
            rows = await Database.fetch(query)
        else:
            query = "SELECT topic FROM pinya_docs WHERE topic ILIKE $1 LIMIT 25"
            rows = await Database.fetch(query, f"%{current}%")
        
        return [app_commands.Choice(name=row['topic'], value=row['topic']) for row in rows]

    @app_commands.command(name="teach", description="Add new knowledge to the bot")
    @is_configured_role('librarian')
    async def teach(self, interaction: discord.Interaction):
        modal = TeachModal(self.save_knowledge)
        await interaction.response.send_modal(modal)

    async def upsert_knowledge(self, topic: str, content: str, spoiler: str, user: discord.User, doc_id: int = None, check_dup: bool = True):
        """Internal logic to save/update knowledge. Returns (doc_id, error_message)."""
        try:
            # Check for duplicates ONLY if it's a new entry (doc_id is None) and check_dup is True
            if doc_id is None and check_dup:
                is_dup = await AI.check_duplicate(f"{topic} {content}")
                if is_dup:
                    return None, "⚠️ This content seems very similar to existing knowledge. Consider using `/edit` instead."

            # Generate embedding
            text_to_embed = f"Topic: {topic}\nContent: {content}"
            embedding = await AI.get_embedding(text_to_embed)
            vec_str = str(embedding)

            import json
            metadata = {
                "votes": 0,
                "flags": 0,
                "is_spoiler": spoiler.lower() in ['yes', 'y', 'true'],
                "author_id": user.id
            }

            if doc_id:
                # Update existing
                # We need to preserve existing metadata (like votes) but update author? 
                # Or usually edits shouldn't reset votes? 
                # The prompt implies we just want to credit the contributor.
                # If we use || it merges. But we are defining a new metadata dict here.
                # If we want to keep votes, we should probably fetch first or use jsonb_set.
                # But the current implementation replaces metadata completely or merges?
                # The SQL uses: metadata = metadata || $4::jsonb
                # So it merges. New keys overwrite old keys.
                # "votes" is in our new dict as 0. This will RESET votes on edit!
                # We should remove "votes" and "flags" from the update dict to avoid resetting them.
                
                update_meta = {
                    "is_spoiler": spoiler.lower() in ['yes', 'y', 'true'],
                    "last_editor_id": user.id
                }
                # For the initial author, we might not want to overwrite if it exists?
                # But for now let's just add author_id to insert.
                
                await Database.execute(
                    """
                    UPDATE pinya_docs 
                    SET topic = $1, content = $2, embedding = $3, metadata = metadata || $4::jsonb
                    WHERE id = $5
                    """,
                    topic, content, vec_str, json.dumps(update_meta), doc_id
                )
                action = "Updated"
                final_id = doc_id
            else:
                # Insert new and get ID
                final_id = await Database.fetchval(
                    """
                    INSERT INTO pinya_docs (topic, content, embedding, metadata)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    topic, content, vec_str, json.dumps(metadata)
                )
                action = "Added"

            # Audit Log
            await self.log_audit(f"Knowledge {action}", f"**Topic:** {topic}\n**Content Length:** {len(content)} chars", user)
            
            return final_id, None

        except Exception as e:
            logger.exception("Error in upsert_knowledge")
            return None, f"An error occurred while saving: {e}"

    async def save_knowledge(self, inter: discord.Interaction, topic: str, content: str, spoiler: str, doc_id: int = None):
        """Shared callback for saving knowledge (Teach & Edit) with UI response."""
        # Interaction is deferred in TeachModal.on_submit
        
        final_id, error = await self.upsert_knowledge(topic, content, spoiler, inter.user, doc_id)
        
        if error:
            await inter.followup.send(error, ephemeral=True)
            return

        action = "Updated" if doc_id else "Added"
        embed = discord.Embed(title=f"Knowledge {action}", description=f"**Topic:** {topic}", color=Colors.SUCCESS)
        await inter.followup.send(embed=embed, ephemeral=True)

    async def open_edit_modal(self, interaction: discord.Interaction, doc_id: int):
        # Fetch the existing doc
        doc = await Database.fetchrow("SELECT id, topic, content, metadata FROM pinya_docs WHERE id = $1", doc_id)
        
        if not doc:
            await interaction.response.send_message(f"❌ Document ID `{doc_id}` not found.", ephemeral=True)
            return

        # Prepare defaults
        import json
        is_spoiler = "no"
        meta = doc['metadata']
        if isinstance(meta, str):
             m = json.loads(meta)
             if m.get('is_spoiler'): is_spoiler = "yes"
        elif isinstance(meta, dict):
             if meta.get('is_spoiler'): is_spoiler = "yes"
        
        # Create a closure for the callback to capture doc['id']
        async def edit_callback(inter, t, c, s):
            await self.save_knowledge(inter, t, c, s, doc_id=doc['id'])

        modal = TeachModal(edit_callback, default_topic=doc['topic'], default_content=doc['content'], default_spoiler=is_spoiler)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="alias", description="Add or update a search alias")
    @is_configured_role('librarian')
    async def alias(self, interaction: discord.Interaction, trigger: str, replacement: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await Database.execute(
                """
                INSERT INTO aliases (trigger, replacement) VALUES ($1, $2)
                ON CONFLICT (trigger) DO UPDATE SET replacement = $2
                """,
                trigger, replacement
            )
            await interaction.followup.send(f"✅ Alias set: `{trigger}` -> `{replacement}`")
            
            # Audit Log
            await self.log_audit("Alias Updated", f"**Trigger:** {trigger}\n**Replacement:** {replacement}", interaction.user)
            
        except Exception as e:
            logger.exception("Error setting alias")
            await interaction.followup.send(f"❌ Error setting alias: {e}")

    @app_commands.command(name="forget", description="Remove knowledge from the bot")
    @is_configured_role('librarian')
    @app_commands.autocomplete(topic=topic_autocomplete)
    async def forget(self, interaction: discord.Interaction, topic: str):
        await interaction.response.defer(ephemeral=True)
        
        # Check if exists
        exists = await Database.fetchval("SELECT id FROM pinya_docs WHERE topic = $1", topic)
        if not exists:
            await interaction.followup.send(f"❌ Topic `{topic}` not found.", ephemeral=True)
            return

        await Database.execute("DELETE FROM pinya_docs WHERE topic = $1", topic)
        await interaction.followup.send(f"🗑️ Forgot everything about `{topic}`.", delete_after=10)
        
        # Audit Log
        await self.log_audit("Knowledge Deleted", f"**Topic:** {topic}", interaction.user)

    @app_commands.command(name="edit", description="Update existing knowledge")
    @is_configured_role('librarian')
    @app_commands.autocomplete(topic=topic_autocomplete)
    async def edit(self, interaction: discord.Interaction, topic: str):
        # Fetch ID from topic
        doc_id = await Database.fetchval("SELECT id FROM pinya_docs WHERE topic = $1", topic)
        if not doc_id:
            await interaction.response.send_message(f"❌ Topic `{topic}` not found.", ephemeral=True)
            return
            
        await self.open_edit_modal(interaction, doc_id)

def import_json_safe(data):
    import json
    if isinstance(data, str):
        return json.loads(data)
    return data


async def setup(bot):
    await bot.add_cog(Knowledge(bot))