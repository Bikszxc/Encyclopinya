import discord
import logging
import re
import json
from discord.ext import commands
from core.database import Database
from core.config_manager import ConfigManager
from utils.ai import AI
from utils.ui import VoteView, TeachGapView, Colors

logger = logging.getLogger("cogs.query")

class Query(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def replace_aliases(self, text: str) -> str:
        """Replaces known aliases in the text."""
        # This should ideally be cached for performance
        rows = await Database.fetch("SELECT trigger, replacement FROM aliases")
        for row in rows:
            text = re.sub(r'\b' + re.escape(row['trigger']) + r'\b', row['replacement'], text, flags=re.IGNORECASE)
        return text

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Check if bot is mentioned
        if self.bot.user in message.mentions:
            # We want to process this.
            # Remove the mention from the content
            content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            # Also handle nickname mention if any
            content = content.replace(f"<@!{self.bot.user.id}>", "").strip()
            
            if not content:
                return

            # --- Permission Checks ---
            
            # 1. Global Toggle
            global_enabled = await ConfigManager.get("global_reply_enabled", "true")
            if global_enabled == "false":
                # Optional: Allow admins to bypass? For now, strict toggle.
                return

            # 2. Role Whitelist
            allowed_roles_raw = await ConfigManager.get("allowed_roles", "")
            if allowed_roles_raw:
                allowed_ids = allowed_roles_raw.split(",")
                user_role_ids = [str(r.id) for r in message.author.roles]
                
                # Check intersection
                has_allowed_role = any(rid in allowed_ids for rid in user_role_ids)
                if not has_allowed_role:
                    return
            
            # -------------------------

            # Show typing to indicate processing
            async with message.channel.typing():
                # 1. Preprocessing
                query_text = await self.replace_aliases(content)

                # 2. Get Config
                threshold_str = await ConfigManager.get("ai_threshold", "0.5")
                threshold = float(threshold_str)

                # 3. Search
                # Translation Layer: Tagalog Query -> English Query
                english_query = await AI.translate_to_english(query_text)
                
                # Search using the English query
                results = await AI.search_knowledge_base(english_query, threshold)

                # 4. Logic
                if not results:
                    # Low confidence / No results -> Log gap but attempt general answer
                    gaps_channel_id = await ConfigManager.get("channel_knowledge_gaps")
                    if gaps_channel_id:
                        channel = self.bot.get_channel(int(gaps_channel_id))
                        if channel:
                            embed = discord.Embed(
                                title="Knowledge Gap Detected",
                                description=f"**Query:** {query_text}\n**User:** {message.author.mention}\n*Attempting fallback answer...*",
                                color=Colors.WARNING
                            )
                            
                            # Add Teach Button
                            knowledge_cog = self.bot.get_cog('Knowledge')
                            view = None
                            if knowledge_cog:
                                view = TeachGapView(query_text, knowledge_cog)
                            
                            await channel.send(embed=embed, view=view)
                    
                    # Proceed to generate answer with empty context
                    pass

                # 5. Generate Answer
                answer = await AI.generate_answer(query_text, results)

                # 6. Map Formatting (Regex for coords like 1234x5678)
                # Simple example: bold them
                answer = re.sub(r'(\d{4,5}x\d{4,5})', r'**\1**', answer)

                # 7. Send Response
                # We attach the VoteView to the first result's ID for tracking (simplification)
                view = None
                confidence_text = "General Knowledge"
                confidence_color = "⚪" # Grey circle for general knowledge
                contributor_name = None
                contributor_icon = None
                
                if results:
                    top_result = results[0]
                    doc_id = top_result['id']
                    view = VoteView(doc_id)
                    
                    # Calculate confidence percentage
                    similarity = top_result.get('similarity', 0)
                    score = int(similarity * 100)
                    
                    # Adjusted thresholds for text-embedding-3-small (0.4-0.6 is typical for strong matches)
                    if score >= 45:
                        confidence_color = "🟢"
                        confidence_text = "High Confidence"
                    elif score >= 30:
                        confidence_color = "🟡"
                        confidence_text = "Medium Confidence"
                    else:
                        confidence_color = "🔴"
                        confidence_text = "Low Confidence"

                    # Extract Author Info
                    try:
                        meta = top_result.get('metadata', {})
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        
                        author_id = meta.get('author_id')
                        if author_id:
                            author = self.bot.get_user(author_id)
                            if not author:
                                try:
                                    author = await self.bot.fetch_user(author_id)
                                except:
                                    pass
                            
                            if author:
                                contributor_name = author.display_name
                                contributor_icon = author.display_avatar.url
                    except Exception as e:
                        logger.error(f"Error extracting author info: {e}")
                
                embed = discord.Embed(description=answer, color=Colors.AI_ANSWER)
                
                footer_text = f"{confidence_color} {confidence_text}"
                if contributor_name:
                    footer_text += f" • Contributed by {contributor_name}"
                
                if contributor_icon:
                    embed.set_footer(text=footer_text, icon_url=contributor_icon)
                else:
                    embed.set_footer(text=footer_text)
                    
                await message.reply(embed=embed, view=view, mention_author=False)

async def setup(bot):
    await bot.add_cog(Query(bot))