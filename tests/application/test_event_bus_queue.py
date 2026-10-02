"""Bounded event bus: frame coalescing, durable lanes, saturation, thread safety (D-C, FT3, D2)."""

from __future__ import annotations

import threading

from depot_vision.adapters.bounded_event_bus import BoundedEventBus
from depot_vision.domain.counting import CountSnapshot
from depot_vision.domain.errors import QueueOverflow
from depot_vision.domain.events import (
    AppEvent,
    DetectionLogged,
    FrameRendered,
    LogEmitted,
    QueueSaturated,
    SessionFault,
    SessionStateChanged,
)
from depot_vision.domain.frames import EncodedImage
from depot_vision.domain.session import SessionState
from depot_vision.ports import EventBus


def _frame(tag: int) -> FrameRendered:
    return FrameRendered(
        image=EncodedImage(data=bytes([tag]), media_type="image/jpeg"),
        snapshot=CountSnapshot(counts={}),
        fps=0.0,
        frame_number=tag,
    )


def test_conforms_to_event_bus_port() -> None:
    assert isinstance(BoundedEventBus(soft_capacity=4, hard_ceiling=8), EventBus)


def test_frame_lane_coalesces_to_the_newest_frame() -> None:
    bus = BoundedEventBus(soft_capacity=4, hard_ceiling=8)
    for tag in range(100):
        bus.publish(_frame(tag))
    assert list(bus.drain()) == [_frame(99)]


def test_state_and_log_events_are_never_dropped_and_keep_fifo_order() -> None:
    bus = BoundedEventBus(soft_capacity=2, hard_ceiling=1000)
    sent: list[AppEvent] = []
    for i in range(50):
        for event in (
            SessionStateChanged(state=SessionState.RUNNING),
            LogEmitted(message=f"log {i}"),
            DetectionLogged(message=f"det {i}"),
        ):
            bus.publish(event)
            sent.append(event)
    drained = [e for e in bus.drain() if not isinstance(e, QueueSaturated)]
    assert drained == sent


def test_drain_returns_durable_events_then_newest_frame_and_clears_both_lanes() -> None:
    bus = BoundedEventBus(soft_capacity=8, hard_ceiling=16)
    bus.publish(_frame(1))
    bus.publish(LogEmitted(message="a"))
    bus.publish(_frame(2))
    bus.publish(SessionStateChanged(state=SessionState.PAUSED))
    assert list(bus.drain()) == [
        LogEmitted(message="a"),
        SessionStateChanged(state=SessionState.PAUSED),
        _frame(2),
    ]
    assert list(bus.drain()) == []


def test_frames_never_count_toward_saturation() -> None:
    bus = BoundedEventBus(soft_capacity=2, hard_ceiling=4)
    for tag in range(50):
        bus.publish(_frame(tag))
    assert [e for e in bus.drain() if isinstance(e, QueueSaturated)] == []


def test_queue_saturated_published_once_at_soft_capacity_and_event_is_still_kept() -> None:
    bus = BoundedEventBus(soft_capacity=3, hard_ceiling=100)
    for i in range(6):
        bus.publish(LogEmitted(message=str(i)))
    drained = list(bus.drain())
    saturated = [e for e in drained if isinstance(e, QueueSaturated)]
    assert saturated == [QueueSaturated(depth=3)]
    assert [e.message for e in drained if isinstance(e, LogEmitted)] == [str(i) for i in range(6)]


def test_queue_saturated_is_rearmed_after_the_lane_falls_below_half() -> None:
    bus = BoundedEventBus(soft_capacity=4, hard_ceiling=100)
    for i in range(4):
        bus.publish(LogEmitted(message=str(i)))
    bus.drain()
    for i in range(4):
        bus.publish(LogEmitted(message=str(i)))
    assert len([e for e in bus.drain() if isinstance(e, QueueSaturated)]) == 1


def test_hard_ceiling_publishes_one_overflow_fault_without_dropping_anything() -> None:
    bus = BoundedEventBus(soft_capacity=2, hard_ceiling=5)
    for i in range(20):
        bus.publish(LogEmitted(message=str(i)))
    drained = list(bus.drain())
    faults = [e for e in drained if isinstance(e, SessionFault)]
    assert len(faults) == 1
    assert isinstance(faults[0].error, QueueOverflow)
    assert len([e for e in drained if isinstance(e, LogEmitted)]) == 20


def test_overflow_fault_is_rearmed_after_drain() -> None:
    bus = BoundedEventBus(soft_capacity=2, hard_ceiling=4)
    for _ in range(2):
        for i in range(8):
            bus.publish(LogEmitted(message=str(i)))
        faults = [e for e in bus.drain() if isinstance(e, SessionFault)]
        assert len(faults) == 1


def test_concurrent_producers_and_a_drainer_lose_no_durable_event() -> None:
    producers, per_producer = 8, 500
    bus = BoundedEventBus(soft_capacity=10_000_000, hard_ceiling=10_000_000)
    barrier = threading.Barrier(producers + 1)
    done = threading.Event()
    collected: list[AppEvent] = []

    def produce(pid: int) -> None:
        barrier.wait()
        for seq in range(per_producer):
            bus.publish(LogEmitted(message=f"{pid}:{seq}"))
            bus.publish(_frame(seq % 256))

    def consume() -> None:
        barrier.wait()
        while not done.is_set():
            collected.extend(bus.drain())

    threads = [threading.Thread(target=produce, args=(p,)) for p in range(producers)]
    drainer = threading.Thread(target=consume)
    for t in (*threads, drainer):
        t.start()
    for t in threads:
        t.join()
    done.set()
    drainer.join()
    collected.extend(bus.drain())

    logs = [e.message for e in collected if isinstance(e, LogEmitted)]
    assert len(logs) == producers * per_producer
    assert len(set(logs)) == len(logs)
    for pid in range(producers):  # per-producer FIFO is preserved
        seqs = [int(m.split(":")[1]) for m in logs if m.startswith(f"{pid}:")]
        assert seqs == sorted(seqs)
