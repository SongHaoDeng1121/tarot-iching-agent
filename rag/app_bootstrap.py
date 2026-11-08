"""Initialize deployment settings before any eager RAG data imports."""
import os
import uuid

from rag import runtime_data  # Load local .env before reading deployment settings.

SETTINGS = (
    "SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_MODEL",
    "KNOWLEDGE_ROOT", "KNOWLEDGE_BUNDLE_URL", "KNOWLEDGE_BUNDLE_SHA256",
    "KNOWLEDGE_BUNDLE_TOKEN", "KNOWLEDGE_CACHE_DIR", "APP_RUNTIME_DIR",
    "APP_ACCESS_PASSWORD", "API_GLOBAL_DAILY_UNITS", "API_SESSION_DAILY_UNITS",
    "API_COOLDOWN_SECONDS", "API_MAX_CONCURRENT", "TAROT_SOURCE_REGISTRY",
)


def initialize(st):
    try:
        for name in SETTINGS:
            if name in st.secrets:
                os.environ[name] = str(st.secrets[name])
    except FileNotFoundError:
        pass
    cloud = os.getenv("APP_MODE", "local") == "cloud"
    if cloud:
        os.environ.setdefault("APP_RUNTIME_DIR", "/tmp/tarot-private-runtime")
        if not os.getenv("KNOWLEDGE_ROOT") and not os.getenv("KNOWLEDGE_BUNDLE_URL"):
            st.error("尚未配置私有知识数据源，应用未启动。")
            st.stop()
    from rag.cloud_access import require_cloud_access
    require_cloud_access(st)
    if "_history_session" not in st.session_state:
        st.session_state["_history_session"] = uuid.uuid4().hex

    @st.cache_resource(show_spinner="正在检查知识库…")
    def prepare():
        from rag.private_bundle import restore_private_bundle
        from rag.knowledge_check import check_knowledge
        restore_private_bundle()
        return check_knowledge()

    try:
        result = prepare()
    except Exception:
        st.error("私有知识数据加载失败，请管理员检查数据包、校验值及访问凭证。")
        st.stop()
    if not result["ready"]:
        st.error("知识库尚未就绪，应用已停止。")
        for error in result["errors"]:
            st.write(error)
        st.stop()
    missing = [name for name in ("SILICONFLOW_API_KEY", "DEEPSEEK_API_KEY") if not os.getenv(name)]
    if missing:
        st.error("缺少 API 配置：" + ", ".join(missing))
        st.stop()


def history_dir(st):
    from rag.runtime_data import session_history_dir
    return session_history_dir(st.session_state["_history_session"])
