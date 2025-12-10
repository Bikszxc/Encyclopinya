import discord
from discord import ui

# --- Colors ---
class Colors:
    SUCCESS = 0x57F287
    ERROR = 0xED4245
    WARNING = 0xFEE75C
    AI_ANSWER = 0x5865F2

# --- UI Components ---

class VoteView(ui.View):
    def __init__(self, doc_id: int):
        super().__init__(timeout=None) # Persistent view
        self.doc_id = doc_id

    @ui.button(label="Helpful", style=discord.ButtonStyle.success, emoji="👍", custom_id="vote_helpful")
    async def helpful(self, interaction: discord.Interaction, button: ui.Button):
        # Update button state
        button.label = "Voted"
        button.disabled = True
        self.children[1].disabled = True # Disable 'Wrong' button too
        
        await interaction.response.edit_message(view=self)
        
        # In a real app, you would call the database to log the vote
        # await Database.execute("UPDATE pinya_docs SET metadata = jsonb_set(metadata, '{votes}', (COALESCE(metadata->>'votes','0')::int + 1)::text::jsonb) WHERE id = $1", self.doc_id)
        
        # For now, just logging or a placeholder since Database import might cause circular dependency if not careful
        # We will handle the database logic in the Cog or inject a callback.
        # But for simplicity, we'll just acknowledge.
        # Ideally, this view should be created with a callback or reference to the DB logic.
        pass

    @ui.button(label="Wrong", style=discord.ButtonStyle.danger, emoji="👎", custom_id="vote_wrong")
    async def wrong(self, interaction: discord.Interaction, button: ui.Button):
         # Update button state
        button.label = "Flagged"
        button.disabled = True
        self.children[0].disabled = True
        
        await interaction.response.edit_message(view=self)
        # Logic for flagging would go here.

class TeachModal(ui.Modal, title="Teach PinyaBot"):
    topic = ui.TextInput(label="Topic", placeholder="e.g., How to fish", required=True, max_length=100)
    content = ui.TextInput(label="Content", placeholder="Detailed explanation...", style=discord.TextStyle.paragraph, required=True)
    spoiler = ui.TextInput(label="Spoiler? (yes/no)", placeholder="no", required=False, max_length=3)

    def __init__(self, callback_func, default_topic=None, default_content=None, default_spoiler="no"):
        super().__init__()
        self.callback_func = callback_func
        if default_topic:
            self.topic.default = default_topic
        if default_content:
            self.content.default = default_content
        self.spoiler.default = default_spoiler

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.callback_func(interaction, self.topic.value, self.content.value, self.spoiler.value)

class EditGapView(ui.View):
    def __init__(self, doc_id, knowledge_cog):
        super().__init__(timeout=None)
        self.doc_id = doc_id
        self.knowledge_cog = knowledge_cog
        
    @ui.button(label="Edit", style=discord.ButtonStyle.secondary, emoji="✏️")
    async def edit(self, interaction: discord.Interaction, button: ui.Button):
         await self.knowledge_cog.open_edit_modal(interaction, self.doc_id)

class TeachGapView(ui.View):
    def __init__(self, missing_query: str, knowledge_cog):
        super().__init__(timeout=None)
        self.missing_query = missing_query
        self.knowledge_cog = knowledge_cog

    @ui.button(label="Teach This", style=discord.ButtonStyle.primary, emoji="🧠")
    async def teach(self, interaction: discord.Interaction, button: ui.Button):
        origin_message = interaction.message
        
        async def callback(inter, topic, content, spoiler):
             # 1. Upsert via cog
             doc_id, error = await self.knowledge_cog.upsert_knowledge(topic, content, spoiler, user=inter.user)
             
             if error:
                 await inter.followup.send(error, ephemeral=True)
                 return

             # 2. Update origin message
             if origin_message and origin_message.embeds:
                 embed = origin_message.embeds[0]
                 embed.title = "Knowledge Gap Resolved"
                 embed.color = Colors.SUCCESS
                 embed.set_footer(text=f"Taught by {inter.user.display_name}")
                 
                 # 3. Create view with Edit button
                 new_view = EditGapView(doc_id, self.knowledge_cog)
                 await origin_message.edit(embed=embed, view=new_view)
             
             # 4. Acknowledge the modal interaction
             await inter.followup.send("✅ Saved.", ephemeral=True)

        # Open TeachModal pre-filled with the missing query
        modal = TeachModal(callback, default_topic=self.missing_query)
        await interaction.response.send_modal(modal)

class ConfirmView(ui.View):
    def __init__(self):
        super().__init__()
        self.value = None

    @ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()
