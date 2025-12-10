import os
import logging
from typing import List, Tuple
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.database import Database
from core.config_manager import ConfigManager

logger = logging.getLogger("utils.ai")

class AI:
    _embeddings = None
    _llm = None

    @classmethod
    def init(cls):
        if cls._embeddings is None:
            cls._embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=os.getenv("OPENAI_API_KEY")
            )
        if cls._llm is None:
            cls._llm = ChatOpenAI(
                model="gpt-4o-mini", # Fallback as requested, gpt-5-mini not avail public yet usually
                temperature=1,
                api_key=os.getenv("OPENAI_API_KEY")
            )

    @classmethod
    async def get_embedding(cls, text: str) -> List[float]:
        cls.init()
        # embed_query is synchronous in LangChain usually, might need to run in executor if blocking
        # but for small text it's fast. For async safe:
        return await cls._embeddings.aembed_query(text)

    @classmethod
    async def translate_to_english(cls, text: str) -> str:
        """Translates the user query to English for better database retrieval."""
        cls.init()
        # Explicitly mention Filipino/Tagalog context to avoid confusion with Spanish (e.g., 'ano')
        system_prompt = (
            "You are a translator for a Filipino gaming community. "
            "Translate the following Project Zomboid related query to English. "
            "The input is likely in Tagalog, English, or Taglish. "
            "Return ONLY the English translation."
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{text}")
        ])
        chain = prompt | cls._llm | StrOutputParser()
        return await chain.ainvoke({"text": text})

    @classmethod
    async def search_knowledge_base(cls, text: str, threshold: float = 0.5) -> List[dict]:
        """
        Retrieves top chunks from the database using vector similarity.
        """
        cls.init()
        query_vec = await cls.get_embedding(text)
        
        # pgvector syntax: <=> is cosine distance. 1 - distance = similarity.
        # We want similarity > threshold.
        # ORDER BY distance ASC (closest first)
        
        query = """
            SELECT id, topic, content, metadata, 1 - (embedding <=> $1) as similarity
            FROM pinya_docs
            WHERE 1 - (embedding <=> $1) > $2
            ORDER BY similarity DESC
            LIMIT 3
        """
        
        vec_str = str(query_vec)
        
        rows = await Database.fetch(query, vec_str, threshold)
        return [dict(row) for row in rows]

    @classmethod
    async def generate_answer(cls, question: str, context_chunks: List[dict]) -> str:
        cls.init()
        
        # Build context string or indicate it's missing
        if context_chunks:
            context_text = "\n\n".join([f"Topic: {c['topic']}\nContent: {c['content']}" for c in context_chunks])
            instruction_mode = "Use the provided context to answer."
        else:
            context_text = "No database context available."
            instruction_mode = "Use your general knowledge about Project Zomboid to answer."

        system_prompt = f"""You are PinyaBot, a helpful assistant for a Project Zomboid server.
        
        Task:
        1. {instruction_mode}
        2. LANGUAGE MATCHING (STRICT):
           - **Output Language Rule:** MIRROR the language of the "User's Question".
           - User: "What is the IP?" (English) -> Reply in English.
           - User: "ano ip?" (Tagalog) -> Reply in Tagalog/Taglish.
           - **Override:** Do NOT be influenced by the language of the Context. The User's language dictates the reply language.
        3. ANSWERING STRATEGY:
           - **Prioritize the Context.** If the Context contains ANY relevant information, use it to answer, even if it's partial.
           - If Context is missing or irrelevant, use General Knowledge (must be ~60% confident).
           - **Refusal:** Only reply "I don't know that yet" if the Context is completely useless AND you don't know the answer from general knowledge.
        4. FORMATTING & STYLE (RAW MARKDOWN):
           - **Target Display:** Discord Embed Description.
           - **Syntax Rules (Use these characters):**
             - Bold: `**text**` (NOT "BOLD: text")
             - Italics: `*text*`
             - Code: `` `text` `` (Inline) or ```block``` (Multi-line)
             - Lists: `- Item` or `1. Item`
             - Hyperlinks: `[Link Text](URL)` (e.g., `[Map](https://map.projectzomboid.com)`)
             - Blockquotes: `> Text` (Use for tips or emphasized notes)
             - Spoilers: `||Hidden Text||` (Use for secrets)
           - **Bad Examples (DO NOT USE):**
             - ❌ BOLD: The IP is...
             - ❌ [Bold] The IP is...
             - ❌ Raw URLs like https://google.com (Always use named links)
           - **Headers:** Use `## Title` or `**TITLE**` (Do not use `# Title`).
           - **Key Info:** Always bold important locations/items (e.g., **Riverside**, **Hammer**).
           - Keep paragraphs short (2-3 lines max).
        """
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Context:\n{context}\n\nUser's Question: {question}")
        ])
        
        chain = prompt | cls._llm | StrOutputParser()
        
        response = await chain.ainvoke({"context": context_text, "question": question})
        return response

    @classmethod
    async def check_duplicate(cls, text: str, threshold=0.9) -> bool:
        """Checks if a similar topic already exists."""
        results = await cls.search_knowledge_base(text, threshold)
        return len(results) > 0
