from __future__ import annotations

import re

import streamlit as st

from src.youtube_rag import config
from src.youtube_rag.search_engine import ask_question

st.set_page_config(page_title="YouTube Knowledge Base", page_icon="📚", layout="wide")


def t(lang: str, en: str, zh: str) -> str:
    return en if lang == "English" else zh


def format_seconds(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def link_source_citations(answer_text: str, sources: list[dict]) -> str:
    def replace(match: re.Match[str]) -> str:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(sources):
            url = sources[idx].get("timestamp_url", "")
            if url:
                return f"[[Source {idx + 1}]]({url})"
        return match.group(0)

    return re.sub(r"\[Source\s+(\d+)\]", replace, answer_text)


def apply_model_selection(provider: str, model: str) -> None:
    config.LLM_PROVIDER = provider
    if provider == "openai":
        config.OPENAI_MODEL = model
    elif provider == "groq":
        config.GROQ_MODEL = model
    else:
        config.OLLAMA_MODEL = model


def render_sources(sources: list[dict], lang: str, show_embed_video: bool) -> None:
    with st.expander(t(lang, "Sources", "来源"), expanded=False):
        if not sources:
            st.write(t(lang, "No sources returned.", "没有返回来源。"))
            return

        for idx, src in enumerate(sources, start=1):
            title = src.get("title") or t(lang, "Untitled", "无标题")
            start_sec = float(src.get("start_sec", 0.0))
            end_sec = float(src.get("end_sec", start_sec))
            timestamp_url = src.get("timestamp_url") or ""
            youtube_url = src.get("youtube_url") or ""
            snippet = src.get("chunk_text") or ""

            with st.container(border=True):
                st.markdown(f"**{idx}. {title}**")
                st.markdown(
                    f"{t(lang, 'Time', '时间')}: `{format_seconds(start_sec)} → {format_seconds(end_sec)}`"
                )
                if timestamp_url:
                    st.markdown(
                        f"[{t(lang, 'Open at timestamp', '打开时间戳')}]({timestamp_url})"
                    )
                if snippet:
                    st.caption(snippet)
                if show_embed_video and youtube_url:
                    st.video(youtube_url, start_time=int(start_sec))


def append_and_render_assistant(
    query: str,
    lang: str,
    top_k: int,
    provider: str,
    model: str,
    show_debug_chunks: bool,
    show_embed_video: bool,
) -> None:
    st.session_state.chat_history.append({"role": "user", "content": query})

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner(t(lang, "Searching and generating grounded answer...", "正在检索并生成有依据的回答...")):
            try:
                apply_model_selection(provider=provider, model=model)
                result = ask_question(query=query, top_k=top_k)
            except Exception as exc:
                st.error(f"{t(lang, 'Backend error', '后端错误')}: {exc}")
                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "content": f"❌ {t(lang, 'Backend error', '后端错误')}: {exc}",
                        "sources": [],
                    }
                )
                return

            answer_text = result.get("answer_text", "")
            sources = result.get("sources", [])
            rendered_answer = link_source_citations(answer_text, sources)

            st.markdown(rendered_answer)
            render_sources(sources=sources, lang=lang, show_embed_video=show_embed_video)

            if show_debug_chunks:
                st.markdown(f"**{t(lang, 'Debug: Retrieved Chunks', '调试：检索到的分块')}**")
                st.json(sources)

            st.session_state.chat_history.append(
                {
                    "role": "assistant",
                    "content": answer_text,
                    "sources": sources,
                }
            )


if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "hero_query" not in st.session_state:
    st.session_state.hero_query = ""

header_left, header_right = st.columns([6, 1])
with header_left:
    st.title("YouTube Knowledge Base")
    st.caption("政经鲁社长频道知识库")
with header_right:
    language = st.selectbox("Language", options=["English", "中文"], index=0, label_visibility="collapsed")

