import pytest
from main import _try_intent_route

@pytest.mark.parametrize(
    "user_input, expected_tool, expected_args",
    [
        ("coloca o volume em 70", "set_volume", {"level": 70}),
        ("volume 50", "set_volume", {"level": 50}),
        ("aumenta o volume para 80%", "set_volume", {"level": 80}),
        ("brilho 50", "set_brightness", {"level": 50}),
        ("qual o volume", "get_volume", {}),
        ("bloquear tela", "lock_screen", {}),
        ("próxima música", "control_media", {"action": "next"}),
        ("música anterior", "control_media", {"action": "previous"}),
        ("pausar", "control_media", {"action": "play_pause"}),
        ("play", "control_media", {"action": "play_pause"}),
        ("uma frase aleatória", None, None),
    ],
)
def test_try_intent_route(user_input, expected_tool, expected_args):
    """Test the intent router with various user inputs."""
    result = _try_intent_route(user_input)
    if expected_tool:
        assert result is not None
        tool_name, tool_args = result
        assert tool_name == expected_tool
        assert tool_args == expected_args
    else:
        assert result is None
