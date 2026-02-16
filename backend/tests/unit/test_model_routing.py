from unittest.mock import patch


class TestModelRouter:
    def test_detects_coding_intent(self):
        from services.model_router import is_coding_intent

        assert is_coding_intent("write a python function to parse csv")
        assert not is_coding_intent("what is the quadratic formula")

    @patch("config.CODER_MODEL_NAME", "coder-model")
    @patch("config.CONVERSATION_MODEL_NAME", "chat-model")
    def test_choose_model_for_prompt(self):
        from services.model_router import choose_model_for_prompt

        assert choose_model_for_prompt("write rust code") == "coder-model"
        assert choose_model_for_prompt("explain photosynthesis") == "chat-model"


class TestProviderFactoryRouting:
    @patch("config.MODEL_ROUTING_ENABLED", True)
    @patch("config.CONVERSATION_MODEL_NAME", "chat-model")
    @patch("config.CODER_MODEL_NAME", "coder-model")
    @patch("config.MODEL_NAME", "coder-model")
    @patch("config.OLLAMA_HOST", "http://localhost:11434")
    @patch("config.NUM_CTX", 32768)
    def test_get_provider_routes_models(self):
        from services.provider_factory import get_provider, reset_provider

        reset_provider()
        p_chat = get_provider(prompt="what is linear algebra")
        p_code = get_provider(prompt="write a python function")

        assert p_chat.model == "chat-model"
        assert p_code.model == "coder-model"
        reset_provider()