with st.sidebar:
    st.header(t(language, "Settings", "设置"))
    top_k = st.slider(t(language, "Top-K Retrieval", "Top-K检索"), min_value=1, max_value=15, value=5, step=1)
    show_debug_chunks = st.toggle(t(language, "Show top retrieved chunks", "显示检索到的Top分块"), value=False)
    show_embed_video = st.toggle(t(language, "Show embedded video", "显示内嵌视频"), value=False)

    provider_options = ["openai", "groq", "ollama"]
    default_provider = config.LLM_PROVIDER if config.LLM_PROVIDER in provider_options else "openai"
    provider = st.selectbox(t(language, "Provider", "模型提供方"), provider_options, index=provider_options.index(default_provider))

    if provider == "openai":
        model = st.text_input(t(language, "Model", "模型"), value=config.OPENAI_MODEL)
    elif provider == "groq":
        model = st.text_input(t(language, "Model", "模型"), value=config.GROQ_MODEL)
    else:
        model = st.text_input(t(language, "Model", "模型"), value=config.OLLAMA_MODEL)

st.markdown(f"### {t(language, 'Search the channel knowledge', '搜索频道知识库')}")
search_col, button_col = st.columns([7, 1])
with search_col:
    st.session_state.hero_query = st.text_input(
        t(language, "Ask a grounded question", "提出一个有依据的问题"),
        value=st.session_state.hero_query,
        placeholder=t(
            language,
            "e.g. How does Lu Shezhang evaluate Bo Guagua?",
            "例如：鲁社长如何评价薄瓜瓜？",
        ),
        label_visibility="collapsed",
    )
with button_col:
    search_clicked = st.button(t(language, "Search", "搜索"), use_container_width=True)

st.markdown(f"#### {t(language, 'Example questions', '示例问题')}")
example_questions = [
    "鲁社长如何评价薄瓜瓜？",
    "王立军如何登上历史舞台？",
    "泰国政治的三个阶段是什么？",
    "他信为什么会下台？",
]
example_cols = st.columns(2)
example_trigger: str | None = None
for idx, question in enumerate(example_questions):
    with example_cols[idx % 2]:
        if st.button(question, key=f"example_{idx}", use_container_width=True):
            example_trigger = question

st.markdown(f"#### {t(language, 'Explore topics', '探索话题')}")
topic_labels = ["薄熙来", "王立军", "泰国", "柬埔寨", "习近平", "金融权贵"]
topic_cols = st.columns(3)
topic_trigger: str | None = None
for idx, topic in enumerate(topic_labels):
    with topic_cols[idx % 3]:
        if st.button(topic, key=f"topic_{idx}", use_container_width=True):
            topic_trigger = f"鲁社长如何评价{topic}？"

st.divider()

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        if message["role"] == "assistant":
            rendered = link_source_citations(message["content"], message.get("sources", []))
            st.markdown(rendered)
            sources = message.get("sources", [])
            render_sources(sources=sources, lang=language, show_embed_video=show_embed_video)
            if show_debug_chunks:
                st.markdown(f"**{t(language, 'Debug: Retrieved Chunks', '调试：检索到的分块')}**")
                st.json(sources)
        else:
            st.markdown(message["content"])

chat_query = st.chat_input(
    t(language, "Ask about people, events, or timelines...", "可以提问人物、事件或时间线...")
)

triggered_query: str | None = None
if search_clicked and st.session_state.hero_query.strip():
    triggered_query = st.session_state.hero_query.strip()
elif example_trigger:
    triggered_query = example_trigger
    st.session_state.hero_query = example_trigger
elif topic_trigger:
    triggered_query = topic_trigger
    st.session_state.hero_query = topic_trigger
elif chat_query:
    triggered_query = chat_query.strip()

if triggered_query:
    append_and_render_assistant(
        query=triggered_query,
        lang=language,
        top_k=top_k,
        provider=provider,
        model=model,
        show_debug_chunks=show_debug_chunks,
        show_embed_video=show_embed_video,
    )
