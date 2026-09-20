from ai_butler import realtime_protocol as proto


def test_run_claude_code_tool_schema_shape():
    schema = proto.run_claude_code_tool_schema()
    assert schema["type"] == "function"
    assert schema["name"] == proto.RUN_CLAUDE_CODE_TOOL_NAME
    assert schema["parameters"]["required"] == ["task"]
    assert "task" in schema["parameters"]["properties"]


def test_session_update_event_shape():
    event = proto.session_update_event(
        instructions="be nice", voice="marin", model="gpt-realtime-2.1"
    )
    assert event["type"] == "session.update"
    session = event["session"]
    assert session["type"] == "realtime"
    assert session["model"] == "gpt-realtime-2.1"
    assert session["instructions"] == "be nice"
    assert session["output_modalities"] == ["audio"]

    audio_in = session["audio"]["input"]
    assert audio_in["format"] == {"type": "audio/pcm", "rate": 24000}
    assert audio_in["turn_detection"]["type"] == "semantic_vad"

    audio_out = session["audio"]["output"]
    assert audio_out["format"] == {"type": "audio/pcm", "rate": 24000}
    assert audio_out["voice"] == "marin"

    tool_names = [t["name"] for t in session["tools"]]
    assert proto.RUN_CLAUDE_CODE_TOOL_NAME in tool_names


def test_session_update_event_custom_turn_detection():
    event = proto.session_update_event(
        instructions="x",
        voice="alloy",
        model="gpt-realtime-2.1",
        turn_detection={"type": "server_vad"},
    )
    assert event["session"]["audio"]["input"]["turn_detection"] == {"type": "server_vad"}


def test_input_audio_append_event():
    event = proto.input_audio_append_event("QUJD")
    assert event == {"type": "input_audio_buffer.append", "audio": "QUJD"}


def test_function_call_output_event():
    event = proto.function_call_output_event("call_123", "done")
    assert event["type"] == "conversation.item.create"
    item = event["item"]
    assert item["type"] == "function_call_output"
    assert item["call_id"] == "call_123"
    assert item["output"] == "done"


def test_system_message_event():
    event = proto.system_message_event("hello")
    item = event["item"]
    assert item["role"] == "system"
    assert item["type"] == "message"
    assert item["content"] == [{"type": "input_text", "text": "hello"}]


def test_response_create_event():
    assert proto.response_create_event() == {"type": "response.create"}


def test_dumps_is_valid_json_round_trip():
    import json

    event = proto.function_call_output_event("call_1", "結果だよ")
    text = proto.dumps(event)
    assert json.loads(text) == event
    # ensure_ascii=False: Japanese text should not be escaped
    assert "結果だよ" in text
