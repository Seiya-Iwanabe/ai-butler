import asyncio

import pytest

from ai_butler.mic_gate import MicGate


def test_initial_state_defaults_closed_listening_open_gate():
    gate = MicGate(cooldown_seconds=0.05)
    assert gate.listening_enabled is False
    assert gate.playback_gate_open is True
    assert gate.is_mic_open() is False  # listening not enabled yet


def test_toggle_listening():
    gate = MicGate(cooldown_seconds=0.05)
    assert gate.toggle_listening() is True
    assert gate.listening_enabled is True
    assert gate.toggle_listening() is False
    assert gate.listening_enabled is False


def test_mic_open_requires_both_listening_and_playback_gate():
    gate = MicGate(cooldown_seconds=0.05, listening_enabled=True)
    assert gate.is_mic_open() is True

    gate.on_playback_started()
    assert gate.playback_gate_open is False
    assert gate.is_mic_open() is False


@pytest.mark.asyncio
async def test_playback_gate_reopens_after_cooldown():
    gate = MicGate(cooldown_seconds=0.05, listening_enabled=True)
    gate.on_playback_started()
    assert gate.is_mic_open() is False

    loop = asyncio.get_running_loop()
    gate.on_playback_finished(loop)

    # Still muted immediately after the turn ends (cooldown not elapsed yet).
    assert gate.is_mic_open() is False

    await asyncio.sleep(0.1)
    assert gate.is_mic_open() is True


@pytest.mark.asyncio
async def test_new_playback_during_cooldown_cancels_pending_reopen():
    # cooldown=0.05s. First turn finishes at t=0, would reopen at t=0.05.
    # A second turn starts at t=0.02 and finishes immediately, so the mic
    # must stay closed until 0.05s *after the second finish* (t=0.07), not
    # the original t=0.05.
    gate = MicGate(cooldown_seconds=0.05, listening_enabled=True)
    loop = asyncio.get_running_loop()

    gate.on_playback_started()
    gate.on_playback_finished(loop)

    await asyncio.sleep(0.02)  # t=0.02
    gate.on_playback_started()
    gate.on_playback_finished(loop)  # reopen now scheduled for t=0.07

    await asyncio.sleep(0.04)  # t=0.06: past the original 0.05 deadline
    assert gate.is_mic_open() is False

    await asyncio.sleep(0.03)  # t=0.09: past the rescheduled 0.07 deadline
    assert gate.is_mic_open() is True
